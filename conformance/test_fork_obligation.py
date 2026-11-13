"""Fork obligations (see conftest.py): the template proves its stubs are unfilled; a fork proves it filled them.

- `test_template_stub_is_unfilled` (template only): every translation stub raises NotImplementedError("fill …").
- `test_no_stub_left_unfilled` (fork_obligation): no stub still raises NotImplementedError("fill …").
- `test_a_simulated_fork_*` (template only): a copy renamed as a fork is run in a subprocess; with every
  stub filled it is green, with ONE stub unfilled it is red and names that stub.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any, Callable

import pytest

from conformance.conftest import is_template
from nil_adapter_template.system import FakeSystem
from nil_adapter_template.translate import QUERY_VERBS, WRITE_VERBS

_IN_SIMULATION = os.environ.get("NIL_FORK_SIMULATION") == "1"


def _stubs() -> dict[str, Callable[[], Any]]:
    out: dict[str, Callable[[], Any]] = {}
    for name, w in WRITE_VERBS.items():
        args = {field: "x" for field in w.required}
        out[name] = lambda w=w, args=args: w.to_native(args)
    for name, q in QUERY_VERBS.items():
        out[name] = lambda q=q: q.run(FakeSystem(), {})
    return out


STUBS = _stubs()


def _unfilled(call: Callable[[], Any]) -> NotImplementedError | None:
    try:
        call()
    except NotImplementedError as exc:
        return exc if str(exc).startswith("fill ") else None
    except Exception:  # placeholder args may be refused by a filled stub: that is not an unfilled stub
        return None
    return None


@pytest.mark.skipif(not is_template(), reason="template contract only")
@pytest.mark.parametrize("verb_name", sorted(STUBS))
def test_template_stub_is_unfilled(verb_name: str) -> None:
    with pytest.raises(NotImplementedError, match=r"^fill "):
        STUBS[verb_name]()


@pytest.mark.fork_obligation
@pytest.mark.parametrize("verb_name", sorted(STUBS))
def test_no_stub_left_unfilled(verb_name: str) -> None:
    exc = _unfilled(STUBS[verb_name])
    assert exc is None, f"{verb_name}: the template stub is still unfilled ({exc}) — fill translate.py"


# --- the planted proof: a simulated fork ---------------------------------------------------------------

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_FILL = re.compile(r'raise NotImplementedError\("fill (_\w+):[^"]*"\)')


def _make_fork(dest: pathlib.Path, leave_unfilled: str | None) -> None:
    shutil.copytree(_ROOT / "conformance", dest / "conformance",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(_ROOT / "src" / "nil_adapter_template", dest / "src" / "sim_fork_nil_adapter",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(_ROOT / "requirements-manifest.json", dest / "requirements-manifest.json")
    (dest / "pyproject.toml").write_text(
        (_ROOT / "pyproject.toml").read_text().replace('name = "nil-adapter-template"',
                                                        'name = "sim-fork-nil-adapter"'))
    for py in dest.rglob("*.py"):
        py.write_text(py.read_text().replace("nil_adapter_template", "sim_fork_nil_adapter"))
    translate = dest / "src" / "sim_fork_nil_adapter" / "translate.py"

    def fill(m: re.Match[str]) -> str:
        fn = m.group(1)
        if fn == leave_unfilled:
            return m.group(0)
        return 'return {"items": []}' if fn.startswith("_run_") else "return dict(args)"

    translate.write_text(_FILL.sub(fill, translate.read_text()))


def _run_fork(dest: pathlib.Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(dest / "src"), "NIL_FORK_SIMULATION": "1"}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "conformance"],
                          cwd=dest, env=env, capture_output=True, text=True, timeout=300)


_template_only = pytest.mark.skipif(not is_template() or _IN_SIMULATION, reason="template proof only")


@_template_only
def test_a_simulated_fork_with_every_stub_filled_is_green(tmp_path: pathlib.Path) -> None:
    _make_fork(tmp_path, leave_unfilled=None)
    r = _run_fork(tmp_path)
    assert r.returncode == 0, r.stdout[-3000:]
    assert "failed" not in r.stdout.splitlines()[-1], r.stdout[-3000:]


@_template_only
def test_a_simulated_fork_with_one_stub_unfilled_is_red(tmp_path: pathlib.Path) -> None:
    _make_fork(tmp_path, leave_unfilled="_to_native_create_invoice")
    r = _run_fork(tmp_path)
    assert r.returncode == 1, r.stdout[-3000:]
    failed = sorted(set(re.findall(r"^FAILED (\S+)", r.stdout, re.M)))
    assert failed == [
        "conformance/test_conformance.py::test_write_verb_reaches_executed[services.create_invoice]",
        "conformance/test_fork_obligation.py::test_no_stub_left_unfilled[services.create_invoice]",
    ], r.stdout[-3000:]
