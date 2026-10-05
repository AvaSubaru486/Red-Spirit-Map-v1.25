"""Local Edge zoom/hover benchmark. Reports and browser temp files stay on D:."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "自动部署" / "logs"
TEMP = ROOT / "自动部署" / "cache" / "performance"
TEMP.mkdir(parents=True, exist_ok=True)
ARTIFACTS.mkdir(parents=True, exist_ok=True)
os.environ.update(TEMP=str(TEMP), TMP=str(TEMP), TMPDIR=str(TEMP))

from playwright.sync_api import sync_playwright

PROBE = """() => {
  window.__perf = {frames: [], tasks: [], last: performance.now(), running: true};
  window.__perf.observer = new PerformanceObserver(list => {
    __perf.tasks.push(...list.getEntries().map(e => e.duration));
  });
  __perf.observer.observe({type: 'longtask'});
  const tick = now => {
    if (!__perf.running) return;
    __perf.frames.push(now - __perf.last); __perf.last = now;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}"""
RESULT = """() => {
  __perf.running = false; __perf.observer.disconnect();
  const values = __perf.frames.filter(x => x >= 0).sort((a,b) => a-b);
  return {frames: values.length, frame_p95_ms: values[Math.floor(values.length*.95)] || 0,
    longest_frame_ms: Math.max(0, ...values), frames_over_50ms: values.filter(x => x>50).length,
    long_tasks: __perf.tasks.length, blocking_ms: __perf.tasks.reduce((a,b)=>a+Math.max(0,b-50),0),
    active_boundaries: boundaryLayer.getLayers().length, markers: eventLayer.getLayers().length,
    level: state.boundaryLevel};
}"""


def benchmark(label: str, url: str) -> dict:
    report = {"label": label, "tested_at": datetime.now().astimezone().isoformat(), "url": url}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            headless=True,
            args=["--no-first-run", "--disable-background-networking", f"--disk-cache-dir={TEMP / 'cache'}"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda req: external.append(req.url) if not req.url.startswith(url.rstrip("/")) else None)
        page.goto(url)
        page.wait_for_function("typeof state !== 'undefined' && state.events.length > 0 && boundaryLayer.getLayers().length > 0")
        page.evaluate("() => { map.setView([23.12, 113.27], 6, {animate:false}); }")
        page.wait_for_timeout(250)
        page.evaluate(PROBE)
        started = time.perf_counter()
        for zoom in (7, 8, 9):
            page.evaluate("z => { map.setZoom(z, {animate:true}); }", zoom)
            page.wait_for_timeout(400)
        page.wait_for_function("state.boundaryLevel === 'district' && boundaryLayer.getLayers().some(l => l.feature?.properties.level === 'district')", timeout=60000)
        page.wait_for_timeout(400)
        report["zoom"] = page.evaluate(RESULT)
        report["zoom"]["sequence_ms"] = round((time.perf_counter() - started) * 1000, 1)
        report["geometry_resources"] = page.evaluate("performance.getEntriesByType('resource').filter(e => e.name.includes('/api/geo')).map(e=>({url:new URL(e.name).pathname+new URL(e.name).search,bytes:e.decodedBodySize,duration_ms:e.duration}))")
        box = page.locator("#map").bounding_box()
        page.mouse.move(box["x"] + box["width"] * .52, box["y"] + box["height"] * .42)
        page.evaluate(PROBE)
        for _ in range(12):
            page.mouse.wheel(0, -60)
            page.wait_for_timeout(24)
        page.wait_for_timeout(850)
        report["wheel"] = page.evaluate(RESULT)
        page.evaluate("() => { map.setView([23.12,113.27],9,{animate:false}); }")
        page.wait_for_timeout(350)
        page.evaluate(PROBE)
        for index in range(150):
            x = box["x"] + 100 + (index % 75) * (box["width"] - 220) / 75
            y = box["y"] + box["height"] * (0.38 if index < 75 else 0.57)
            page.mouse.move(x, y)
            page.wait_for_timeout(8)
        report["hover"] = page.evaluate(RESULT)
        page.screenshot(path=str(ARTIFACTS / f"map-performance-{label}.png"))
        report["page_errors"], report["external_requests"] = errors, external
        browser.close()
    path = ARTIFACTS / f"map-performance-{label}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="after")
    parser.add_argument("--url", default="http://127.0.0.1:8010/")
    args = parser.parse_args()
    benchmark(args.label, args.url)
