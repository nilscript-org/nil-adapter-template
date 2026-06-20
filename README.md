# nil-adapter-template

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20774491.svg)](https://doi.org/10.5281/zenodo.20774491)

> **The fork base for every NIL adapter.** Click **"Use this template"** to start a new
> adapter for your backend. You never fork the core (`nilscript`) — you fork *this*.

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
   - `src/<pkg>/translate.py` — map each active NIL verb to a native document, and back.
   - `src/<pkg>/compensation.py` — declare reversible verbs + compensation tokens.
4. Prove it.

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
`NotImplementedError`) — proving the harness detects non-conformance, not just conformance.
Fill the stubs until it is green.

Then, against a running shim:

```
nilscript conformance-test --url https://your-shim.example --verb services.create_invoice
nilscript manifest validate requirements-manifest.json
```

## The three conformance gates

CI (`.github/workflows/conformance.yml`) wires all three — see [CONTRIBUTING.md](./CONTRIBUTING.md)
for what each means and what "conformant" precisely is (and is not):

1. **Offline proof** — `pytest` green (every write verb reaches `executed`; rollback honesty holds).
2. **Live proof** — `nilscript conformance-test` green per verb, across all three reversibility tiers.
3. **Manifest honesty** — `nilscript manifest validate` passes; tiers are earned, not asserted.

## Layout

```
src/nil_adapter_template/
  edge.py          # generic NIL edge — do not edit
  state.py         # proposal/commit state machine — do not edit
  models.py        # generated request/response models — do not edit
  manifest.py      # reads requirements-manifest.json — do not edit
  run.py           # uvicorn entrypoint
  system.py        # <- FILL: RealSystemClient (the only I/O)
  translate.py     # <- FILL: verb -> native mapping
  compensation.py  # <- FILL: reversibility + compensation tokens
conformance/
  test_conformance.py   # the offline proof (red until you fill the stubs)
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
