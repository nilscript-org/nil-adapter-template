"""Fork obligations: one marker, two meanings, decided by WHICH repo runs it (never by a flag).

`@pytest.mark.fork_obligation` marks a conformance test a fork must satisfy (it needs the fork's
filled translation). In a FORK it runs like any test and must pass: a stub left unfilled is red.
In the TEMPLATE itself it is skipped, because the template's contract is the opposite and is
proven positively by `test_fork_obligation.py::test_template_stub_is_unfilled` (every stub raises
NotImplementedError("fill …")). The template's own gate is therefore green with zero waivers.

The template is the repo whose pyproject says `name = "nil-adapter-template"`; README step 2 makes
a fork rename it. A fork that kept the name but filled any stub fails the template's positive test,
so it cannot hide behind the template's identity.
"""

from __future__ import annotations

import pathlib
import tomllib

import pytest

TEMPLATE_NAME = "nil-adapter-template"
_PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"


def is_template() -> bool:
    with _PYPROJECT.open("rb") as f:
        return tomllib.load(f).get("project", {}).get("name") == TEMPLATE_NAME


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "fork_obligation: a conformance test every fork must pass; in the template it is skipped and "
        "the template's stubs are proven unfilled instead",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not is_template():
        return
    skip = pytest.mark.skip(reason="fork obligation: the template's stubs are proven unfilled by "
                                   "test_fork_obligation.py::test_template_stub_is_unfilled")
    for item in items:
        if item.get_closest_marker("fork_obligation"):
            item.add_marker(skip)
