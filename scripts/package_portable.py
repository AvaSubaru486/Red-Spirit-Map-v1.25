"""Build and verify an offline Windows ZIP bundle beside the project."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
# Keep delivery outside the source tree so a clean checkout can be zipped and
# extracted without accidentally including the staging directory.  Override
# with REDMAP_OUTPUT_DIR for CI or another delivery location.
AAA = Path(os.environ.get("REDMAP_OUTPUT_DIR", str(ROOT.parent / "new v1.1")))
DEPLOY = ROOT / "自动部署"
VERSION = "3.14.3"
PYTHON_URL = f"https://www.python.org/ftp/python/{VERSION}/python-{VERSION}-embed-amd64.zip"
EMBED_CACHE = DEPLOY / "cache" / "package" / f"python-{VERSION}-embed-amd64.zip"
ARCHIVE = AAA / "红色精神离线地图_便携版.zip"
PENDING_ARCHIVE = AAA / ".portable-build.zip.partial"
PACKAGE_NAME = "红色精神离线地图"
STAGE = AAA / f".stage-{uuid.uuid4().hex}"
RUNTIME_MODULES = {
    "annotated_doc", "annotated_types", "anyio", "click", "colorama", "dotenv", "fastapi",
    "h11", "httptools", "idna", "pydantic", "pydantic_core", "sniffio", "starlette",
    "typing_extensions.py", "typing_inspection", "uvicorn", "watchfiles", "websockets", "yaml",
}
DIST_INFO = {
    "annotated-doc", "annotated-types", "anyio", "click", "colorama", "fastapi", "h11", "httptools",
    "idna", "pydantic", "pydantic-core", "python-dotenv", "pyyaml", "sniffio", "starlette",
    "typing-extensions", "typing-inspection", "uvicorn", "watchfiles", "websockets",
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def ignore_build_noise(directory, names):
    return {name for name in names if name in {"__pycache__", "tests", "test", ".pytest_cache", "_distutils_hack"} or name.endswith((".pyc", ".pyo"))}


def fetch_python():
    EMBED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    if EMBED_CACHE.exists():
        return
    request = urllib.request.Request(PYTHON_URL, headers={"User-Agent": "RedHistoryOfflineMap-Builder/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response, EMBED_CACHE.open("wb") as output:
        shutil.copyfileobj(response, output)


def package_runtime():
    runtime = STAGE / "runtime"
    bundled_runtime = ROOT / "runtime"
    # Development checkouts and the delivered v1.1 tree already carry the
    # verified portable interpreter.  Reuse it when present so packaging is
    # deterministic and does not require a network download or a host venv.
    if (bundled_runtime / "python.exe").is_file():
        shutil.copytree(bundled_runtime, runtime, ignore=ignore_runtime_exclusions)
        return
    runtime.mkdir(parents=True)
    with zipfile.ZipFile(EMBED_CACHE) as archive:
        for name in archive.namelist():
            if Path(name).name != name:
                raise RuntimeError("Unexpected nested entry in the official embedded runtime")
            archive.extract(name, runtime)
    package_root = ROOT / ".venv" / "Lib" / "site-packages"
    if not package_root.is_dir():
        raise RuntimeError("缺少 runtime/python.exe 或 .venv/Lib/site-packages，无法构建便携包")
    target_packages = runtime / "Lib" / "site-packages"
    target_packages.mkdir(parents=True)
    for entry in package_root.iterdir():
        if entry.is_dir() and entry.name.lower().endswith(".dist-info"):
            package_name = entry.name.split("-", 1)[0].lower().replace("_", "-")
            if package_name in DIST_INFO:
                shutil.copytree(entry, target_packages / entry.name, ignore=ignore_build_noise)
        elif entry.name in RUNTIME_MODULES:
            destination = target_packages / entry.name
            if entry.is_dir():
                shutil.copytree(entry, destination, ignore=ignore_build_noise)
            else:
                shutil.copy2(entry, destination)
    pth = runtime / "python314._pth"
    if not pth.exists():
        raise RuntimeError("Python Embeddable Bundle did not contain python314._pth")
    # All package directories are explicit. Do not import site: user-site
    # discovery would reintroduce the host's AppData dependency directory.
    pth.write_text("python314.zip\n.\nLib/site-packages\n..\n", encoding="utf-8")
    (runtime / "portable-runtime.json").write_text(json.dumps({
        "distribution": "python-embed-amd64", "version": VERSION, "source": PYTHON_URL,
        "archive_sha256": digest(EMBED_CACHE), "site_packages_are_local": True,
        "uses_host_python_or_pip": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def ignore_runtime_exclusions(directory, names):
    path = Path(directory)
    relative = path.relative_to(ROOT)
    excluded = {"__pycache__", ".pytest_cache", "logs", "cache", "build", "raw", "backups", "bundles", "node_modules"}
    ignored = {name for name in names if name in excluded or name.endswith((".pyc", ".pyo", ".log", ".tmp"))}
    if relative == Path("自动部署"):
        ignored.update({"verify_launcher.py", "verify_portable.py", ".launcher.lock"})
    if path == ROOT / "data" / "geo":
        ignored.update({"raw", "backups", "build"})
    return ignored


def stage_project():
    for relative in ("app", "static", "data", "scripts", "tests", "自动部署"):
        shutil.copytree(ROOT / relative, STAGE / relative, ignore=ignore_runtime_exclusions)
    for relative in ("README.md", "AGENTS.md", "requirements.txt", "requirements-geo.txt"):
        shutil.copy2(ROOT / relative, STAGE / relative)
    # Include verified local GGUF assets when present; source checkouts without
    # a model remain honest and continue to package without multi-GB files.
    model_dir = ROOT / "models"
    if model_dir.is_dir() and any(path.is_file() for path in model_dir.rglob("*")):
        shutil.copytree(model_dir, STAGE / "models", ignore=ignore_runtime_exclusions)
    runtime_ai = ROOT / "runtime-ai"
    if runtime_ai.is_dir() and any(path.is_file() for path in runtime_ai.rglob("*")):
        shutil.copytree(runtime_ai, STAGE / "runtime-ai", ignore=ignore_runtime_exclusions)
    local_ai = ROOT / "local-ai"
    if local_ai.is_dir():
        shutil.copytree(local_ai, STAGE / "local-ai", ignore=lambda directory, names: {name for name in names if name.endswith((".lock", ".part"))})
    license_dir = STAGE / "data" / "geo" / "licenses"
    license_dir.mkdir(exist_ok=True)
    for filename in ("areacity_LICENSE.txt", "taiwan_atlas_LICENSE.txt"):
        source_license = ROOT / "data" / "geo" / "raw" / "admin_2026" / filename
        if not source_license.is_file():
            source_license = ROOT / "data" / "geo" / "licenses" / filename
        if source_license.is_file():
            shutil.copy2(source_license, license_dir / filename)
        else:
            (license_dir / filename).write_text(
                "Bundled offline boundary attribution; see data/geo/world_manifest.json and README.md for source and license details.\n",
                encoding="utf-8",
            )
    portable_note = ROOT / "自动部署" / "便携版使用说明.txt"
    if portable_note.is_file():
        shutil.copy2(portable_note, STAGE / "先读我.txt")
    else:
        (STAGE / "先读我.txt").write_text(
            "解压后双击 自动部署\\启动本地网站.exe。地图和历史资料均已内置；GitHub Pages 网页特殊版不加载 AI 模型。\n",
            encoding="utf-8",
        )
    package_runtime()
    hashes = {}
    for path in sorted(STAGE.rglob("*")):
        if path.is_file():
            hashes[path.relative_to(STAGE).as_posix()] = digest(path)
    (STAGE / "PACKAGE_INFO.json").write_text(json.dumps({
        "package": PACKAGE_NAME, "offline_runtime": True, "requires_installed_python": False,
        "requires_runtime_internet": False,
        "local_ai_model_bundled": any((STAGE / "local-ai" / "models").glob("*.gguf")),
        "local_ai_first_deployment_requires_internet": not any((STAGE / "local-ai" / "models").glob("*.gguf")),
        "sha256_by_file": hashes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def verify_runtime():
    runtime = STAGE / "runtime" / "python.exe"
    result = subprocess.run([str(runtime), "-B", "-X", "utf8", "-c", "import sys,fastapi,uvicorn; from app.main import app; print(sys.executable); print(len(app.routes))"],
                            cwd=STAGE, env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
                            capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(f"Portable runtime import test failed:\n{result.stdout}\n{result.stderr}")
    print(result.stdout.strip())


def create_archive():
    with zipfile.ZipFile(PENDING_ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                archive.write(path, Path(PACKAGE_NAME) / path.relative_to(STAGE))
    with zipfile.ZipFile(PENDING_ARCHIVE) as archive:
        if archive.testzip():
            raise RuntimeError("Corrupt archive member")
        exe = next((name for name in archive.namelist() if name.endswith("/自动部署/启动本地网站.exe")), None)
        if not exe or archive.read(exe)[:2] != b"MZ":
            raise RuntimeError("Deployment executable missing or invalid")
        ai_exe = next((name for name in archive.namelist() if name.endswith("/自动部署/一键部署本地AI.exe")), None)
        if not ai_exe or archive.read(ai_exe)[:2] != b"MZ":
            raise RuntimeError("Local AI executable missing or invalid")
        if not any(name.endswith("/runtime/python.exe") for name in archive.namelist()):
            raise RuntimeError("Portable Python interpreter missing")
    PENDING_ARCHIVE.replace(ARCHIVE)
    ARCHIVE.with_suffix(".zip.sha256").write_text(f"{digest(ARCHIVE)}  {ARCHIVE.name}\n", encoding="utf-8")


def main():
    if os.name != "nt":
        raise RuntimeError("The EXE bundle is Windows-only")
    AAA.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "runtime" / "python.exe").is_file():
        fetch_python()
    stage_project()
    verify_runtime()
    create_archive()
    print(json.dumps({"archive": str(ARCHIVE), "bytes": ARCHIVE.stat().st_size, "sha256": digest(ARCHIVE)}, ensure_ascii=False))
    shutil.rmtree(STAGE)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if STAGE.exists():
            shutil.rmtree(STAGE)
        raise
