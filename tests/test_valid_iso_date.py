"""Tests for _valid_iso_date() in __init__.py (strict AAAA-MM-JJ validation).

No pytest-homeassistant-custom-component fixture needed: this targets a
pure validator function with no hass dependency.
"""
from __future__ import annotations

import pytest

import custom_components.recettes_express as rx

# Do NOT `import voluptuous as vol` separately here. __init__.py imports
# voluptuous (as its own module-level `vol`) *before* it imports
# homeassistant, and importing homeassistant installs a compatibility shim
# that replaces sys.modules["voluptuous"] with a different module/class
# from that point on (see the "install_as_voluptuous is shadowing an
# already-imported voluptuous" warning). That means the production code's
# `vol.Invalid` is bound to the PRE-shim class, while any `import
# voluptuous as vol` done afterwards - regardless of where, including in
# this test file - resolves to the POST-shim class. The two are different
# classes with the same name, so pytest.raises(vol.Invalid) would never
# catch the exception the production code actually raises. Pulling `vol`
# straight off the already-imported module avoids the mismatch entirely.
_valid_iso_date = rx._valid_iso_date
Invalid = rx.vol.Invalid


def test_accepts_a_valid_canonical_date():
    assert _valid_iso_date("2026-10-16") == "2026-10-16"


def test_rejects_a_non_string():
    with pytest.raises(Invalid):
        _valid_iso_date(20261016)


def test_rejects_an_impossible_calendar_date():
    with pytest.raises(Invalid):
        _valid_iso_date("2026-99-99")


def test_rejects_free_text():
    with pytest.raises(Invalid):
        _valid_iso_date("not a date")


def test_rejects_compact_iso_format_without_dashes():
    # date.fromisoformat() accepts "YYYYMMDD" (no separators) since
    # Python 3.11. Stored as-is, this breaks the string-comparison-based
    # expiration filter against "YYYY-MM-DD" dates. Must be rejected.
    with pytest.raises(Invalid):
        _valid_iso_date("20261016")


def test_rejects_iso_week_date_format():
    # Also accepted by fromisoformat() since Python 3.11, also not
    # AAAA-MM-JJ.
    with pytest.raises(Invalid):
        _valid_iso_date("2026-W42-5")


def test_accepted_value_round_trips_through_isoformat_unchanged():
    # Canonical form must be returned completely unchanged (no
    # reformatting side effect), since callers compare it as a string.
    value = "2026-01-05"
    assert _valid_iso_date(value) is value or _valid_iso_date(value) == value
