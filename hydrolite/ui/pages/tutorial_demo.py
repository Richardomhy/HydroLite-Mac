from __future__ import annotations

import pandas as pd
import streamlit as st

from hydrolite.__version__ import __version__
from hydrolite.tutorial import (
    generate_demo_summary,
    get_demo_checklist,
    get_demo_steps,
    read_demo_progress,
    reset_demo_progress,
    write_demo_progress,
)
from hydrolite.ui.components import show_download, show_markdown_file
from hydrolite.ui.state import WorkbenchContext


STREAMLIT_URL = "https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app"
GITHUB_URL = "https://github.com/Richardomhy/HydroLite-Mac.git"


def _completed_steps(context: WorkbenchContext) -> list[str]:
    return list(read_demo_progress(context.project_dir).get("completed_steps", []))


def _set_completed(context: WorkbenchContext, completed: list[str]) -> None:
    write_demo_progress(context.project_dir, completed)


def render(context: WorkbenchContext) -> None:
    st.header("教程与 Demo")
    st.caption("面向第一次使用者的引导式软件演示，从项目加载到报告导出。")
    if not context.project_loaded:
        st.error(context.error_message)
        st.info("推荐先加载 `projects/demo_project`，再进入教程模式。")
        return

    steps = get_demo_steps()
    completed = _completed_steps(context)
    completed_set = set(completed)
    progress = len(completed_set) / len(steps) if steps else 0.0

    c1, c2, c3 = st.columns(3)
    c1.metric("当前版本", __version__)
    c2.metric("Demo 项目", context.project_dir.name)
    c3.metric("完成进度", f"{len(completed_set)}/{len(steps)}")
    st.progress(progress)
    st.write(f"在线体验地址: {STREAMLIT_URL}")
    st.write(f"GitHub 仓库地址: {GITHUB_URL}")
    st.write(f"Demo 项目路径: `{context.project_dir}`")

    st.subheader("推荐演示路线")
    route_cols = st.columns(3)
    route_cols[0].info("路线 A：在线快速体验。浏览项目、结果、图表和报告，不强制认证 GEE/SWMM/OpenHydroNet。")
    route_cols[1].success("路线 B：本地完整演示。运行校验、批量计算、GEE 摘要、SWMM 隔离求解器和输入包生成。")
    route_cols[2].warning("路线 C：工程交付演示。重点展示项目向导、结果对比、Word/HTML/Markdown 报告和项目包。")
    st.info("完成 Demo 后，建议进入左侧 `Beta 反馈` 页面提交体验反馈；请勿上传敏感数据、账号、token 或涉密工程资料。")

    if context.is_cloud:
        st.info("当前看起来是 Streamlit Cloud 环境：GEE 认证、SWMM 后端和 OpenHydroNet 外部仓库不会被强制执行；可优先展示已有 demo 输出。")
    else:
        st.caption("本地环境可运行完整工作流；可根据需要配置 GEE_PROJECT、HYDROLITE_SWMM_PYTHON 和 OpenHydroNet 外部仓库。")

    step_ids = [step["step_id"] for step in steps]
    current_default = next((idx for idx, step in enumerate(steps) if step["step_id"] not in completed_set), 0)
    selected_id = st.selectbox(
        "当前步骤",
        step_ids,
        index=current_default,
        format_func=lambda value: f"{value} - {next(step['title'] for step in steps if step['step_id'] == value)}",
    )
    current_index = step_ids.index(selected_id)
    current = steps[current_index]

    buttons = st.columns(5)
    if buttons[0].button("开始 Demo", use_container_width=True):
        _set_completed(context, [])
        st.success("Demo 进度已初始化。")
        st.rerun()
    if buttons[1].button("标记当前步骤完成", use_container_width=True):
        if selected_id not in completed_set:
            completed.append(selected_id)
            _set_completed(context, completed)
        st.success(f"已标记完成：{current['title']}")
        st.rerun()
    if buttons[2].button("跳到下一步", use_container_width=True):
        next_index = min(current_index + 1, len(steps) - 1)
        st.session_state["tutorial_next_step"] = step_ids[next_index]
        st.info(f"下一步：{steps[next_index]['title']}")
    if buttons[3].button("重置 Demo 进度", use_container_width=True):
        reset_demo_progress(context.project_dir)
        st.success("Demo 进度已重置，项目计算成果未删除。")
        st.rerun()
    if buttons[4].button("生成 Demo 总结", use_container_width=True):
        path = generate_demo_summary(context.project_dir)
        st.success(f"Demo 总结已生成: `{path}`")

    st.subheader("当前步骤详情")
    st.markdown(f"### {current['title']}")
    st.write(current["description"])
    detail = pd.DataFrame(
        [
            {"字段": "要做什么", "内容": current["action"]},
            {"字段": "预期结果", "内容": current["expected_output"]},
            {"字段": "所在页面", "内容": current["page_name"]},
            {"字段": "CLI 等价命令", "内容": current["cli_equivalent"]},
            {"字段": "在线版说明", "内容": current["online_note"]},
            {"字段": "本地版说明", "内容": current["local_note"]},
        ]
    )
    st.dataframe(detail, use_container_width=True, hide_index=True)

    st.subheader("步骤列表")
    checklist = pd.DataFrame(get_demo_checklist(context.project_dir))
    if not checklist.empty:
        st.dataframe(
            checklist[
                [
                    "step_id",
                    "title",
                    "page_name",
                    "marked_complete",
                    "success_file_count",
                    "expected_file_count",
                    "status",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无教程步骤。")

    st.subheader("在线版与本地版差异")
    st.markdown(
        """
- 在线版：适合快速演示、查看示例结果、阅读报告和理解流程；不会强制 GEE 登录、SWMM 后端或 OpenHydroNet 外部仓库。
- 本地版：适合完整生产式工作流，可配置 GEE project、SWMM 隔离求解器、项目数据导入和外部 AI 仓库诊断。
- 两者共同点：都以项目为中心，保留 data_raw 原始数据只读原则，并将结果输出到项目 reports/output 目录。
"""
    )

    show_markdown_file("demo_summary.md", context.project_dir / "reports" / "demo_summary.md")
    show_download("下载 demo_summary.md", context.project_dir / "reports" / "demo_summary.md", "text/markdown")
