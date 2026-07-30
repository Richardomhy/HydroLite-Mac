"""HydroLite Studio macOS desktop runtime helpers."""

from hydrolite.desktop.backend import start_streamlit_backend, stop_streamlit_backend
from hydrolite.desktop.desktop_diagnosis import build_desktop_diagnosis

__all__ = ["build_desktop_diagnosis", "start_streamlit_backend", "stop_streamlit_backend"]
