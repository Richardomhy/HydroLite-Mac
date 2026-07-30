from __future__ import annotations

from importlib.util import find_spec
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd


def detect_torch_environment() -> dict[str, Any]:
    available = find_spec("torch") is not None
    result = {"torch_available": available, "version": None, "mps_available": False, "device": "unavailable"}
    if available:
        import torch
        result.update({"version": torch.__version__, "mps_available": bool(torch.backends.mps.is_available()), "device": "mps" if torch.backends.mps.is_available() else "cpu"})
    return result


def detect_mps_support() -> bool:
    return bool(detect_torch_environment()["mps_available"])


def assess_lstm_data_readiness(data: pd.DataFrame | str | Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    frame = pd.read_csv(data) if isinstance(data, (str, Path)) else data
    event_count = frame["event_id"].nunique() if "event_id" in frame else 1
    ready = len(frame) >= 500 and event_count >= 5
    return {"status": "ready_synthetic_demo" if ready else "insufficient_data", "ready": ready, "steps": len(frame), "events": int(event_count), "real_training_ready": False}


def build_lstm_sequences(data: pd.DataFrame | np.ndarray, lookback: int, horizon: int, features: list[str] | None, target: str | int) -> tuple[np.ndarray, np.ndarray]:
    values = data[features].to_numpy(float) if isinstance(data, pd.DataFrame) else np.asarray(data, float)
    target_values = data[target].to_numpy(float) if isinstance(data, pd.DataFrame) else values[:, int(target)]
    x, y = [], []
    for index in range(lookback, len(values) - horizon + 1):
        x.append(values[index - lookback:index])
        y.append(target_values[index:index + horizon])
    return np.asarray(x), np.asarray(y)


def fit_sequence_scaler(train_data: np.ndarray) -> dict[str, list[float]]:
    array = np.asarray(train_data, float)
    mean = array.reshape(-1, array.shape[-1]).mean(axis=0)
    std = array.reshape(-1, array.shape[-1]).std(axis=0)
    std[std == 0] = 1
    return {"mean": mean.tolist(), "std": std.tolist()}


def transform_lstm_data(data: np.ndarray, scaler: dict[str, list[float]]) -> np.ndarray:
    return (np.asarray(data, float) - np.asarray(scaler["mean"])) / np.asarray(scaler["std"])


def build_lstm_model(input_size: int, hidden_size: int, layers: int, horizon: int, dropout: float):
    if find_spec("torch") is None:
        raise RuntimeError("PyTorch is unavailable")
    import torch
    from torch import nn

    class TinyLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, layers, batch_first=True, dropout=dropout if layers > 1 else 0)
            self.head = nn.Linear(hidden_size, horizon)

        def forward(self, x):
            values, _ = self.lstm(x)
            return self.head(values[:, -1])

    return TinyLSTM()


def train_lstm_model(train: tuple[np.ndarray, np.ndarray], validation: tuple[np.ndarray, np.ndarray], config: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    environment = detect_torch_environment()
    if not environment["torch_available"]:
        return {"status": "skipped_optional_dependency", "runtime_seconds": 0.0, **environment}
    import torch
    started = time.perf_counter()
    torch.manual_seed(int(config.get("seed", 42)))
    device = torch.device(environment["device"])
    x_train, y_train = train
    model = build_lstm_model(x_train.shape[-1], min(int(config.get("hidden_size", 16)), 32), min(int(config.get("layers", 1)), 2), min(y_train.shape[-1], 6), float(config.get("dropout", 0.0))).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(config.get("learning_rate", 0.01)))
    loss_fn = torch.nn.MSELoss()
    x = torch.tensor(x_train, dtype=torch.float32, device=device)
    y = torch.tensor(y_train, dtype=torch.float32, device=device)
    epochs = min(int(config.get("epochs", 5)), 20)
    losses = []
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = loss_fn(model(x), y)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
        if time.perf_counter() - started > 110:
            return {"status": "timeout", "runtime_seconds": time.perf_counter() - started, **environment}
    return {"status": "passed", "runtime_seconds": time.perf_counter() - started, "device": environment["device"], "epochs": epochs, "final_loss": losses[-1], "model": model}


def predict_lstm_model(model, data: np.ndarray, config: dict[str, Any] | None = None) -> np.ndarray:
    import torch
    device = next(model.parameters()).device
    with torch.no_grad():
        return model(torch.tensor(data, dtype=torch.float32, device=device)).cpu().numpy()


def evaluate_lstm_forecast(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = np.asarray(predicted) - np.asarray(observed)
    return {"RMSE": float(np.sqrt(np.mean(error**2))), "MAE": float(np.mean(np.abs(error)))}


def save_lstm_checkpoint_metadata(output_dir: str | Path, result: dict[str, Any]) -> Path:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "lstm_checkpoint_metadata.json"
    path.write_text(json.dumps({key: value for key, value in result.items() if key != "model"}, indent=2, default=str), encoding="utf-8")
    return path


def run_lstm_synthetic_smoke_test(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    environment = detect_torch_environment()
    if not environment["torch_available"]:
        result = {"status": "skipped_optional_dependency", "runtime_seconds": 0.0, **environment}
    else:
        rng = np.random.default_rng(42)
        rainfall = np.maximum(rng.normal(1.0, 0.5, 180), 0)
        flow = np.convolve(rainfall, [0.1, 0.3, 0.4, 0.2], mode="same")
        values = np.column_stack([rainfall, flow])
        x, y = build_lstm_sequences(values, 12, 3, None, 1)
        scaler = fit_sequence_scaler(x[:120])
        x = transform_lstm_data(x, scaler)
        result = train_lstm_model((x[:120], y[:120]), (x[120:], y[120:]), {"epochs": 3, "hidden_size": 8, "seed": 42}, root)
        if result["status"] == "passed":
            prediction = predict_lstm_model(result["model"], x[120:])
            result["metrics"] = evaluate_lstm_forecast(y[120:], prediction)
    safe = {key: value for key, value in result.items() if key != "model"}
    (root / "lstm_smoke_test_report.md").write_text(f"# LSTM synthetic smoke test\n\nStatus: `{safe['status']}`.\n\nDevice: `{safe.get('device', 'unavailable')}`.\n\nFramework validated only; no real project model was trained.\n", encoding="utf-8")
    pd.DataFrame([{**safe, "metrics": json.dumps(safe.get("metrics", {}))}]).to_excel(root / "lstm_smoke_test_metrics.xlsx", index=False)
    save_lstm_checkpoint_metadata(root, safe)
    return safe
