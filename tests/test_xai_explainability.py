from sklearn.ensemble import RandomForestClassifier
from hydrolite.flood_susceptibility_features import build_synthetic_flood_features, CONDITIONING_FACTORS
from hydrolite.xai_explainability import explain_model


def test_xai_uses_noncausal_fallback_when_shap_unavailable():
    frame=build_synthetic_flood_features(40); model=RandomForestClassifier(n_estimators=10,random_state=1).fit(frame[CONDITIONING_FACTORS],frame.flood); result=explain_model(model,frame[CONDITIONING_FACTORS],frame.flood)
    assert "importance" in result["global_importance"] and "causal" in result["global_importance"].interpretation.iloc[0]
