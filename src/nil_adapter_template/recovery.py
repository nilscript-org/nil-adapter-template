"""THE RECOVERY CONTRACT — what every externally mutating verb must be able to answer.

> **Idempotency is not a property declared by a verb. It is a recovery property demonstrated by
> the complete mutation path.**

The platform rule this module enforces:

> **Every externally mutating verb must have a DEMONSTRATED durable recovery witness, or the
> platform must refuse to automatically replay it.**

And the question the witness exists to answer:

> *If the process disappears one microsecond after the backing system accepts this request, can the
> restarted system safely determine whether it should execute it again?*

Why this lives in the TEMPLATE. The attempt key already reaches every adapter as the COMMIT body's
`idempotency_key` — and, before this contract, it died in `ShimState.ledger`: a plain dict that is
lost when the process is. No backing system ever learned it. Nothing named where a verb's durable
evidence lives, nothing distinguished a read's retry from a write's, and nothing refused to report
an unobserved effect as `failed_terminal`. Two independently-built forks therefore each invented an
UNKEYED retry loop, and each turned one lost answer into a second irreversible business act. A
template that says nothing is not merely incomplete — it is a mechanism for reproducing an unsafe
recovery model in every future fork. So the contract is here, and the forks inherit it.

## The six questions — answering them IS the declaration

1. What identity represents this attempt?            -> `shape` + `identity`
2. Where is that identity durably stored?            -> `field` (attempt-keyed) / the record itself
3. Is it propagated to the external system?          -> the edge stamps `field`; the gate proves it
4. How do we query it after a crash?                 -> `lookup`
5. What happens if the response disappears?          -> `OutcomeInDoubt` -> witness lookup
6. Can we prove that replay is safe?                 -> `negative_authoritative` + the gate

Unanswerable => UNKNOWN => UNSAFE => human gate.

## The two shapes that pass

* **ATTEMPT_KEYED** — a caller-controlled attempt identity is propagated INTO the backing system and
  is queryable there after a restart. ("did attempt X land?")
* **CONVERGENT** — a stable, pre-existing identity plus SET semantics: re-applying the mutation
  produces the same state, and that state is independently verifiable after a crash. (enable /
  disable, ensure-role, set-quantity, confirm-by-existing-id.) This shape needs **no attempt key at
  all**; forcing one on it would add ceremony without adding safety.

Anything else declares `NO_WITNESS` with a reason and is permanently UNSAFE — which is a conformant,
honest answer. For a business operating system, **stopping is preferable to silently duplicating
reality.** Silence is the only unacceptable outcome, and silence is what this gate refuses.

## The verdicts are three-valued, and UNKNOWN IS UNSAFE

| verdict | meaning | recovery |
|---|---|---|
| SAFE    | a witness exists and has been DEMONSTRATED by the conformance gate | may replay |
| UNSAFE  | no durable witness (declared honestly)                            | never replay — human gate |
| UNKNOWN | a mechanism is *claimed* but not demonstrated, or nothing was said | treated exactly as UNSAFE |

**A declaration is not proof.** `witness_verdict()` therefore returns UNKNOWN for a verb that merely
declares; only the conformance gate, which drives PROPOSE -> COMMIT against the backing system and
reads the witness back, may pass `demonstrated=True`.

## And "NOT FOUND" is not automatically "safe to replay"

    ambiguous transport failure -> OUTCOME_IN_DOUBT -> witness lookup
        FOUND      -> SUCCEEDED  (recover the receipt, do not re-execute)
        NOT FOUND  -> UNKNOWN    (do NOT automatically replay)

NOT FOUND collapses to "safe to execute" ONLY where the witness query is read-your-writes consistent
with the mutation path — the same committed store, no async indexing, no delivery pipeline between.
A record search right after a create in the same transactional store qualifies; a mailbox search for
a message the transport just accepted does NOT, because delivery is asynchronous and NOT FOUND there
means "not yet" as easily as "never". That is what `negative_authoritative` declares, and a
non-authoritative negative is routed to the human gate rather than to a replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# ── the sentence this whole module exists to enforce ─────────────────────────────────────────────
CANONICAL_SENTENCE = (
    "Idempotency is not a property declared by a verb. "
    "It is a recovery property demonstrated by the complete mutation path."
)

SIX_QUESTIONS: tuple[str, ...] = (
    "What identity represents this attempt?",
    "Where is that identity durably stored?",
    "Is it propagated to the external system?",
    "How do we query it after a crash?",
    "What happens if the response disappears?",
    "Can we prove that replay is safe?",
)

# ── declaration shapes ───────────────────────────────────────────────────────────────────────────
ATTEMPT_KEYED = "attempt_keyed"
CONVERGENT = "convergent"
NO_WITNESS = "none"
SHAPES: frozenset[str] = frozenset({ATTEMPT_KEYED, CONVERGENT, NO_WITNESS})

# ── verdicts (three-valued; UNKNOWN is treated exactly as UNSAFE) ────────────────────────────────
SAFE = "SAFE"
UNSAFE = "UNSAFE"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RecoveryWitness:
    """WHERE the durable evidence of one mutation attempt lives in the backing system.

    A witness is not a promise that a verb is idempotent — it is the mechanism by which a RESTARTED
    process can find out what happened. Backing-system agnostic on purpose: Odoo's `origin` and
    Daftara's `ref` are *instances* of `field`, not the idea.

        # (a) attempt-keyed: the caller's attempt identity reaches the backing system
        RecoveryWitness(
            shape=ATTEMPT_KEYED,
            field="reference",                      # a free-text field the backend persists
            lookup="list('Invoice', {'reference': <marker>})",
            negative_authoritative=True,            # the query reads the store the write committed to
            note="`reference` is a document reference the backend persists and can filter on.",
        )

        # (b) convergent: a stable pre-existing identity + SET semantics, no attempt key needed
        RecoveryWitness(
            shape=CONVERGENT,
            identity=("sku",),                      # the caller args that name the record forever
            lookup="get('Stock Level', <sku>)",
            negative_authoritative=True,
            note="SET semantics: the same quantity on the same sku is the same state.",
        )

        # (c) none: honest, conformant, and permanently UNSAFE
        no_witness("Lead carries no free-text reference field — there is nothing to query on.")
    """

    shape: str
    field: str | None = None            # ATTEMPT_KEYED: the native field carrying the attempt key
    identity: tuple[str, ...] = ()      # CONVERGENT: the caller args forming the stable identity
    lookup: str = ""                    # Q4 — how the witness is queried after a crash
    negative_authoritative: bool = False  # Q6 — is NOT FOUND authoritative? (read-your-writes)
    note: str = ""                      # why this is the honest answer, and what it cannot do

    def __post_init__(self) -> None:
        # An under-answered declaration fails at import time, not at 3am. "Make the unsafe thing
        # hard to write" is the only defence that survives the next fork author's deadline.
        if self.shape not in SHAPES:
            raise ValueError(
                f"unknown recovery shape {self.shape!r}; one of {sorted(SHAPES)}. {CANONICAL_SENTENCE}"
            )
        if self.shape == ATTEMPT_KEYED and not self.field:
            raise ValueError(
                "an attempt-keyed witness must name the native `field` the attempt identity is "
                "persisted in — a key that reaches no backing system proves nothing."
            )
        if self.shape == CONVERGENT and not self.identity:
            raise ValueError(
                "a convergent witness must name the `identity` args that address the record "
                "forever — SET semantics without a stable identity is just an unkeyed write."
            )
        if self.shape == NO_WITNESS and not self.note:
            raise ValueError(
                "declaring that a verb has NO durable witness requires a reason in `note`; "
                '"none" must be a considered answer, never a default.'
            )
        if self.shape != NO_WITNESS and not self.lookup:
            raise ValueError(
                f"'{self.shape}' must answer question 4 — {SIX_QUESTIONS[3]} — in `lookup`."
            )

    @property
    def is_durable(self) -> bool:
        """Does a witness exist at all? (Not: has it been demonstrated. See `witness_verdict`.)"""
        return self.shape in (ATTEMPT_KEYED, CONVERGENT)


def no_witness(reason: str) -> RecoveryWitness:
    """This verb has no durable recovery witness, and here is why. UNSAFE, honestly and on purpose."""
    return RecoveryWitness(shape=NO_WITNESS, note=reason)


def witness_verdict(verb: Any, *, demonstrated: bool = False) -> str:
    """SAFE / UNSAFE / UNKNOWN for one write verb.

    `demonstrated` is passed ONLY by the conformance gate, after it has driven the complete mutation
    path against the backing system and read the witness back. A verb can never promote itself:
    a declaration alone is UNKNOWN, and UNKNOWN is treated exactly as UNSAFE.
    """
    witness = getattr(verb, "witness", None)
    if witness is None:
        return UNKNOWN                       # the question was never asked — the worst answer
    if not witness.is_durable:
        return UNSAFE                        # asked, answered "none": never replay, never guess
    return SAFE if demonstrated else UNKNOWN


def unanswered_verbs(verbs: Mapping[str, Any]) -> list[str]:
    """THE GATE. The verbs that answer the recovery question with SILENCE.

    Not "the unsafe verbs" — declaring `no_witness(reason)` is a conformant answer that keeps the
    verb out of every automatic replay. This names only the verbs that said nothing at all, because
    an unasked question is how the duplicate got built twice already.
    """
    return sorted(name for name, verb in verbs.items() if getattr(verb, "witness", None) is None)


def witness_export(verb: Any) -> dict[str, Any] | None:
    """The witness declaration as it TRAVELS — one backing-agnostic dict on the verb's
    `describe().verb_details` row, so the control plane can route recovery by verdict instead of
    guessing (the matrix's second blocker: "SAFE at the adapter; unreachable from the plane").

    `None` for an UNDECLARED verb, and the caller must then export NO key at all: silence has to
    stay visible — the consumer's fail-closed floor (absent ⇒ UNKNOWN ⇒ UNSAFE) only works if
    absence is absent. `no_witness(reason)` is different: a considered UNSAFE, exported with its
    reason, because "we looked and there is nothing to query on" and "nobody ever asked" must never
    read the same.
    """
    witness = getattr(verb, "witness", None)
    if witness is None:
        return None
    if witness.shape == NO_WITNESS:
        return {"shape": NO_WITNESS, "note": witness.note}
    out: dict[str, Any] = {"shape": witness.shape, "lookup": witness.lookup,
                           "negative_authoritative": witness.negative_authoritative}
    if witness.shape == ATTEMPT_KEYED:
        out["field"] = witness.field
    else:  # CONVERGENT — __post_init__ admits no other durable shape
        out["identity"] = list(witness.identity)
    if witness.note:
        out["note"] = witness.note
    return out


def gate_message(gaps: list[str]) -> str:
    """The conformance gate's failure text: the rule, the offenders, and the six questions to
    answer. A fork author must meet this contract before writing the verb, not after an incident."""
    listing = "\n".join(f"  - {name}" for name in gaps)
    questions = "\n".join(f"  {n}. {q}" for n, q in enumerate(SIX_QUESTIONS, start=1))
    return (
        f"{CANONICAL_SENTENCE}\n\n"
        f"{len(gaps)} externally mutating verb(s) declare no recovery witness at all:\n{listing}\n\n"
        "Every externally mutating verb must have a DEMONSTRATED durable recovery witness, or the "
        "platform must refuse to automatically replay it. Declare `witness=` on each verb in "
        "translate.py by answering:\n"
        f"{questions}\n\n"
        f"Two shapes pass: {ATTEMPT_KEYED} (a caller-controlled attempt identity propagated into the "
        f"backing system and queryable there after a restart) and {CONVERGENT} (a stable "
        "pre-existing identity plus SET semantics, independently verifiable after a crash). "
        "If neither is true, say so with `no_witness(<reason>)` — that is a conformant answer and "
        "the verb is then never automatically replayed. Silence is the one answer that is not."
    )


__all__ = [
    "ATTEMPT_KEYED",
    "CANONICAL_SENTENCE",
    "CONVERGENT",
    "NO_WITNESS",
    "SAFE",
    "SHAPES",
    "SIX_QUESTIONS",
    "UNKNOWN",
    "UNSAFE",
    "RecoveryWitness",
    "gate_message",
    "no_witness",
    "unanswered_verbs",
    "witness_verdict",
]
