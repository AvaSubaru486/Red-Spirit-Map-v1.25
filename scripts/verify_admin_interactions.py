"""Directory, special hierarchies, navigation races and honest coverage in Edge."""
from __future__ import annotations
import json
from datetime import datetime
from verify_map_performance import ARTIFACTS, TEMP, sync_playwright

URL = "http://127.0.0.1:8010/"


def main():
    checks, errors, external = [], [], []
    def record(name, **details):
        checks.append({"name": name, "passed": True, **details})
        print(json.dumps(checks[-1], ensure_ascii=True), flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            headless=True, args=["--no-first-run", "--disable-background-networking", f"--disk-cache-dir={TEMP / 'admin-cache'}"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda req: external.append(req.url) if not req.url.startswith(URL) else None)
        page.goto(URL)
        page.wait_for_function("typeof adminDirectory !== 'undefined' && adminDirectory.items.size > 3600 && boundaryLayer.getLayers().length === 34")
        assert page.locator(".province-label").count() == 34
        assert page.locator("#south-sea-map").is_visible()
        page.locator("#open-region-directory").click()
        page.wait_for_function("adminDirectory.audit !== null")
        assert page.locator("#region-results .region-row").count() == 34
        assert "2 个边界待补" in page.locator("#region-audit-summary").inner_text()
        record("all_provinces_and_sea_inset_present_and_audit_honest")
        page.locator('#region-results [data-browse="440000"]').click()
        assert page.locator("#region-results .region-row").count() == 21
        terminal = page.locator('#region-results [data-locate="442000"]')
        assert "无县级下辖单位" in terminal.inner_text()
        assert page.locator('#region-results [data-browse="442000"]').count() == 0
        record("directory_browse_and_terminal_city_have_true_hierarchy")
        page.locator("#region-search").fill("110101")
        page.evaluate("() => { window.__directoryFrames=[]; window.__directorySampler=()=>__directoryFrames.push(map.getZoom()); map.on('zoom',__directorySampler); }")
        page.locator('#region-results [data-locate="110101"]').click()
        page.wait_for_function("state.selected?.data?.id === '110101' && !state.selected.loading && !mapMoving && adminDirectory.selection.getLayers().length === 1")
        page.wait_for_function("boundaryLayers.has('district:110101') && boundaryRequests.size === 0")
        page.wait_for_timeout(100)
        assert "北京市 · 东城区" in page.locator("#panel-title").inner_text()
        flight = page.evaluate("() => {map.off('zoom',__directorySampler);return {frames:__directoryFrames.length,visible:map.getBounds().contains(adminDirectory.selection.getBounds())};}")
        assert flight["frames"] > 8 and flight["visible"]
        record("county_directory_click_flies_smoothly_and_shows_full_path", **flight)
        page.screenshot(path=str(ARTIFACTS / "admin-beijing-directory.png"))

        def locate_search(query, identifier):
            page.locator("#region-search").fill(query)
            page.locator(f'#region-results [data-locate="{identifier}"]').click()
            page.wait_for_function("id => state.selected?.data?.id === id && !state.selected.loading && !mapMoving", arg=identifier)
            page.wait_for_function("id => boundaryLayers.has(`${state.boundaryLevel}:${id}`) && boundaryRequests.size === 0", arg=identifier)
            page.wait_for_timeout(100)
            assert page.evaluate("map.getBounds().contains(adminDirectory.selection.getBounds())")

        locate_search("台北 中正", "tw:63000050")
        assert "台湾省 · 台北市 · 中正区" in page.locator("#panel-title").inner_text()
        page.screenshot(path=str(ARTIFACTS / "admin-taiwan-directory.png"))
        record("taiwan_county_city_township_path_and_geometry_visible")
        for query, identifier in (("810001", "810001"), ("820001", "820001"), ("469001", "469001"), ("659012", "659012"), ("442000", "442000")):
            locate_search(query, identifier)
            record("special_region_can_be_located", identifier=identifier)
        page.screenshot(path=str(ARTIFACTS / "admin-terminal-city.png"))
        page.locator("#region-search").fill("和安县")
        page.locator('[data-locate="pending:hean"]').click()
        page.wait_for_function("state.selected?.data?.id === 'pending:hean' && !mapMoving")
        page.wait_for_timeout(600)
        assert page.evaluate("adminDirectory.selection.getLayers().length") == 0
        assert "未绘制替代县界" in page.locator("#region-location-status").inner_text()
        page.screenshot(path=str(ARTIFACTS / "admin-missing-explicit.png"))
        record("missing_geometry_is_reported_not_replaced_by_parent_polygon")

        page.evaluate("""() => {
          window.__originalGetJson=getJson;
          getJson=async function(url,...rest) {
            const result=await __originalGetJson(url,...rest);
            if(url==='/api/regions/440000/geometry') await new Promise(r=>setTimeout(r,450));
            return result;
          };
        }""")
        page.evaluate("() => { adminDirectory.locate('440000'); setTimeout(()=>adminDirectory.locate('110101'),30); }")
        page.wait_for_function("state.selected?.data?.id === '110101' && !mapMoving")
        page.wait_for_timeout(500)
        assert page.evaluate("state.selected.data.id") == "110101"
        assert page.evaluate("adminDirectory.selection.getLayers()[0].feature.properties.id") == "110101"
        page.evaluate("() => { getJson=__originalGetJson; }")
        record("late_location_response_cannot_replace_newer_selection")
        page.locator("#region-search").fill("")
        page.locator("#region-show-all").click()
        assert page.locator("#region-results .region-row").count() == 50
        page.locator("#region-load-more").click()
        assert page.locator("#region-results .region-row").count() == 100
        page.locator("#region-search").fill("臺北市")
        page.locator("#region-search").press("Enter")
        page.wait_for_function("state.selected?.data?.id === 'tw:63000' && !mapMoving")
        page.locator("#region-search").press("Escape")
        assert not page.locator("#region-directory").is_visible()
        record("pagination_keyboard_and_traditional_name_search")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(150)
        page.locator("#open-region-directory").click()
        page.locator("#region-search").fill("110101")
        page.locator('[data-locate="110101"]').click()
        page.wait_for_function("state.selected?.data?.id === '110101' && !mapMoving")
        page.wait_for_function("boundaryLayers.has('district:110101') && boundaryRequests.size === 0")
        page.wait_for_timeout(100)
        assert not page.locator("#region-directory").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(ARTIFACTS / "admin-mobile.png"))
        record("mobile_location_dismisses_directory_without_horizontal_overflow")
        assert not errors, errors
        assert not external, external
        record("no_javascript_errors_or_external_requests")
        browser.close()
    report={"tested_at":datetime.now().astimezone().isoformat(),"checks":checks,"page_errors":errors,"external_requests":external}
    (ARTIFACTS / "admin-browser-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"PASS: {len(checks)} admin browser checks",flush=True)


if __name__ == "__main__": main()
