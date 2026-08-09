"""Synthetic truth, parameter recovery, and reporting for Gamma Lag Features."""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from pathlib import Path
from typing import Any, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from scipy.optimize import least_squares

from hydrolite.__version__ import __version__
from hydrolite.gamma_lag_features import (
    NOTICE,
    build_gamma_feature_series,
    build_gamma_kernel,
    build_multi_gamma_features,
    calculate_discrete_kernel_mean_lag,
    calculate_discrete_kernel_peak_lag,
    calculate_gamma_feature_manifest,
    calculate_gamma_mean_lag,
    calculate_gamma_peak_lag,
    convolve_causal_series,
    detect_gamma_future_leakage,
)
from hydrolite.metrics import calculate_all_metrics
from hydrolite.provenance import is_protected_path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "methods" / "gamma_lag_features.example.yaml"
DEFAULT_DEMO_ROOT = ROOT / "data_demo" / "method_inspiration" / "gamma"
DEFAULT_OUTPUT = ROOT / "output" / "method_inspiration" / "gamma"
DEMO_KINDS = ("single_kernel", "multi_kernel", "noise", "stress_test")
IDENTIFIABILITY_STATUSES = {"well_identified", "partially_identified", "equifinal_good_response", "weak_response", "boundary_limited"}


def _safe_root(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    if is_protected_path(target):
        raise ValueError(f"Protected path cannot receive Gamma outputs: {target}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_gamma_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def default_components() -> list[dict[str, Any]]:
    return [
        {"component_id": "quick", "shape": 1.6, "scale": 1.2, "support_length": 24, "weight": 0.55, "enabled": True},
        {"component_id": "intermediate", "shape": 3.0, "scale": 2.0, "support_length": 36, "weight": 0.30, "enabled": True},
        {"component_id": "slow", "shape": 5.0, "scale": 4.0, "support_length": 60, "weight": 0.15, "enabled": True},
    ]


def _rainfall(seed: int, length: int, stress: bool = False) -> np.ndarray:
    rng = np.random.default_rng(seed)
    wet = rng.random(length) < (0.28 if not stress else 0.38)
    rain = wet * rng.gamma(2.1, 5.0 if not stress else 8.0, length)
    for start, multiplier in ((22, 2.2), (73, 2.8), (121, 2.4)):
        rain[start : start + 3] *= multiplier
    return rain


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_synthetic_demo_data(demo_root: str | Path = DEFAULT_DEMO_ROOT, length: int = 180) -> dict[str, Path]:
    root = _safe_root(demo_root)
    outputs: dict[str, Path] = {}
    for index, kind in enumerate(DEMO_KINDS):
        folder = root / kind; folder.mkdir(parents=True, exist_ok=True)
        seed = 20260720 + index
        rain = _rainfall(seed, length, stress=kind == "stress_test")
        effective = rain * (0.68 if kind != "stress_test" else 0.75)
        dates = pd.date_range("2020-01-01", periods=length, freq="D")
        single = {"shape": 2.5, "scale": 2.0, "support_length": 40, "runoff_coefficient": 0.82}
        single_kernel = build_gamma_kernel(single["shape"], single["scale"], single["support_length"], 1.0)
        single_response = convolve_causal_series(effective, single_kernel) * single["runoff_coefficient"]
        multi = build_multi_gamma_features(effective, default_components(), 1.0)
        multi_response = multi["combined"].to_numpy()
        truth_type = "multi" if kind == "multi_kernel" else "single"
        clean = multi_response if truth_type == "multi" else single_response
        noise_std = float(np.std(clean) * 0.05) if kind == "noise" else 0.0
        observed = np.maximum(0.0, clean + np.random.default_rng(seed + 100).normal(0.0, noise_std, length))
        pd.DataFrame({"datetime": dates, "rainfall": rain}).to_csv(folder / "rainfall.csv", index=False)
        pd.DataFrame({"datetime": dates, "effective_rainfall": effective}).to_csv(folder / "effective_rainfall.csv", index=False)
        response = pd.DataFrame({"datetime": dates, "observed_response": observed, "clean_response": clean})
        for component in multi["features"]:
            response[f"{component}_response"] = multi["features"][component]
        response.to_csv(folder / "observed_response.csv", index=False)
        truth = {"synthetic_demo": True, "truth_type": truth_type, "single": single, "components": default_components(), "noise_std": noise_std}
        (folder / "truth_parameters.yaml").write_text(yaml.safe_dump(truth, sort_keys=False, allow_unicode=True), encoding="utf-8")
        demo_config = load_gamma_config()
        demo_config.update({"synthetic_demo": True, "demo_kind": kind})
        (folder / "gamma_config.yaml").write_text(yaml.safe_dump(demo_config, sort_keys=False, allow_unicode=True), encoding="utf-8")
        (folder / "expected_results.json").write_text(json.dumps({"synthetic_demo": True, "forward_nse_min": 0.999, "forward_kge_min": 0.995, "forward_abs_pbias_max": 0.1}, indent=2), encoding="utf-8")
        tracked_files = [folder / name for name in ("rainfall.csv", "effective_rainfall.csv", "observed_response.csv", "truth_parameters.yaml", "gamma_config.yaml", "expected_results.json")]
        manifest = {
            "synthetic_demo": True,
            "generator": "HydroLite Gamma Lag Features",
            "generator_version": "1",
            "hydrolite_version": __version__,
            "random_seed": seed,
            "date_range": [str(dates[0].date()), str(dates[-1].date())],
            "timestep": 1.0,
            "timestep_unit": "day",
            "truth_parameters": truth,
            "noise": {"standard_deviation": noise_std},
            "checksums": {path.name: _sha256(path) for path in tracked_files},
        }
        (folder / "generation_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        outputs[kind] = folder
    return outputs


def response_metrics(observed: Any, simulated: Any, timestep: float = 1.0) -> dict[str, Any]:
    obs = np.asarray(observed, dtype=float); sim = np.asarray(simulated, dtype=float)
    metrics = calculate_all_metrics(obs, sim)
    metrics.pop("warnings", None)
    obs_peak = int(np.argmax(obs)); sim_peak = int(np.argmax(sim))
    metrics.update({
        "peak_error": float(sim.max() - obs.max()),
        "peak_error_percent": float((sim.max() - obs.max()) / obs.max() * 100.0) if obs.max() else np.nan,
        "timing_error": float((sim_peak - obs_peak) * timestep),
        "volume_error": float((sim.sum() - obs.sum()) * timestep),
        "volume_error_percent": float((sim.sum() - obs.sum()) / obs.sum() * 100.0) if obs.sum() else np.nan,
    })
    return metrics


def classify_identifiability(response_nse: float, maximum_relative_parameter_error: float, *, weak_response: bool = False, boundary_hit: bool = False) -> str:
    if weak_response: return "weak_response"
    if boundary_hit: return "boundary_limited"
    if response_nse >= .995 and maximum_relative_parameter_error > .2: return "equifinal_good_response"
    if maximum_relative_parameter_error <= .2: return "well_identified"
    return "partially_identified"


def _load_demo(kind: str, demo_root: str | Path = DEFAULT_DEMO_ROOT) -> tuple[np.ndarray, pd.DataFrame, dict[str, Any]]:
    folder = Path(demo_root) / kind
    if not (folder / "observed_response.csv").exists():
        generate_synthetic_demo_data(demo_root)
    source = pd.read_csv(folder / "effective_rainfall.csv")["effective_rainfall"].to_numpy(dtype=float)
    response = pd.read_csv(folder / "observed_response.csv")
    truth = yaml.safe_load((folder / "truth_parameters.yaml").read_text(encoding="utf-8"))
    return source, response, truth


def run_kernel_demo(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    generate_synthetic_demo_data()
    root = _safe_root(output_dir); kernels = root / "kernels"; kernels.mkdir(exist_ok=True)
    config = load_gamma_config(); single = config["single_kernel"]
    kernel = build_gamma_kernel(single["shape"], single["scale"], single["support_length"], config["timestep"])
    pd.DataFrame({"lag": np.arange(len(kernel)) * config["timestep"], "weight": kernel}).to_csv(kernels / "single_kernel.csv", index=False)
    multi_rows = []
    for component in config["components"]:
        item = build_gamma_kernel(component["shape"], component["scale"], component["support_length"], config["timestep"])
        pd.DataFrame({"lag": np.arange(len(item)) * config["timestep"], "weight": item}).to_csv(kernels / f"multi_kernel_{component['component_id']}.csv", index=False)
        multi_rows.append((component, item))
    fig, ax = plt.subplots(figsize=(7, 3.5)); ax.plot(np.arange(len(kernel)), kernel); ax.set(xlabel="Lag (day)", ylabel="Weight", title="Single causal Gamma kernel"); fig.tight_layout(); fig.savefig(root / "gamma_kernel_single.png", dpi=150); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 3.5))
    for component, values in multi_rows: ax.plot(np.arange(len(values)), values, label=component["component_id"])
    ax.set(xlabel="Lag (day)", ylabel="Weight", title="Multi-timescale causal Gamma kernels"); ax.legend(); fig.tight_layout(); fig.savefig(root / "gamma_kernel_multi.png", dpi=150); plt.close(fig)
    leakage = detect_gamma_future_leakage(np.arange(100, dtype=float), kernel, 40)
    return {"status": "passed" if leakage["status"] == "passed" else "failed", "kernel_sum": float(kernel.sum()), "leakage": leakage, "single_kernel": kernels / "single_kernel.csv"}


def run_single_truth(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    source, response, truth = _load_demo("single_kernel")
    params = truth["single"]
    kernel = build_gamma_kernel(params["shape"], params["scale"], params["support_length"], 1.0)
    predicted = convolve_causal_series(source, kernel) * params["runoff_coefficient"]
    clean = response["clean_response"].to_numpy(dtype=float)
    metrics = response_metrics(clean, predicted)
    full_volume_error = float(np.convolve(source, kernel, mode="full").sum() - source.sum())
    metrics.update({"scenario": "single_no_noise", "shape": params["shape"], "scale": params["scale"], "analytical_mean_lag": calculate_gamma_mean_lag(params["shape"], params["scale"]), "analytical_peak_lag": calculate_gamma_peak_lag(params["shape"], params["scale"]), "discrete_mean_lag": calculate_discrete_kernel_mean_lag(kernel), "discrete_peak_lag": calculate_discrete_kernel_peak_lag(kernel), "kernel_sum": float(kernel.sum()), "full_convolution_volume_error": full_volume_error})
    _, noisy_response, _ = _load_demo("noise")
    noisy_metrics = response_metrics(noisy_response["observed_response"], noisy_response["clean_response"])
    noisy_metrics["scenario"] = "single_with_noise"
    root = _safe_root(output_dir); truth_dir = root / "truth"; truth_dir.mkdir(exist_ok=True)
    pd.DataFrame([metrics, noisy_metrics]).to_excel(truth_dir / "single_truth_metrics.xlsx", index=False)
    return {"status": "passed" if metrics["NSE"] >= 0.999 and metrics["KGE"] >= 0.995 and abs(metrics["PBIAS"]) <= 0.1 else "forward_inconsistency", "metrics": metrics, "noisy_metrics": noisy_metrics, "output": truth_dir / "single_truth_metrics.xlsx"}


def run_multi_truth(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    source, response, truth = _load_demo("multi_kernel")
    result = build_multi_gamma_features(source, truth["components"], 1.0)
    combined = result["combined"].to_numpy()
    expected = response["clean_response"].to_numpy(dtype=float)
    metrics = response_metrics(expected, combined)
    component_sum_error = float(np.max(np.abs(combined - result["features"].to_numpy() @ np.asarray(result["normalized_weights"]))))
    metrics.update({"scenario": "multi_no_noise", "component_sum_max_error": component_sum_error, "kernel_sum_min": min(float(item.sum()) for item in result["kernels"].values()), "kernel_sum_max": max(float(item.sum()) for item in result["kernels"].values())})
    root = _safe_root(output_dir); truth_dir = root / "truth"; truth_dir.mkdir(exist_ok=True); features = root / "features"; features.mkdir(exist_ok=True)
    pd.DataFrame([metrics]).to_excel(truth_dir / "multi_truth_metrics.xlsx", index=False)
    component_frame = result["features"].copy(); component_frame["combined"] = combined; component_frame.to_csv(features / "component_features.csv", index=False)
    feature_meta = build_gamma_feature_series(source, next(iter(result["kernels"].values())), "gamma_single_reference")
    pd.DataFrame({"source": source, **feature_meta, "gamma_combined": combined}).to_csv(features / "gamma_features.csv", index=False)
    fig, ax = plt.subplots(figsize=(8, 4)); component_frame.plot(ax=ax); ax.set_title("Gamma response components"); fig.tight_layout(); fig.savefig(root / "gamma_response_components.png", dpi=150); plt.close(fig)
    return {"status": "passed" if metrics["NSE"] >= 0.999 and component_sum_error <= 1e-12 else "forward_inconsistency", "metrics": metrics, "result": result, "output": truth_dir / "multi_truth_metrics.xlsx"}


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values); exp = np.exp(shifted); return exp / exp.sum()


def fit_single_gamma(source: Any, observed: Any, initial: tuple[float, float, float] = (1.4, 3.5, 0.6), support_length: int = 40) -> dict[str, Any]:
    x = np.asarray(source, dtype=float); y = np.asarray(observed, dtype=float)
    start = np.log(np.asarray(initial, dtype=float))
    def residual(transformed: np.ndarray) -> np.ndarray:
        shape, scale, coefficient = np.exp(transformed)
        return convolve_causal_series(x, build_gamma_kernel(shape, scale, support_length, 1.0)) * coefficient - y
    fitted = least_squares(residual, start, bounds=(np.log([0.25, 0.15, 0.05]), np.log([12.0, 20.0, 3.0])), max_nfev=450)
    shape, scale, coefficient = np.exp(fitted.x)
    prediction = convolve_causal_series(x, build_gamma_kernel(shape, scale, support_length, 1.0)) * coefficient
    return {"success": bool(fitted.success), "shape": float(shape), "scale": float(scale), "runoff_coefficient": float(coefficient), "prediction": prediction, "cost": float(fitted.cost), "boundary_hit": bool(np.any(fitted.active_mask != 0))}


def fit_multi_gamma(source: Any, observed: Any, components: list[dict[str, Any]] | None = None, max_nfev: int = 700) -> dict[str, Any]:
    x = np.asarray(source, dtype=float); y = np.asarray(observed, dtype=float); specs = components or default_components()
    initial_physical = []
    for item in specs: initial_physical.extend([item["shape"] * 0.85, item["scale"] * 1.2])
    logits = np.log(np.asarray([item["weight"] for item in specs]))
    start = np.r_[np.log(initial_physical), logits]
    lower = np.r_[np.tile(np.log([0.25, 0.15]), len(specs)), np.repeat(-8.0, len(specs))]
    upper = np.r_[np.tile(np.log([12.0, 20.0]), len(specs)), np.repeat(8.0, len(specs))]
    def unpack(vector: np.ndarray) -> tuple[list[tuple[float, float]], np.ndarray]:
        physical = np.exp(vector[: 2 * len(specs)]).reshape(-1, 2); return [(float(a), float(b)) for a, b in physical], _softmax(vector[2 * len(specs) :])
    def residual(vector: np.ndarray) -> np.ndarray:
        parameters, weights = unpack(vector); prediction = np.zeros_like(x)
        for index, ((shape, scale), item) in enumerate(zip(parameters, specs)):
            prediction += weights[index] * convolve_causal_series(x, build_gamma_kernel(shape, scale, int(item["support_length"]), 1.0))
        return prediction - y
    fitted = least_squares(residual, start, bounds=(lower, upper), max_nfev=max_nfev)
    parameters, weights = unpack(fitted.x); prediction = y + residual(fitted.x)
    recovered = [{"component_id": item["component_id"], "shape": pair[0], "scale": pair[1], "weight": float(weights[index]), "support_length": int(item["support_length"])} for index, (item, pair) in enumerate(zip(specs, parameters))]
    return {"success": bool(fitted.success), "components": recovered, "prediction": prediction, "cost": float(fitted.cost), "boundary_hit": bool(np.any(fitted.active_mask != 0))}


def _recovery_rows(true_components: list[dict[str, Any]], recovered: list[dict[str, Any]], boundary_hit: bool) -> list[dict[str, Any]]:
    rows = []
    for truth, estimate in zip(true_components, recovered):
        for parameter in ("shape", "scale", "weight"):
            true = float(truth[parameter]); value = float(estimate[parameter]); relative = abs(value - true) / true if true else np.nan
            initial = true * ({"shape": .85, "scale": 1.2, "weight": 1.0}[parameter])
            rows.append({"component_id": truth["component_id"], "parameter": parameter, "true_value": true, "initial_value": initial, "recovered_value": value, "absolute_error": abs(value - true), "relative_error": relative, "identifiability_status": "well_identified" if relative <= 0.2 else "partially_identified", "boundary_hit": boundary_hit})
    return rows


def run_parameter_recovery(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    source, response, truth = _load_demo("single_kernel")
    single = fit_single_gamma(source, response["clean_response"], support_length=truth["single"]["support_length"])
    single_metrics = response_metrics(response["clean_response"], single["prediction"])
    source_m, response_m, truth_m = _load_demo("multi_kernel")
    multi = fit_multi_gamma(source_m, response_m["clean_response"], truth_m["components"])
    multi_metrics = response_metrics(response_m["clean_response"], multi["prediction"])
    rows = []
    for parameter in ("shape", "scale", "runoff_coefficient"):
        true = float(truth["single"][parameter]); value = float(single[parameter]); relative = abs(value - true) / true
        rows.append({"model": "single", "component_id": "single", "parameter": parameter, "true_value": true, "initial_value": {"shape": 1.4, "scale": 3.5, "runoff_coefficient": 0.6}[parameter], "recovered_value": value, "absolute_error": abs(value - true), "relative_error": relative, "identifiability_status": "well_identified" if relative <= 0.1 else "partially_identified", "boundary_hit": single["boundary_hit"]})
    for row in _recovery_rows(truth_m["components"], multi["components"], multi["boundary_hit"]): rows.append({"model": "multi", **row})
    maximum_error = max(row["relative_error"] for row in rows if row["model"] == "multi")
    identifiability = classify_identifiability(multi_metrics["NSE"], maximum_error, weak_response=float(np.std(response_m["clean_response"])) < 1e-8, boundary_hit=multi["boundary_hit"])
    root = _safe_root(output_dir); truth_dir = root / "truth"; truth_dir.mkdir(exist_ok=True)
    table = pd.DataFrame(rows); table.to_excel(truth_dir / "parameter_recovery.xlsx", index=False)
    fig, ax = plt.subplots(figsize=(8, 4)); ax.plot(response["clean_response"], label="truth"); ax.plot(single["prediction"], "--", label="recovered"); ax.legend(); ax.set_title("Truth vs recovered single Gamma response"); fig.tight_layout(); fig.savefig(root / "truth_vs_recovered.png", dpi=150); plt.close(fig)
    figure = table[table["model"] == "single"]
    fig, ax = plt.subplots(figsize=(7, 3.5)); ax.bar(np.arange(len(figure)) - .18, figure["true_value"], .36, label="true"); ax.bar(np.arange(len(figure)) + .18, figure["recovered_value"], .36, label="recovered"); ax.set_xticks(np.arange(len(figure)), figure["parameter"]); ax.legend(); fig.tight_layout(); fig.savefig(root / "parameter_recovery.png", dpi=150); plt.close(fig)
    return {"status": "passed" if single_metrics["NSE"] >= 0.995 and multi_metrics["NSE"] >= 0.99 else "failed", "single": single, "multi": multi, "single_metrics": single_metrics, "multi_metrics": multi_metrics, "identifiability": identifiability, "output": truth_dir / "parameter_recovery.xlsx"}


def validate_gamma_outputs(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = Path(output_dir); required = [root / "kernels" / "single_kernel.csv", root / "truth" / "single_truth_metrics.xlsx", root / "truth" / "multi_truth_metrics.xlsx", root / "truth" / "parameter_recovery.xlsx"]
    single = run_single_truth(root); multi = run_multi_truth(root)
    kernel = pd.read_csv(required[0])["weight"].to_numpy() if required[0].exists() else build_gamma_kernel(2.5, 2.0, 40, 1.0)
    leakage = detect_gamma_future_leakage(np.arange(100, dtype=float), kernel, 50)
    missing = [str(path) for path in required if not path.exists()]
    return {"status": "passed" if not missing and single["status"] == "passed" and multi["status"] == "passed" and leakage["status"] == "passed" else "failed", "missing": missing, "single_truth": single["status"], "multi_truth": multi["status"], "causality": leakage}


def write_gamma_reports(output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Path]:
    from hydrolite.gamma_benchmark import run_gamma_benchmark, run_sample_efficiency

    root = _safe_root(output_dir); reports = root / "reports"; reports.mkdir(exist_ok=True)
    kernel_demo = run_kernel_demo(root); single = run_single_truth(root); multi = run_multi_truth(root)
    recovery = run_parameter_recovery(root); benchmark = run_gamma_benchmark(root); sample = run_sample_efficiency(root)
    validation = validate_gamma_outputs(root)
    manifest = calculate_gamma_feature_manifest(load_gamma_config(), multi["result"])
    manifest.update({
        "validation": validation,
        "kernel_demo_status": kernel_demo["status"],
        "single_truth_metrics": single["metrics"],
        "multi_truth_metrics": multi["metrics"],
        "noisy_truth_metrics": single["noisy_metrics"],
        "parameter_recovery_status": recovery["status"],
        "identifiability": recovery["identifiability"],
        "benchmark_metrics": benchmark["metrics"].to_dict(orient="records"),
        "sample_efficiency_metrics": sample["metrics"].to_dict(orient="records"),
        "synthetic_value_added": benchmark["synthetic_value_added"],
        "real_data_value_added": "not_tested",
        "absolute_paths_in_bundle": False,
    })
    zh = reports / "gamma_lag_report_zh.md"; en = reports / "gamma_lag_report_en.md"; manifest_path = reports / "gamma_lag_manifest.json"
    zh.write_text(f"# Gamma 因果滞后与多时间尺度特征\n\n{NOTICE}\n\n- 验证状态：`{validation['status']}`\n- 合成增益：`{benchmark['synthetic_value_added']}`\n- 真实数据增益：`not_tested`\n- 参数辨识：`{recovery['identifiability']}`\n- 仅为 derived feature，不修改 HydroLite 水量账本。\n- 合成真值只验证软件一致性，不代表真实流域有效。\n", encoding="utf-8")
    en.write_text("# Gamma Lag Features\n\nIndependent causal feature implementation; not a source-model reproduction. Synthetic truth is not real-project validation.\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"report_zh": zh, "report_en": en, "manifest": manifest_path}


def build_gamma_bundle(output_dir: str | Path = DEFAULT_OUTPUT) -> Path:
    root = _safe_root(output_dir); reports = write_gamma_reports(root); bundle = root / "reports" / "gamma_lag_bundle.zip"
    forbidden = ("data_raw", "external", ".dss", ".hdf5", ".h5", "credential", "secret", ".pt", ".pth", ".ckpt", ".onnx", "runtime.db")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == bundle: continue
            relative = path.relative_to(root)
            lowered = str(relative).lower()
            if any(token in lowered for token in forbidden): continue
            archive.write(path, relative)
    return bundle


def gamma_status() -> dict[str, Any]:
    config = load_gamma_config()
    return {"status": "partial", "method_id": config["method_id"], "implementation_name": "Gamma Lag Features", "numpy_required": True, "scipy_required_for_recovery": True, "sklearn_required": False, "pytorch_required": False, "synthetic_demo": True, "real_data_value_added": "not_tested", "notice": NOTICE}
