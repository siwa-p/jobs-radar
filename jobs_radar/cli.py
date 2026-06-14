import subprocess
import sys
from importlib.resources import files


def serve():
    from jobs_radar.config import settings
    import uvicorn
    uvicorn.run(
        "jobs_radar.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


def ui():
    ui_path = str(files("jobs_radar") / "ui.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", ui_path])
