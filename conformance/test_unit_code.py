"""ODOO-UNITS (D-554 4a): a connected system's unit reaches the hub as an approved Rec 20 code, or not at all.

The hook is `translate.unit_code(system_unit)`, backed by ONE table (`translate.UNIT_TABLE`). A unit the
table does not name is NEVER guessed and NEVER defaulted: the product read carries `unit: None` plus
`unit_source` (the system's own word), so the hub's no-unit rule lists the item as not pickable.
"""

from __future__ import annotations

import pytest

from nil_adapter_template import translate
from nil_adapter_template.translate import APPROVED_UNIT_CODES, UNIT_TABLE, product_unit, unit_code


def test_every_table_entry_is_an_approved_code() -> None:
    assert set(UNIT_TABLE.values()) <= APPROVED_UNIT_CODES


def test_mapped_unit_gives_its_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(translate.UNIT_TABLE, "Units", "H87")
    assert unit_code("Units") == "H87"
    assert product_unit("Units") == {"unit": "H87"}


@pytest.mark.parametrize("word", ["Bucket", "units", "", None, 7])
def test_unmapped_unit_is_null_with_source_never_a_default(word: object) -> None:
    assert unit_code(word) is None
    assert product_unit(word) == {"unit": None, "unit_source": word}


def test_a_code_outside_the_approved_set_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(translate.UNIT_TABLE, "Can", "CAN")
    assert unit_code("Can") is None
    assert product_unit("Can") == {"unit": None, "unit_source": "Can"}
