from pathlib import Path

import pandas as pd

from hydrolite.drought_monitoring import assess_current_meteorological_drought, calculate_current_composite_status, write_current_drought_status


def test_current_drought_records_freshness(tmp_path: Path):
    component=assess_current_meteorological_drought(pd.Series([-1.2]))
    result=calculate_current_composite_status([component])
    result.update({"analysis_date":"2025-02-01","latest_observation_date":"2025-01-01","components":[component],"maximum_latency_days":7})
    paths=write_current_drought_status(tmp_path,result)
    assert paths["json"].exists()
    assert "stale_data" in paths["json"].read_text()
