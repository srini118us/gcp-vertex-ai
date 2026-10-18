"""Offline unit tests for the narrative guard and deterministic fallback."""
from logistics_claude.agent import (
    authoritative_codes, guard_narrative, render_fallback,
)

RESULT = {
    "order_id": 109778,
    "items": [
        {"item_id": 159064, "cause": "WAREHOUSE_DELAY", "dc": "Savannah, GA"},
        {"item_id": 159065, "cause": "TRANSIT_DELAY", "dc": "Los Angeles, CA"},
    ],
}


def test_authoritative_extracts_nested_codes():
    assert authoritative_codes(RESULT) == {"WAREHOUSE_DELAY", "TRANSIT_DELAY"}


def test_guard_passes_when_all_codes_present():
    text = "Item 159064 WAREHOUSE_DELAY and item 159065 TRANSIT_DELAY."
    ok, _ = guard_narrative(text, RESULT)
    assert ok


def test_guard_fails_on_missing_code():
    ok, reason = guard_narrative("Only WAREHOUSE_DELAY mentioned.", RESULT)
    assert not ok and "missing" in reason


def test_guard_fails_on_invented_code():
    text = "WAREHOUSE_DELAY TRANSIT_DELAY and also NOT_YET_SHIPPED."
    ok, reason = guard_narrative(text, RESULT)
    assert not ok and "invented" in reason


def test_guard_forces_fallback_on_error_result():
    ok, reason = guard_narrative("anything", {"order_id": 1, "error": "DATA_UNAVAILABLE"})
    assert not ok and "error" in reason


def test_fallback_contains_every_authoritative_code():
    text = render_fallback(109778, RESULT)
    assert "WAREHOUSE_DELAY" in text and "TRANSIT_DELAY" in text


def test_fallback_reports_sanitized_error():
    text = render_fallback(42, {"order_id": 42, "error": "ACCESS_DENIED"})
    assert "ACCESS_DENIED" in text
