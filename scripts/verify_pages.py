"""Browser smoke checks for the static v1.25 special Pages build."""
from pathlib import Path
import json
import os
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("REDMAP_VERIFY_BASE", "http://127.0.0.1:4180")
report = {"status": "passed", "checks": []}
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    ai_requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: ai_requests.append(request.url) if "/api/ai" in request.url else None)
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.wait_for_function("typeof state !== 'undefined' && state.events.length > 0")
    assert page.locator("#map").is_visible()
    assert page.locator("#open-test-panel").count() == 0
    assert page.locator("#test-panel").count() == 0
    report["checks"].append("地图静态数据初始化，网页未加载 AI 面板")
    page.locator('[data-mode="time"]').click()
    page.locator("#year-input").fill("1937")
    page.locator("#year-input").dispatch_event("change")
    page.wait_for_timeout(700)
    assert page.locator("#history-controls").is_visible()
    page.locator('[data-mode="person"]').click()
    page.wait_for_timeout(500)
    assert page.locator("#person-select").is_visible()
    report["checks"].append("年份与人物模式可以切换")
    page.locator('[data-mode="ordinary"]').click()
    page.wait_for_timeout(500)
    first_event = page.locator(".event-marker").first
    if first_event.count():
        first_event.click()
        page.wait_for_timeout(500)
        assert page.locator(".event-ai").count() == 0
    assert not ai_requests, ai_requests
    report["checks"].append("事件详情不创建 AI 面板且不发起 AI 请求")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(ROOT / "static-pages-mobile.png"), full_page=True)
    report["checks"].append("手机宽度无横向溢出")
    assert not errors, errors
    browser.close()
(ROOT / "pages-acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
