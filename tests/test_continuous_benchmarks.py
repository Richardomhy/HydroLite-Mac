import pandas as pd
from hydrolite.continuous_benchmarks import build_persistence_benchmark

def test_persistence_has_no_initial_nan():
    assert build_persistence_benchmark(pd.DataFrame({"date":["2020-01-01","2020-01-02"],"streamflow_cms":[1.,2.]})).notna().all()
