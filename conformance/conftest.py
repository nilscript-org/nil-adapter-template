"""Fork obligations: one marker; fail CLOSED by default.

`@pytest.mark.fork_obligation` marks a conformance test a fork must satisfy (it needs the fork's
filled translation). By DEFAULT it runs and must pass: a stub left unfilled is red, whatever the
repo or package is called.

Only the template's own self-check turns this around: with `TEMPLATE_SELF_CHECK=1` in the
environment the fork_obligation tests are skipped and `test_fork_obligation.py::test_template_stub_is_unfilled`
proves the opposite (every stub raises NotImplementedError("fill …")). Nothing in the repo's code
sets that variable: it is set by the merge queue's target line for the template (outside the repo)
and by the template's own CI workflow. A fork runs every obligation unless it sets it on purpose.
"""

from __future__ import annotations

import os

import pytest

SELF_CHECK_ENV = "TEMPLATE_SELF_CHECK"


def is_template_self_check() -> bool:
    return os.environ.get(SELF_CHECK_ENV) == "1"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "fork_obligation: a conformance test every fork must pass; skipped only under "
        "TEMPLATE_SELF_CHECK=1, where the template's stubs are proven unfilled instead",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not is_template_self_check():
        return
    skip = pytest.mark.skip(reason="TEMPLATE_SELF_CHECK=1: the stubs are proven unfilled by "
                                   "test_fork_obligation.py::test_template_stub_is_unfilled")
    for item in items:
        if item.get_closest_marker("fork_obligation"):
            item.add_marker(skip)
