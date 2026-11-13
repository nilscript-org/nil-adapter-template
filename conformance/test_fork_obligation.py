"""Fork obligations (see conftest.py): fail closed by default; the template self-check only under TEMPLATE_SELF_CHECK=1.

- `test_no_stub_left_unfilled` (fork_obligation, runs by default): no stub still raises NotImplementedError("fill …").
- `test_template_stub_is_unfilled` (TEMPLATE_SELF_CHECK=1 only): every stub raises NotImplementedError("fill …").
- `test_planted_*` (TEMPLATE_SELF_CHECK=1 only): copies of this repo run in a subprocess WITHOUT the variable:
  a filled fork is green; a fork with one stub unfilled is red (renamed, or still named as the template);
  the untouched template is red; and the untouched template WITH the variable is green.
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

from conformance.conftest import SELF_CHECK_ENV, is_template_self_check
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


@pytest.mark.skipif(not is_template_self_check(), reason="TEMPLATE_SELF_CHECK=1 only")
@pytest.mark.parametrize("verb_name", sorted(STUBS))
def test_template_stub_is_unfilled(verb_name: str) -> None:
    with pytest.raises(NotImplementedError, match=r"^fill "):
        STUBS[verb_name]()


@pytest.mark.fork_obligation
@pytest.mark.parametrize("verb_name", sorted(STUBS))
def test_no_stub_left_unfilled(verb_name: str) -> None:
    exc = _unfilled(STUBS[verb_name])
    assert exc is None, f"{verb_name}: the template stub is still unfilled ({exc}) — fill translate.py"


# --- the planted proofs: copies of this repo, run in a subprocess -------------------------------------

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PKG = "nil_adapter_template"
_FILL = re.compile(r'raise NotImplementedError\("fill (_\w+):[^"]*"\)')
_INVOICE = [
    "conformance/test_conformance.py::test_write_verb_reaches_executed[services.create_invoice]",
    "conformance/test_fork_obligation.py::test_no_stub_left_unfilled[services.create_invoice]",
]


def _copy(dest: pathlib.Path, *, rename: bool, fill_all_but: str | None, fill: bool = True) -> None:
    pkg = "sim_fork_nil_adapter" if rename else _PKG
    shutil.copytree(_ROOT / "conformance", dest / "conformance", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(_ROOT / "src" / _PKG, dest / "src" / pkg, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(_ROOT / "requirements-manifest.json", dest / "requirements-manifest.json")
    pyproject = (_ROOT / "pyproject.toml").read_text()
    if rename:
        pyproject = pyproject.replace('name = "nil-adapter-template"', 'name = "sim-fork-nil-adapter"')
        for py in dest.rglob("*.py"):
            py.write_text(py.read_text().replace(_PKG, pkg))
    (dest / "pyproject.toml").write_text(pyproject)
    if not fill:
        return
    translate = dest / "src" / pkg / "translate.py"

    def sub(m: re.Match[str]) -> str:
        if m.group(1) == fill_all_but:
            return m.group(0)
        return 'return {"items": []}' if m.group(1).startswith("_run_") else "return dict(args)"

    translate.write_text(_FILL.sub(sub, translate.read_text()))


def _run(dest: pathlib.Path, *, self_check: bool) -> tuple[int, list[str], str]:
    env = {k: v for k, v in os.environ.items() if k != SELF_CHECK_ENV}
    env.update(PYTHONPATH=str(dest / "src"), NIL_FORK_SIMULATION="1")
    if self_check:
        env[SELF_CHECK_ENV] = "1"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "conformance"],
                       cwd=dest, env=env, capture_output=True, text=True, timeout=300)
    return r.returncode, sorted(set(re.findall(r"^FAILED (\S+)", r.stdout, re.M))), r.stdout[-3000:]


_planted = pytest.mark.skipif(not is_template_self_check() or _IN_SIMULATION,
                              reason="planted proofs run from the template self-check only")


@_planted
def test_planted_filled_fork_is_green(tmp_path: pathlib.Path) -> None:
    _copy(tmp_path, rename=True, fill_all_but=None)
    rc, failed, out = _run(tmp_path, self_check=False)
    assert rc == 0 and failed == [], out


@_planted
def test_planted_fork_with_one_stub_unfilled_is_red(tmp_path: pathlib.Path) -> None:
    _copy(tmp_path, rename=True, fill_all_but="_to_native_create_invoice")
    rc, failed, out = _run(tmp_path, self_check=False)
    assert rc == 1 and failed == _INVOICE, out


@_planted
def test_planted_fork_keeping_the_template_name_with_one_stub_unfilled_is_red(tmp_path: pathlib.Path) -> None:
    _copy(tmp_path, rename=False, fill_all_but="_to_native_create_invoice")
    rc, failed, out = _run(tmp_path, self_check=False)
    assert rc == 1 and failed == _INVOICE, out


@_planted
def test_planted_untouched_template_without_the_variable_is_red(tmp_path: pathlib.Path) -> None:
    _copy(tmp_path, rename=False, fill_all_but=None, fill=False)
    rc, failed, out = _run(tmp_path, self_check=False)
    assert rc == 1 and len(failed) == 2 * 15 + 1, out  # 15 write verbs x2 + 1 query stub


@_planted
def test_planted_untouched_template_with_the_variable_is_green(tmp_path: pathlib.Path) -> None:
    _copy(tmp_path, rename=False, fill_all_but=None, fill=False)
    rc, failed, out = _run(tmp_path, self_check=True)
    assert rc == 0 and failed == [], out
