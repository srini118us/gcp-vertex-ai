"""The extracted module must reproduce the Phase 1 function exactly: same SQL, parameters and output."""
import random
import pytest
from conftest import FakeBigQuery, row
from legacy import load_legacy
from logistics_core import diagnosis as d

@pytest.fixture(scope="module")
def legacy():
    return load_legacy()

def run_both(legacy, monkeypatch, order_id, rows):
    old_bq, new_bq = FakeBigQuery(rows), FakeBigQuery(rows)
    monkeypatch.setattr(legacy, "_client", lambda: old_bq)
    return legacy.delay_root_cause(order_id), d.delay_root_cause(order_id, client=new_bq), old_bq.calls, new_bq.calls

def random_row(rng, item_id):
    shipped = rng.random() > 0.15
    return row(item_id=item_id, shipped=shipped, delivered=rng.random() > 0.2,
               lag_h=rng.choice([rng.randint(-12, 120), 0, 15, 16]),
               transit_h=rng.choice([rng.randint(-5, 300), 0, 75, 76]),
               avg_lag_h=rng.choice([None, 0.0, 10.0, rng.uniform(0, 60)]),
               avg_transit_h=rng.choice([None, 0.0, 50.0, rng.uniform(0, 150)]),
               dc=rng.choice(["Savannah GA", "Los Angeles CA", "Memphis TN"]))

def test_sql_text_is_byte_identical(legacy, monkeypatch, as_of):
    _, _, old_calls, new_calls = run_both(legacy, monkeypatch, 109778, [])
    assert old_calls == new_calls  # same SQL string and same typed parameters

def test_not_found_identical(legacy, monkeypatch, as_of):
    old, new, *_ = run_both(legacy, monkeypatch, 999999999, [])
    assert old == new == {"order_id": 999999999, "cause": "ORDER_NOT_FOUND"}

@pytest.mark.parametrize("seed", range(300))
def test_random_orders_identical(legacy, monkeypatch, as_of, seed):
    rng = random.Random(seed)
    rows = [random_row(rng, 1000 + i) for i in range(rng.randint(1, 5))]
    old, new, old_calls, new_calls = run_both(legacy, monkeypatch, rng.randint(1, 200000), rows)
    assert old == new and old_calls == new_calls

def test_documented_behavior_differences(legacy, monkeypatch, as_of):
    """Malformed ids: legacy queried BigQuery (0 and -5 came back ORDER_NOT_FOUND); now rejected before any query."""
    monkeypatch.setattr(legacy, "_client", lambda: FakeBigQuery([]))
    for bad in (0, -5):
        assert legacy.delay_root_cause(bad) == {"order_id": bad, "cause": "ORDER_NOT_FOUND"}
        with pytest.raises(d.InvalidOrderId):
            d.delay_root_cause(bad, client=FakeBigQuery([]))
    old, new, *_ = run_both(legacy, monkeypatch, "109778", [])  # digit string: legacy echoed the string
    assert old["order_id"] == "109778" and new["order_id"] == 109778
