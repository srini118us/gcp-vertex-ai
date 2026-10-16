import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

AS_OF = "2026-10-14"


class FakeBigQuery:
    """Records each query and returns canned rows, or raises a given error."""

    def __init__(self, rows=None, error: Exception | None = None):
        self.rows, self.error, self.calls = rows or [], error, []

    def query(self, sql, job_config=None):
        self.calls.append((sql, [p.to_api_repr() for p in job_config.query_parameters]))
        if self.error:
            raise self.error
        rows = self.rows
        return type("Job", (), {"result": lambda self: [dict(r) for r in rows]})()


T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)

def row(item_id=1, lag_h=10, avg_lag_h=10.0, transit_h=50, avg_transit_h=50.0,
        shipped=True, delivered=True, status=None, dc="Savannah GA", dc_id=1):
    """One query row as the SQL returns it. lag_h/transit_h are what TIMESTAMP_DIFF would yield."""
    return {"id": item_id, "status": status or ("Complete" if delivered else "Shipped" if shipped else "Processing"),
            "created_at": T0, "shipped_at": T0 if shipped else None, "delivered_at": T0 if (shipped and delivered) else None,
            "dc_id": dc_id, "dc": dc, "lag_h": lag_h if shipped else None,
            "transit_h": transit_h if (shipped and delivered) else None,
            "avg_lag_h": avg_lag_h, "avg_transit_h": avg_transit_h}


@pytest.fixture
def as_of(monkeypatch):
    monkeypatch.setenv("AS_OF_DATE", AS_OF)
    return AS_OF


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_CLOUD_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="cloud test: set RUN_CLOUD_TESTS=1 with ADC")
    for item in items:
        if "cloud" in item.keywords:
            item.add_marker(skip)
