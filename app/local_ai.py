"""Portable project-local model discovery and deployment."""
import json
import os
import subprocess
import threading
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent.parent
MODEL_PROJECT = Path(os.environ.get("REDMAP_LOCAL_AI_PROJECT", str(ROOT))).expanduser()
MODEL_ROOT = MODEL_PROJECT / "local-ai"
DEPLOY_ROOT = MODEL_PROJECT / "自动部署"
OPENER = build_opener(ProxyHandler({}))
LOCK = threading.Lock()
PROCESS = None

def discover():
    try:
        saved = json.loads((MODEL_ROOT / "server.json").read_text(encoding="utf-8-sig"))
        saved_port = int(saved["port"])
    except (OSError, ValueError, KeyError, TypeError):
        saved_port = 18090
    # 18092 is the port used by the bundled v1.1 local model package.
    for port in dict.fromkeys((saved_port, 18090, 18092, 1235, 1234)):
        try:
            with OPENER.open(f"http://127.0.0.1:{port}/v1/models", timeout=2) as response:
                models = json.load(response).get("data", [])
            if models:
                return {"reachable": True, "base_url": f"http://127.0.0.1:{port}/v1", "model": models[0]["id"], "provider": "local"}
        except (OSError, ValueError):
            pass
    try:
        deployment = json.loads((DEPLOY_ROOT / "logs/ai-state.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        deployment = {"phase": "idle", "message": "尚未部署本地模型"}
    return {"reachable": False, "provider": "local", "model": "", "deployment": deployment}

def start():
    global PROCESS
    with LOCK:
        status = discover()
        if status["reachable"]:
            return status
        if PROCESS is None or PROCESS.poll() is not None:
            script = DEPLOY_ROOT / "setup_ai.ps1"
            if not script.exists():
                return {**status, "starting": False, "error": "未找到本地 AI 部署脚本，请设置 REDMAP_LOCAL_AI_PROJECT"}
            PROCESS = subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], cwd=MODEL_PROJECT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {**status, "starting": True}
