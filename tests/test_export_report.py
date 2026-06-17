from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import zipfile


def _snapshot_data_raw() -> dict[str, tuple[int, int]]:
    root = Path("data_raw")
    if not root.exists():
        return {}
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_export_report_module_imports():
    import hydrolite.export_report as export_report

    assert callable(export_report.collect_project_report_data)
    assert callable(export_report.render_project_report_docx)
    assert callable(export_report.export_project_report_bundle)


def test_project_report_generates_core_formats(tmp_path: Path):
    from hydrolite.export_report import (
        collect_project_report_data,
        render_project_report_docx,
        render_project_report_html,
        render_project_report_markdown,
        render_project_report_pdf,
    )
    from hydrolite.project import create_project

    before = _snapshot_data_raw()
    project_dir = tmp_path / "report_demo_project"
    create_project(project_dir)

    data = collect_project_report_data(project_dir)
    assert data["project_name"]

    markdown = render_project_report_markdown(project_dir)
    docx = render_project_report_docx(project_dir)
    html = render_project_report_html(project_dir)
    pdf_or_note = render_project_report_pdf(project_dir)

    assert markdown.exists()
    assert docx.exists()
    assert html.exists()
    assert pdf_or_note.exists()
    assert pdf_or_note.name in {"project_report.pdf", "project_report_pdf_unavailable.md"}
    assert "Executive Summary" in markdown.read_text(encoding="utf-8")
    assert _snapshot_data_raw() == before


def test_project_report_bundle_is_safe(tmp_path: Path):
    from hydrolite.export_report import export_project_report_bundle
    from hydrolite.project import create_project

    project_dir = tmp_path / "report_demo_project"
    create_project(project_dir)
    forbidden = project_dir / "external" / "model.ckpt"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_text("do not package", encoding="utf-8")
    secret = project_dir / "reports" / "service-account.json"
    secret.write_text("{}", encoding="utf-8")

    bundle = export_project_report_bundle(project_dir)
    assert bundle.exists()
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
    assert "reports/project_report.md" in names
    assert "reports/project_report.docx" in names
    assert not any(name.startswith("external/") for name in names)
    assert not any("service-account" in name for name in names)
    assert not any(name.endswith((".pt", ".pth", ".ckpt", ".onnx")) for name in names)


def test_report_cli_project_and_docx(tmp_path: Path):
    from hydrolite.project import create_project

    project_dir = tmp_path / "report_cli_project"
    create_project(project_dir)
    for command in ("docx", "project"):
        completed = subprocess.run(
            [sys.executable, "-m", "hydrolite", "report", command, str(project_dir)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (project_dir / "reports" / "project_report.docx").exists()
    assert (project_dir / "reports" / "project_report_bundle.zip").exists()


def test_report_export_page_imports():
    import hydrolite.ui.pages.report_export as page

    assert callable(page.render)


def test_report_export_does_not_track_secrets_weights_or_external_repo():
    completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=False, timeout=60)
    tracked = completed.stdout.splitlines()
    assert not any(path.endswith((".pt", ".pth", ".ckpt", ".onnx")) for path in tracked)
    assert not any("secrets.toml" in path or "credentials" in path.lower() for path in tracked)
    assert not any(path.startswith("external/") for path in tracked)
