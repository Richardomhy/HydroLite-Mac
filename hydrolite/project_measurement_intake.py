"""Project-scoped measurement intake; separate from public-data acquisition."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
import json
import math
import re
import shutil
import stat
import zipfile

import pandas as pd

from hydrolite.workspace import calculate_file_checksum, read_workspace_manifest, write_workspace_manifest


MAX_UPLOAD_BYTES = 50 * 1024 * 1024
POLLUTANTS = {"CODMn", "NH3-N", "TN", "TP"}
TEMPLATES = {
    "MR01": {"template_id": "point_source_identity_v1", "data_type": "coordinate_crs", "title": "排口基础与坐标", "fields": ["source_id", "source_name", "longitude", "latitude", "geometry", "crs", "coordinate_source", "survey_date", "notes"], "required": ["source_id", "source_name", "crs", "coordinate_source", "survey_date"], "labels": ["排口唯一编号", "排口名称", "经度", "纬度", "Point 几何（GeoJSON，可选）", "坐标系/参考", "坐标来源", "调查日期", "备注"], "units": ["文本", "文本", "十进制度", "十进制度", "GeoJSON Point", "EPSG/WGS84/CGCS2000/GCJ-02/BD-09", "文本", "YYYY-MM-DD", "文本"]},
    "MR02": {"template_id": "point_source_flow_v1", "data_type": "outfall_actual_flow", "title": "排口实际水量", "fields": ["source_id", "timestamp", "flow", "unit", "measurement_method", "flow_semantics", "data_source"], "required": ["source_id", "timestamp", "flow", "unit", "measurement_method", "flow_semantics", "data_source"], "labels": ["排口唯一编号", "测量时间/期段起始", "实测数值", "单位", "测量方法", "数据语义", "数据来源"], "units": ["文本", "ISO日期时间", "数值", "m3/s、m3/day、m3/period", "文本", "measured_actual/reported_actual/estimated_actual/design_capacity/permitted_maximum", "文本"]},
    "MR03": {"template_id": "point_source_concentration_v1", "data_type": "outfall_concentration", "title": "污染物监测", "fields": ["source_id", "timestamp", "pollutant", "concentration", "unit", "sample_type", "detection_limit", "quality_flag"], "required": ["source_id", "timestamp", "pollutant", "concentration", "unit", "sample_type", "quality_flag"], "labels": ["排口唯一编号", "采样时间", "污染物", "浓度（可填 <检出限）", "单位", "样品类型", "检出限（可选）", "质量标记"], "units": ["文本", "ISO日期时间", "CODMn/NH3-N/TN/TP", "数值或 <数值", "mg/L 或 ug/L", "瞬时/混合/其他", "与浓度同单位", "文本"]},
    "MR04": {"template_id": "receiving_water_reach_v1", "data_type": "receiving_water", "title": "受纳水体 / 河段", "fields": ["source_id", "receiving_water", "reach_id", "evidence_type", "confirmation", "notes"], "required": ["source_id", "receiving_water", "evidence_type", "confirmation"], "labels": ["排口唯一编号", "受纳水体名称", "正式河段编号（可选）", "关系证据类型", "人工确认状态", "备注"], "units": ["文本", "文本", "文本", "现场/排水图/批复等", "confirmed/unconfirmed", "文本"]},
    "MR05": {"template_id": "wastewater_facility_operation_v1", "data_type": "wastewater_volume", "title": "污水设施运行", "fields": ["facility_id", "timestamp", "wastewater_volume", "unit", "influent", "effluent", "operating_status"], "required": ["facility_id", "timestamp", "wastewater_volume", "unit", "effluent", "operating_status"], "labels": ["设施编号", "记录时间/期段", "实际废水量", "单位", "进水（可选）", "出水", "运行状态"], "units": ["文本", "ISO日期时间", "数值", "m3、m3/day、m3/period", "mg/L（按指标注明）", "文本/数值", "运行/停运/检修等"]},
    "MR06": {"template_id": "factor_approval_v1", "data_type": "project_factor_approval", "title": "项目系数审批", "fields": ["factor_id", "project_decision", "reviewer", "comment", "approval_date"], "required": ["factor_id", "project_decision", "reviewer", "comment", "approval_date"], "labels": ["系数编号", "项目采用决定", "审核人", "审核意见", "审批日期"], "units": ["文本", "approved_for_project/rejected/reviewed", "文本", "文本", "YYYY-MM-DD"]},
}
ALIASES = {"排口编号": "source_id", "排口唯一编号": "source_id", "来源编号": "source_id", "设施编号": "facility_id", "排口名称": "source_name", "测量时间": "timestamp", "采样时间": "timestamp", "时间": "timestamp", "日期": "timestamp", "流量": "flow", "实际废水量": "wastewater_volume", "浓度": "concentration", "坐标系": "crs", "坐标系/参考": "crs", "经度": "longitude", "纬度": "latitude", "几何": "geometry", "Point 几何（GeoJSON，可选）": "geometry", "污染物": "pollutant", "河段编号": "reach_id", "受纳水体名称": "receiving_water", "审核人": "reviewer", "审核意见": "comment", "审批日期": "approval_date", "单位": "unit", "测量方法": "measurement_method", "数据语义": "flow_semantics", "数据来源": "data_source", "样品类型": "sample_type", "检出限": "detection_limit", "质量标记": "quality_flag", "确认状态": "confirmation", "关系证据类型": "evidence_type", "设施编号": "facility_id", "运行状态": "operating_status", "系数编号": "factor_id", "项目采用决定": "project_decision", "坐标来源": "coordinate_source", "调查日期": "survey_date"}
for _template in TEMPLATES.values():
    ALIASES.update(dict(zip(_template["labels"], _template["fields"])))
FLOW_SEMANTICS = {"measured_actual", "reported_actual", "estimated_actual", "design_capacity", "permitted_maximum"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workspace(path: str | Path) -> Path:
    raw = Path(path).expanduser()
    if not raw.exists() or not raw.is_dir():
        raise OSError("project_storage_unavailable: workspace is missing or offline; no fallback write was attempted")
    root = raw.resolve(strict=True)
    if "data_raw" in {part.casefold() for part in root.parts}:
        raise ValueError("Project measurement storage cannot be inside data_raw")
    if not (root / "project.yaml").is_file():
        raise ValueError("workspace project.yaml is missing")
    if not os_access_writable(root):
        raise OSError("project_storage_unavailable: workspace is not writable")
    return root


def os_access_writable(path: Path) -> bool:
    import os
    return os.access(path, os.W_OK)


def _manifest(root: Path) -> dict:
    path = root / "measurements" / "measurement_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": 1, "submissions": [], "review_history": [], "gate_refreshes": []}


def _registered_source_ids(root: Path) -> set[str]:
    known = set()
    workspace_manifest = read_workspace_manifest(root)
    for record in workspace_manifest.get("datasets", []):
        kind = (record.get("user_declared_type") or record.get("dataset_type") or "").casefold()
        if kind not in {"pollution_source_inventory", "source_inventory", "point_source_inventory"} or record.get("quality_status") not in {"ready", "ready_with_warnings"}: continue
        relative = record.get("standardized_path") or record.get("processed_path")
        if not relative: continue
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file(): continue
        try:
            frame = pd.read_excel(path) if path.suffix.lower() == ".xlsx" else pd.read_csv(path)
            if "source_id" in frame: known.update(frame.source_id.dropna().astype(str).str.strip())
        except Exception: continue
    for submission in _manifest(root)["submissions"]:
        if submission.get("requirement_id") == "MR01" and submission.get("status") == "accepted":
            try:
                frame, _, _ = _read_table(root / submission["original_path"])
                frame = _canonicalize(frame)
                known.update(frame.source_id.dropna().astype(str).str.strip())
            except Exception: continue
    return {value for value in known if value}


def _save(root: Path, manifest: dict) -> Path:
    path = root / "measurements" / "measurement_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def list_templates() -> list[dict]:
    return [{"requirement_id": key, "template_id": row["template_id"], "version": row["template_id"].rsplit("_v", 1)[-1], "data_type": row["data_type"], "title": row["title"], "required_fields": row["required"], "optional_fields": [f for f in row["fields"] if f not in row["required"]], "accepted_formats": [".xlsx", ".csv"]} for key, row in TEMPLATES.items()]


def list_requirements(project: str | Path, scenario: str = "water_environment_source_accounting") -> dict:
    """Use the existing resolver and keep project-measurement requirements distinct from public data."""
    root = _workspace(project)
    from hydrolite.data_requirement_resolver import resolve_scenario_requirements
    resolution = resolve_scenario_requirements(scenario, root, online=False)
    by_id = {row["requirement"]["requirement_id"]: row for row in resolution["requirements"]}
    rows = []
    for requirement_id, template in TEMPLATES.items():
        data_row = by_id.get(requirement_id, {})
        current = data_row.get("status", "project_measurement_required")
        submissions = [s for s in _manifest(root)["submissions"] if s.get("requirement_id") == requirement_id and s.get("status") not in {"rejected", "superseded"}]
        if any(s.get("status") == "accepted" for s in submissions): current = "accepted"
        elif any(s.get("status") == "needs_review" for s in submissions): current = "needs_review"
        elif any(s.get("status") == "invalid" for s in submissions): current = "validation_failed"
        elif submissions: current = "submission_received"
        row_contract = data_row.get("requirement", {})
        rows.append({"requirement_id": requirement_id, "project_id": resolution.get("project_id", root.name), "scenario_id": scenario, "data_type": template["data_type"], "business_name_zh": template["title"], "business_name_en": template["title"], "reason_required": data_row.get("reason", f"{template['title']}属于项目专属证据，公开数据不能替代。"), "blocked_capability": scenario, "required_fields": template["required"], "optional_fields": [f for f in template["fields"] if f not in template["required"]], "units": template.get("units", []), "spatial_requirements": [], "temporal_requirements": ["明确时间或时间段"] if requirement_id in {"MR02", "MR03", "MR05"} else [], "minimum_records": 1, "accepted_formats": [".xlsx", ".csv"], "validation_rules": template["template_id"], "template_id": template["template_id"], "priority": "P0", "current_status": current, "resolver_status": data_row.get("status", "project_measurement_required"), "submission_count": len(submissions)})
    return {"project": str(root), "scenario": scenario, "requirements": rows, "resolver": resolution, "summary": {"resolved": sum(r["current_status"] == "accepted" for r in rows), "missing": sum(r["current_status"] == "project_measurement_required" for r in rows), "needs_review": sum(r["current_status"] == "needs_review" for r in rows)}}


def _write_template(template_key: str, path: Path) -> Path:
    from openpyxl import Workbook
    spec = TEMPLATES[template_key]
    wb = Workbook()
    ws = wb.active
    ws.title = "数据填写"
    ws.append(spec["fields"])
    ws.append(spec["labels"])
    ws.append(spec["units"])
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A1:{chr(64 + len(spec['fields']))}1"
    guide = wb.create_sheet("填写说明")
    guide.append(["模板", spec["template_id"]])
    guide.append(["版本", spec["template_id"].rsplit("_v", 1)[-1]])
    guide.append(["数据类型", spec["title"]])
    guide.append(["注意", "仅填写真实项目证据；上传后需校验和人工审核。原始记录不会被覆盖。"])
    if template_key == "MR03":
        guide.append(["检出限", "例如 <0.05 原样保留限定符；不得替换为 0。"])
    if template_key == "MR04":
        guide.append(["河段", "最近河段仅为候选；不得自动视为已确认受纳关系。"])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def generate_templates(project: str | Path, output_dir: str | Path | None = None) -> dict:
    root = _workspace(project)
    out = Path(output_dir).resolve() if output_dir else root / "reports" / "measurement_intake" / "templates"
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key in TEMPLATES:
        xlsx = _write_template(key, out / f"{TEMPLATES[key]['template_id']}.xlsx")
        paths[key] = str(xlsx)
    request = list_requirements(root)
    pd.DataFrame([{k: row[k] for k in ("requirement_id", "business_name_zh", "reason_required", "current_status", "template_id", "priority")} for row in request["requirements"]]).to_excel(out / "user_required_data.xlsx", index=False)
    pack = out / "project_measurement_request_pack.zip"
    readme = out / "README.txt"
    readme.write_text("HydroLite 项目实测/调查数据补充包\n仅包含空白填写模板，不含项目已有数据。请勿提交敏感信息。上传后需要验证并由项目人员审核。\n", encoding="utf-8")
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(readme, "README.txt")
        archive.write(out / "user_required_data.xlsx", "user_required_data.xlsx")
        for filename in paths.values(): archive.write(filename, Path(filename).name)
    return {"templates": paths, "user_required_data": str(out / "user_required_data.xlsx"), "request_pack": str(pack)}


def _safe_spreadsheet(path: Path) -> None:
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("upload_too_large: maximum is 50 MiB")
    if path.suffix.lower() not in {".csv", ".xlsx"}:
        raise ValueError("unsupported_format: only .csv and .xlsx are accepted; macro-enabled workbooks are prohibited")
    if path.suffix.lower() == ".xlsx":
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if any(PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names):
                    raise ValueError("unsafe_xlsx_path")
                if any("externallinks/" in n.lower() or "connections.xml" in n.lower() or "vbaProject" in n for n in names):
                    raise ValueError("xlsx_external_or_macro_content_not_allowed")
                infos = archive.infolist()
                expanded = sum(i.file_size for i in infos)
                if len(infos) > 500 or expanded > 100 * 1024 * 1024 or expanded > max(path.stat().st_size * 100, 10 * 1024 * 1024):
                    raise ValueError("xlsx_expansion_limit_exceeded")
                if "xl/workbook.xml" not in names:
                    raise ValueError("malformed_xlsx")
        except zipfile.BadZipFile as exc:
            raise ValueError("malformed_xlsx") from exc


def _read_table(path: Path, sheet_name: str | None = None, expected_fields: list[str] | None = None) -> tuple[pd.DataFrame, list[str], int]:
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype=object, encoding="utf-8-sig")
        frame.attrs["source_rows"] = list(range(2, len(frame) + 2))
        return frame, [], 2
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    name = sheet_name or next((n for n in wb.sheetnames if n != "填写说明"), wb.sheetnames[0])
    if name not in wb.sheetnames: raise ValueError(f"unknown_sheet:{name}")
    ws = wb[name]
    values = list(ws.iter_rows(values_only=True))
    wb.close()
    if not values: return pd.DataFrame(), [name], 1
    def canonical_headers(row):
        return [ALIASES.get(str(value).strip(), str(value).strip()) if value is not None else "" for value in row]
    candidates = range(min(len(values), 10))
    header_index = max(candidates, key=lambda index: len(set(canonical_headers(values[index])) & set(expected_fields or ()))) if expected_fields else 0
    if expected_fields and not set(canonical_headers(values[header_index])) & set(expected_fields): header_index = 0
    headers = [str(x).strip() if x is not None else "" for x in values[header_index]]
    start = header_index + 1
    # Generated templates keep two annotation rows after their field header.
    if header_index == 0 and len(values) >= 3 and any("文本" in str(x) or "数值" in str(x) or "YYYY" in str(x) for x in values[2]): start = 3
    source_rows = [index + 1 for index, row in enumerate(values[start:], start=start) if any(value not in (None, "") for value in row)]
    rows = [list(row[:len(headers)]) for row in values[start:] if any(value not in (None, "") for value in row)]
    frame = pd.DataFrame(rows, columns=headers)
    frame.attrs["source_rows"] = source_rows
    return frame, [name], start + 1


def _canonicalize(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for column in frame.columns:
        value = str(column).strip()
        rename[column] = ALIASES.get(value, value)
    return frame.rename(columns=rename)


def _num(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError): return None


def _write_audit_xlsx(frame: pd.DataFrame, path: Path, sheet_name: str) -> None:
    # Uploaded values are untrusted; keep spreadsheet exports as literal text.
    safe = frame.map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
    safe.to_excel(path, index=False, sheet_name=sheet_name)


def _row_coordinates(row: dict) -> tuple[float, float] | None:
    lon, lat = _num(row.get("longitude")), _num(row.get("latitude"))
    if lon is not None and lat is not None: return lon, lat
    try:
        geometry = json.loads(str(row.get("geometry", "")))
        if geometry.get("type") == "Point" and len(geometry.get("coordinates", [])) == 2:
            return float(geometry["coordinates"][0]), float(geometry["coordinates"][1])
    except (ValueError, TypeError, AttributeError): pass
    return None


def validate_measurement_file(path: str | Path, template_id: str | None = None, *, source_ids: set[str] | None = None, sheet_name: str | None = None) -> dict:
    target = Path(path).expanduser().resolve()
    errors = []
    if not target.is_file(): return {"status": "invalid", "errors": [{"sheet": "", "row": 0, "column": "file", "value": str(path), "rule": "file_exists", "suggested_action": "选择已存在的 .csv 或 .xlsx 文件"}], "preview": [], "template_id": template_id}
    try:
        _safe_spreadsheet(target)
        if not template_id:
            raise ValueError("template_id_required: select one of MR01-MR06 before validating")
        key = next((k for k, v in TEMPLATES.items() if v["template_id"] == template_id), template_id)
        if key not in TEMPLATES: raise ValueError(f"unknown_template:{template_id}")
        frame, sheets, first_data_excel_row = _read_table(target, sheet_name, TEMPLATES[key]["required"])
        frame = _canonicalize(frame)
        spec = TEMPLATES[key]
        missing = sorted(set(spec["required"]) - set(frame.columns))
        if missing:
            for name in missing: errors.append({"sheet": sheets[0] if sheets else "", "row": 1, "column": name, "value": "", "rule": "required_column", "suggested_action": f"补充必需字段 {name}"})
            return {"status": "invalid", "errors": errors, "preview": frame.head(20).fillna("").to_dict("records"), "accepted_rows": 0, "invalid_rows": 0, "sheets": sheets, "template_id": spec["template_id"], "checksum": calculate_file_checksum(target)}
        if frame.empty:
            return {"status": "invalid", "errors": [{"sheet": sheets[0] if sheets else "", "row": first_data_excel_row, "column": "data", "value": "", "rule": "at_least_one_record", "suggested_action": "填写至少一条真实记录；空白模板不能提交为证据"}], "preview": [], "accepted_rows": 0, "invalid_rows": 0, "sheets": sheets, "template_id": spec["template_id"], "checksum": calculate_file_checksum(target)}
        source_ids = source_ids or set()
        invalid_rows = set()
        for index, row in frame.iterrows():
            line = frame.attrs.get("source_rows", [])[index] if frame.attrs.get("source_rows") else index + first_data_excel_row
            for field in spec["required"]:
                value = row.get(field)
                if pd.isna(value) or str(value).strip() == "":
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": field, "value": "", "rule": "required_value", "suggested_action": "按模板说明补齐；未知值不要用 0 代替"}); invalid_rows.add(index)
            if key in {"MR02", "MR03", "MR05"} and pd.notna(row.get("timestamp")):
                if pd.isna(pd.to_datetime(row.get("timestamp"), errors="coerce")):
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "timestamp", "value": str(row.get("timestamp")), "rule": "valid_timestamp", "suggested_action": "使用明确的 ISO 日期时间/期段"}); invalid_rows.add(index)
            if key in {"MR02", "MR05"}:
                value_col = "flow" if key == "MR02" else "wastewater_volume"
                number = _num(row.get(value_col))
                if number is None or number < 0:
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": value_col, "value": str(row.get(value_col)), "rule": "finite_nonnegative_value", "suggested_action": "提供非负有限实测数值及单位"}); invalid_rows.add(index)
                else:
                    from hydrolite.unit_system import validate_unit_compatibility
                    target_unit = "m3/s" if key == "MR02" else "m3"
                    unit_ok = validate_unit_compatibility(str(row.get("unit", "")), target_unit)["compatible"]
                    if key == "MR05": unit_ok = unit_ok or validate_unit_compatibility(str(row.get("unit", "")), "m3/s")["compatible"]
                    if not unit_ok:
                        errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "unit", "value": str(row.get("unit")), "rule": "compatible_volume_or_flow_unit", "suggested_action": f"使用与 {target_unit} 兼容的单位"}); invalid_rows.add(index)
            if key == "MR02" and str(row.get("flow_semantics", "")).strip() not in FLOW_SEMANTICS:
                errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "flow_semantics", "value": str(row.get("flow_semantics")), "rule": "flow_semantics", "suggested_action": "选用明确语义；设计/许可值不属于实测流量"}); invalid_rows.add(index)
            if key == "MR03":
                pollutant = str(row.get("pollutant", "")).strip()
                if pollutant not in POLLUTANTS:
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "pollutant", "value": pollutant, "rule": "supported_pollutant", "suggested_action": "限 CODMn、NH3-N、TN、TP"}); invalid_rows.add(index)
                raw = str(row.get("concentration", "")).strip()
                match = re.fullmatch(r"<\s*([0-9]+(?:\.[0-9]+)?)", raw)
                number = float(match.group(1)) if match else _num(raw)
                if number is None or number < 0:
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "concentration", "value": raw, "rule": "nonnegative_concentration", "suggested_action": "填非负数或保留 <检出限；不得填负值"}); invalid_rows.add(index)
                unit = str(row.get("unit", "")).strip().lower().replace("μ", "u")
                if unit not in {"mg/l", "mg/litre", "mg/liter", "ug/l", "μg/l", "µg/l"}:
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "unit", "value": str(row.get("unit")), "rule": "concentration_unit", "suggested_action": "使用 mg/L 或 ug/L；其他单位待人工核验"}); invalid_rows.add(index)
            if key == "MR01":
                crs = str(row.get("crs", "")).strip().upper()
                point = _row_coordinates(row)
                if point is None:
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "longitude/latitude/geometry", "value": "", "rule": "coordinate_or_point_geometry_required", "suggested_action": "填写经纬度或 GeoJSON Point 几何"}); invalid_rows.add(index)
                lon, lat = point or (None, None)
                if crs in {"EPSG:4326", "WGS84", "WGS 84"} and (lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90)):
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "longitude/latitude", "value": f"{row.get('longitude')},{row.get('latitude')}", "rule": "wgs84_bounds", "suggested_action": "核实坐标值与 WGS84/EPSG:4326 声明"}); invalid_rows.add(index)
                if not crs or crs in {"UNKNOWN", "未知"} or crs in {"GCJ-02", "BD-09"}:
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "crs", "value": str(row.get("crs")), "rule": "crs_human_review", "suggested_action": "保留原坐标系，由审核人确认；不自动伪转换"})
            if key in {"MR02", "MR03", "MR04"} and source_ids:
                source_id = str(row.get("source_id", "")).strip()
                if source_id not in source_ids:
                    errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "source_id", "value": source_id, "rule": "exact_source_id_match", "suggested_action": "补充精确 source_id 或提交人工身份核对；不按名称自动绑定"}); invalid_rows.add(index)
            if key == "MR04" and str(row.get("confirmation", "")).strip().lower() != "confirmed":
                errors.append({"sheet": sheets[0] if sheets else "", "row": line, "column": "confirmation", "value": str(row.get("confirmation")), "rule": "receiving_reach_manual_confirmation", "suggested_action": "由项目人员审核正式受纳水体/河段及证据；最近河段不可自动确认"})
        status = "invalid" if invalid_rows or any(e["rule"] == "required_column" for e in errors) else "review_required"
        return {"status": status, "errors": errors, "accepted_rows": len(frame) - len(invalid_rows), "invalid_rows": len(invalid_rows), "warning_count": sum(e["rule"].endswith("human_review") or e["rule"] == "receiving_reach_manual_confirmation" for e in errors), "preview": frame.head(20).fillna("").to_dict("records"), "sheets": sheets, "template_id": spec["template_id"], "checksum": calculate_file_checksum(target), "source_file": target.name}
    except Exception as exc:
        return {"status": "invalid", "errors": [{"sheet": sheet_name or "", "row": 0, "column": "file", "value": target.name, "rule": "safe_parse", "suggested_action": str(exc)}], "preview": [], "accepted_rows": 0, "invalid_rows": 0, "template_id": template_id, "checksum": calculate_file_checksum(target)}


def submit_measurement_file(path: str | Path, project: str | Path, requirement_id: str, template_id: str | None = None, *, submitter: str = "local_user", source_ids: set[str] | None = None, sheet_name: str | None = None) -> dict:
    root = _workspace(project)
    key = requirement_id.upper()
    if key not in TEMPLATES: raise ValueError("requirement_id must be MR01-MR06")
    spec = TEMPLATES[key]
    expected = spec["template_id"]
    if template_id not in (None, key, expected): raise ValueError("template ID does not match selected requirement")
    source = Path(path).expanduser().resolve(); _safe_spreadsheet(source)
    source_ids = set(source_ids) if source_ids is not None else _registered_source_ids(root)
    checksum = calculate_file_checksum(source)
    manifest = _manifest(root)
    if any(s.get("checksum") == checksum for s in manifest["submissions"]):
        return {"status": "duplicate_submission", "checksum": checksum}
    submission_id = "ms_" + checksum[:16]
    folder = root / "measurements" / "originals" / submission_id
    folder.mkdir(parents=True, exist_ok=False)
    destination = folder / source.name
    shutil.copy2(source, destination)
    destination.chmod(destination.stat().st_mode & ~0o222)
    validation = validate_measurement_file(destination, expected, source_ids=source_ids, sheet_name=sheet_name)
    if key in {"MR02", "MR03", "MR04"} and not source_ids:
        validation["status"] = "invalid"
        validation["errors"].append({"sheet": "", "row": 0, "column": "source_id", "value": "", "rule": "source_registry_required", "suggested_action": "先接受 MR01 或登记来源清单；再以精确 source_id 重新提交"})
    status = "invalid" if validation["status"] == "invalid" else "needs_review"
    record = {"submission_id": submission_id, "requirement_id": key, "template_id": expected, "template_version": expected.rsplit("_v", 1)[-1], "sheet_name": sheet_name, "original_path": str(destination.relative_to(root)), "checksum": checksum, "status": status, "submitter": submitter, "uploaded_at": _now(), "validation": validation}
    manifest["submissions"].append(record); _save(root, manifest)
    return record


def review_measurement_submission(project: str | Path, submission_id: str, action: str, *, reviewer: str, comment: str) -> dict:
    root = _workspace(project)
    if action not in {"accept", "reject", "keep_unresolved"} or not reviewer.strip() or not comment.strip():
        raise ValueError("action, reviewer, and non-empty comment are required")
    manifest = _manifest(root)
    row = next((s for s in manifest["submissions"] if s["submission_id"] == submission_id), None)
    if not row: raise KeyError(f"unknown submission: {submission_id}")
    if action == "accept" and (row["status"] != "needs_review" or row["validation"]["status"] != "review_required" or row["validation"].get("invalid_rows")):
        raise ValueError("submission cannot be accepted until schema and row validation pass")
    if action == "accept" and row["requirement_id"] == "MR04":
        frame, _, _ = _read_table(root / row["original_path"])
        frame = _canonicalize(frame)
        if any(str(item.get("confirmation", "")).strip().lower() != "confirmed" or (not str(item.get("reach_id", "")).strip() and not str(item.get("receiving_water", "")).strip()) or not str(item.get("evidence_type", "")).strip() for item in frame.to_dict("records")):
            raise ValueError("MR04 requires explicit human confirmation, receiving water/reach, evidence type, and review comment")
    if action == "accept" and row["requirement_id"] == "MR06":
        row["factor_approval_records"] = _approve_factor_rows(root, row, reviewer, comment)
    status = {"accept": "accepted", "reject": "rejected", "keep_unresolved": "needs_review"}[action]
    audit = {"submission_id": submission_id, "action": action, "status": status, "reviewer": reviewer, "comment": comment, "timestamp": _now(), "evidence_checksum": row["checksum"]}
    if action == "accept":
        _import_accepted(root, row, reviewer)
        for prior in manifest["submissions"]:
            if prior is not row and prior.get("requirement_id") == row["requirement_id"] and prior.get("status") == "accepted": prior["status"] = "superseded"
    row["status"] = status; row["review"] = audit
    manifest["review_history"].append(audit); _save(root, manifest)
    if action == "accept":
        try:
            audit["gate_refresh"] = refresh_measurement_gates(root)
        except Exception as exc:
            audit["gate_refresh"] = {"status": "refresh_failed", "error_class": type(exc).__name__, "error_message": str(exc), "manual_ready_override": False}
        manifest = _manifest(root)
        manifest["review_history"][-1]["gate_refresh_timestamp"] = audit["gate_refresh"].get("timestamp")
        manifest["review_history"][-1]["gate_refresh_status"] = audit["gate_refresh"].get("status", "completed")
        _save(root, manifest)
    return audit


def _approve_factor_rows(root: Path, submission: dict, reviewer: str, comment: str) -> dict:
    from hydrolite.emission_factor_approval import approve_factor
    from hydrolite.source_evidence_workflow import read_evidence_state
    from hydrolite.water_environment_contracts import EmissionFactor
    state = read_evidence_state()
    project_id = state.get("project_id")
    factors = [EmissionFactor(**item) for item in state.get("factors", [])]
    frame, _, _ = _read_table(root / submission["original_path"])
    approvals = []
    for _, row in frame.iterrows():
        factor = next((f for f in factors if f.factor_id == str(row["factor_id"])), None)
        if factor is None: raise ValueError(f"factor_id is not a verified M9A.1 factor: {row['factor_id']}")
        decision = str(row["project_decision"])
        # This is deliberately the existing M9A.1 decision API, not a parallel approval engine.
        approvals.append(approve_factor(factor, project_id, decision, actor=reviewer, comment=comment).as_dict())
    return {"project_id": project_id, "factors": [item.as_dict() for item in factors], "approvals": approvals}


def _normalized_frame(root: Path, submission: dict) -> pd.DataFrame:
    frame, _, _ = _read_table(root / submission["original_path"], submission.get("sheet_name"), TEMPLATES[submission["requirement_id"]]["required"])
    frame = _canonicalize(frame)
    key = submission["requirement_id"]
    if key == "MR03":
        values, qualifiers, limits = [], [], []
        source_limits = frame["detection_limit"] if "detection_limit" in frame else [None] * len(frame)
        for raw, unit, source_limit in zip(frame["concentration"], frame["unit"], source_limits):
            text = str(raw).strip(); match = re.fullmatch(r"<\s*([0-9]+(?:\.[0-9]+)?)", text)
            number = float(match.group(1)) if match else float(text)
            limit = _num(source_limit)
            if match and limit is None: limit = float(match.group(1))
            if str(unit).strip().lower().replace("μ", "u") in {"ug/l", "µg/l"}:
                number /= 1000
                if limit is not None: limit /= 1000
            values.append(None if match else number); qualifiers.append("<" if match else "="); limits.append(limit)
        frame["raw_concentration"] = frame["concentration"]
        frame["raw_detection_limit"] = frame.get("detection_limit")
        frame["qualifier"] = qualifiers; frame["detection_limit_mg_l"] = limits
        frame["concentration"] = values; frame["unit"] = "mg/L"
        frame = frame.rename(columns={"concentration": "value", "timestamp": "date_start"})
        frame["date_end"] = frame["date_start"]; frame["measurement_role"] = "measured_concentration"
        frame["document_reference"] = submission["original_path"]
    elif key == "MR02":
        frame = frame.rename(columns={"flow": "value", "timestamp": "date_start", "flow_semantics": "flow_kind"})
        frame["flow_kind"] = frame["flow_kind"].replace({"measured_actual": "measured_flow", "reported_actual": "reported_actual_flow", "estimated_actual": "estimated_flow", "permitted_maximum": "permitted_capacity"})
        frame["date_end"] = frame["date_start"]; frame["document_reference"] = submission["original_path"]
    elif key == "MR05":
        frame = frame.rename(columns={"facility_id": "source_id", "wastewater_volume": "value", "timestamp": "date_start"})
        frame["date_end"] = frame["date_start"]; frame["measurement_role"] = "measured_wastewater_volume"; frame["flow_kind"] = "reported_actual_flow"; frame["document_reference"] = submission["original_path"]
    elif key == "MR01":
        frame["coordinate_reference"] = frame["crs"]; frame["document_reference"] = submission["original_path"]
    elif key == "MR04":
        frame["relation_evidence"] = frame["evidence_type"].astype(str) + ":" + frame["notes"].fillna("").astype(str); frame["document_reference"] = submission["original_path"]
    elif key == "MR06":
        frame["applicability_evidence"] = frame["comment"]; frame["proposed_action"] = frame["project_decision"]; frame["document_reference"] = submission["original_path"]
    return frame


def _import_accepted(root: Path, submission: dict, reviewer: str) -> None:
    from hydrolite.data_lineage import create_lineage_record
    frame = _normalized_frame(root, submission)
    target_dir = root / "measurements" / "processed"; target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{submission['submission_id']}.csv"
    if target.exists(): raise FileExistsError(target)
    frame.to_csv(target, index=False)
    original = root / submission["original_path"]
    raw_hash, normalized_hash = calculate_file_checksum(original), calculate_file_checksum(target)
    measurement_eligible = True
    registry_path = target
    if submission["requirement_id"] == "MR02":
        eligible_frame = frame[frame["flow_kind"].astype(str).isin({"measured_flow", "reported_actual_flow"})]
        measurement_eligible = not eligible_frame.empty
        if measurement_eligible and len(eligible_frame) != len(frame):
            registry_path = target_dir / f"{submission['submission_id']}_eligible.csv"
            eligible_frame.to_csv(registry_path, index=False)
    registry_hash = calculate_file_checksum(registry_path)
    sub = {"dataset_id": "md_" + normalized_hash[:12], "original_filename": original.name, "stored_filename": registry_path.name, "source_type": "project_measurement", "source_platform": "user_submission", "source_type_reference": "project measurement", "upload_time": submission["uploaded_at"], "checksum": raw_hash, "size": original.stat().st_size, "license": "user_supplied", "processing_status": "normalized", "quality_status": "ready_with_warnings" if measurement_eligible else "needs_review", "user_declared_type": TEMPLATES[submission["requirement_id"]]["data_type"], "project_measurement_confirmed": measurement_eligible, "standardized_path": str(registry_path.relative_to(root)), "standardized_checksum": registry_hash, "processed_path": str(target.relative_to(root)), "normalized_checksum": normalized_hash, "raw_path": submission["original_path"], "submission_id": submission["submission_id"], "template_id": submission["template_id"], "reviewer": reviewer}
    manifest = read_workspace_manifest(root); manifest.setdefault("datasets", []).append(sub); write_workspace_manifest(root, manifest)
    submission["normalized_path"] = str(target.relative_to(root)); submission["normalized_checksum"] = normalized_hash
    submission["lineage"] = create_lineage_record({"dataset_id": sub["dataset_id"], "checksum": raw_hash})
    from hydrolite.data_lineage import add_lineage_operation
    add_lineage_operation("md_raw_" + submission["submission_id"], sub["dataset_id"], "measurement_normalization", root, source_checksum=raw_hash, output_checksum=normalized_hash, operator=reviewer, parameters={"template_id": submission["template_id"]}, warnings=[])
    if registry_path != target:
        add_lineage_operation(sub["dataset_id"], sub["dataset_id"] + "_eligible", "exclude_nonmeasured_flow", root, source_checksum=normalized_hash, output_checksum=registry_hash, operator="hydrolite_gate", parameters={"eligibility": ["measured_flow", "reported_actual_flow"]}, warnings=["design/estimated rows retained in normalized audit file but excluded from USER_REQUIRED readiness"])
    try:
        from hydrolite.project_versioning import create_project_version
        submission["project_version"] = create_project_version(root, created_by=reviewer, description=f"Accepted project measurement {submission['submission_id']}", snapshot_mode="referenced")
    except Exception:
        manifest = read_workspace_manifest(root)
        manifest["datasets"] = [row for row in manifest.get("datasets", []) if row.get("dataset_id") != sub["dataset_id"]]
        write_workspace_manifest(root, manifest)
        target.unlink(missing_ok=True)
        if registry_path != target: registry_path.unlink(missing_ok=True)
        raise


def refresh_measurement_gates(project: str | Path, scenario: str = "water_environment_source_accounting") -> dict:
    root = _workspace(project)
    from hydrolite.data_requirement_resolver import resolve_scenario_requirements
    result = resolve_scenario_requirements(scenario, root, online=False)
    manifest = _manifest(root)
    prior = manifest["gate_refreshes"][-1]["statuses"] if manifest["gate_refreshes"] else {}
    statuses = {row["requirement"]["requirement_id"]: row["status"] for row in result["requirements"]}
    transitions = [{"requirement_id": key, "old_status": prior.get(key, "unknown"), "new_status": value, "evidence": [s["submission_id"] for s in manifest["submissions"] if s["status"] == "accepted" and s["requirement_id"] == key], "timestamp": _now()} for key, value in statuses.items() if prior.get(key) != value]
    existing_gate = _refresh_existing_m9a2_gate(root, manifest) if scenario == "water_environment_source_accounting" else {"status": "not_applicable"}
    gate_transitions = [{"gate": "requirement:" + item["requirement_id"], "old_status": item["old_status"], "new_status": item["new_status"], "evidence": item["evidence"], "timestamp": item["timestamp"]} for item in transitions]
    gate_transitions += [{"gate": "m9a2:" + item["gate"], "old_status": item["old_status"], "new_status": item["new_status"], "evidence": [], "timestamp": _now()} for item in existing_gate.get("transitions", [])]
    refresh = {"timestamp": _now(), "scenario": scenario, "run_gate": result["run_gate"], "statuses": statuses, "transitions": transitions, "gate_transitions": gate_transitions, "blockers": result["required_blockers"], "manual_ready_override": False, "resolver": "hydrolite.data_requirement_resolver.resolve_scenario_requirements", "existing_m9a2_gate_engine": existing_gate}
    manifest["gate_refreshes"].append(refresh); _save(root, manifest)
    return refresh


def _refresh_existing_m9a2_gate(root: Path, manifest: dict) -> dict:
    """Evaluate the existing M9A.2 engine in a new M10A output; never write its frozen package."""
    from hydrolite.point_source_workflow import DEFAULT_OUTPUT as M9A2_OUTPUT, run_point_source_closure
    from hydrolite.source_evidence_workflow import read_evidence_state, _save_state
    from hydrolite.source_evidence import SourceEvidenceRecord, review_evidence
    spatial = root / "derived/m8b"
    if not all((spatial / name).is_file() for name in ("reviewed_subbasins.geojson", "reviewed_river_lines.geojson")):
        return {"status": "skipped_project_spatial_inputs_missing", "m9a2_frozen_output_modified": False}
    state = read_evidence_state(M9A2_OUTPUT)
    if not state or not state.get("project_id"):
        return {"status": "skipped_m9a2_baseline_unavailable", "m9a2_frozen_output_modified": False}
    import yaml
    from hydrolite.workspace import read_workspace_project_identity
    project_config = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8")) or {}
    workspace_id = read_workspace_project_identity(project_config, root.name)["project_id"]
    if workspace_id and workspace_id != state["project_id"]:
        return {"status": "skipped_project_id_mismatch", "workspace_project_id": workspace_id, "baseline_project_id": state["project_id"], "m9a2_frozen_output_modified": False}
    baseline_path = M9A2_OUTPUT / "m9a2_manifest.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.is_file() else {}
    baseline_gates = baseline.get("gates", {})
    baseline_checksum = calculate_file_checksum(baseline_path) if baseline_path.is_file() else None
    inventory_path = Path(__file__).resolve().parents[1] / "output/water_environment/m9a/inventory/pollution_source_inventory.xlsx"
    known_sources = set(pd.read_excel(inventory_path).source_id.astype(str)) if inventory_path.is_file() else set()
    evidence = [SourceEvidenceRecord(**item) for item in state.get("evidence", [])]
    coordinate_review_required = []
    for submission in manifest["submissions"]:
        if submission.get("status") != "accepted": continue
        key = submission["requirement_id"]
        frame, _, _ = _read_table(root / submission["original_path"])
        frame = _canonicalize(frame)
        checksum = submission["checksum"]
        reviewer = submission.get("review", {}).get("reviewer", "")
        comment = submission.get("review", {}).get("comment", "")
        for index, row in frame.iterrows():
            source_id = str(row.get("source_id", "")).strip()
            if key in {"MR01", "MR02", "MR03", "MR04"} and source_id not in known_sources: continue
            provenance = {"checksum": checksum, "identity_rule": "explicit_source_id", "context": row.to_dict(), "m10a_submission_id": submission["submission_id"]}
            common = {"evidence_id": "ev_m10a_" + sha256(f"{checksum}:{index}:{key}".encode()).hexdigest()[:16], "source_id": source_id, "file_reference": submission["original_path"], "row_reference": str(index + 2), "confidence": "high"}
            if key == "MR01":
                crs = str(row.get("crs", "")).strip().upper()
                if crs not in {"EPSG:4326", "WGS84", "WGS 84"}:
                    coordinate_review_required.append({"submission_id": submission["submission_id"], "source_id": source_id, "crs": crs or "unknown", "status": "unconverted_crs_not_used_for_spatial_gate"})
                    continue
                point = _row_coordinates(row)
                if point is None: continue
                coordinates = json.dumps({"longitude": point[0], "latitude": point[1]})
                item = SourceEvidenceRecord(**common, evidence_type="location", field_name="coordinate source", extracted_value=coordinates, spatial_reference=str(row.get("crs", "")), provenance={**provenance, "coordinate_reference": submission["original_path"]})
                evidence.append(review_evidence(item, "confirm", actor=reviewer, comment=comment))
            elif key == "MR02":
                flow_kind = {"measured_actual": "measured_flow", "reported_actual": "reported_actual_flow", "estimated_actual": "estimated_flow", "design_capacity": "design_capacity", "permitted_maximum": "permitted_capacity"}.get(str(row.get("flow_semantics")), "unknown_flow_context")
                item = SourceEvidenceRecord(**common, evidence_type="discharge_flow", field_name="measured flow" if flow_kind == "measured_flow" else flow_kind, extracted_value=float(row["flow"]), unit=str(row["unit"]), date_start=str(row["timestamp"]), date_end=str(row["timestamp"]), temporal_basis="instantaneous", provenance={**provenance, "flow_kind": flow_kind})
                try: item = review_evidence(item, "confirm", actor=reviewer, comment=comment)
                except ValueError: pass
                evidence.append(item)
            elif key == "MR03":
                raw = str(row.get("concentration", "")); match = re.fullmatch(r"<\s*([0-9]+(?:\.[0-9]+)?)", raw.strip())
                item = SourceEvidenceRecord(**common, evidence_type="measured_concentration", field_name="outfall concentration", extracted_value=raw if match else float(raw), unit=str(row["unit"]), date_start=str(row["timestamp"]), date_end=str(row["timestamp"]), temporal_basis="instantaneous", pollutant=str(row["pollutant"]), measurement_role="outfall_effluent", provenance=provenance)
                try: item = review_evidence(item, "confirm", actor=reviewer, comment=comment)
                except ValueError: pass
                evidence.append(item)
            elif key == "MR04":
                base = SourceEvidenceRecord(**common, evidence_type="receiving_water", field_name="receiving water", extracted_value=str(row["receiving_water"]), provenance={**provenance, "relation_evidence": str(row["evidence_type"])})
                evidence.append(review_evidence(base, "confirm", actor=reviewer, comment=comment))
                if pd.notna(row.get("reach_id")) and str(row.get("reach_id")).strip():
                    relation = SourceEvidenceRecord(**{**common, "evidence_id": common["evidence_id"] + "_reach"}, evidence_type="outfall_to_reach_relation", field_name="confirmed reach", extracted_value=str(row["reach_id"]), provenance={**provenance, "relation_evidence": str(row["evidence_type"])})
                    evidence.append(review_evidence(relation, "confirm", actor=reviewer, comment=comment))
    state["evidence"] = [row.as_dict() for row in evidence]
    for submission in manifest["submissions"]:
        approval = submission.get("factor_approval_records") if submission.get("status") == "accepted" else None
        if approval:
            state["factors"] = approval["factors"]
            state.setdefault("approvals", []).extend(approval["approvals"])
    output = Path(__file__).resolve().parents[1] / "output/measurement_intake/m10a/gate_engine" / root.name
    _save_state(output, state)
    try:
        result = run_point_source_closure(output_dir=output, workspace_dir=root)
        new_gates = result.get("gates", {})
        transitions = [{"gate": key, "old_status": value, "new_status": new_gates.get(key)} for key, value in baseline_gates.items() if value != new_gates.get(key)]
        current_checksum = calculate_file_checksum(baseline_path) if baseline_path.is_file() else None
        return {"status": "refreshed", "gates": new_gates, "baseline_gates": baseline_gates, "transitions": transitions, "coordinate_review_required": coordinate_review_required, "baseline_checksum_unchanged": baseline_checksum == current_checksum, "output_dir": str(output), "m9a2_frozen_output_modified": False}
    except Exception as exc:
        return {"status": "refresh_failed", "error_class": type(exc).__name__, "error_message": str(exc), "output_dir": str(output), "m9a2_frozen_output_modified": False}


def measured_load_matches(project: str | Path) -> list[dict]:
    """Only exact source + period pairs of measured/reported flow and concentrations qualify."""
    root = _workspace(project); manifest = _manifest(root)
    flow, concentration = [], []
    for sub in manifest["submissions"]:
        if sub.get("status") != "accepted" or not sub.get("normalized_path"): continue
        frame = pd.read_csv(root / sub["normalized_path"], dtype=object)
        if sub["requirement_id"] == "MR02": flow.extend(frame.to_dict("records"))
        elif sub["requirement_id"] == "MR03": concentration.extend(frame.to_dict("records"))
    rows = []
    for f in flow:
        if f.get("flow_kind") not in {"measured_actual", "reported_actual", "measured_flow", "reported_actual_flow"}: continue
        for c in concentration:
            if f.get("source_id") != c.get("source_id") or f.get("date_start") != c.get("date_start") or f.get("date_end") != c.get("date_end"): continue
            rows.append({"source_id": f["source_id"], "pollutant": c.get("pollutant"), "date_start": f["date_start"], "date_end": f["date_end"], "flow_semantics": f["flow_kind"], "concentration_qualifier": c.get("qualifier", "="), "status": "measured_load_ready" if c.get("qualifier") == "=" else "detection_limit_requires_scientific_method", "load_algorithm": "existing point_source_load.point_source_loads required for load calculation"})
    return rows


def read_frozen_m9a2_gate_baseline() -> dict:
    """Read only the exact M9A.2 manifest; never scan its directory or rewrite it."""
    path = Path.home() / ".hydrolite/workspaces/gaoqiao-river-basin-real-validation/derived/m9a2/m9a2_manifest.json"
    if not path.is_file(): return {"status": "unavailable", "gates": {}, "modified": False}
    value = json.loads(path.read_text(encoding="utf-8"))
    return {"status": "read_only", "gates": value.get("gates", {}), "sha256": calculate_file_checksum(path), "modified": False}


def write_measurement_intake_reports(project: str | Path, output_dir: str | Path) -> dict:
    root = _workspace(project); out = Path(output_dir).expanduser().resolve()
    dirs = {name: out / name for name in ("requirements", "validation", "review", "readiness", "reports")}
    for folder in dirs.values(): folder.mkdir(parents=True, exist_ok=True)
    req = list_requirements(root); manifest = _manifest(root)
    refresh = manifest["gate_refreshes"][-1] if manifest["gate_refreshes"] else {"run_gate": "not_refreshed", "statuses": {}, "transitions": [], "gate_transitions": [], "manual_ready_override": False, "resolver": "not_run"}
    _write_audit_xlsx(pd.DataFrame(req["requirements"]), dirs["requirements"] / "user_required_data.xlsx", "requirements")
    with pd.ExcelWriter(dirs["validation"] / "measurement_validation_summary.xlsx") as writer:
        submissions = pd.DataFrame([{k: s.get(k) for k in ("submission_id", "requirement_id", "status", "template_id", "checksum")} for s in manifest["submissions"]])
        submissions = submissions.map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
        submissions.to_excel(writer, sheet_name="submissions", index=False)
        errors = [{"submission_id": s["submission_id"], **error} for s in manifest["submissions"] for error in s.get("validation", {}).get("errors", [])]
        row_errors = pd.DataFrame(errors, columns=["submission_id", "sheet", "row", "column", "value", "rule", "suggested_action"])
        row_errors = row_errors.map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
        row_errors.to_excel(writer, sheet_name="row_errors", index=False)
    _write_audit_xlsx(pd.DataFrame(manifest["review_history"]), dirs["review"] / "measurement_review_history.xlsx", "reviews")
    _write_audit_xlsx(pd.DataFrame(refresh.get("gate_transitions", refresh["transitions"])), dirs["readiness"] / "gate_refresh_summary.xlsx", "transitions")
    report = dirs["reports"] / "m10a_measurement_intake_report_zh.md"
    report.write_text("# M10A 项目实测数据接入状态\n\n公开数据、项目实测/调查数据与项目审批参数分开管理。任何上传都不会自动变成 accepted；只有人工审核后才进入项目数据登记。\n\n" + "\n".join(f"- {r['requirement_id']} {r['business_name_zh']}: {r['current_status']}" for r in req["requirements"]) + f"\n\n门禁刷新：`{refresh['run_gate']}`；人工直接置 ready：禁止。\n", encoding="utf-8")
    manifest_path = dirs["reports"] / "m10a_manifest.json"
    frozen_gates = read_frozen_m9a2_gate_baseline()
    manifest_path.write_text(json.dumps({"project": root.name, "generated_at": _now(), "requirements": len(req["requirements"]), "submissions": len(manifest["submissions"]), "accepted": sum(s["status"] == "accepted" for s in manifest["submissions"]), "anonymous_demo": False, "resolver": refresh["resolver"], "gate_refresh": refresh, "frozen_m9a2_baseline": frozen_gates}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return {"requirements": dirs["requirements"] / "user_required_data.xlsx", "validation": dirs["validation"] / "measurement_validation_summary.xlsx", "review": dirs["review"] / "measurement_review_history.xlsx", "readiness": dirs["readiness"] / "gate_refresh_summary.xlsx", "report": report, "manifest": manifest_path}
