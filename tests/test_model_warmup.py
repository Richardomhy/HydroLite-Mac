import pandas as pd

from hydrolite.model_warmup import calculate_required_warmup, create_warmup_forcing, repeat_climatology_warmup


def test_warmup_is_preceding_and_bounded():
    frame=pd.DataFrame({"date":pd.date_range("2020-01-01",periods=400),"value":range(400)})
    result=calculate_required_warmup({"warmup":{"days":365}},frame)
    warmup=create_warmup_forcing(frame,result["warmup_days"])
    assert len(warmup)==365
    assert warmup["date"].max()<frame["date"].max()
    assert len(repeat_climatology_warmup(frame.iloc[:365],2))==730
