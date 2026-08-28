# nil-adapter-template

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20774491.svg)](https://doi.org/10.5281/zenodo.20774491)

**The fork base for every NIL governed-action adapter.** Every adapter built from this template speaks
the NIL contract (propose -> approve -> commit, skeleton-bounded, earned reversibility): an agent
proposes intent, the deterministic kernel is the only thing that commits, and a verb or target the
backend never declared is unexpressible, not filtered.

> Click **"Use this template"** to start a new adapter for your backend. You never fork the core
> (`nilscript`) — you fork *this*.

This is a pristine `nilscript scaffold-shim` output: a complete, bootable NIL shim whose
edge / state / models / manifest loader are generic and finished, and whose three
fill-in files ship as `NotImplementedError` stubs. **The bundled conformance proof is red
on day one** — that is the point. As you fill the stubs, the write verbs flip green.

## Quick start

1. **Use this template** → your repo `my-backend-nil-adapter`.
2. Rename the package `src/nil_adapter_template/` → `src/my_backend_nil_adapter/` and update
   `name`/`description` in `pyproject.toml`.
3. Fill the three files (see [CONTRIBUTING.md](./CONTRIBUTING.md)):
   - `src/<pkg>/system.py` — `RealSystemClient`: the **one** place I/O happens. Implement
     `create/list/update/delete` **and** `exists(target)`, `schema(target)`, `get(target,id)` —
     these light up discovery, the PROPOSE preflight, and generic reversibility.
     **Do not write your own retry loop** — route calls through `RetryPolicy` (see below).
   - `src/<pkg>/translate.py` — map each active NIL verb to a native document, and back, **and
     declare each write verb's recovery witness** (see [The recovery contract](#the-recovery-contract)).
   - `src/<pkg>/compensation.py` — declare reversible verbs + compensation tokens.
4. Prove it.

## The recovery contract

> **Idempotency is not a property declared by a verb. It is a recovery property demonstrated by
> the complete mutation path.**

The platform rule, enforced by `src/<pkg>/recovery.py` and by a conformance gate that fails your
fork by name:

> **Every externally mutating verb must have a DEMONSTRATED durable recovery witness, or the
> platform must refuse to automatically replay it.**

The question each write verb must answer, one verb at a time:

> *If the process disappears one microsecond after the backing system accepts this request, can the
> restarted system safely determine whether it should execute it again?*

**Answering the six questions IS the declaration.** Unanswerable ⇒ UNKNOWN ⇒ UNSAFE ⇒ human gate.

1. What identity represents this attempt?
2. Where is that identity durably stored?
3. Is it propagated to the external system?
4. How do we query it after a crash?
5. What happens if the response disappears?
6. Can we prove that replay is safe?

### Two shapes pass — and no, not every mutation needs a key

```python
from nil_adapter_template.recovery import ATTEMPT_KEYED, CONVERGENT, RecoveryWitness, no_witness

# (a) ATTEMPT-KEYED — the caller's attempt identity reaches the BACKING SYSTEM and is queryable
#     there after a restart. The edge stamps it and ASKS FIRST, before writing.
witness=RecoveryWitness(shape=ATTEMPT_KEYED, field="reference",
                        lookup="list('Invoice', {'reference': <marker>})",
                        negative_authoritative=True,
                        note="`reference` is a free-text document reference we persist.")

# (b) CONVERGENT — a stable pre-existing identity plus SET semantics: re-applying the mutation is
#     the same state, and that state is verifiable after a crash. NO attempt key is needed, and
#     forcing one here would be ceremony, not safety. (enable/disable, ensure-role, set-quantity,
#     password overwrite, confirm-by-existing-id.)
witness=RecoveryWitness(shape=CONVERGENT, identity=("sku",),
                        lookup="get('Stock Level', <sku>)", negative_authoritative=True,
                        note="SET semantics: same sku + same quantity = same state.")

# (c) NONE — honest, conformant, and permanently UNSAFE: the verb is never automatically replayed.
witness=no_witness("Lead has no free-text reference field — there is nothing to query on.")
```

Leaving `witness` unset is **silence**, and silence is the one answer that does not pass.

### Three verdicts, and UNKNOWN is UNSAFE

| verdict | meaning | recovery |
|---|---|---|
| **SAFE** | a witness exists and has been **demonstrated** by the conformance gate | may replay |
| **UNSAFE** | no durable witness (declared honestly) | never replay — human gate |
| **UNKNOWN** | claimed but not demonstrated, or nothing was said | treated **exactly** as UNSAFE |

**A declaration is not proof.** `witness_verdict()` returns UNKNOWN for a verb that merely declares;
only the gate — which drives PROPOSE → COMMIT against the backing system and reads the witness
back — may call it SAFE.

### "NOT FOUND" is not automatically "safe to replay"

```
ambiguous transport failure -> OUTCOME_IN_DOUBT -> witness lookup
    FOUND      -> SUCCEEDED  (recover the receipt, do not re-execute)
    NOT FOUND  -> UNKNOWN    (do NOT automatically replay)
```

NOT FOUND collapses to "safe to execute" **only** where the witness query is read-your-writes
consistent with the mutation path — same committed store, no async indexing, no delivery pipeline
between. A record search right after a create in the same transactional store qualifies; a mailbox
search for a message the transport just accepted does **not** (delivery is asynchronous, so NOT
FOUND there means "not yet" as easily as "never"). Declare which you have with
`negative_authoritative`; a non-authoritative negative routes to the human gate.

### What the edge does for you, once you declare

- stamps the COMMIT's `idempotency_key` into the declared field as `[WSL-<key>]`, **beside** any
  caller-supplied value, and checks the live schema first (a declaration is a belief; the backend's
  schema is the truth — a target that lacks the field degrades to the honest refusal, never to a
  rejected write);
- **asks first**: queries the witness *before* writing, and returns the existing record if the
  attempt already landed — which also survives an adapter restart, because `ShimState.ledger` is a
  fast path that dies with the process and is never the proof;
- answers a lost write as a structured **refusal** (`SUSPENDED`, message opening `OUTCOME_IN_DOUBT`)
  — never a 500, and never `failed_terminal`, which asserts *"it did not happen"* when nobody knows
  that. `OUTCOME_IN_DOUBT` is deliberately **not** a refusal code: the kernel's `RefusalCode` enum is
  closed, and an invented code makes pydantic raise in the SDK and kills the run at its first step;
- refuses **before writing anything** if the ask-first probe cannot run (`UPSTREAM_UNAVAILABLE`,
  "NOTHING WAS WRITTEN" — determinate, and safe to retry).

### And the retry rule your `RealSystemClient` must not re-invent

> **A retry is only safe when the operation is idempotent OR can be checked first.**

Both existing NIL adapters independently wrote "retry 3× on any exception" — which repeats a write
the backend already committed and mints a second irreversible business act, invisible to every layer
above. Use the shipped `RetryPolicy`:

```python
def create(self, target, doc):
    return self._retry.call("create", target, lambda: self._post(target, doc))
```

Reads retry with backoff. A write is repeated **only** on `RequestNeverDispatched` — proof it never
reached the backend (a limiter rejecting before dispatch). A timeout is *not* proof: it raises
`OutcomeInDoubt`. Unclassified operations are treated as writes (fail closed).

### Free for every adapter (0.3.0)

You do **not** author these — the generic edge provides them once you implement the I/O above:
- **`GET /nil/v0.1/describe`** — your *skeleton* (`{system, verbs, targets:{name:{exists, fields[]}}}`), the mandatory conformance row.
- **PROPOSE preflight** — refuses (`UPSTREAM_UNAVAILABLE`) when a target isn't provisioned.
- **Generic `resource.*` CRUD** (`create/read/update/delete`) over any target, with synthesized
  reversibility (before-image restore) and id-or-human-identifier resolution.

## Verify

```
pip install -e ".[dev]"
pytest                         # offline conformance proof against the in-memory FakeSystem
```

On a fresh template `pytest` **fails** every active write verb (the stubs raise
`NotImplementedError`) **and the recovery gate** (no verb has declared a witness yet) — proving the
harness detects non-conformance, not just conformance. Fill the stubs and answer the six questions
per verb until it is green.

Then, against a running shim:

```
nilscript conformance-test --url https://your-shim.example --verb services.create_invoice
nilscript manifest validate requirements-manifest.json
```

## The three conformance gates

CI (`.github/workflows/conformance.yml`) wires all three — see [CONTRIBUTING.md](./CONTRIBUTING.md)
for what each means and what "conformant" precisely is (and is not):

0. **Recovery witness** — every externally mutating verb declares a witness (or honestly declares it
   has none), and the declaration is *demonstrated* against the backing system
   (`conformance/test_recovery_witness.py`). See [The recovery contract](#the-recovery-contract).
1. **Offline proof** — `pytest` green (every write verb reaches `executed`; rollback honesty holds).
2. **Live proof** — `nilscript conformance-test` green per verb, across all three reversibility tiers.
3. **Manifest honesty** — `nilscript manifest validate` passes; tiers are earned, not asserted.

### The contract gate (rule C3 — adapters conform; capabilities never change)

An adapter implements the platform's **canonical capabilities** (`IssueInvoice`, `ManageContact`,
`RecordPayment`, …) — never backend-named verbs like `DaftaraCreateInvoice`. The capability
contract is the API; `translate.py` is where YOUR backend conforms to it, not the other way
around. Two obligations:

- **Declare the shape**: `describe` must publish `verb_details: [{verb, tier, target, required}]`
  so the control plane can shape-check a capability's cycle against your backend
  (`CONTRACT_MISMATCH` at readiness instead of a silent post-approval failure).
- **Prove the transform**: a `conformance/test_contract_gate.py` exercises every canonical verb
  with the baseline contract's canonical inputs and asserts the native payload is postable
  (e.g. a canonical invoice with a flat `amount` MUST synthesize the priced line item — a
  line-less invoice is rejected by every real backend).

## Layout

```
src/nil_adapter_template/
  edge.py          # generic NIL edge (incl. the ask-first witness probe) — do not edit
  recovery.py      # THE RECOVERY CONTRACT: witness shapes, verdicts, the gate — do not edit
  state.py         # proposal/commit state machine — do not edit
  models.py        # generated request/response models — do not edit
  manifest.py      # reads requirements-manifest.json — do not edit
  run.py           # uvicorn entrypoint
  system.py        # <- FILL: RealSystemClient (the only I/O) — use the shipped RetryPolicy
  translate.py     # <- FILL: verb -> native mapping + each write verb's `witness=`
  compensation.py  # <- FILL: reversibility + compensation tokens
conformance/
  test_conformance.py       # the offline proof (red until you fill the stubs)
  test_recovery_witness.py  # the recovery gate (red until every write verb declares)
requirements-manifest.json
```

## License

See the core standard at [github.com/nilscript-org/nilscript](https://github.com/nilscript-org/nilscript).

## Citation

This template is part of the **NIL (Network Intent Layer)** framework, described in a published paper
archived on Zenodo with a permanent DOI:
**[10.5281/zenodo.20774491](https://doi.org/10.5281/zenodo.20774491)**.

```bibtex
@misc{elkhider2026nil,
  title  = {Unexpressible, Not Filtered: A Structural Framework for Governing AI-Agent Actions --- the Network Intent Layer},
  author = {Elkhider, ElBasheir A. M.},
  year   = {2026},
  doi    = {10.5281/zenodo.20774491},
  url    = {https://doi.org/10.5281/zenodo.20774491}
}
```
