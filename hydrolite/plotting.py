from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def plot_hydrograph(df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["time"], df["inflow_cms"], label="Catchment inflow", linewidth=2)
    ax.plot(df["time"], df["outflow_cms"], label="Outlet outflow", linewidth=2)
    ax.set_xlabel("Time")
    ax.set_ylabel("Flow (m3/s)")
    ax.set_title("HydroLite Demo Hydrograph")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)

