from __future__ import annotations

from pathlib import Path
import importlib.metadata
import platform
import socket
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "hydrolite" / "ui" / "app.py"
OUTPUT_PATH = PROJECT_ROOT / "output" / "streamlit_local_diagnosis.txt"


def _streamlit_version() -> str:
    try:
        return importlib.metadata.version("streamlit")
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _port_in_use(host: str = "127.0.0.1", port: int = 8501) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"python_version={sys.version}",
        f"python_executable={sys.executable}",
        f"platform={platform.platform()}",
        f"current_working_directory={Path.cwd()}",
        f"project_root={PROJECT_ROOT}",
        f"streamlit_version={_streamlit_version()}",
        f"app_path={APP_PATH}",
        f"app_path_exists={APP_PATH.exists()}",
        f"port_8501_in_use_before_start={_port_in_use()}",
    ]

    process: subprocess.Popen[str] | None = None
    if APP_PATH.exists() and _streamlit_version() != "not installed":
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(APP_PATH),
                    "--server.address",
                    "127.0.0.1",
                    "--server.port",
                    "8501",
                    "--server.headless",
                    "true",
                    "--browser.gatherUsageStats",
                    "false",
                ],
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            time.sleep(5)
            lines.append(f"streamlit_process_started={process.poll() is None}")
            lines.append(f"port_8501_in_use_after_start={_port_in_use()}")
        except Exception as exc:
            lines.append(f"streamlit_start_error={exc}")
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    stdout, _ = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, _ = process.communicate(timeout=5)
                lines.append("streamlit_stdout_begin")
                lines.append(stdout or "")
                lines.append("streamlit_stdout_end")
    else:
        lines.append("streamlit_start_skipped=app missing or streamlit not installed")

    lines.extend(
        [
            "local_access_suggestions:",
            "http://localhost:8501",
            "http://127.0.0.1:8501",
        ]
    )
    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote Streamlit local diagnosis to: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
