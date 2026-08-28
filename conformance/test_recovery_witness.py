"""The recovery-witness gate — the platform contract every fork inherits from this template.

> **Idempotency is not a property declared by a verb. It is a recovery property demonstrated by
> the complete mutation path.**

The hole this closes, in the template itself: the caller's attempt key arrived as the COMMIT body's
`idempotency_key` and died in `ShimState.ledger`, a plain dict that is lost when the process is. No
backing system ever learned it, no verb declared where its durable evidence lives, `RealSystemClient`
offered no retry policy at all — so both existing forks independently invented an UNKEYED retry loop
and each turned one lost answer into a second irreversible business act.

The contract these tests pin:

  * every externally mutating verb DECLARES its recovery shape — attempt-keyed, convergent, or
    honestly none. Silence is UNKNOWN, and **UNKNOWN is treated exactly as UNSAFE**;
  * a declaration is only a claim. The gate DEMONSTRATES it by driving the complete mutation path:
    an attempt-keyed verb must be found in the backing system by its key after a restart; a
    convergent verb must leave the same state when applied twice;
  * a write whose answer was LOST is never repeated and never reported as `failed_terminal`
    (which asserts "it did not happen" — nobody knows that). It is a structured refusal;
  * FOUND settles a doubt. **NOT FOUND does not** — unless the verb demonstrates its witness query
    is read-your-writes consistent with the mutation path.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nil_adapter_template import edge as edge_mod
from nil_adapter_template import system as system_mod
from nil_adapter_template.edge import CapturingEmitter, create_app
from nil_adapter_template.recovery import (
    ATTEMPT_KEYED,
    CANONICAL_SENTENCE,
    CONVERGENT,
    NO_WITNESS,
    SAFE,
    SIX_QUESTIONS,
    UNKNOWN,
    UNSAFE,
    RecoveryWitness,
    gate_message,
    no_witness,
    unanswered_verbs,
    witness_export,
    witness_verdict,
)
from nil_adapter_template.system import (
    FakeSystem,
    OutcomeInDoubt,
    RequestNeverDispatched,
    RetryPolicy,
    SystemError,
    is_read_operation,
)
from nil_adapter_template.translate import WRITE_VERBS, WriteVerb, write_op

# ── worked examples: the two shapes that pass, and the one that does not ─────────────────────────
# These are the fork author's reference. They are exercised through the REAL edge below, so the
# template's own contract is demonstrated by a running mutation path, not by prose.

KEYED = WriteVerb(
    verb="example.create_order",
    tier="HIGH",
    doctype="Order",
    required=("party_id",),
    to_native=lambda a: {k: v for k, v in
                         {"party_id": a.get("party_id"), "reference": a.get("reference")}.items()
                         if v not in (None, "")},
    preview=lambda a: {"en": "create order", "ar": "إنشاء أمر"},
    entity_type="order",
    witness=RecoveryWitness(
        shape=ATTEMPT_KEYED,
        field="reference",                 # Q2/Q3: where the attempt identity durably lands
        lookup="list('Order', {'reference': <marker>})",   # Q4: how it is queried after a crash
        negative_authoritative=True,       # Q6: the store answers its own writes — NOT FOUND is real
        note="`reference` is a free-text document reference the backend persists and can filter on.",
    ),
)

# The SAME shape, but its witness query cannot prove an absence (an async delivery/index sits between
# the mutation and the lookup). FOUND still settles; NOT FOUND must go to a human, never to a replay.
KEYED_BLIND_NEGATIVE = WriteVerb(
    verb="example.send_notice",
    tier="HIGH",
    doctype="Notice",
    required=("to",),
    to_native=lambda a: {k: v for k, v in
                         {"to": a.get("to"), "reference": a.get("reference")}.items()
                         if v not in (None, "")},
    preview=lambda a: {"en": "send notice", "ar": "إرسال إشعار"},
    entity_type="notice",
    witness=RecoveryWitness(
        shape=ATTEMPT_KEYED,
        field="reference",
        lookup="list('Notice', {'reference': <marker>})",
        negative_authoritative=False,      # delivery is asynchronous: NOT FOUND means "not yet" too
        note="the sent-record is written by an async delivery pipeline, not by the accepting call.",
    ),
)

CONVERGENT_VERB = WriteVerb(
    verb="example.update_stock",
    tier="MEDIUM",
    doctype="Stock Level",
    required=("sku", "quantity"),
    to_native=lambda a: {"sku": a["sku"], "quantity": a["quantity"]},
    preview=lambda a: {"en": "set stock", "ar": "ضبط المخزون"},
    entity_type="stock_level",
    witness=RecoveryWitness(
        shape=CONVERGENT,
        identity=("sku",),                 # Q1: a STABLE, caller-supplied, pre-existing identity
        lookup="get('Stock Level', <sku>)",
        negative_authoritative=True,
        note="SET semantics: re-applying the same quantity to the same sku is the same state.",
    ),
)

UNDECLARED = WriteVerb(
    verb="example.create_thing",
    tier="HIGH",
    doctype="Thing",
    required=("name",),
    to_native=lambda a: {"name": a["name"]},
    preview=lambda a: {"en": "create thing", "ar": "إنشاء"},
    entity_type="thing",
    # witness: NOT DECLARED — the recovery question is unanswered. This is the fork the gate exists
    # to stop, and every assertion about it below is the gate biting.
)

ABSENT = WriteVerb(
    verb="example.create_lead",
    tier="MEDIUM",
    doctype="Lead",
    required=("name",),
    to_native=lambda a: {"name": a["name"]},
    preview=lambda a: {"en": "create lead", "ar": "إنشاء عميل محتمل"},
    entity_type="lead",
    witness=no_witness("Lead carries no free-text reference field — there is nothing to query on."),
)


def _register(monkeypatch: pytest.MonkeyPatch, *verbs: WriteVerb) -> None:
    """Swap the edge's verb registry for the example verbs, so the contract is proven on the REAL
    propose/commit path rather than on a stand-in."""
    registry = {v.verb: v for v in verbs}
    monkeypatch.setattr(edge_mod, "WRITE_VERBS", registry)
    monkeypatch.setattr(edge_mod, "_CURATED_BY_DOCTYPE", {v.doctype: v for v in verbs})


def _app(system: FakeSystem) -> TestClient:
    return TestClient(create_app(system, CapturingEmitter(), bearer=None), raise_server_exceptions=False)


def _commit(client: TestClient, verb: str, args: dict[str, Any], key: str) -> dict[str, Any]:
    env = {"nil": "0.1", "grant": "g", "workspace": "w", "body": {"verb": verb, "args": args}}
    proposed = client.post("/nil/v0.1/propose", json=env).json()["body"]
    assert proposed.get("id"), f"PROPOSE refused: {proposed}"
    return client.post(
        "/nil/v0.1/commit",
        json={"nil": "0.1", "grant": "g", "workspace": "w",
              "body": {"proposal": proposed["id"], "idempotency_key": key}},
    ).json()["body"]


class _LosesTheAnswer(FakeSystem):
    """The backing system ACCEPTS the mutation and then the answer is lost on the wire — the exact
    window in which a blind retry mints a second irreversible act."""

    def __init__(self, *, land: bool = True) -> None:
        super().__init__()
        self._land = land
        self.create_calls = 0
        self.update_calls = 0

    def create(self, target: str, doc: dict[str, Any]) -> dict[str, Any]:
        self.create_calls += 1
        if self.create_calls == 1:
            if self._land:
                super().create(target, doc)          # the backend committed it…
            raise OutcomeInDoubt("simulated lost answer", target=target, operation="create")
        return super().create(target, doc)

    def update(self, target: str, record_id: str, doc: dict[str, Any]) -> dict[str, Any]:
        self.update_calls += 1
        if self.update_calls == 1:
            if self._land:
                super().update(target, record_id, doc)
            raise OutcomeInDoubt("simulated lost answer", target=target, operation="update")
        return super().update(target, record_id, doc)


# ── the contract: what a verb may declare, and what silence means ────────────────────────────────


def test_the_gate_names_a_verb_that_declares_nothing() -> None:
    """The whole point of the exercise: a write verb that never answered the recovery question is
    non-conformant, and the gate says so by name."""
    assert unanswered_verbs({UNDECLARED.verb: UNDECLARED}) == ["example.create_thing"]


def test_the_gate_failure_carries_the_canonical_sentence_and_the_six_questions() -> None:
    message = gate_message(["example.create_thing"])
    assert CANONICAL_SENTENCE in message, "the gate must say WHY, not just WHAT"
    for question in SIX_QUESTIONS:
        assert question in message, f"the gate must ask: {question}"


def test_the_gate_accepts_an_attempt_keyed_declaration() -> None:
    assert unanswered_verbs({KEYED.verb: KEYED}) == []


def test_the_gate_accepts_a_convergent_declaration_without_any_attempt_key() -> None:
    """The owner's correction: a stable identity + SET semantics is genuinely safe. Forcing an
    attempt key onto enable/disable/ensure/set verbs would be ceremony, not safety."""
    assert unanswered_verbs({CONVERGENT_VERB.verb: CONVERGENT_VERB}) == []
    assert CONVERGENT_VERB.witness.field is None, "a convergent verb needs no key at all"


def test_the_gate_accepts_an_honest_declaration_of_no_witness() -> None:
    """Declaring "there is none" is conformant — and permanently UNSAFE. Stopping is preferable to
    silently duplicating reality; silence is the only unacceptable answer."""
    assert unanswered_verbs({ABSENT.verb: ABSENT}) == []
    assert witness_verdict(ABSENT) == UNSAFE


def test_an_undeclared_verb_is_UNKNOWN_and_UNKNOWN_is_treated_exactly_as_UNSAFE() -> None:
    assert witness_verdict(UNDECLARED) == UNKNOWN
    assert not UNDECLARED.may_replay and not ABSENT.may_replay


def test_a_declaration_alone_is_never_SAFE() -> None:
    """`demonstrated=True` is passed by the conformance gate ONLY after it has driven the complete
    mutation path. A verb cannot promote itself."""
    assert witness_verdict(KEYED) == UNKNOWN, CANONICAL_SENTENCE
    assert witness_verdict(KEYED, demonstrated=True) == SAFE
    assert witness_verdict(ABSENT, demonstrated=True) == UNSAFE, "no demonstration can invent a witness"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"shape": ATTEMPT_KEYED},                                  # keyed with nowhere to put the key
        {"shape": CONVERGENT},                                     # convergent with no stable identity
        {"shape": NO_WITNESS},                                     # "none" with no reason given
        {"shape": "probably_fine", "field": "ref"},                # an invented shape
        {"shape": ATTEMPT_KEYED, "field": "ref", "lookup": ""},    # no answer to "how do we query it?"
    ],
)
def test_a_malformed_declaration_cannot_even_be_constructed(kwargs: dict[str, Any]) -> None:
    """Make the unsafe thing hard to write: an under-answered declaration fails at import time,
    not at 3am."""
    with pytest.raises(ValueError):
        RecoveryWitness(**kwargs)


def test_every_write_verb_in_this_template_answers_the_recovery_question() -> None:
    """THE GATE, over this adapter's real registry.

    Red on a fresh template ON PURPOSE — exactly like the `NotImplementedError` translation stubs.
    A fork author must answer the six questions per verb before the offline proof can go green."""
    gaps = unanswered_verbs(WRITE_VERBS)
    assert not gaps, gate_message(gaps)


def test_the_gate_would_pass_a_registry_whose_verbs_all_declared() -> None:
    """The positive control on the gate itself: it is not a check that fails no matter what."""
    assert unanswered_verbs({v.verb: v for v in (KEYED, CONVERGENT_VERB, ABSENT)}) == []


# ── the retry policy: reads may repeat, writes may not ───────────────────────────────────────────


class _Flaky:
    def __init__(self, exc: BaseException, fail_times: int, ok: object = "ok") -> None:
        self._exc, self._fail_times, self._ok, self.calls = exc, fail_times, ok, 0

    def __call__(self) -> object:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise self._exc
        return self._ok


def _policy(max_retries: int = 3) -> RetryPolicy:
    return RetryPolicy(max_retries=max_retries, backoff=0.0, sleep=lambda _s: None)


@pytest.mark.parametrize("operation", ["list", "get", "exists", "schema"])
def test_a_read_still_retries_on_a_transport_fault(operation: str) -> None:
    call = _Flaky(OSError("connection reset"), fail_times=2)
    assert _policy().call(operation, "Order", call) == "ok"
    assert call.calls == 3, f"{operation} is a read — repeating it cannot change the world"


def test_a_write_whose_answer_is_lost_is_never_blindly_repeated() -> None:
    """THE defect both forks shipped. A dropped socket on a create used to be retried — and the
    second attempt minted a second record."""
    call = _Flaky(OSError("connection reset by peer"), fail_times=1)
    with pytest.raises(OutcomeInDoubt):
        _policy().call("create", "Order", call)
    assert call.calls == 1, "the write was repeated — that is the duplicate"


def test_an_unclassified_operation_is_treated_as_a_write() -> None:
    """Fail closed. A backend method this template has not classified (`approve`, `post`, `send`)
    must never be repeated on the transport layer's own initiative."""
    assert not is_read_operation("approve")
    call = _Flaky(OSError("broken pipe"), fail_times=1)
    with pytest.raises(OutcomeInDoubt):
        _policy().call("approve", "Invoice", call)
    assert call.calls == 1


def test_a_write_retries_only_on_PROOF_it_was_never_dispatched() -> None:
    """A rate-limit rejection emitted BEFORE dispatch is evidence, not a guess: the backend never
    saw the request. That is the one write failure a retry may act on."""
    call = _Flaky(RequestNeverDispatched("rate limited before dispatch"), fail_times=2)
    assert _policy().call("create", "Order", call) == "ok"
    assert call.calls == 3


def test_an_exhausted_never_dispatched_write_is_a_determinate_failure_not_a_doubt() -> None:
    call = _Flaky(RequestNeverDispatched("rate limited"), fail_times=99)
    with pytest.raises(SystemError) as caught:
        _policy().call("create", "Order", call)
    assert not isinstance(caught.value, OutcomeInDoubt), "nothing was dispatched — that is known"


def test_a_backend_that_ANSWERED_and_rejected_stays_terminal() -> None:
    """An application-level rejection is an OBSERVED outcome, never a doubt, and never retried."""
    call = _Flaky(SystemError("Order: party_id is required"), fail_times=99)
    with pytest.raises(SystemError) as caught:
        _policy().call("create", "Order", call)
    assert not isinstance(caught.value, OutcomeInDoubt)
    assert call.calls == 1


def test_a_read_that_never_recovers_is_a_plain_system_error() -> None:
    call = _Flaky(OSError("connection reset"), fail_times=99)
    with pytest.raises(SystemError) as caught:
        _policy(max_retries=2).call("list", "Order", call)
    assert not isinstance(caught.value, OutcomeInDoubt), "a read has no outcome to be in doubt about"


def test_outcome_in_doubt_is_a_system_error_so_no_layer_ever_500s() -> None:
    assert issubclass(OutcomeInDoubt, SystemError)
    assert issubclass(RequestNeverDispatched, SystemError)


# ── the demonstration: the complete mutation path, not the declaration ───────────────────────────


def test_an_attempt_keyed_create_puts_the_key_where_the_backing_system_persists_it(monkeypatch) -> None:
    """The middle link that did not exist: the attempt identity reaches the BACKING SYSTEM, in a
    field this adapter can query — which is the whole difference between "cannot tell" and "ask"."""
    _register(monkeypatch, KEYED)
    system = FakeSystem()
    body = _commit(_app(system), KEYED.verb, {"party_id": "7"}, "prep:abc123:r1")
    assert body["state"] == "executed", body
    assert "prep:abc123:r1" in system.docs["Order"][0]["reference"], system.docs["Order"]


def test_a_caller_supplied_reference_is_kept_alongside_the_attempt_key(monkeypatch) -> None:
    """The witness field is usually human-visible. The key rides WITH it, never over it."""
    _register(monkeypatch, KEYED)
    system = FakeSystem()
    _commit(_app(system), KEYED.verb, {"party_id": "7", "reference": "PO-0001"}, "prep:abc123:r1")
    reference = system.docs["Order"][0]["reference"]
    assert "PO-0001" in reference and "prep:abc123:r1" in reference, reference


def test_a_restarted_adapter_finds_the_attempt_in_the_backing_system_not_in_its_dict(monkeypatch) -> None:
    """`ShimState.ledger` dies with the process, so it can never be the proof. A FRESH app is an
    adapter that restarted: the same attempt must find the record the first leg wrote."""
    _register(monkeypatch, KEYED)
    system = FakeSystem()
    first = _commit(_app(system), KEYED.verb, {"party_id": "7"}, "prep:abc123:r1")
    assert first["state"] == "executed" and first["replayed"] is False

    second = _commit(_app(system), KEYED.verb, {"party_id": "7"}, "prep:abc123:r1")
    assert second["state"] == "executed"
    assert second["replayed"] is True, "the second commit must announce itself as a replay"
    assert len(system.docs["Order"]) == 1, "a second order was created"


def test_a_lost_answer_returns_the_record_that_did_land(monkeypatch) -> None:
    """The hazard itself: the backend committed, the answer vanished. Ask first, answer with the
    record that exists — one act, one truth, no second purchase order."""
    _register(monkeypatch, KEYED)
    system = _LosesTheAnswer(land=True)
    body = _commit(_app(system), KEYED.verb, {"party_id": "7"}, "prep:abc123:r1")
    assert body["state"] == "executed", body
    assert body["replayed"] is True
    assert len(system.docs["Order"]) == 1
    assert system.create_calls == 1, "the create was re-issued instead of asked about"


def test_a_lost_answer_with_an_AUTHORITATIVE_negative_is_determinately_unapplied(monkeypatch) -> None:
    """NOT FOUND collapses to "safe to execute" ONLY here: the witness query reads the same
    committed store the mutation wrote. The answer is retriable, and it is not a doubt."""
    _register(monkeypatch, KEYED)
    system = _LosesTheAnswer(land=False)
    body = _commit(_app(system), KEYED.verb, {"party_id": "7"}, "prep:abc123:r1")
    assert body["outcome"] == "refusal", body
    assert body["code"] == "UPSTREAM_UNAVAILABLE", body
    assert "NOT APPLIED" in body["message"], body["message"]


def test_a_lost_answer_with_a_NON_authoritative_negative_stays_in_doubt(monkeypatch) -> None:
    """The owner's tightening. An async delivery sits between the mutation and the lookup, so NOT
    FOUND means "not yet" as easily as "never" — it routes to a human, never to a replay."""
    _register(monkeypatch, KEYED_BLIND_NEGATIVE)
    system = _LosesTheAnswer(land=False)
    body = _commit(_app(system), KEYED_BLIND_NEGATIVE.verb, {"to": "a@b.c"}, "prep:abc123:r1")
    assert body["outcome"] == "refusal", body
    assert body["code"] == "SUSPENDED", body
    assert "OUTCOME_IN_DOUBT" in body["message"]
    assert "not authoritative" in body["message"].lower(), body["message"]


def test_a_non_authoritative_witness_still_settles_a_doubt_it_can_SEE(monkeypatch) -> None:
    """FOUND is trustworthy from any witness. Only the negative is asymmetric."""
    _register(monkeypatch, KEYED_BLIND_NEGATIVE)
    system = _LosesTheAnswer(land=True)
    body = _commit(_app(system), KEYED_BLIND_NEGATIVE.verb, {"to": "a@b.c"}, "prep:abc123:r1")
    assert body["state"] == "executed", body
    assert body["replayed"] is True
    assert len(system.docs["Notice"]) == 1


def test_a_probe_that_cannot_run_refuses_BEFORE_writing_anything(monkeypatch) -> None:
    """If the ask-first guard cannot run, writing anyway is how the duplicate gets made. Nothing is
    written — and "nothing was written" is DETERMINATE, so it is safe to retry."""

    class _BlindProbe(FakeSystem):
        def list(self, target: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            raise SystemError("transport error: connection reset")

    _register(monkeypatch, KEYED)
    system = _BlindProbe()
    body = _commit(_app(system), KEYED.verb, {"party_id": "7"}, "prep:abc123:r1")
    assert body["outcome"] == "refusal", body
    assert body["code"] == "UPSTREAM_UNAVAILABLE"
    assert "NOTHING WAS WRITTEN" in body["message"]
    assert not system.docs.get("Order"), "it wrote without being able to check first"


def test_a_probe_blinded_AFTER_the_write_leaves_the_doubt_standing(monkeypatch) -> None:
    """"nothing here" and "I could not look" must never be the same answer."""

    class _BlindAfterTheWrite(_LosesTheAnswer):
        def list(self, target: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            if self.create_calls:      # the ask-first probe works; the recovery probe does not
                raise SystemError("transport error: connection reset")
            return super().list(target, filters)

    _register(monkeypatch, KEYED)
    body = _commit(_app(_BlindAfterTheWrite(land=True)), KEYED.verb, {"party_id": "7"}, "prep:abc:r1")
    assert body["outcome"] == "refusal", body
    assert body["code"] == "SUSPENDED"
    assert "OUTCOME_IN_DOUBT" in body["message"]


def test_a_key_that_already_matches_two_records_refuses_instead_of_adding_a_third(monkeypatch) -> None:
    """The state a past duplicate leaves behind. Which of the two this commit owns is unknowable
    from here — so it stops, rather than making the pile deeper."""
    _register(monkeypatch, KEYED)
    system = FakeSystem()
    marker = "[WSL-prep:abc123:r1]"
    system.docs["Order"] = [
        {"id": "1", "name": "O-1", "reference": marker, "target": "Order"},
        {"id": "2", "name": "O-2", "reference": marker, "target": "Order"},
    ]
    body = _commit(_app(system), KEYED.verb, {"party_id": "7"}, "prep:abc123:r1")
    assert body["outcome"] == "refusal", body
    assert "OUTCOME_IN_DOUBT" in body["message"]
    assert len(system.docs["Order"]) == 2, "a third order was created"


def test_a_declared_field_the_LIVE_schema_denies_degrades_to_the_refusal(monkeypatch) -> None:
    """A declaration is our belief; the live schema is the instance's truth. A backend whose target
    lacks the field must fall back to the honest doubt — never to a write it would reject."""
    _register(monkeypatch, KEYED)
    system = _LosesTheAnswer(land=True)
    system.schemas["Order"] = [{"name": "party_id", "type": "char"}]   # no `reference` here
    body = _commit(_app(system), KEYED.verb, {"party_id": "7"}, "prep:abc123:r1")
    assert body["outcome"] == "refusal", body
    assert "OUTCOME_IN_DOUBT" in body["message"]
    assert "reference" in body["message"], body["message"]


def test_a_convergent_verb_is_demonstrated_by_applying_it_twice(monkeypatch) -> None:
    """Shape (b), proven the only way it can be: run the COMPLETE mutation path twice under
    DIFFERENT attempt keys and show the backing system holds the same single state."""
    _register(monkeypatch, CONVERGENT_VERB)
    system = FakeSystem()
    args = {"sku": "SKU-1", "quantity": 12}
    first = _commit(_app(system), CONVERGENT_VERB.verb, args, "prep:abc:r1")
    after_first = [dict(r) for r in system.docs["Stock Level"]]
    second = _commit(_app(system), CONVERGENT_VERB.verb, args, "prep:zzz:r9")

    assert first["state"] == "executed" and second["state"] == "executed"
    assert [dict(r) for r in system.docs["Stock Level"]] == after_first, "re-applying changed the state"
    assert len(system.docs["Stock Level"]) == 1


def test_a_convergent_verb_in_doubt_is_safe_to_re_apply_not_a_human_gate(monkeypatch) -> None:
    """A convergent mutation whose answer is lost does not need a key: re-applying it is the same
    state. The adapter says that determinately instead of parking a human."""
    _register(monkeypatch, CONVERGENT_VERB)
    system = _LosesTheAnswer(land=False)
    body = _commit(_app(system), CONVERGENT_VERB.verb, {"sku": "SKU-1", "quantity": 12}, "prep:a:r1")
    assert body["outcome"] == "refusal", body
    assert body["code"] == "UPSTREAM_UNAVAILABLE", body
    assert "safe to re-apply" in body["message"].lower(), body["message"]


def test_a_convergent_verb_whose_state_DID_land_recovers_the_receipt(monkeypatch) -> None:
    _register(monkeypatch, CONVERGENT_VERB)
    system = _LosesTheAnswer(land=True)
    body = _commit(_app(system), CONVERGENT_VERB.verb, {"sku": "SKU-1", "quantity": 12}, "prep:a:r1")
    assert body["state"] == "executed", body
    assert body["replayed"] is True
    assert system.update_calls == 1, "the update was re-issued instead of verified"


def test_an_undeclared_verb_in_doubt_refuses_naming_the_unanswered_question(monkeypatch) -> None:
    _register(monkeypatch, UNDECLARED)
    body = _commit(_app(_LosesTheAnswer(land=True)), UNDECLARED.verb, {"name": "Acme"}, "prep:a:r1")
    assert body["outcome"] == "refusal", body
    assert "OUTCOME_IN_DOUBT" in body["message"]
    assert CANONICAL_SENTENCE.split(".")[0] in body["message"], body["message"]


def test_a_verb_that_declares_no_witness_says_so_rather_than_guessing(monkeypatch) -> None:
    _register(monkeypatch, ABSENT)
    body = _commit(_app(_LosesTheAnswer(land=True)), ABSENT.verb, {"name": "Acme"}, "prep:a:r1")
    assert body["outcome"] == "refusal", body
    assert "OUTCOME_IN_DOUBT" in body["message"]
    assert "no free-text reference field" in body["message"], body["message"]


def test_an_in_doubt_write_is_never_reported_as_failed_terminal(monkeypatch) -> None:
    """`failed_terminal` asserts "it did not happen". After a lost answer nobody knows that."""
    _register(monkeypatch, UNDECLARED)
    body = _commit(_app(_LosesTheAnswer(land=True)), UNDECLARED.verb, {"name": "Acme"}, "prep:a:r1")
    assert body.get("state") != "failed_terminal", body


def test_the_generic_resource_path_also_refuses_in_doubt(monkeypatch) -> None:
    """`resource.*` names an ARBITRARY target, so no witness can be declared for it in advance —
    which makes the honest refusal the only correct answer there."""
    _register(monkeypatch, KEYED)
    system = _LosesTheAnswer(land=True)
    body = _commit(_app(system), "resource.create", {"target": "Order", "party_id": "7"}, "prep:a:r1")
    assert body["outcome"] == "refusal", body
    assert "OUTCOME_IN_DOUBT" in body["message"]


def test_a_doubted_commit_leaves_no_ledger_row_claiming_it_succeeded(monkeypatch) -> None:
    """The ledger may be a fast path; it may never be the proof, and it may never be written before
    the mutation it claims to record. A commit that ended in doubt must leave nothing behind that
    would answer the next commit with a fabricated `executed` receipt."""
    _register(monkeypatch, UNDECLARED)
    client = _app(_LosesTheAnswer(land=True))
    assert _commit(client, UNDECLARED.verb, {"name": "Acme"}, "prep:a:r1")["outcome"] == "refusal"

    # the SAME live process, the SAME key: if the doubt had written a ledger row, this would come
    # back `replayed: True` — a receipt for an effect nobody ever observed.
    replay = _commit(client, UNDECLARED.verb, {"name": "Acme"}, "prep:a:r1")
    assert replay.get("replayed") is not True, replay


def test_what_the_declaration_actually_BUYS_measured_in_duplicate_records(monkeypatch) -> None:
    """The same lost answer, the same caller retry, twice — once for a verb that declared a witness
    and once for a verb that declared nothing. This is the whole exercise in one assertion.

    Note what it also shows: the adapter CANNOT stop the undeclared duplicate. With no witness there
    is nothing to ask, so a re-commit writes again. That is why the gate demands the declaration
    rather than trying to be clever at commit time."""
    _register(monkeypatch, KEYED)
    keyed_system = _LosesTheAnswer(land=True)
    keyed = _app(keyed_system)
    _commit(keyed, KEYED.verb, {"party_id": "7"}, "prep:a:r1")
    _commit(keyed, KEYED.verb, {"party_id": "7"}, "prep:a:r1")

    _register(monkeypatch, UNDECLARED)
    blind_system = _LosesTheAnswer(land=True)
    blind = _app(blind_system)
    _commit(blind, UNDECLARED.verb, {"name": "Acme"}, "prep:a:r1")
    _commit(blind, UNDECLARED.verb, {"name": "Acme"}, "prep:a:r1")

    assert len(keyed_system.docs["Order"]) == 1, "the declared witness failed to prevent the duplicate"
    assert len(blind_system.docs["Thing"]) == 2, (
        "the undeclared verb did NOT duplicate — this test has stopped measuring anything")


# ── refusals the kernel can actually read ────────────────────────────────────────────────────────

# The kernel's `RefusalCode` is a CLOSED enum. A code outside it makes pydantic raise in the SDK and
# kills the run at its first step — a refusal nobody can parse is worse than no refusal at all. This
# list is the kernel's enum as of nilscript 0.3.0; the test below cross-checks it against the real
# enum whenever the kernel is importable, so the copy cannot silently rot.
_KERNEL_REFUSAL_CODES = frozenset({
    "MALFORMED", "UNKNOWN_PERFORMATIVE", "UNKNOWN_VERB", "SCOPE_DENIED", "CAPABILITY_DENIED",
    "POLICY_DENIED", "INVALID_ARGS", "UNRESOLVED", "AMBIGUOUS", "BUDGET_EXHAUSTED",
    "QUOTA_EXHAUSTED", "SUSPENDED", "EXPIRED", "RATE_LIMITED", "UPSTREAM_UNAVAILABLE",
    "IRREVERSIBLE", "COMPENSATION_EXPIRED", "PRECONDITION_FAILED",
})


def test_every_refusal_code_this_edge_emits_is_one_the_kernel_can_parse() -> None:
    """Static guardrail over the whole edge: no future refusal may invent a code the kernel's closed
    enum does not carry. `OUTCOME_IN_DOUBT` is NOT a code for exactly this reason — it is a token
    inside a `SUSPENDED` message."""
    source = Path(edge_mod.__file__).read_text(encoding="utf-8")
    codes = set(re.findall(r"_refusal\(\s*\n?\s*env,\s*\"([A-Z_]+)\"", source))
    assert codes, "the scanner found no refusals — it would pass even if every code were wrong"
    assert not sorted(codes - _KERNEL_REFUSAL_CODES), \
        f"refusal codes the kernel cannot parse: {sorted(codes - _KERNEL_REFUSAL_CODES)}"


def test_the_local_copy_of_the_kernels_refusal_enum_is_still_accurate() -> None:
    """The copy above is a convenience so this gate runs without the kernel installed. When the
    kernel IS installed it becomes the authority, so the copy cannot drift unnoticed."""
    refusals = pytest.importorskip("nilscript.sdk.refusals")
    assert _KERNEL_REFUSAL_CODES == {c.value for c in refusals.RefusalCode}


def test_write_op_classifies_the_standards_verb_lexicon() -> None:
    assert write_op("commerce.delete_product") == "delete"
    assert write_op("commerce.update_product") == "update"
    assert write_op("services.create_invoice") == "create"
    assert write_op("services.send_proposal") == "create", "a non-update/delete action mutates anew"


# ── the hand-rolled retry loop: the hole BOTH existing forks fell into ───────────────────────────
#
# `RetryPolicy` gives a fork the right answer, but nothing stopped it from writing its own loop a
# few lines below — and that is not hypothetical. odoo and daftara each INDEPENDENTLY invented an
# unkeyed `for attempt in range(N)` around a write, which is how `commerce.record_payment` and
# `services.create_invoice` became UNSAFE. A contract that only offers the safe path, without
# closing the unsafe one, reproduces the defect in the next fork exactly as it did in the last two.

_SANCTIONED_RETRY_OWNER = "RetryPolicy"


def _hand_rolled_retry_loops(source: str) -> list[str]:
    """Bounded loops in `system.py` that live OUTSIDE `RetryPolicy` — i.e. a fork's own retry.

    Deliberately narrow: it flags the SHAPE both forks actually wrote (`for _ in range(N)` and
    `while attempt/retries/tries ...`), not every loop. A transport module has legitimate loops
    (pagination, parsing); a bounded retry counter around I/O is the one that duplicates money.
    """
    owner, offenders = None, []
    for lineno, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if stripped.startswith(("class ", "def ")) and indent == 0:
            owner = stripped
        if owner and _SANCTIONED_RETRY_OWNER in owner:
            continue                                   # the one place a retry loop belongs
        if re.match(r"for\s+\w+\s+in\s+range\s*\(", stripped) or \
           re.match(r"while\s+.*\b(attempt|retries|tries|backoff)\b", stripped):
            offenders.append(f"{lineno}: {stripped}")
    return offenders


def test_no_fork_hand_rolls_its_own_retry_loop_in_system_py() -> None:
    """THE GUARDRAIL. `RetryPolicy` is the only sanctioned retry in the transport module."""
    source = Path(system_mod.__file__).read_text(encoding="utf-8")
    offenders = _hand_rolled_retry_loops(source)
    assert not offenders, (
        "a hand-rolled retry loop in system.py — route it through RetryPolicy instead.\n"
        "Both shipped forks wrote exactly this and turned a write into a duplicate:\n  "
        + "\n  ".join(offenders)
    )


def test_the_retry_loop_detector_actually_detects_one() -> None:
    """POSITIVE CONTROL — mandatory. Without it, "0 offenders" and "the scanner is broken" are the
    same result. This is the real daftara loop (`system.py:225-234`), verbatim in shape."""
    daftara_shaped = (
        "class RealSystemClient:\n"
        "    def _request(self, method, path, **kwargs):\n"
        "        delay = 0.5\n"
        "        for attempt in range(5):\n"
        "            resp = self._http.request(method, path, **kwargs)\n"
        "            if resp.status_code != 429:\n"
        "                return resp\n"
        "            time.sleep(delay)\n"
        "        return resp\n"
    )
    assert _hand_rolled_retry_loops(daftara_shaped), "the detector is blind to the real defect"


def test_the_detector_does_not_flag_the_sanctioned_policy() -> None:
    """The other half of the control: it must not fire on `RetryPolicy` itself, or the guardrail
    would be unsatisfiable and every fork would delete it."""
    sanctioned = (
        "class RetryPolicy:\n"
        "    def run(self, fn, *, is_write):\n"
        "        for attempt in range(self.attempts):\n"
        "            return fn()\n"
    )
    assert _hand_rolled_retry_loops(sanctioned) == []


# ── the declaration must TRAVEL: describe() exports the witness so the plane can read it ─────────
#
# The witness matrix's second blocker (docs/EXTERNAL-WITNESS-MATRIX-2026-08-28.md §6, wosool-hub):
# odoo's six witnessed verbs were "SAFE at the adapter; unreachable from the plane that would
# recover them" — `describe().verb_details` carried verb/tier/target/required/reversibility and
# nothing about recovery, so no control plane could ever route a retry by verdict. The contract
# therefore requires the declaration to be EXPORTED, in one backing-agnostic shape, and requires
# silence to stay visibly silent: an undeclared verb exports NO witness key at all, which every
# consumer must read as UNKNOWN — and UNKNOWN is treated exactly as UNSAFE.


class TestTheWitnessTravels:
    def test_an_attempt_keyed_witness_serializes_completely(self) -> None:
        out = witness_export(KEYED)
        assert out == {
            "shape": "attempt_keyed",
            "field": "reference",
            "lookup": "list('Order', {'reference': <marker>})",
            "negative_authoritative": True,
            "note": "`reference` is a free-text document reference the backend persists and can "
                    "filter on.",
        }

    def test_a_convergent_witness_serializes_its_identity(self) -> None:
        out = witness_export(CONVERGENT_VERB)
        assert out["shape"] == "convergent"
        assert out["identity"] == ["sku"]
        assert out["negative_authoritative"] is True and out["lookup"]

    def test_a_blind_negative_travels_as_False_never_by_omission(self) -> None:
        """The recovery policy routes a non-authoritative NOT FOUND to the human gate. A consumer
        that has to GUESS the flag from absence will guess wrong exactly once."""
        assert witness_export(KEYED_BLIND_NEGATIVE)["negative_authoritative"] is False

    def test_an_honest_none_is_an_ANSWER_distinct_from_silence(self) -> None:
        """`no_witness(reason)` and 'never declared' are different facts: the first is a considered
        UNSAFE, the second is an unanswered question (UNKNOWN). Collapsing them would hide exactly
        the verbs the gate exists to surface."""
        out = witness_export(ABSENT)
        assert out["shape"] == "none" and "reference field" in out["note"]

    def test_an_undeclared_verb_exports_NOTHING(self) -> None:
        assert witness_export(UNDECLARED) is None

    def test_describe_carries_the_witness_per_verb(self, monkeypatch) -> None:
        """The wire proof: a declared witness appears on the verb's describe row, serialized."""
        monkeypatch.setitem(WRITE_VERBS, KEYED.verb, KEYED)
        rows = _app(FakeSystem()).get("/nil/v0.1/describe").json()["verb_details"]
        row = next(r for r in rows if r["verb"] == KEYED.verb)
        assert row["witness"] == witness_export(KEYED)
        assert row["tier"] == "HIGH" and row["target"] == "Order"

    def test_describe_stays_SILENT_for_an_undeclared_verb(self) -> None:
        """Silence must travel as silence: no witness key, not `null`, not a defaulted shape —
        the consumer's fail-closed floor (UNKNOWN ⇒ UNSAFE) only works if absence is absent."""
        rows = _app(FakeSystem()).get("/nil/v0.1/describe").json()["verb_details"]
        undeclared = [r for r in rows if getattr(WRITE_VERBS.get(r["verb"]), "witness", None) is None]
        assert undeclared, "the fresh template should still have undeclared verbs to prove this on"
        assert all("witness" not in r for r in undeclared), (
            "an undeclared verb exported a witness key — silence stopped being visible",
            [r for r in undeclared if "witness" in r][:3],
        )
