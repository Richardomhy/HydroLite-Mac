from __future__ import annotations

import shutil
import streamlit as st

from hydrolite.app_settings import load_settings, reset_settings, save_settings
from hydrolite.deployment import build_deployment_manifest
from hydrolite.environment_capture import capture_environment
from hydrolite.process_manager import cleanup_orphaned_runtime_processes
from hydrolite.resource_monitor import inspect_cpu, inspect_disk_space, inspect_memory
from hydrolite.runtime_db import get_database_version
from hydrolite.runtime_paths import get_runtime_root
from hydrolite.task_queue import get_queue_status


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
