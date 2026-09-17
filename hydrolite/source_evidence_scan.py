"""Bounded metadata-first evidence scan; unknown identity never becomes activity."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import re

import pandas as pd

from hydrolite.source_evidence import SourceEvidenceRecord
from hydrolite.workspace import calculate_file_checksum

KEYWORDS = "排污口 排口 污水 废水 水量 排水量 排放量 流量 设计规模 处理规模 日处理 万吨 m3/d 人口 常住人口 户数 村庄 生活污水 用水量 生猪 猪 牛 羊 鸡 鸭 存栏 出栏 养殖场 畜禽 耕地 农田 种植 施肥 化肥 氮肥 磷肥 农作物 面积 水产 鱼塘 池塘 养殖面积 投饵 产量 尾水 企业 工业 产品 排放 许可 环评".split()
ALIASES = {
    "treatment_capacity": ("设计规模", "处理规模", "设计能力", "design_capacity"),
    "discharge_flow": ("排水流量", "排放流量", "实际流量", "出水流量", "流量", "discharge_flow", "flow_cms", "q("),
    "wastewater_volume": ("实际处理量", "污水量", "废水量", "排水量", "日水量", "wastewater_volume"),
    "population": ("常住人口", "人口", "population"),
    "livestock_count": ("存栏", "出栏", "头数", "livestock_count"),
    "farm_capacity": ("养殖规模", "farm_capacity"),
    "cropland_area": ("耕地面积", "种植面积", "cropland_area"),
    "fertilizer_application": ("施肥量", "氮肥", "磷肥", "fertilizer_application"),
    "aquaculture_area": ("养殖面积", "aquaculture_area"),
    "aquaculture_production": ("水产产量", "aquaculture_production"),
    "industrial_activity": ("产品产量", "industrial_activity"),
    "treatment_efficiency": ("去除率", "削减率", "treatment_efficiency"),
    "receiving_water": ("受纳水体", "排入河流", "河流名称", "receiving_water"),
    "outfall_to_reach_relation": ("reach_id", "河段编号"),
    "source_type": ("一级分类", "二级分类", "source_type"),
    "location": ("经度", "纬度", "longitude", "latitude"),
}
POLLUTANT_NAMES = {"CODMn": ("codmn", "高锰酸钾", "高锰酸盐"), "NH3-N": ("nh3-n", "nh₃-n", "氨氮"), "TN": ("总氮", "tn"), "TP": ("总磷", "tp")}
IDENTITY = ("source_id", "排污口名称", "排口名称", "污染源名称", "企业名称", "养殖场名称", "污水处理厂名称")


def classify_field(header: str) -> tuple[str, str]:
    text = header.lower().replace("（", "(").replace("）", ")")
    for pollutant, aliases in POLLUTANT_NAMES.items():
        if any(alias in text for alias in aliases):
            return ("measured_concentration" if "mg" in text or "浓度" in text else "reported_pollutant_load"), pollutant
    return next(((kind, "") for kind, aliases in ALIASES.items() if any(alias in text for alias in aliases)), ("other", ""))


def parse_unit(header: str) -> str:
    text = header.lower().replace("³", "3").replace("²", "2").replace(" ", "")
    for unit in ("kg/day", "kg/year", "t/year", "kg/d", "m3/day", "m3/d", "m3/s", "mg/l", "ug/l", "万m3", "km2", "m2", "m3", "ha", "kg"):
        if unit in text: return unit
    if "t/a" in text: return "t/year"
    if "人" in text and "人口" not in text: return "person"
    if "头" in text: return "head"
    return ""


def _tables(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=False, data_only=True)
        try:
            for sheet in book:
                if sheet.max_row > 100000 or sheet.max_column > 200: raise ValueError("Table size requires manual review")
                rows = [list(r) for r in sheet.iter_rows(values_only=True)]
                for merged in sheet.merged_cells.ranges:
                    if merged.max_row <= 20:
                        value = rows[merged.min_row - 1][merged.min_col - 1]
                        for r in range(merged.min_row - 1, merged.max_row):
                            for c in range(merged.min_col - 1, merged.max_col): rows[r][c] = value
                yield sheet.title, sheet.sheet_state, rows
        finally: book.close()
    elif suffix == ".xls":
        with pd.ExcelFile(path) as book:
            for name in book.sheet_names: yield name, "unknown", book.parse(name, header=None).values.tolist()
    elif suffix == ".csv":
        yield "csv", "visible", pd.read_csv(path, header=None).values.tolist()
    elif suffix == ".docx":
        from docx import Document
        doc = Document(path)
        for index, table in enumerate(doc.tables): yield f"table_{index + 1}", "visible", [[c.text for c in row.cells] for row in table.rows]
        paragraphs = [[p.text] for p in doc.paragraphs if any(k in p.text for k in KEYWORDS)]
        yield "paragraphs", "visible", paragraphs
    elif suffix in {".gpkg", ".shp", ".geojson"}:
        import geopandas as gpd
        import pyogrio
        layers = pyogrio.list_layers(path) if suffix == ".gpkg" else [(None, None)]
        for name, _ in layers:
            frame = gpd.read_file(path, layer=name).drop(columns="geometry")
            yield str(name or "features"), "visible", [list(frame.columns), *frame.values.tolist()]
    elif suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("records", [])
        if rows and all(isinstance(r, dict) for r in rows):
            frame = pd.DataFrame(rows); yield "records", "visible", [list(frame.columns), *frame.values.tolist()]
    elif suffix == ".txt":
        yield "text", "visible", [[line] for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if any(k in line for k in KEYWORDS)]


def scan_source_evidence(root: str | Path, sources: pd.DataFrame) -> tuple[list[SourceEvidenceRecord], pd.DataFrame]:
    root = Path(root).expanduser().resolve()
    if not root.is_dir(): raise FileNotFoundError(f"external_project_storage_unavailable: {root}")
    names = {}
    for source in sources.itertuples():
        for key in (source.source_id, source.name): names.setdefault(str(key).strip(), set()).add(source.source_id)
    records, audit, seen = [], [], set()
    supported = {".xlsx", ".xls", ".csv", ".docx", ".txt", ".json", ".gpkg", ".shp", ".geojson"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink(): continue
        logical = path.relative_to(root).as_posix()
        row = {"file_reference": logical, "status": "metadata_only", "reason": "not_targeted"}
        # ponytail: bounded metadata scan, no OCR or model-output parsing.
        if any(part.lower() in {"txtinout", ".git", "node_modules", "__pycache__"} for part in path.parts):
            row["reason"] = "model_output_or_runtime_excluded"; audit.append(row); continue
        selected = path.suffix.lower() in {".xlsx", ".xls", ".gpkg", ".shp", ".geojson"} or any(k in path.name for k in KEYWORDS)
        if not selected or path.suffix.lower() not in supported:
            if selected: row["reason"] = "image_or_pdf_requires_existing_text_only"
            audit.append(row); continue
        row["status"] = "targeted"
        if path.stat().st_size > 30_000_000: row["reason"] = "size_limit_manual_review"; audit.append(row); continue
        checksum = calculate_file_checksum(path); row["checksum"] = checksum
        if checksum in seen: row["reason"] = "duplicate_content"; audit.append(row); continue
        seen.add(checksum)
        try:
            count_before = len(records)
            for table, visibility, cells in _tables(path):
                clean = [["" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip() for x in line] for line in cells]
                if not clean: continue
                header_index = max(range(min(20, len(clean))), key=lambda i: sum(classify_field(c)[0] != "other" or any(a in c for a in IDENTITY) for c in clean[i]))
                headers = clean[header_index]
                if max((len(r) for r in clean), default=0) == 1:
                    for i, line in enumerate(clean):
                        if not line or not any(k in line[0] for k in KEYWORDS): continue
                        records.append(SourceEvidenceRecord("ev_" + sha256(f"{checksum}:{table}:{i}".encode()).hexdigest()[:16], "", "other", document_id=checksum[:16], file_reference=logical, table_name=table, row_reference=str(i + 1), extracted_value=line[0][:800], extraction_method="text_context_only", status="ambiguous", provenance={"checksum": checksum, "context": line[0][:800]}))
                    continue
                start = header_index + 1
                if start < len(clean) and any(parse_unit(c) for c in clean[start]) and all(not v or parse_unit(v) or v in {"单位", "unit"} for v in clean[start]):
                    headers = [h + " " + u for h, u in zip(headers, clean[start])]; start += 1
                for i in range(start, len(clean)):
                    values = clean[i]; context = dict(zip(headers, values))
                    identities = set().union(*(names.get(v, set()) for h, v in context.items() if any(a in h for a in IDENTITY)))
                    source_id = next(iter(identities)) if len(identities) == 1 else ""
                    date = next((v for h, v in context.items() if "采样时间" in h or h in {"date", "date_start", "日期"}), "")
                    try: date = pd.Timestamp(date).isoformat() if date else ""
                    except (ValueError, TypeError): date = ""
                    end = context.get("date_end", date)
                    for column, (header, value) in enumerate(context.items()):
                        kind, pollutant = classify_field(header)
                        if kind == "other" or not value: continue
                        unit = parse_unit(header)
                        number = pd.to_numeric(value, errors="coerce")
                        extracted = float(number) if pd.notna(number) else value
                        records.append(SourceEvidenceRecord("ev_" + sha256(f"{checksum}:{table}:{i}:{column}".encode()).hexdigest()[:16], source_id, kind, dataset_id="src_" + checksum[:16], document_id=checksum[:16], file_reference=logical, sheet_name=table, table_name=table, row_reference=str(i + 1), field_name=header, extracted_value=extracted, unit=unit, date_start=date, date_end=end, confidence="medium" if source_id else "low", status="candidate" if source_id else "ambiguous", pollutant=pollutant, temporal_basis="instantaneous" if date and end == date else "period_total" if date else "", measurement_role="effluent" if "出水" in header else "influent" if "进水" in header else "unknown", provenance={"checksum": checksum, "sheet_visibility": visibility, "context": json.dumps(context, ensure_ascii=False)[:1800], "identity_rule": "exact_unique_source_name_or_id", "source_status": "unreviewed"}))
            row.update(status="searched", reason="read_only", evidence_count=len(records) - count_before)
        except Exception as exc: row.update(status="read_failed", reason=f"{type(exc).__name__}: {exc}")
        audit.append(row)
    return records, pd.DataFrame(audit)
