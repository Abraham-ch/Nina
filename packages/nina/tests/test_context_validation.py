"""Validation of fire events against a point registry, on synthetic layers."""

from datetime import date, timedelta

import h3
import pandas as pd

from nina.io.context_validation import point_registry_events


def test_registry_records_are_matched_in_place_and_time_with_a_chance_baseline(tmp_path):
    context = tmp_path / "context"
    (context / "events").mkdir(parents=True)
    (context / "registries").mkdir()
    cell = h3.latlng_to_cell(40.0, -120.0, 7)
    far = h3.latlng_to_cell(45.0, -110.0, 7)
    start = date(2020, 8, 1)
    # One large event of 6 cell-days at `cell`, starting on the registered date.
    later = start + timedelta(days=400)  # a small unrelated event that extends the covered period
    events = pd.DataFrame([{"event_id": 1, "country": "Testland", "start_day": pd.Timestamp(start),
                            "end_day": pd.Timestamp(start + timedelta(days=5)), "cell_days": 6, "era": "viirs"},
                           {"event_id": 2, "country": "Testland", "start_day": pd.Timestamp(later),
                            "end_day": pd.Timestamp(later), "cell_days": 1, "era": "viirs"}])
    members = pd.DataFrame([{"event_id": 1, "cell": cell, "day": pd.Timestamp(start + timedelta(days=i))} for i in range(6)]
                           + [{"event_id": 2, "cell": far, "day": pd.Timestamp(later)}])
    events.to_parquet(context / "events/fire_events.parquet", index=False)
    members.to_parquet(context / "events/event_cell_days.parquet", index=False)
    registry = pd.DataFrame([
        {"record_id": "hit", "day": pd.Timestamp(start + timedelta(days=1)), "latitude": 40.0, "longitude": -120.0, "size_ha": 5000.0},
        {"record_id": "far", "day": pd.Timestamp(start), "latitude": 45.0, "longitude": -110.0, "size_ha": 5000.0},
        {"record_id": "late", "day": pd.Timestamp(start + timedelta(days=30)), "latitude": 40.0, "longitude": -120.0, "size_ha": 10.0},
    ])
    registry.to_parquet(context / "registries/test.parquet", index=False)
    assert far != cell
    result = point_registry_events(context, "Testland", "test", "Test registry")
    headline = result["headline"]
    assert headline["records"] == 2 and headline["rate"] == 0.5  # 'hit' matches, 'far' does not
    assert headline["chance_rate"] == 0.0  # nothing burned there one year earlier or later
    assert headline["records_all_sizes"] == 3 and headline["rate_all_sizes"] == round(1 / 3, 4)
    assert headline["registered_share"] == 1.0  # the single significant event has a registered record
    small = next(c for c in result["by_size"] if c["size_ha"] == [0, 40])
    assert small["records"] == 1 and small["rate"] == 0.0  # 'late' is outside the -2/+7 day window
