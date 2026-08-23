"""Single bilingual top-level navigation definition."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class NavigationItem:
    nav_id: str
    name_zh: str
    name_en: str
    primary_page: str
    advanced_pages: tuple[str, ...] = ()

    def label(self, language: str) -> str:
        return self.name_zh if language == "中文" else self.name_en


NAVIGATION = (
    NavigationItem("home", "首页", "Home", "项目首页", ("教程与 Demo", "Beta 反馈")),
    NavigationItem("projects", "项目", "Projects", "项目中心", ("项目向导", "真实项目基线")),
    NavigationItem("scenarios", "场景", "Scenarios", "场景中心", ("全流程工作流", "情景运行")),
    NavigationItem("data", "数据", "Data", "数据中心", ("数据与校验", "数据连接器", "数据模板", "GEE 数据集智能", "GEE 数据中心")),
    NavigationItem("runs", "运行", "Runs", "运行中心", ("任务中心",)),
    NavigationItem("results", "成果", "Results", "成果中心", ("成果资产", "报告与导出", "结果对比", "水量平衡审计", "水环境源负荷核算")),
    NavigationItem("research", "方法实验室", "Research Lab", "水文研究方法实验室", ("洪水易发性", "水质方法实验室", "参数率定与敏感性", "连续模型验证", "历史洪水验证")),
    NavigationItem("system", "系统", "System", "系统与环境", ("系统诊断", "QGIS Bridge", "HEC-HMS", "SWMM 联动", "OpenHydroNet AI 输入")),
)


TERMS = {
    "project": ("项目", "Project"), "scenario": ("场景", "Scenario"),
    "data_readiness": ("数据就绪度", "Data Readiness"), "run": ("运行", "Run"),
    "artifact": ("成果", "Artifact"), "validation": ("验证", "Validation"),
    "susceptibility": ("易发性", "Susceptibility"), "risk": ("风险", "Risk"),
    "experimental": ("实验功能", "Experimental"), "planned": ("规划中", "Planned"),
    "ready_with_warnings": ("可用但有警告", "Ready with warnings"),
}


def list_navigation(language: str = "中文") -> list[dict]:
    return [{**asdict(item), "label": item.label(language)} for item in NAVIGATION]


def get_navigation_item(nav_id: str) -> NavigationItem:
    for item in NAVIGATION:
        if item.nav_id == nav_id: return item
    raise KeyError(f"Unknown navigation item: {nav_id}")


def term(key: str, language: str = "中文") -> str:
    values = TERMS[key]; return values[0] if language == "中文" else values[1]
