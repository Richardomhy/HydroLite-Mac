from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import streamlit as st

from hydrolite.app_settings import load_settings, reset_settings, save_settings
from hydrolite.deployment import build_deployment_manifest
from hydrolite.environment_capture import capture_environment
from hydrolite.process_manager import cleanup_orphaned_runtime_processes
from hydrolite.resource_monitor import inspect_cpu, inspect_disk_space, inspect_memory
from hydrolite.runtime_db import get_database_version
from hydrolite.runtime_paths import get_runtime_root
from hydrolite.task_queue import get_queue_status
from hydrolite.desktop.desktop_diagnosis import build_desktop_diagnosis
from hydrolite.desktop.desktop_update import inspect_update_status


PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_PATH = PROJECT_ROOT / "dist" / "macos" / "HydroLite-Studio-0.7.0-arm64.app"


def _desktop_action(command: str) -> dict:
    result = subprocess.run(
        [os.sys.executable, "-m", "hydrolite", "desktop", command],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {"return_code": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


def render(context) -> None:
    st.header("系统与环境")
    root = get_runtime_root()
    st.json({"database_version": get_database_version(), "runtime_root": str(root), "disk": inspect_disk_space(root), "memory": inspect_memory(), "cpu": inspect_cpu(), "queue": get_queue_status()})
    if st.button("运行完整诊断"): st.json({"deployment": build_deployment_manifest(), "environment": capture_environment()})
    if st.button("捕获环境快照"): st.json(capture_environment())
    if st.button("检查孤儿进程"): st.json(cleanup_orphaned_runtime_processes(root))
    if st.button("清理安全缓存"):
        cache = root / "cache"
        if cache.exists(): shutil.rmtree(cache)
        cache.mkdir(parents=True, exist_ok=True)
        st.success(f"仅清理运行缓存：{cache}")
    settings = load_settings(); modes = ["local_full", "local_light", "cloud_streamlit", "test", "read_only"]
    mode = st.selectbox("运行模式", modes, index=modes.index(settings["runtime_mode"]))
    if st.button("保存设置"): settings["runtime_mode"] = mode; st.success(save_settings(settings))
    if st.button("恢复安全默认设置"): st.json(reset_settings())
    st.subheader("macOS 桌面发行")
    diagnosis = build_desktop_diagnosis(APP_PATH)
    st.json({
        "app_bundle": diagnosis["app_bundle"],
        "architecture": diagnosis["architecture"],
        "signing": diagnosis["signing"],
        "developer_identities": diagnosis["developer_identities"],
        "update": inspect_update_status(PROJECT_ROOT / "packaging" / "macos" / "update_config.example.json"),
        "zip": str(PROJECT_ROOT / "dist" / "macos" / "HydroLite-Studio-0.7.0-arm64.zip"),
        "dmg": str(PROJECT_ROOT / "dist" / "macos" / "HydroLite-Studio-0.7.0-arm64.dmg"),
    })
    cloud = bool(os.environ.get("STREAMLIT_SHARING_MODE") or os.environ.get("STREAMLIT_CLOUD"))
    if cloud:
        st.info("Streamlit Cloud 仅展示桌面发行状态；构建、签名和打包请在本地 macOS 执行。")
    else:
        actions = {
            "诊断构建环境": "diagnose", "构建本地 App": "build", "验证 Bundle": "verify",
            "创建 ZIP": "package-zip", "创建 DMG": "package-dmg", "检查签名": "signing-status",
            "公证 dry-run": "notarization-gate", "检查更新配置": "update-status",
        }
        columns = st.columns(2)
        for index, (label, command) in enumerate(actions.items()):
            if columns[index % 2].button(label, key=f"desktop_{command}"):
                st.json(_desktop_action(command))
        if st.button("打开 dist"):
            subprocess.run(["open", str(PROJECT_ROOT / "dist")], check=False)
    report = PROJECT_ROOT / "output" / "macos_packaging" / "macos_release_report_zh.md"
    if report.exists():
        st.download_button("下载构建报告", report.read_bytes(), file_name=report.name)
