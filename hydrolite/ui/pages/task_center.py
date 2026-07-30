from __future__ import annotations

from pathlib import Path
import streamlit as st

from hydrolite.runtime_db import list_task_records
from hydrolite.runtime_logging import read_task_log
from hydrolite.task_engine import cancel_task, cleanup_task, retry_task
from hydrolite.task_queue import get_queue_status, pause_queue, resume_queue, run_queue_once, run_queue_until_empty


def render(context) -> None:
    st.header("任务中心")
    st.json(get_queue_status())
    a, b, c, d = st.columns(4)
    if a.button("暂停队列"): st.json(pause_queue())
    if b.button("恢复队列"): st.json(resume_queue())
    if c.button("运行下一任务"): st.json(run_queue_once())
    if d.button("运行至队列为空"): st.json(run_queue_until_empty())
    tasks = list_task_records(); st.dataframe(tasks, use_container_width=True)
    if tasks:
        task_id = st.selectbox("任务", [row["task_id"] for row in tasks])
        x, y, z = st.columns(3)
        if x.button("取消任务"): st.json(cancel_task(task_id))
        if y.button("重试任务"): st.json(retry_task(task_id))
        if z.button("清理工作临时文件"): st.json(cleanup_task(task_id))
        st.dataframe(read_task_log(task_id), use_container_width=True)
        task = next(row for row in tasks if row["task_id"] == task_id)
        for label, field in (("stdout", "stdout_path"), ("stderr", "stderr_path")):
            path = Path(task.get(field) or "")
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
                st.text_area(label, content[-20000:], height=180)
                st.download_button(f"下载 {label}", content, file_name=path.name, key=f"{label}_{task_id}")
