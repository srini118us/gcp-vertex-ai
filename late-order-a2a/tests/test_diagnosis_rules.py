"""Phase 1 rules, asserted as they are today (including the documented edge cases)."""
from datetime import date
import google.auth.exceptions
import pytest
from google.api_core import exceptions as gexc
from conftest import FakeBigQuery, row
from logistics_core import diagnosis as d

def diagnose(*rows, order_id=109778):
    return d.delay_root_cause(order_id, client=FakeBigQuery(list(rows)))

def causes(result):
    return [i["cause"] for i in result["items"]]


# --- the four causes and their precedence

def test_warehouse_delay(as_of):
    assert causes(diagnose(row(lag_h=40, avg_lag_h=13.3))) == ["WAREHOUSE_DELAY"]

def test_transit_delay(as_of):
    assert causes(diagnose(row(lag_h=10, avg_lag_h=13.1, transit_h=115, avg_transit_h=58.2))) == ["TRANSIT_DELAY"]

def test_not_yet_shipped(as_of):
    assert causes(diagnose(row(shipped=False))) == ["NOT_YET_SHIPPED"]

def test_within_normal(as_of):
    assert causes(diagnose(row(lag_h=12, avg_lag_h=13.0, transit_h=60, avg_transit_h=58.0))) == ["WITHIN_NORMAL"]

def test_one_cause_per_item_warehouse_wins_over_transit(as_of):
    assert causes(diagnose(row(lag_h=40, avg_lag_h=13.3, transit_h=115, avg_transit_h=56.8))) == ["WAREHOUSE_DELAY"]

def test_threshold_is_strictly_greater_than_1_5x(as_of):
    assert causes(diagnose(row(lag_h=15, avg_lag_h=10.0, transit_h=75, avg_transit_h=50.0))) == ["WITHIN_NORMAL"]
    assert causes(diagnose(row(lag_h=16, avg_lag_h=10.0))) == ["WAREHOUSE_DELAY"]


# --- multiple items: order preserved, one entry per item

def test_multiple_items_keep_query_order_and_fields(as_of):
    r = diagnose(row(item_id=159064, lag_h=40, avg_lag_h=13.333, transit_h=115, avg_transit_h=56.84, dc="Savannah GA"),
                 row(item_id=159065, lag_h=-6, avg_lag_h=13.1, transit_h=115, avg_transit_h=58.2, dc="Los Angeles CA"))
    assert r == {"order_id": 109778, "baseline_window": ["2026-07-16", "2026-10-14"], "items": [
        {"item_id": 159064, "status": "Complete", "distribution_center": "Savannah GA", "warehouse_lag_h": 40,
         "dc_avg_lag_h": 13.3, "transit_h": 115, "dc_avg_transit_h": 56.8, "cause": "WAREHOUSE_DELAY"},
        {"item_id": 159065, "status": "Complete", "distribution_center": "Los Angeles CA", "warehouse_lag_h": -6,
         "dc_avg_lag_h": 13.1, "transit_h": 115, "dc_avg_transit_h": 58.2, "cause": "TRANSIT_DELAY"}]}
    assert list(r) == ["order_id", "baseline_window", "items"]


# --- documented edge cases (current behavior, intentionally unchanged)

def test_missing_baseline_treated_as_zero(as_of):
    """No baseline rows for the DC: averages count as 0, so any positive duration is a delay."""
    r = diagnose(row(item_id=1, lag_h=5, avg_lag_h=None, avg_transit_h=None),
                 row(item_id=2, lag_h=0, transit_h=3, avg_lag_h=None, avg_transit_h=None),
                 row(item_id=3, lag_h=0, transit_h=0, avg_lag_h=None, avg_transit_h=None))
    assert causes(r) == ["WAREHOUSE_DELAY", "TRANSIT_DELAY", "WITHIN_NORMAL"]
    assert all(i["dc_avg_lag_h"] == 0 and i["dc_avg_transit_h"] == 0 for i in r["items"])

def test_negative_durations_pass_through_unflagged(as_of):
    r = diagnose(row(item_id=1, lag_h=-6, avg_lag_h=13.1, transit_h=-3, avg_transit_h=58.2))
    assert causes(r) == ["WITHIN_NORMAL"]
    assert (r["items"][0]["warehouse_lag_h"], r["items"][0]["transit_h"]) == (-6, -3)

def test_negative_lag_with_slow_transit_is_transit_delay(as_of):
    assert causes(diagnose(row(lag_h=-6, avg_lag_h=13.1, transit_h=115, avg_transit_h=58.2))) == ["TRANSIT_DELAY"]

def test_undelivered_shipment_only_checks_warehouse_lag(as_of):
    r = diagnose(row(item_id=1, lag_h=10, avg_lag_h=13.0, delivered=False),
                 row(item_id=2, lag_h=40, avg_lag_h=13.0, delivered=False))
    assert causes(r) == ["WITHIN_NORMAL", "WAREHOUSE_DELAY"]
    assert r["items"][0]["transit_h"] is None and r["items"][0]["status"] == "Shipped"

def test_not_shipped_wins_regardless_of_baseline(as_of):
    assert causes(diagnose(row(shipped=False, avg_lag_h=None, avg_transit_h=None))) == ["NOT_YET_SHIPPED"]


# --- order level results

def test_missing_order_is_order_not_found(as_of):
    assert diagnose(order_id=999999999) == {"order_id": 999999999, "cause": "ORDER_NOT_FOUND"}

def test_baseline_window_is_90_days_ending_as_of(as_of):
    assert d.baseline_window() == (date(2026, 7, 16), date(2026, 10, 14))
    assert d.baseline_window(date(2026, 1, 31)) == (date(2025, 11, 2), date(2026, 1, 31))

def test_query_parameters(as_of):
    bq = FakeBigQuery([])
    d.delay_root_cause(42, client=bq)
    (sql, params), = bq.calls
    assert sql == d.SQL and "@order_id" in sql
    assert [(p["name"], p["parameterType"]["type"], p["parameterValue"]["value"]) for p in params] == [
        ("order_id", "INT64", "42"), ("start", "STRING", "2026-07-16"), ("end", "STRING", "2026-10-14")]

def test_sql_reads_only_logistics_dataset():
    tables = {t.split("`")[0] for t in d.SQL.split("`enterprise-agent-labs-1012.")[1:]}
    assert tables == {"logistics_data.order_items", "logistics_data.inventory_items", "logistics_data.distribution_centers"}


# --- input validation

@pytest.mark.parametrize("value, expected", [(109778, 109778), ("109778", 109778), (" 7 ", 7),
                                             (109778.0, 109778), (2**63 - 1, 2**63 - 1)])
def test_valid_order_ids(value, expected):
    assert d.validate_order_id(value) == expected

@pytest.mark.parametrize("value", [0, -5, "-5", 2**63, True, False, None, 1.5, float("nan"), "abc", "",
                                   "12a", "1e5", "１２", [1], {"order_id": 1}])
def test_invalid_order_ids_raise_before_any_query(value, as_of):
    bq = FakeBigQuery([])
    with pytest.raises(d.InvalidOrderId) as e:
        d.delay_root_cause(value, client=bq)
    assert bq.calls == []
    assert isinstance(e.value, ValueError)
    assert str(e.value) == "INVALID_ORDER_ID: order_id must be a positive integer"


# --- failures surface as fixed, sanitized messages

LEAKY = ("Access Denied: Table enterprise-agent-labs-1012:logistics_data.order_items: User does not have permission "
         "to query table; principal logistics-agent@enterprise-agent-labs-1012.iam.gserviceaccount.com")

@pytest.mark.parametrize("error, kind, message", [
    (gexc.Forbidden(LEAKY), d.LogisticsDataAccessDenied, "ACCESS_DENIED: logistics data access denied"),
    (google.auth.exceptions.RefreshError(LEAKY), d.LogisticsDataAccessDenied, "ACCESS_DENIED: logistics data access denied"),
    (gexc.ServiceUnavailable(LEAKY), d.LogisticsDataUnavailable, "DATA_UNAVAILABLE: logistics data temporarily unavailable"),
    (gexc.BadRequest(LEAKY), d.LogisticsDataUnavailable, "DATA_UNAVAILABLE: logistics data temporarily unavailable"),
    (TimeoutError(LEAKY), d.LogisticsDataUnavailable, "DATA_UNAVAILABLE: logistics data temporarily unavailable"),
])
def test_bigquery_errors_are_sanitized(error, kind, message, as_of):
    with pytest.raises(kind) as e:
        d.delay_root_cause(109778, client=FakeBigQuery(error=error))
    assert str(e.value) == message and e.value.code in message
    assert "enterprise-agent-labs" not in str(e.value) and "@" not in str(e.value)
    assert e.value.__cause__ is error  # full error kept for server logs only
