"""System-client layer: the ONE module that performs I/O against your backend.

`SystemClient` is the protocol the edge/translation depend on, so the conformance proof can run
against `FakeSystem` with no live instance. Fill `RealSystemClient` with your backend's API.
"""

from __future__ import annotations

from typing import Any, Protocol


class SystemError(RuntimeError):
    """A write the System rejected — its message is surfaced/logged by the edge."""


class SystemClient(Protocol):
    def create(self, target: str, doc: dict[str, Any]) -> dict[str, Any]: ...

    def list(self, target: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    def update(self, target: str, record_id: str, doc: dict[str, Any]) -> dict[str, Any]: ...

    def delete(self, target: str, record_id: str) -> None: ...


class RealSystemClient:
    """TODO: talk to your backend here (the only I/O in the adapter)."""

    def __init__(self, base_url: str, **auth: str) -> None:
        self._base_url = base_url
        self._auth = auth

    def create(self, target: str, doc: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("implement create() against your backend")

    def list(self, target: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError("implement list() against your backend")

    def update(self, target: str, record_id: str, doc: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("implement update() against your backend")

    def delete(self, target: str, record_id: str) -> None:
        raise NotImplementedError("implement delete() against your backend")


class FakeSystem:
    """In-memory backend for the conformance proof — no live instance needed."""

    def __init__(self) -> None:
        self.docs: dict[str, list[dict[str, Any]]] = {}
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
