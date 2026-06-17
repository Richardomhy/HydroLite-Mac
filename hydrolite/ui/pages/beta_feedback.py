from __future__ import annotations

import streamlit as st

from hydrolite.__version__ import __version__
from hydrolite.beta import GITHUB_URL, RELEASE_TAG, STREAMLIT_URL
from hydrolite.ui.state import WorkbenchContext


BUG_URL = "https://github.com/Richardomhy/HydroLite-Mac/issues/new?template=bug_report.yml"
FEATURE_URL = "https://github.com/Richardomhy/HydroLite-Mac/issues/new?template=feature_request.yml"
BETA_URL = "https://github.com/Richardomhy/HydroLite-Mac/issues/new?template=beta_feedback.yml"
DATA_TEMPLATE_URL = "https://github.com/Richardomhy/HydroLite-Mac/issues/new?template=data_template_issue.yml"


def render(context: WorkbenchContext) -> None:
    st.header("Beta 反馈")
    st.caption("发布后验证、用户反馈和问题闭环入口。")

    c1, c2, c3 = st.columns(3)
    c1.metric("当前版本", __version__)
    c2.metric("Release tag", RELEASE_TAG)
    c3.metric("Streamlit Cloud", "online" if context.is_cloud else "local")

    st.write(f"GitHub 仓库: {GITHUB_URL}")
    st.write(f"在线体验地址: {STREAMLIT_URL}")
    st.warning("提交反馈前请删除敏感数据、私有路径、账号、token、API key、service account json 和工程涉密信息。")

    st.subheader("提交入口")
    issue_cols = st.columns(4)
    issue_cols[0].link_button("提交 Bug", BUG_URL, use_container_width=True)
    issue_cols[1].link_button("提交功能建议", FEATURE_URL, use_container_width=True)
    issue_cols[2].link_button("提交 Beta 反馈", BETA_URL, use_container_width=True)
    issue_cols[3].link_button("提交数据模板问题", DATA_TEMPLATE_URL, use_container_width=True)

    st.subheader("复制用反馈模板")
    st.code(
        f"""HydroLite version: {__version__}
运行环境: 本地版 / 在线版
操作系统:
Python 版本:
正在使用的页面或 CLI:
输入数据类型: demo / 自有 rainfall_csv / subbasin_csv / reach_csv / SWMM inp / GEE boundary / OpenHydroNet input
复现步骤:
1.
2.
3.
预期结果:
实际结果:
报错信息或日志:
是否已删除敏感数据: 是 / 否
截图或附件说明:
""",
        language="text",
    )

    st.subheader("常见问题与 smoke test")
    st.markdown(
        """
- FAQ：`docs/faq_zh.md`
- 在线版 smoke test：`docs/cloud_smoke_test.md`
- 本地版 smoke test：`docs/local_smoke_test.md`
- 反馈处理流程：`docs/beta_feedback_workflow.md`
"""
    )
    st.code(
        """python -m hydrolite version
python -m hydrolite beta info
python -m hydrolite beta checklist
python -m hydrolite beta smoke-local
python -m hydrolite healthcheck
python -m streamlit run streamlit_app.py --server.headless true
""",
        language="bash",
    )

    if context.is_cloud:
        st.info("在线版适合演示和查看示例输出；GEE/SWMM/OpenHydroNet 完整后端建议在本地配置后运行。")
    else:
        st.success("本地版可执行完整 smoke test，并可附上脱敏后的日志片段帮助复现。")
