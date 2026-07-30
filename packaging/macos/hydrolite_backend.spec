from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parents[1]
datas = [
    (str(ROOT / "streamlit_app.py"), "."),
    (str(ROOT / ".streamlit" / "config.toml"), ".streamlit"),
]
for name in ("templates", "configs", "docs", "data_demo", "cases"):
    path = ROOT / name
    if path.exists():
        datas.append((str(path), name))
demo = ROOT / "projects" / "demo_project"
for source, destination in (
    (demo / "project.yaml", "demo_project_template"),
    (demo / "project_summary.md", "demo_project_template"),
    (demo / "cases", "demo_project_template/cases"),
    (demo / "configs", "demo_project_template/configs"),
    (demo / "data" / "README.md", "demo_project_template/data"),
):
    if source.exists():
        datas.append((str(source), destination))

streamlit_datas, streamlit_bins, streamlit_hidden = collect_all("streamlit")
datas += streamlit_datas

a = Analysis(
    [str(ROOT / "hydrolite" / "desktop" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=streamlit_bins,
    datas=datas,
    hiddenimports=streamlit_hidden + collect_submodules("hydrolite"),
    excludes=["torch", "tensorflow", "geopandas", "rasterio", "earthaccess", "cdsapi", "netCDF4", "xarray", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="hydrolite-backend", console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="hydrolite-backend")
