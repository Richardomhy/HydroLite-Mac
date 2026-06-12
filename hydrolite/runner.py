from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import logging
import time

from hydrolite.config import load_case
from hydrolite.hydrology import runoff_to_flow_cms
from hydrolite.io import read_rainfall, read_reaches, read_subcatchments, write_summary
from hydrolite.observed import (
    build_model_performance,
    load_observed_streamflow,
    plot_observed_vs_simulated,
    write_observed_quality_report,
)
from hydrolite.plotting import plot_hydrograph
from hydrolite.routing import route_reaches
from hydrolite.swmm.runner import run_swmm
from hydrolite.validate import validate_target
from hydrolite.water_balance import (
    balance_warning_messages,
    build_water_balance,
    write_water_balance,
)


@dataclass(frozen=True)
class RunOutputs:
    output_dir: Path
    result_flow_csv: Path
    summary_xlsx: Path
    hydrograph_png: Path
    water_balance_xlsx: Path
    log_file: Path
    swmm_summary_xlsx: Path | None = None
    observed_vs_simulated_csv: Path | None = None
    model_performance_xlsx: Path | None = None
    model_performance_report_md: Path | None = None
    observed_vs_simulated_png: Path | None = None


def _configure_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("hydrolite")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(stream_handler)
    return logger


def run_case(case_file: str | Path, output_dir: str | Path | None = None, skip_validate: bool = False) -> RunOutputs:
    started = time.perf_counter()
    validation = None
    if not skip_validate:
        validation = validate_target(case_file)
        if validation.has_fatal_errors:
            messages = "; ".join(validation.errors["message"].astype(str).head(5))
            raise ValueError(f"Validation failed for {case_file}: {messages}")

    config = load_case(case_file)
    if output_dir is not None:
        config = replace(config, output_dir=Path(output_dir).expanduser().resolve())
    config.output_dir.mkdir(parents=True, exist_ok=True)

    outputs = RunOutputs(
        output_dir=config.output_dir,
        result_flow_csv=config.output_dir / "result_flow.csv",
        summary_xlsx=config.output_dir / "summary.xlsx",
        hydrograph_png=config.output_dir / "hydrograph.png",
        water_balance_xlsx=config.output_dir / "water_balance.xlsx",
        log_file=config.output_dir / "run.log",
    )
    logger = _configure_logger(outputs.log_file)

    try:
        logger.info("Starting HydroLite case: %s", config.name)
        if validation is not None:
            logger.info("Validation summary: %s", validation.outputs.xlsx)
            for _, warning in validation.warnings.iterrows():
                logger.warning("Validation warning: %s - %s", warning["check_name"], warning["message"])
        logger.info("Case file: %s", Path(case_file).expanduser().resolve())
        logger.info("Input directory: %s", config.input_dir)
        logger.info("Output directory: %s", config.output_dir)
        logger.info("Model parameters: time_step_hours=%s", config.time_step_hours)
        logger.info(
            "Input files: rainfall=%s, subcatchments=%s, reaches=%s",
            config.rainfall_csv,
            config.subcatchments_csv,
            config.reaches_csv,
        )
        logger.info(
            "SWMM configuration: enabled=%s, inp_file=%s",
            config.swmm_enabled,
            config.swmm_inp_file,
        )

        rainfall = read_rainfall(config.rainfall_csv)
        subcatchments = read_subcatchments(config.subcatchments_csv)
        reaches = read_reaches(config.reaches_csv)
        logger.info(
            "Loaded rows: rainfall=%d, subcatchments=%d, reaches=%d",
            len(rainfall),
            len(subcatchments),
            len(reaches),
        )

        logger.info("Computing SCS-CN runoff and unit hydrograph routing")
        flow = runoff_to_flow_cms(rainfall, subcatchments, config.time_step_hours)

        logger.info("Routing %d reaches with Muskingum method", len(reaches))
        result = route_reaches(flow, reaches, config.time_step_hours, logger=logger)
        result.to_csv(outputs.result_flow_csv, index=False)

        peak_idx = int(result["outflow_cms"].idxmax())
        elapsed_seconds = time.perf_counter() - started
        summary = {
            "case_name": config.name,
            "time_step_hours": config.time_step_hours,
            "rainfall_total_mm": float(rainfall["rain_mm"].sum()),
            "subcatchment_count": int(len(subcatchments)),
            "reach_count": int(len(reaches)),
            "peak_outflow_cms": float(result.loc[peak_idx, "outflow_cms"]),
            "peak_outflow_time": str(result.loc[peak_idx, "time"]),
            "outflow_volume_m3": float(result["outflow_cms"].sum() * config.time_step_hours * 3600.0),
            "elapsed_seconds": elapsed_seconds,
        }
        plot_hydrograph(result, outputs.hydrograph_png)
        subbasin_balance, outlet_balance = build_water_balance(
            case_name=config.name,
            rainfall=rainfall,
            subcatchments=subcatchments,
            result=result,
            dt_hours=config.time_step_hours,
        )
        write_water_balance(outputs.water_balance_xlsx, subbasin_balance, outlet_balance)
        for message in balance_warning_messages(subbasin_balance, outlet_balance):
            logger.warning(message)

        performance_status = "not_configured"
        performance_file = ""
        if config.observed.enabled:
            assert config.observed.observed_streamflow_csv is not None
            logger.info("Observed streamflow enabled: %s", config.observed.observed_streamflow_csv)
            observed_df = load_observed_streamflow(
                config.observed.observed_streamflow_csv,
                time_column=config.observed.time_column,
                flow_column=config.observed.flow_column,
                gauge_id_column=config.observed.gauge_id_column,
            )
            simulated_flow_col = "outflow_cms" if "outflow_cms" in result.columns else result.select_dtypes("number").columns[-1]
            metrics_df, aligned, quality_checks, perf_warnings = build_model_performance(
                config.name,
                observed_file=config.observed.observed_streamflow_csv,
                simulated_file=outputs.result_flow_csv,
                observed_df=observed_df,
                simulated_df=result,
                simulated_flow_col=str(simulated_flow_col),
            )
            observed_vs_simulated_csv = config.output_dir / "observed_vs_simulated.csv"
            model_performance_xlsx = config.output_dir / "model_performance.xlsx"
            model_performance_report_md = config.output_dir / "model_performance_report.md"
            observed_vs_simulated_png = config.output_dir / "observed_vs_simulated.png"
            aligned.to_csv(observed_vs_simulated_csv, index=False)
            write_observed_quality_report(
                model_performance_xlsx,
                {
                    "metrics": metrics_df,
                    "aligned_timeseries": aligned,
                    "quality_checks": quality_checks,
                    "warnings": perf_warnings,
                },
            )
            plot_observed_vs_simulated(aligned, observed_vs_simulated_png)
            n_pairs = int(metrics_df.loc[0, "n_pairs"]) if not metrics_df.empty else 0
            model_performance_report_md.write_text(
                "\n".join(
                    [
                        "# HydroLite Model Performance Report",
                        "",
                        f"Case: `{config.name}`",
                        f"Observed data source: `{config.observed.observed_streamflow_csv}`",
                        "Observed data note: synthetic/demo only, not real station observation.",
                        f"Simulated data source: `{outputs.result_flow_csv}`",
                        f"Aligned sample count: `{n_pairs}`",
                        f"Time range: `{aligned['datetime'].min() if not aligned.empty else ''}` to `{aligned['datetime'].max() if not aligned.empty else ''}`",
                        "",
                        "## Metrics",
                        "",
                        "- NSE: Nash-Sutcliffe efficiency, higher is better.",
                        "- RMSE: root mean square error, lower is better.",
                        "- MAE: mean absolute error, lower is better.",
                        "- PBIAS: percent bias, closer to zero is better.",
                        "- R2: coefficient of determination, higher is better.",
                        "- KGE: Kling-Gupta efficiency, higher is better.",
                        "",
                        "```text",
                        metrics_df.to_string(index=False),
                        "```",
                        "",
                        "## Limitations",
                        "",
                        "This demo observed streamflow is synthetic and exists only to exercise the evaluation workflow.",
                        "Real calibration, evaluation, or OpenHydroNet training requires true gauge observations and QA flags.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            outputs = replace(
                outputs,
                observed_vs_simulated_csv=observed_vs_simulated_csv,
                model_performance_xlsx=model_performance_xlsx,
                model_performance_report_md=model_performance_report_md,
                observed_vs_simulated_png=observed_vs_simulated_png,
            )
            performance_status = "success"
            performance_file = str(model_performance_xlsx)

        swmm_status = "not_configured"
        swmm_summary_xlsx: Path | None = None
        if config.swmm_enabled:
            assert config.swmm_inp_file is not None
            swmm_result, swmm_summary_xlsx = run_swmm(
                inp_file=config.swmm_inp_file,
                case_output_dir=config.output_dir,
                result_flow_csv=outputs.result_flow_csv,
                coupling=config.swmm_coupling,
                logger=logger,
            )
            swmm_status = swmm_result.run_status
            outputs = replace(outputs, swmm_summary_xlsx=swmm_summary_xlsx)

        summary["swmm_status"] = swmm_status
        summary["swmm_summary_xlsx"] = "" if swmm_summary_xlsx is None else str(swmm_summary_xlsx)
        summary["performance_status"] = performance_status
        summary["model_performance_xlsx"] = performance_file
        write_summary(outputs.summary_xlsx, summary)

        logger.info("Wrote %s", outputs.result_flow_csv)
        logger.info("Wrote %s", outputs.summary_xlsx)
        logger.info("Wrote %s", outputs.hydrograph_png)
        logger.info("Wrote %s", outputs.water_balance_xlsx)
        if swmm_summary_xlsx is not None:
            logger.info("Wrote %s", swmm_summary_xlsx)
        if outputs.model_performance_xlsx is not None:
            logger.info("Wrote %s", outputs.model_performance_xlsx)
        logger.info("HydroLite case complete in %.3f seconds", elapsed_seconds)
        return outputs
    except Exception:
        logger.exception("HydroLite case failed")
        raise
