from pathlib import Path
import plistlib


ROOT = Path(__file__).resolve().parents[1]


def test_macos_packaging_sources_and_plist():
    plist = plistlib.loads((ROOT / "desktop/macos/HydroLiteStudio/Resources/Info.plist").read_bytes())
    assert plist["CFBundleIdentifier"] == "com.hydrolite.studio"
    assert plist["CFBundleShortVersionString"] == "0.7.0"
    assert plist["CFBundleExecutable"] == "HydroLite Studio"
    assert plist["SUFeedURL"].startswith("https://github.com/")
    package = (ROOT / "desktop/macos/HydroLiteStudio/Package.swift").read_text()
    assert "Sparkle" in package and ".build/vendor/Sparkle.xcframework" in package
    assert "@executable_path/../Frameworks" in package
    assert (ROOT / "packaging/macos/hydrolite_backend.spec").exists()
    assert (ROOT / "packaging/macos/HydroLiteStudio.entitlements").read_text().find("get-task-allow") == -1
    assert "data_raw" not in (ROOT / "packaging/macos/hydrolite_backend.spec").read_text()


def test_desktop_workflow_stages_remain_partial():
    from hydrolite.workflow_engine import list_workflow_stages

    stages = {row["stage_id"]: row for row in list_workflow_stages()}
    for stage in ("desktop_build", "desktop_signing", "desktop_packaging", "desktop_notarization", "desktop_update_readiness"):
        assert stages[stage]["status"] == "partial"
    assert stages["deployment_readiness"]["status"] == "partial"
    assert stages["flood_forecast"]["status"] == "partial"
    assert stages["drought_forecast"]["status"] == "partial"
    from hydrolite.capability_registry import list_capabilities
    assert {row["capability_id"]: row for row in list_capabilities()}["water_quality"]["status"] == "planned"
