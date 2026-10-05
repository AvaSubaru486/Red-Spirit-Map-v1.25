"""Cache pinned public source snapshots on D:; never called by the web app."""
from __future__ import annotations

import hashlib
import json
import subprocess
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "geo" / "raw" / "admin_2026"
VERSION = "2025.251231.260403"
BASE = f"https://raw.githubusercontent.com/xiangyuecn/AreaCity-JsSpider-StatsGov/{VERSION}/"
# The release tag is immutable; source URLs, dates, and checksums are retained.
SOURCES = {
    "areacity_roster.csv": BASE + quote("src/采集到的数据/ok_data_level3.csv"),
    "areacity_README.md": BASE + "README.md",
    "areacity_LICENSE.txt": BASE + "LICENSE",
    "areacity_geo.7z": f"https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov/releases/download/{VERSION}/ok_geo.csv.7z",
    "taiwan_atlas_towns.topo.json": "https://cdn.jsdelivr.net/npm/taiwan-atlas@2021.9.20/towns-10t.json",
    "taiwan_atlas_README.md": "https://cdn.jsdelivr.net/npm/taiwan-atlas@2021.9.20/README.md",
    "taiwan_atlas_LICENSE.txt": "https://cdn.jsdelivr.net/npm/taiwan-atlas@2021.9.20/LICENSE",
    "mca_publication_notice.html": "https://www.mca.gov.cn/n156/n186/index.html",
}


def fetch(entry: tuple[str, str]) -> dict:
    filename, url = entry
    target = RAW / filename
    if not target.exists():
        request = Request(url, headers={"User-Agent": "OfflineRedHistoryMap/1.0 (source preparation)"})
        context = None
        if url.startswith("https://www.tgos.tw/"):
            # Python 3.13+ strict RFC checks reject this public download's
            # legacy chain (missing SKI). Keep CA and hostname verification;
            # only relax the new extension-conformance flag for this host.
            context = ssl.create_default_context()
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        with urlopen(request, timeout=90, context=context) as response:
            payload = response.read(200 * 1024 * 1024)
        target.write_bytes(payload)
    payload = target.read_bytes()
    return {"file": filename, "url": url, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        entries = list(pool.map(fetch, SOURCES.items()))
    unavailable = []
    for dataset_id, label in ((7442, "taiwan_county"), (7441, "taiwan_town")):
        try:
            metadata_entry = fetch((f"{label}_metadata.json", f"https://data.gov.tw/api/v2/rest/dataset/{dataset_id}"))
            entries.append(metadata_entry)
            metadata = json.loads((RAW / metadata_entry["file"]).read_text(encoding="utf-8"))["result"]
            resource = next(r for r in metadata["distribution"] if r["resourceFormat"] == "SHP")
            entries.append(fetch((f"{label}.zip", quote(resource["resourceDownloadUrl"], safe=":/?=&%"))))
        except Exception as exc:
            unavailable.append({"dataset": dataset_id, "error": str(exc)})
    archive = RAW / "areacity_geo.7z"
    sevenzip = Path(r"C:\Program Files\7-Zip\7z.exe")
    if not (RAW / "ok_geo.csv").exists():
        subprocess.run([str(sevenzip), "x", str(archive), "ok_geo.csv", f"-o{RAW}", "-y"], check=True, capture_output=True)
    if not (RAW / "ok_geo.csv").exists():
        raise RuntimeError("Expected ok_geo.csv was not found in the pinned archive")
    metadata = {
        "release": VERSION,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "publisher": "AreaCity (third-party aggregation; not an official publication)",
        "source_crs": "GCJ-02",
        "taiwan_crs": "TWD97 geographic EPSG:3824 (effectively WGS84 at display scale)",
        "known_source_omissions": ["和安县", "和康县"],
        "unavailable_official_downloads": unavailable,
        "files": entries,
    }
    (RAW / "sources.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
