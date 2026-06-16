# Building a NIL adapter from this template

This repository is the **fork base** for every NIL adapter. You never fork the core
(`nilscript`) — the core is the protected kernel (CLI, generator, conformance engine,
constitutional schemas). You fork **this template**, fill three files, prove conformance,
and submit. The core only *receives* adapters; it is never forked to build one.

## The journey

```
 1. Use this template ───▶ "Use this template" / Fork  →  your repo: <service>-nil-adapter
 2. Fill three files  ───▶ src/<pkg>/system.py · translate.py · compensation.py
 3. Prove it          ───▶ offline pytest  +  live `nilscript conformance-test`  +  manifest validate
 4. Submit            ───▶ PR / "request official status" to nilscript-org
 5. Adopt             ───▶ re-homed as nilscript-org/<service>-nil-adapter, badged "Official Verified Adapter"
```

The edge, state, models, and manifest loader are generated and identical across every
adapter — **do not edit them**. You only ever touch your backend's I/O and verb mapping.

## The three files you fill

| File | Your job |
| --- | --- |
| `src/<pkg>/system.py` | `RealSystemClient` — the **one** place I/O against your backend happens. |
| `src/<pkg>/translate.py` | Map each active NIL verb to a native document, and back. |
| `src/<pkg>/compensation.py` | Declare which verbs are reversible and how to mint/honor a compensation token. |

Until you fill them, the bundled proof is **red** — every active write verb fails because
the stub raises `NotImplementedError`. That is intentional: it proves the harness detects
non-conformance, not just conformance.

## What "conformant" precisely means

Conformance is **not** "passes the kernel's 160 tests" — those are the *kernel's own* suite.
Your adapter proves conformance by three concrete gates (all wired in `.github/workflows/conformance.yml`):

1. **Offline proof** — `pytest` is green: every active write verb reaches `executed` against
   the in-memory `FakeSystem`, and the rollback-honesty test passes (a reversible verb mints a
   compensation token and `ROLLBACK` *previews* a compensation — never a silent write; an unknown
   token is refused).
2. **Live proof** — `nilscript conformance-test --url <running shim> --verb <verb>` is green for
   every write verb, **including the rollback-honesty rows across all three tiers**:
   `REVERSIBLE`/`COMPENSABLE` preview a compensation, `IRREVERSIBLE` refuses honestly, and
   unknown/expired tokens never trigger a phantom reversal.
3. **Manifest honesty** — `nilscript manifest validate requirements-manifest.json` passes.
   Reversibility tiers are **earned, not asserted**: do not declare a tier in `compensation.py`
   that your backend cannot actually honor.

> **Roadmap (not built yet):** a hosted attestation service that signs a conformance run into a
> certificate. Today, "certification" = the three gates above passing in your CI. Do not advertise
> a signed certificate until that service exists.

## Discover hidden requirements (optional, once)

```
nilscript scan --replay captured-errors.json -o requirements-manifest.json
```

`scan` infers the requirements your backend does not advertise (required fields, prerequisite
entities, transport quirks) from captured native errors, so you do not re-learn them by collision.
The shim reads that manifest and pre-fills them automatically (`src/<pkg>/manifest.py`).

## Submitting for official status

Open a PR (or an issue requesting adoption) against `nilscript-org`. The core team reviews:

- **Security** — no credential leakage, no SSRF, inputs validated at the edge.
- **No silent writes** — `ROLLBACK` always *previews*; reversibility is honored, not faked.
- **Tier honesty** — every declared reversibility tier is backed by real compensation behavior.

On acceptance your repo is transferred / re-homed under `nilscript-org/<service>-nil-adapter`
and badged **Official Verified Adapter**.

## Naming conventions

- Repo: `<service>-nil-adapter` (e.g. `pocketbase-nil-adapter`).
- Python package inside: `<service>_nil_adapter`.
- Pin the minimum kernel version you conform to (e.g. `nilscript>=0.3.0`); your own version is independent.
