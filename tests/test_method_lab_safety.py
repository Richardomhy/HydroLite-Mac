from pathlib import Path
import subprocess

from hydrolite.capability_registry import get_capability


ROOT = Path(__file__).resolve().parents[1]


def test_method_lab_preserves_capability_boundaries_and_protected_ignore_rules():
    assert get_capability("water_quality")["status"] == "planned"
    assert get_capability("flood_forecast")["status"] == "partial"
    assert get_capability("drought_forecast")["status"] == "partial"
    assert "tmp_emergency_0722" not in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert not (ROOT / "tmp_emergency_0722" / ".gitignore").exists()


def test_tracked_files_exclude_forbidden_method_lab_assets():
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).lower()
    forbidden = ("gee-dataset-intelligence-skill/", "external/", ".pdf", ".pth", ".ckpt", ".onnx", "service-account", "credentials")
    assert not any(item in tracked for item in forbidden)
