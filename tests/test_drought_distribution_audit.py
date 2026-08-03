import pandas as pd
from hydrolite.drought_distribution_audit import audit_baseline_period

def test_twenty_year_record_is_limited():
    assert audit_baseline_period(pd.DataFrame({"date":["2000-01-01","2019-12-31"]}))["status"]=="limited_baseline_record"
