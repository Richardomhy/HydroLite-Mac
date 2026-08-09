from hydrolite.flood_susceptibility_models import assess_rl_suitability
from hydrolite.__main__ import main


def test_static_classification_does_not_justify_rl():
    result = assess_rl_suitability({})
    assert result["status"] == "rl_not_justified"
    assert result["rl_implemented"] is False
    assert result["rl_dependencies_required"] is False


def test_susceptibility_cli_status_and_rl_gate(capsys):
    assert main(["susceptibility", "status"]) == 0
    assert '"validation_level": "synthetic_spatial_demo"' in capsys.readouterr().out
    assert main(["susceptibility", "rl-readiness"]) == 0
    assert "rl_not_justified" in capsys.readouterr().out
