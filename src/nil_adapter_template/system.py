"""System-client layer: the ONE module that performs I/O against your backend.

`SystemClient` is the protocol the edge/translation depend on, so the conformance proof can run
against `FakeSystem` with no live instance. Fill `RealSystemClient` with your backend's API.

It is also where the recovery contract meets the wire (see `recovery.py`). Both existing NIL
adapters independently wrote an UNKEYED retry loop here — "retry 3x on any exception" — which turns
a create the backend COMMITTED but whose answer was lost into a second irreversible business act,
invisible to every layer above. So this module ships the policy rather than leaving a hole shaped
like one: **reads may retry; a write is repeated only on PROOF it was never dispatched.**
"""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol, TypeVar

T = TypeVar("T")


class SystemError(RuntimeError):
    """A write the System rejected — its message is surfaced/logged by the edge.

    An OBSERVED outcome: the backing system answered, and the answer was "no". Terminal, never
    retried by `RetryPolicy` — repeating a rejection only repeats the rejection.
    """


class OutcomeInDoubt(SystemError):
    """A mutation whose outcome NOBODY OBSERVED — the request went out and no answer came back.

    This is the honest third verdict, and its absence is why the duplicate was possible: the layer
    above knew only `executed` and `failed_terminal`, and `failed_terminal` asserts *"it did not
    happen"*. After a dropped socket or a gateway timeout on a create, that assertion is a guess —
    the backing system may hold the record already. Repeating the call is how one commit becomes
    two purchase orders.

    A SUBCLASS of `SystemError` on purpose: every existing handler already catches it, so an
    un-updated path degrades to today's behaviour instead of escaping as a 500. Paths that CAN
    answer honestly catch it FIRST and return a structured refusal (`edge._in_doubt_refusal`).
    """

    def __init__(self, message: str, *, target: str = "", operation: str = "") -> None:
        super().__init__(message)
        self.target = target
        self.operation = operation


class RequestNeverDispatched(SystemError):
    """PROOF that the backing system never received the request.

    A rate-limit rejection emitted by a limiter or proxy BEFORE dispatch, a local connection
    refused, a request rejected by your own client-side governor. This is the ONE class of write
    failure whose outcome is observed — "not applied" — so retrying it is not a guess. Raise it from
    `RealSystemClient` only where you can point at the evidence; a timeout is NOT evidence.
    """


# The `SystemClient` operations that only READ. Repeating one cannot change the world, so a
# transport fault on them is retried. EVERYTHING ELSE IS TREATED AS A WRITE — fail closed: an
# operation this template has not classified (a backend method like `approve`, `post`, `send`) must
# never be repeated on this layer's own initiative.
READ_OPERATIONS: frozenset[str] = frozenset({
    "list", "get", "exists", "schema", "read", "search", "count", "describe",
})


def is_read_operation(name: str) -> bool:
    """Fail closed: unknown ⇒ write. The safe default must be the one you get by saying nothing."""
    return name in READ_OPERATIONS


class RetryPolicy:
    """The retry rule the forks got wrong: **a retry is only safe when the operation is idempotent
    or can be checked first.**

    Wrap every backend call in `RealSystemClient` with `policy.call(<operation>, <target>, fn)`:

        def create(self, target, doc):
            return self._retry.call("create", target, lambda: self._api.post(target, doc))

    * a READ repeats harmlessly ⇒ exponential backoff, exactly as an unguarded loop would;
    * a WRITE is repeated ONLY when the failure proves it was never applied
      (`RequestNeverDispatched`). Every other transport failure leaves the outcome UNOBSERVED and
      raises `OutcomeInDoubt`, moving the decision up to a layer that can ask the backing system
      what actually happened (see `edge.py`'s ask-first probe);
    * a `SystemError` the backend itself raised is an ANSWER — terminal, never retried.
    """

    def __init__(self, *, max_retries: int = 3, backoff: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep

    def call(self, operation: str, target: str, call: Callable[[], T]) -> T:
        is_read = is_read_operation(operation)
        for attempt in range(self._max_retries + 1):
            try:
                return call()
            except RequestNeverDispatched:
                # Observed "not applied" — the one failure a write may retry on.
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                    continue
                raise SystemError(
                    f"{target}.{operation}: rejected before dispatch on every attempt — "
                    f"nothing was applied"
                ) from None
            except SystemError:
                raise  # the backing system ANSWERED and rejected: observed, terminal
            except Exception as exc:  # noqa: BLE001 — socket reset, timeout, unreadable answer
                if is_read and attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                    continue
                if not is_read:
                    raise OutcomeInDoubt(
                        f"{target}.{operation} sent no readable answer ({exc}) — the write may or "
                        f"may not have been applied; it was NOT repeated",
                        target=target, operation=operation,
                    ) from exc
                raise SystemError(f"{target}.{operation} transport error: {exc}") from exc
        raise SystemError(f"{target}.{operation}: exhausted {self._max_retries} retries")  # guard


class SystemClient(Protocol):
    def create(self, target: str, doc: dict[str, Any]) -> dict[str, Any]: ...

    def list(self, target: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    def update(self, target: str, record_id: str, doc: dict[str, Any]) -> dict[str, Any]: ...

    def delete(self, target: str, record_id: str) -> None: ...

    def exists(self, target: str) -> bool: ...  # is this native target provisioned? (PROPOSE preflight)

    def schema(self, target: str) -> list[dict[str, Any]] | None: ...  # target shape (skeleton), or None

    def get(self, target: str, record_id: str) -> dict[str, Any] | None: ...  # one record (before-image)


class RealSystemClient:
    """TODO: talk to your backend here (the only I/O in the adapter).

    **Do not write your own retry loop.** That is the single most-repeated defect in this codebase:
    "retry 3x on any exception" repeats a write the backend already committed. Route every call
    through `self._retry.call(<operation>, <target>, fn)` — it retries reads, and repeats a write
    only on `RequestNeverDispatched`. See `RetryPolicy` above and `recovery.py` for the contract.
    """

    def __init__(self, base_url: str, retry: RetryPolicy | None = None, **auth: str) -> None:
        self._base_url = base_url
        self._auth = auth
        self._retry = retry or RetryPolicy()

    def create(self, target: str, doc: dict[str, Any]) -> dict[str, Any]:
        # e.g. return self._retry.call("create", target, lambda: self._post(target, doc))
        raise NotImplementedError("implement create() against your backend")

    def list(self, target: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        # The witness lookup runs through here: an attempt-keyed verb is recovered by filtering on
        # its declared field, so `filters` must reach the backend (or be applied client-side).
        raise NotImplementedError("implement list() against your backend")

    def update(self, target: str, record_id: str, doc: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("implement update() against your backend")

    def delete(self, target: str, record_id: str) -> None:
        raise NotImplementedError("implement delete() against your backend")

    def exists(self, target: str) -> bool:
        # Override to check your backend (e.g. does this table/collection exist?). Returning True
        # disables the PROPOSE preflight; implement a real check for honest "not provisioned" refusals.
        return True

    def schema(self, target: str) -> list[dict[str, Any]] | None:
        # Override to fetch your backend's target shape (skeleton): a list of {name, type, required}
        # field dicts, or None if the target isn't provisioned. Powers /describe + agent awareness.
        return []

    def get(self, target: str, record_id: str) -> dict[str, Any] | None:
        # Override to fetch one record by id (the before-image used for generic-CRUD reversibility).
        return None


class FakeSystem:
    """In-memory backend for the conformance proof — no live instance needed."""

    def __init__(self) -> None:
        self.docs: dict[str, list[dict[str, Any]]] = {}
        # Declared field lists per target, as a real backend's schema/`fields_get` would answer.
        # EMPTY (the default) means schemaless — provisioned, declaring no fields. The edge treats
        # that honestly: it will not contradict a witness declaration a schemaless store cannot
        # confirm or deny. Populate it to prove the opposite case: a target whose live schema DENIES
        # the declared witness field must degrade to the honest refusal, never to a rejected write.
        self.schemas: dict[str, list[dict[str, Any]]] = {}
        self._counter = 0

    def create(self, target: str, doc: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        name = str(doc.get("name") or f"{target}-{self._counter:05d}")
        record = {**doc, "name": name, "target": target}
        self.docs.setdefault(target, []).append(record)
        return record

    def list(self, target: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = list(self.docs.get(target, []))
        for field, value in (filters or {}).items():
            rows = [r for r in rows if str(value).lower() in str(r.get(field, "")).lower()]
        return rows

    def update(self, target: str, record_id: str, doc: dict[str, Any]) -> dict[str, Any]:
        for record in self.docs.get(target, []):
            if record.get("name") == record_id:
                record.update(doc)
                return record
        record = {**doc, "name": record_id, "target": target}  # upsert keeps the proof deterministic
        self.docs.setdefault(target, []).append(record)
        return record

    def delete(self, target: str, record_id: str) -> None:
        self.docs[target] = [r for r in self.docs.get(target, []) if r.get("name") != record_id]

    def exists(self, target: str) -> bool:
        return True  # in-memory backend is always ready (creates targets on demand)

    def schema(self, target: str) -> list[dict[str, Any]] | None:
        return self.schemas.get(target, [])  # schemaless by default: provisioned, no declared fields

    def get(self, target: str, record_id: str) -> dict[str, Any] | None:
        return next((r for r in self.docs.get(target, []) if r.get("name") == record_id), None)
