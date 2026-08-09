from hydrolite.flood_susceptibility import load_susceptibility_demo
from hydrolite.flood_susceptibility_features import CATEGORICAL_FACTORS, CONDITIONING_FACTORS
from hydrolite.flood_susceptibility_models import fit_supervised_models
from hydrolite.model_registry import list_models
from hydrolite.capability_registry import get_capability
from hydrolite.run_recipes import get_run_recipe
from hydrolite.workflow_engine import list_workflow_stages


def test_four_probability_baselines_and_train_only_preprocessing():
    frame = load_susceptibility_demo()["table"].iloc[:400].copy()
    models = fit_supervised_models(frame, CONDITIONING_FACTORS, CATEGORICAL_FACTORS)
    assert set(models) == {"prevalence_baseline", "logistic_regression", "random_forest", "gradient_boosting"}
    for model in models.values():
        probability = model.predict_proba(frame.iloc[:5])
        assert ((probability >= 0) & (probability <= 1)).all()
        assert model.preprocessing_manifest["fit_split"] == "train"


def test_experimental_model_registry_uses_independent_name():
    models = {item["model_id"]: item for item in list_models()}
    assert models["adaptive_flood_susceptibility_xai"]["status"] == "experimental"
    assert "RL-Stack" not in models
    assert get_capability("flood_susceptibility_xai")["status"] == "partial"
    stages = {item["stage_id"]: item for item in list_workflow_stages()}
    assert stages["flood_susceptibility"]["status"] == "partial"
    assert stages["flood_susceptibility_xai"]["status"] == "partial"
    assert get_run_recipe("flood_susceptibility_mapping")["validation_level"] == "synthetic_spatial_demo"
