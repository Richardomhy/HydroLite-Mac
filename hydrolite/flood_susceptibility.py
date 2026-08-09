"""M6 static flood-susceptibility spatial modeling and XAI orchestration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import zipfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from hydrolite.flood_susceptibility_contracts import IMPLEMENTATION_NOTICE, SUSCEPTIBILITY_RISK_NOTICE, calculate_class_balance, classify_inventory_quality, default_factor_specs, validate_flood_inventory
from hydrolite.flood_susceptibility_evaluation import assess_spatial_stability, calculate_model_value_added, calculate_reliability_bins, evaluate_spatial_blocks, validate_susceptibility_risk_language
from hydrolite.flood_susceptibility_features import CATEGORICAL_FACTORS, CONDITIONING_FACTORS, detect_constant_factors, detect_high_correlation, detect_missing_factors, recommend_flood_susceptibility_datasets, validate_factor_coverage, write_factor_manifest
from hydrolite.flood_susceptibility_mapping import classify_relative_susceptibility, validate_susceptibility_map, write_susceptibility_geojson, write_susceptibility_raster_if_available
from hydrolite.flood_susceptibility_models import assess_rl_suitability, evaluate_candidates, fit_supervised_models, select_susceptibility_model
from hydrolite.flood_xai import feature_importance_stability, local_perturbation_explanation, partial_dependence, permutation_importance, select_local_explanation_cases, validate_xai_causality_claim, xai_status
from hydrolite.spatial_validation import build_leakage_audit, calculate_spatial_separation, split_spatial_train_validation_test, validate_spatial_blocks


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DIR = ROOT / "data_demo" / "method_inspiration" / "flood_susceptibility"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "method_inspiration" / "flood_susceptibility"
SYNTHETIC_NOTICE = "SYNTHETIC DEMO: software-method validation only; not real-project validation."


def _logistic(values: np.ndarray) -> np.ndarray: return 1 / (1 + np.exp(-np.clip(values, -30, 30)))


def _write_geojson_blocks(block_rows: list[dict[str, Any]], path: Path) -> Path:
    features = []
    for row in block_rows:
        left, bottom, right, top = row["extent"]
        features.append({"type": "Feature", "properties": {key: value for key, value in row.items() if key != "extent"}, "geometry": {"type": "Polygon", "coordinates": [[[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]]}})
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8"); return path


def generate_synthetic_susceptibility_demo(demo_dir: str | Path = DEFAULT_DEMO_DIR, seed: int = 20260809, points_per_block: int = 100) -> dict[str, Any]:
    root = Path(demo_dir); root.mkdir(parents=True, exist_ok=True); rng = np.random.default_rng(seed); rows = []; factor_rows = []; block_rows = []
    for block_index in range(24):
        column, row_index = block_index % 8, block_index // 8; center_lon, center_lat = 113.0 + column * .15, 22.0 + row_index * .15; block_id = f"B{block_index:02d}"; block_effect = rng.normal(0, .35)
        left, right, bottom, top = center_lon - .04, center_lon + .04, center_lat - .04, center_lat + .04
        block_rows.append({"block_id": block_id, "block_index": block_index, "extent": [left, bottom, right, top], "synthetic_demo": True})
        longitude = rng.uniform(left, right, points_per_block); latitude = rng.uniform(bottom, top, points_per_block); local_x = (longitude - center_lon) / .04; local_y = (latitude - center_lat) / .04
        elevation = 80 + 180 * (latitude - 22.0) + 35 * np.sin(column / 2) + rng.normal(0, 12, points_per_block)
        slope = np.clip(4 + 11 * np.abs(local_y) + rng.gamma(2, 1.2, points_per_block), 0, 45); aspect = rng.uniform(0, 360, points_per_block)
        plan_curvature = rng.normal(0, .3, points_per_block); profile_curvature = .5 * plan_curvature + rng.normal(0, .25, points_per_block)
        distance_stream = rng.gamma(2.2, 130, points_per_block); flow_accumulation = np.exp(np.clip(6.2 - distance_stream / 260 + rng.normal(0, .5, points_per_block), 0, 9)); twi = np.log1p(flow_accumulation / np.maximum(slope, .2))
        distance_road = rng.gamma(2, 180, points_per_block); distance_settlement = rng.gamma(2, 230, points_per_block)
        land_cover = rng.choice(["forest", "cropland", "urban", "water", "grass"], points_per_block, p=[.28, .30, .22, .05, .15]); soil = rng.choice(["clay", "loam", "sand", "silt"], points_per_block)
        ndvi = np.clip(np.where(land_cover == "forest", .75, np.where(land_cover == "urban", .18, .48)) + rng.normal(0, .08, points_per_block), -.2, .95)
        impervious = np.clip(np.where(land_cover == "urban", .72, .12) + rng.normal(0, .08, points_per_block), 0, 1)
        rainfall = np.clip(65 + 22 * row_index + 12 * np.sin(local_x * np.pi) + rng.normal(0, 12, points_per_block), 10, 180); antecedent = np.clip(.68 * rainfall + rng.normal(0, 10, points_per_block), 0, 150)
        soil_moisture = np.clip(.18 + .0025 * antecedent + np.where(soil == "clay", .08, 0) + rng.normal(0, .04, points_per_block), .05, .85)
        runoff = np.clip(.13 * rainfall + 13 * impervious + 7 * soil_moisture + rng.normal(0, 3, points_per_block), 0, 70)
        score = -3.1 + .022 * (rainfall - 65) + .055 * runoff + .24 * (twi - np.mean(twi)) - .0018 * distance_stream + .9 * impervious + .32 * np.sin(np.radians(aspect)) + .35 * (rainfall > 100) * (impervious > .5) + block_effect + rng.normal(0, .95, points_per_block)
        probability = _logistic(score); label = rng.binomial(1, probability)
        for point_index in range(points_per_block):
            point_id = f"P{block_index:02d}_{point_index:03d}"; flooded = int(label[point_index]); random_value = rng.random()
            inventory_type = "observed_flood" if flooded else "pseudo_absence" if random_value < .35 else "verified_non_flood" if random_value < .55 else "background_sample"
            event_id = f"EV_{block_id}_{point_index % 5}" if flooded else f"BG_{block_id}_{point_index:03d}"
            rows.append({"point_id": point_id, "event_id": event_id, "timestamp": f"2024-{1 + point_index % 9:02d}-{1 + point_index % 27:02d}", "label": flooded, "longitude": longitude[point_index], "latitude": latitude[point_index], "inventory_type": inventory_type, "verification_status": "synthetic_known_label", "source": "synthetic_generator", "source_confidence": "synthetic", "provenance": "seeded_clean_room_generator", "block_id": block_id, "synthetic_demo": True})
            values = {"elevation": elevation[point_index], "slope": slope[point_index], "aspect": aspect[point_index], "plan_curvature": plan_curvature[point_index], "profile_curvature": profile_curvature[point_index], "TWI": twi[point_index], "flow_accumulation": flow_accumulation[point_index], "distance_to_stream": distance_stream[point_index], "distance_to_road": distance_road[point_index], "distance_to_settlement": distance_settlement[point_index], "land_cover": land_cover[point_index], "NDVI": ndvi[point_index], "soil": soil[point_index], "imperviousness": impervious[point_index], "rainfall_extreme": rainfall[point_index], "antecedent_rainfall": antecedent[point_index], "soil_moisture": soil_moisture[point_index], "surface_runoff": runoff[point_index]}
            factor_rows.append({"point_id": point_id, **values, "synthetic_demo": True})
    inventory = pd.DataFrame(rows); factors = pd.DataFrame(factor_rows); inventory.to_csv(root / "flood_inventory.csv", index=False); factors.to_csv(root / "conditioning_factors.csv", index=False); _write_geojson_blocks(block_rows, root / "spatial_blocks.geojson")
    metadata = {"synthetic_demo": True, "factor_specs": [spec.as_dict() for spec in default_factor_specs().values()], "high_correlation_threshold": .80}; (root / "factor_metadata.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True), encoding="utf-8")
    config = {"synthetic_demo": True, "validation_mode": "spatial_block_cv", "train_blocks": [f"B{i:02d}" for i in range(16)], "validation_blocks": [f"B{i:02d}" for i in range(16, 20)], "test_blocks": [f"B{i:02d}" for i in range(20, 24)], "minimum_neighbor_distance": .02, "correlation_threshold": .80, "class_weight": "balanced", "calibration_methods": ["uncalibrated", "sigmoid", "isotonic"], "notice": SYNTHETIC_NOTICE}; (root / "susceptibility_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    checksums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file() and path.name not in {"generation_manifest.json", "expected_results.json"}}
    balance = calculate_class_balance(inventory); manifest = {"synthetic_demo": True, "seed": seed, "point_count": len(inventory), "spatial_block_count": 24, "factor_count": len(CONDITIONING_FACTORS), "spatial_pattern": "clustered blocks with gaps, nonlinear gradients, heterogeneity, and class imbalance", "class_balance": balance, "label_logic": "seeded stochastic nonlinear synthetic probability", "checksums": checksums, "notice": SYNTHETIC_NOTICE}
    (root / "generation_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"); (root / "expected_results.json").write_text(json.dumps({"status": "passed", "selected_model_not_predefined": True, "complex_model_may_not_add_value": True, "rl_expected": "rl_not_justified", "real_data_value_added": "not_tested"}, indent=2), encoding="utf-8")
    return {"status": "passed", "demo_dir": str(root), **manifest}


def load_susceptibility_demo(demo_dir: str | Path = DEFAULT_DEMO_DIR) -> dict[str, Any]:
    root = Path(demo_dir)
    if not (root / "flood_inventory.csv").exists(): generate_synthetic_susceptibility_demo(root)
    inventory = pd.read_csv(root / "flood_inventory.csv"); factors = pd.read_csv(root / "conditioning_factors.csv"); config = yaml.safe_load((root / "susceptibility_config.yaml").read_text(encoding="utf-8"))
    return {"root": root, "inventory": inventory, "factors": factors, "config": config, "table": inventory.merge(factors, on="point_id", validate="one_to_one", suffixes=("", "_factor"))}


def _write_charts(root: Path, table: pd.DataFrame, model_metrics: pd.DataFrame, calibration: pd.DataFrame, block_metrics: pd.DataFrame, predictions: pd.DataFrame, importance: pd.DataFrame, stability: pd.DataFrame, local: pd.DataFrame) -> list[Path]:
    charts = root / "charts"; charts.mkdir(parents=True, exist_ok=True); paths = []
    def save(name: str, title: str): plt.title(title + "\nSYNTHETIC DEMO"); plt.tight_layout(); path = charts / name; plt.savefig(path, dpi=140); plt.close(); paths.append(path)
    plt.figure(figsize=(8, 5)); plt.scatter(table.longitude, table.latitude, c=table.label, s=7, cmap="coolwarm"); plt.xlabel("Longitude"); plt.ylabel("Latitude"); save("inventory_distribution.png", "Flood inventory distribution")
    plt.figure(figsize=(5, 4)); table.label.value_counts().sort_index().plot(kind="bar"); plt.xticks([0, 1], ["background", "flood"], rotation=0); save("class_balance.png", "Class balance")
    plt.figure(figsize=(8, 5)); plt.scatter(table.longitude, table.latitude, c=pd.Categorical(table.block_id).codes, s=7, cmap="tab20"); plt.xlabel("Longitude"); plt.ylabel("Latitude"); save("spatial_blocks.png", "Spatial validation blocks")
    test = model_metrics[model_metrics.split == "test"].set_index("model_id")[["ROC_AUC", "PR_AUC"]]; plt.figure(figsize=(8, 4)); test.plot(kind="bar", ax=plt.gca()); plt.ylim(0, 1); save("roc_pr_comparison.png", "ROC-AUC and PR-AUC")
    selected_cal = calibration[calibration.selected].copy(); plt.figure(figsize=(7, 4)); plt.scatter(selected_cal.model_id, selected_cal.Brier); plt.ylabel("Validation Brier score"); plt.xticks(rotation=20); save("calibration_curve.png", "Selected calibration comparison")
    plt.figure(figsize=(8, 4)); block_metrics.plot(x="block_id", y="PR_AUC", kind="bar", ax=plt.gca(), legend=False); plt.ylim(0, 1); plt.ylabel("PR-AUC"); save("block_performance.png", "Independent test-block performance")
    plt.figure(figsize=(8, 5)); plt.scatter(predictions.longitude, predictions.latitude, c=predictions.probability, s=8, cmap="viridis", vmin=0, vmax=1); plt.colorbar(label="Susceptibility probability"); save("susceptibility_map.png", "Relative flood susceptibility, not flood risk")
    plt.figure(figsize=(8, 5)); importance.head(12).sort_values("importance").plot(x="factor_id", y="importance", kind="barh", ax=plt.gca(), legend=False); save("global_feature_importance.png", "Global permutation importance, association only")
    plt.figure(figsize=(8, 5)); stability.head(12).sort_values("importance_std").plot(x="factor_id", y="importance_std", kind="barh", ax=plt.gca(), legend=False); save("feature_stability.png", "Feature-importance variability")
    plt.figure(figsize=(7, 4)); local.plot(x="case_type", y=["base_probability", "prediction"], kind="bar", ax=plt.gca()); plt.ylim(0, 1); plt.xticks(rotation=20); save("local_explanations.png", "Local perturbation examples, association only")
    return paths


def run_flood_susceptibility_demo(demo_dir: str | Path = DEFAULT_DEMO_DIR, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    inputs = load_susceptibility_demo(demo_dir); table = inputs["table"].copy(); config = inputs["config"]; root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    inventory_validation = validate_flood_inventory(inputs["inventory"]); inventory_quality = classify_inventory_quality(inputs["inventory"]); factor_validation = validate_factor_coverage(inputs["factors"])
    split, split_manifest = split_spatial_train_validation_test(table); spatial_validation = validate_spatial_blocks(split, split_manifest); separation = calculate_spatial_separation(split)
    train = split[split.split == "train"]; validation = split[split.split == "validation"]; test = split[split.split == "test"]
    models = fit_supervised_models(train, CONDITIONING_FACTORS, CATEGORICAL_FACTORS); model_metrics, artifacts, calibrators, calibration_metrics = evaluate_candidates(models, validation, test, CONDITIONING_FACTORS)
    validation_block_parts = []
    for model_id, artifact in artifacts.items():
        frame = validation[["block_id", "split", "label"]].copy(); frame["probability"] = artifact["validation_probability"]; item = evaluate_spatial_blocks(frame, threshold=artifact["threshold"]["threshold"]); item["model_id"] = model_id; validation_block_parts.append(item)
    validation_blocks = pd.concat(validation_block_parts, ignore_index=True); selection = select_susceptibility_model(model_metrics, validation_blocks); selected_id = selection["selected_model"]; selected_model = models[selected_id]; selected_artifact = artifacts[selected_id]; selected_calibrator = calibrators[selected_id]; selected_threshold = selected_artifact["threshold"]["threshold"]
    all_probability = selected_calibrator.predict(selected_model.predict_proba(split[CONDITIONING_FACTORS])); predictions = split[["point_id", "event_id", "longitude", "latitude", "block_id", "split", "label", "synthetic_demo"]].copy(); predictions["probability"] = all_probability; predictions["relative_susceptibility_class"] = classify_relative_susceptibility(all_probability).astype(str); predictions["selected_model"] = selected_id; predictions["is_flood_risk"] = False
    test_predictions = predictions[predictions.split == "test"]; block_metrics = evaluate_spatial_blocks(test_predictions, threshold=selected_threshold); spatial_stability = assess_spatial_stability(block_metrics)
    selection_manifest = {**selection, "selected_threshold": selected_threshold, "calibration_method": selected_calibrator.method}; leakage = build_leakage_audit(split, selected_model.preprocessing_manifest, selection_manifest, config["minimum_neighbor_distance"])
    importance_parts = []
    for model_id in ("logistic_regression", "random_forest", "gradient_boosting"):
        item = permutation_importance(models[model_id], test, test.label, CONDITIONING_FACTORS); item["model_id"] = model_id; item["replicate"] = f"model:{model_id}"; importance_parts.append(item)
    for block, group in test.groupby("block_id"):
        item = permutation_importance(selected_model, group, group.label, CONDITIONING_FACTORS); item["model_id"] = selected_id; item["replicate"] = f"block:{block}"; importance_parts.append(item)
    importance_all = pd.concat(importance_parts, ignore_index=True); global_importance = importance_all[importance_all.model_id == selected_id].groupby("factor_id", as_index=False).importance.mean().sort_values("importance", ascending=False); global_importance["interpretation"] = "association_not_causal_effect"
    stability_table, importance_stability = feature_importance_stability(importance_all); pdp = partial_dependence(selected_model, test, CONDITIONING_FACTORS)
    local_source = test.copy(); local_source["probability"] = selected_artifact["test_probability"]; cases = select_local_explanation_cases(local_source, "probability", selected_threshold); reference = {factor: (train[factor].median() if factor not in CATEGORICAL_FACTORS else train[factor].mode().iloc[0]) for factor in CONDITIONING_FACTORS}
    local_rows = []
    for case_type, row in cases.items():
        explanation = local_perturbation_explanation(selected_model, row, reference, CONDITIONING_FACTORS, case_type=case_type, block_id=row.block_id, uncertainty=float(spatial_stability["metric_variance"])); explanation.update({"point_id": row.point_id, "model": selected_id, "observed_label": int(row.label)}); local_rows.append(explanation)
    local_explanations = pd.DataFrame(local_rows); xai = xai_status(); xai_gate = validate_xai_causality_claim("Feature importance is association, not causal effect."); rl = assess_rl_suitability({})
    value_added = calculate_model_value_added(model_metrics); supervised_status = "demonstrated" if value_added[value_added.model_id != "prevalence_baseline"].value_added.eq("demonstrated").any() else "not_demonstrated"; complex_status = "demonstrated" if value_added[value_added.model_id.isin(["random_forest", "gradient_boosting"])].complex_vs_logistic.eq("demonstrated").any() else "not_demonstrated"
    data_quality = root / "data_quality"; data_quality.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(data_quality / "inventory_qc.xlsx") as writer: pd.DataFrame([inventory_validation]).to_excel(writer, sheet_name="overview", index=False); inputs["inventory"].to_excel(writer, sheet_name="inventory", index=False)
    write_factor_manifest(inputs["factors"], data_quality, config["correlation_threshold"]); pd.DataFrame([calculate_class_balance(inputs["inventory"])]).to_excel(data_quality / "class_balance.xlsx", index=False)
    spatial_dir = root / "spatial_validation"; spatial_dir.mkdir(parents=True, exist_ok=True); block_geojson_rows = separation.to_dict(orient="records"); _write_geojson_blocks(block_geojson_rows, spatial_dir / "spatial_blocks.geojson"); (spatial_dir / "split_manifest.json").write_text(json.dumps(split_manifest, indent=2), encoding="utf-8"); block_metrics.to_excel(spatial_dir / "block_metrics.xlsx", index=False); (spatial_dir / "leakage_audit.json").write_text(json.dumps(leakage, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    model_dir = root / "models"; model_dir.mkdir(parents=True, exist_ok=True); model_metrics.to_excel(model_dir / "model_metrics.xlsx", index=False); calibration_metrics.to_excel(model_dir / "calibration_metrics.xlsx", index=False)
    with pd.ExcelWriter(model_dir / "model_selection.xlsx") as writer:
        pd.DataFrame([selection_manifest]).to_excel(writer, sheet_name="selection", index=False)
        model_metrics[model_metrics.split == "validation"].to_excel(writer, sheet_name="validation_metrics", index=False)
    model_metrics[["model_id", "split", "threshold", "true_negative", "false_positive", "false_negative", "true_positive"]].to_excel(model_dir / "confusion_matrix.xlsx", index=False); value_added.to_excel(model_dir / "model_value_added.xlsx", index=False)
    mapping_dir = root / "mapping"; mapping_dir.mkdir(parents=True, exist_ok=True); predictions.to_csv(mapping_dir / "susceptibility_predictions.csv", index=False); geojson = write_susceptibility_geojson(predictions, mapping_dir / "susceptibility_map.geojson"); raster = write_susceptibility_raster_if_available(predictions, mapping_dir / "susceptibility_map.tif"); map_validation = validate_susceptibility_map(predictions)
    if raster.get("path"):
        raster["path"] = str(Path(raster["path"]).relative_to(root))
    xai_dir = root / "xai"; xai_dir.mkdir(parents=True, exist_ok=True); global_importance.to_excel(xai_dir / "global_importance.xlsx", index=False); local_explanations.to_excel(xai_dir / "local_explanations.xlsx", index=False); stability_table.to_excel(xai_dir / "importance_stability.xlsx", index=False); pdp.to_excel(xai_dir / "partial_dependence.xlsx", index=False)
    reliability = calculate_reliability_bins(test.label, selected_artifact["test_probability"]); reliability.to_excel(model_dir / "reliability_bins.xlsx", index=False)
    charts = _write_charts(root, split, model_metrics, calibration_metrics, block_metrics, predictions, global_importance, stability_table, local_explanations)
    reports = root / "reports"; reports.mkdir(parents=True, exist_ok=True); selected_test = model_metrics[(model_metrics.model_id == selected_id) & (model_metrics.split == "test")].iloc[0].to_dict(); risk_gate = validate_susceptibility_risk_language(SUSCEPTIBILITY_RISK_NOTICE)
    value_by_model = value_added.set_index("model_id").value_added.to_dict()
    manifest = {"status": "passed" if all(item["status"] == "passed" for item in (inventory_validation, factor_validation, spatial_validation, leakage, map_validation, xai_gate, risk_gate)) else "failed", "capability": "flood_susceptibility", "capability_status": "partial", "xai_capability_status": "partial", "validation_level": "synthetic_spatial_demo", "synthetic_demo": True, "notice": SYNTHETIC_NOTICE, "method_notice": IMPLEMENTATION_NOTICE, "risk_notice": SUSCEPTIBILITY_RISK_NOTICE, "inventory": calculate_class_balance(inputs["inventory"]), "factor_count": len(CONDITIONING_FACTORS), "spatial_blocks": split.block_id.nunique(), "blocks_by_split": spatial_validation["blocks_by_split"], "spatial_validation_status": leakage["status"], "leakage_audit": leakage, "selected_model": selected_id, "selection": selection_manifest, "selected_test_metrics": selected_test, "spatial_stability": spatial_stability, "map_validation": map_validation, "geojson_status": "passed", "raster_status": raster, "relative_susceptibility_classes": list(predictions.relative_susceptibility_class.value_counts().index), "xai": xai, "xai_readiness": "available_with_fallback" if xai["status"] != "shap_available" else "available_with_shap", "xai_causality_gate": xai_gate, "top_factors": global_importance.head(10).to_dict(orient="records"), "importance_stability": importance_stability, "local_case_types": local_explanations.case_type.tolist(), "rl_suitability": rl, "logistic_value_added": value_by_model.get("logistic_regression"), "random_forest_value_added": value_by_model.get("random_forest"), "gradient_boosting_value_added": value_by_model.get("gradient_boosting"), "supervised_model_value_added": supervised_status, "complex_model_value_added": complex_status, "model_value_added": value_added.to_dict(orient="records"), "real_data_value_added": "not_tested", "charts": [str(path.relative_to(root)) for path in charts], "gee_recommendation": recommend_flood_susceptibility_datasets(), "generated_at": pd.Timestamp.now(tz="UTC").isoformat()}
    zh = f"""# HydroLite 洪水易发性空间实验报告\n\n> {IMPLEMENTATION_NOTICE}\n\n> {SYNTHETIC_NOTICE}\n\n> 易发性不等于风险。风险还需要危险强度、暴露度、脆弱性和后果，本阶段不计算这些内容。\n\n## 方法\n\n洪水清单 QC → 条件因子 → 空间 block train/validation/test → 监督基线 → validation 校准和阈值 → 独立 test block 评价 → 相对易发性图 → 非因果 XAI。随机划分只允许诊断，pseudo-absence 不等于确认非洪水。\n\n## 结果边界\n\n- 选定模型：`{selected_id}`\n- 空间稳定性：`{spatial_stability['status']}`\n- RL 适用性：`{rl['status']}`；本阶段未实现 RL。\n- SHAP：`{xai['status']}`；使用 permutation/PDP/local perturbation fallback。\n"""
    en = f"""# HydroLite Spatial Flood-susceptibility Experiment\n\n> {IMPLEMENTATION_NOTICE}\n\n> {SYNTHETIC_NOTICE}\n\nFlood susceptibility is not flood risk. The workflow uses spatially independent blocks, supervised probability baselines, validation-only calibration/threshold/model selection, relative susceptibility mapping, and association-oriented XAI. RL is not implemented and is `{rl['status']}` for this static classification demo.\n"""
    (reports / "flood_susceptibility_report_zh.md").write_text(zh, encoding="utf-8"); (reports / "flood_susceptibility_report_en.md").write_text(en, encoding="utf-8"); (reports / "flood_susceptibility_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    bundle = reports / "flood_susceptibility_bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path != bundle and path.suffix.lower() not in {".zip", ".pt", ".pth", ".ckpt", ".onnx", ".dss", ".hdf5", ".h5"}: archive.write(path, path.relative_to(root))
    manifest["output_dir"] = str(root); manifest["bundle"] = str(bundle); return manifest


def validate_outputs(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    root = Path(output_dir); required = [root / "data_quality/inventory_qc.xlsx", root / "data_quality/factor_qc.xlsx", root / "spatial_validation/leakage_audit.json", root / "models/model_metrics.xlsx", root / "models/model_selection.xlsx", root / "mapping/susceptibility_predictions.csv", root / "mapping/susceptibility_map.geojson", root / "xai/global_importance.xlsx", root / "xai/local_explanations.xlsx", root / "reports/flood_susceptibility_manifest.json"]
    missing = [str(path) for path in required if not path.exists() or path.stat().st_size == 0]; manifest = json.loads((root / "reports/flood_susceptibility_manifest.json").read_text(encoding="utf-8")) if not missing else {}
    return {"status": "passed" if not missing and manifest.get("status") == "passed" else "failed", "missing": missing, "validation_level": manifest.get("validation_level")}


def run_susceptibility_command(command: str, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Run one CLI view of the shared M6 pipeline without duplicating modeling logic."""
    root = Path(output_dir)
    if command == "status":
        return {
            "status": "partial",
            "validation_level": "synthetic_spatial_demo",
            "supervised_models": "implemented",
            "spatial_validation": "implemented",
            "xai": "implemented_with_optional_shap_fallback",
            "rl": "not_implemented",
            "risk_model": False,
        }
    if command == "demo":
        generate_synthetic_susceptibility_demo()
        result = run_flood_susceptibility_demo(output_dir=root)
    elif not (root / "reports/flood_susceptibility_manifest.json").exists():
        result = run_flood_susceptibility_demo(output_dir=root)
    else:
        result = json.loads((root / "reports/flood_susceptibility_manifest.json").read_text(encoding="utf-8"))
        result.update({"output_dir": str(root), "bundle": str(root / "reports/flood_susceptibility_bundle.zip")})
    views: dict[str, dict[str, Any]] = {
        "qc": {"status": result["status"], "inventory": result["inventory"], "file": str(root / "data_quality/inventory_qc.xlsx")},
        "factors": {"status": result["status"], "factor_count": result["factor_count"], "file": str(root / "data_quality/factor_qc.xlsx")},
        "split": {"status": result["leakage_audit"]["status"], "blocks_by_split": result["blocks_by_split"], "file": str(root / "spatial_validation/split_manifest.json")},
        "train": {"status": result["status"], "selected_model": result["selected_model"], "file": str(root / "models/model_metrics.xlsx")},
        "calibrate": {"status": result["status"], "method": result["selection"]["calibration_method"], "file": str(root / "models/calibration_metrics.xlsx")},
        "evaluate": {"status": result["status"], "test_metrics": result["selected_test_metrics"], "spatial_stability": result["spatial_stability"]},
        "map": {"status": result["map_validation"]["status"], "risk_model": False, "geojson": str(root / "mapping/susceptibility_map.geojson"), "raster": result["raster_status"]},
        "explain": {"status": "passed", "xai": result["xai"], "top_factors": result["top_factors"], "causal_interpretation": False},
        "rl-readiness": {"status": result["rl_suitability"]["status"], **result["rl_suitability"]},
        "validate": validate_outputs(root),
        "report": {"status": "passed", "report_zh": str(root / "reports/flood_susceptibility_report_zh.md"), "report_en": str(root / "reports/flood_susceptibility_report_en.md")},
        "bundle": {"status": "passed", "bundle": str(root / "reports/flood_susceptibility_bundle.zip")},
        "demo": result,
    }
    if command not in views:
        raise ValueError(f"Unknown susceptibility command: {command}")
    return views[command]


def readiness(workspace: Any = DEFAULT_DEMO_DIR) -> dict[str, Any]:
    return {"status": "synthetic_demo_ready", "workspace": str(workspace), "required_factors": CONDITIONING_FACTORS, "spatial_validation": "spatial_block_cv", "random_split": "diagnostic_only", "risk_model": False}


def train_baselines(workspace: Any, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    result = run_flood_susceptibility_demo(output_dir=output_dir); return {"status": result["status"], "selected_model": result["selected_model"], "metrics": pd.read_excel(Path(output_dir) / "models/model_metrics.xlsx")}


def train_adaptive(workspace: Any, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    result = assess_rl_suitability({}); return {"status": "passed", "rl_status": result["status"], "rl_executed": False, "method_value_added": "not_demonstrated"}


def write_report(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    report = Path(output_dir) / "reports/flood_susceptibility_report_en.md"
    if not report.exists(): run_flood_susceptibility_demo(output_dir=output_dir)
    return {"status": "passed", "report": report}
