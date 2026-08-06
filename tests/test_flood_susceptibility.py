from hydrolite.flood_susceptibility import train_adaptive, train_baselines


def test_supervised_baselines_and_optional_rl(tmp_path):
    assert train_baselines("demo",tmp_path)["status"]=="passed"
    result=train_adaptive("demo",tmp_path)
    assert result["status"]=="passed"
    assert result["rl_executed"] is False
