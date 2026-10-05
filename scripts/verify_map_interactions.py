"""Browser regression for viewport loading, hover and continuous wheel zoom."""
from __future__ import annotations

import json
import os
import time

from verify_map_performance import ARTIFACTS, TEMP, sync_playwright

URL = os.environ.get("REDMAP_TEST_URL", "http://127.0.0.1:8010/")


def main():
    checks, errors, external, geometry_requests = [], [], [], []

    def record(name, **details):
        checks.append({"name": name, "passed": True, **details})
        print(json.dumps(checks[-1], ensure_ascii=True), flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            headless=True,
            args=["--no-first-run", "--disable-background-networking", f"--disk-cache-dir={TEMP / 'interactions-cache'}"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda req: external.append(req.url) if not req.url.startswith(URL) else None)
        page.on("request", lambda req: geometry_requests.append(req.url) if "/api/geo/" in req.url else None)
        page.goto(URL)
        page.wait_for_function("typeof state !== 'undefined' && worldBaseLayer.getLayers().length > 100")
        record("offline_world_map_visible", countries=page.evaluate("worldBaseLayer.getLayers().length"))
        page.evaluate("() => { map.setView([35,106],4.2,{animate:false}); }")
        page.wait_for_function("typeof state !== 'undefined' && state.boundaryLevel === 'province' && boundaryLayer.getLayers().length === 34")
        assert page.locator(".province-label").count() == 34
        assert page.locator(".map-hover-label").count() == 1
        record("province_labels_visible_and_one_shared_hover_tooltip")

        def view(lat, lng, zoom, level):
            page.evaluate("v => { map.setView([v[0],v[1]],v[2],{animate:false}); }", [lat, lng, zoom])
            page.wait_for_timeout(150)
            page.wait_for_function("level => !mapMoving && state.boundaryLevel === level && boundaryRequests.size === 0", arg=level)
            page.wait_for_timeout(100)

        def hover(level):
            point = page.evaluate("""() => {
              const size=map.getSize(), rect=map.getContainer().getBoundingClientRect();
              for (let x=180; x<size.x-210; x+=23) for(let y=140;y<size.y-220;y+=23) {
                const p=L.point(x,y), lp=map.containerPointToLayerPoint(p);
                if (document.elementFromPoint(rect.left+x,rect.top+y)?.tagName !== 'CANVAS') continue;
                const layers=boundaryLayer.getLayers().filter(l => l._containsPoint(lp));
                const layer=layers[layers.length-1];
                if(layer) return {x:rect.left+x,y:rect.top+y,label:regionLabel(layer.feature.properties,layer.feature.properties.level||state.boundaryLevel)};
              }
              throw new Error('No hoverable polygon in the viewport');
            }""")
            page.mouse.move(point["x"], point["y"])
            page.wait_for_function("label => !hoverTooltip.hidden && hoverTooltip.textContent === label", arg=point["label"])
            first = page.locator(".map-hover-label").bounding_box()
            page.mouse.move(point["x"] + 8, point["y"] + 7)
            page.wait_for_timeout(70)
            second = page.locator(".map-hover-label").bounding_box()
            assert second and abs(second["x"] - first["x"] - 8) < 2
            assert " · " in point["label"]
            record(f"{level}_hover_label_tracks_pointer", label=point["label"])
            page.screenshot(path=str(ARTIFACTS / f"map-{level}-hover.png"))

        view(23.12, 113.27, 6, "province")
        record("no_city_view_while_guangdong_fits")
        view(23.12, 113.27, 8, "city")
        hover("city")
        view(23.12, 113.27, 9, "district")
        hover("district")

        before_requests = len(geometry_requests)
        before_layers = page.evaluate("Object.fromEntries([...boundaryLayers].map(([id,l])=>[id,L.stamp(l)]))")
        before_markers = page.evaluate("Object.fromEntries([...eventMarkers].map(([id,l])=>[id,L.stamp(l)]))")
        page.evaluate("() => { map.panBy([25,0],{animate:true,duration:.2}); }")
        page.wait_for_timeout(550)
        after_layers = page.evaluate("Object.fromEntries([...boundaryLayers].map(([id,l])=>[id,L.stamp(l)]))")
        after_markers = page.evaluate("Object.fromEntries([...eventMarkers].map(([id,l])=>[id,L.stamp(l)]))")
        assert len(geometry_requests) == before_requests
        shared = set(before_layers) & set(after_layers)
        assert shared and all(before_layers[key] == after_layers[key] for key in shared)
        assert all(before_markers[key] == after_markers[key] for key in set(before_markers) & set(after_markers))
        record("small_pan_reuses_cached_boundaries_and_markers", reused_polygons=len(shared))

        for lat, lng, name in [(39.9, 116.4, "北京"), (30.65, 104.06, "成都"), (25.03, 121.56, "台湾")]:
            view(lat, lng, 9, "district")
            bbox = page.evaluate("boundsArray(map.getBounds().pad(.12)).join(',')")
            expected = page.request.get(f"{URL}api/geo/district?bbox={bbox}").json()["features"]
            actual = page.evaluate("boundaryLayer.getLayers().map(l=>String(l.feature.properties.id))")
            assert set(actual) == {str(f["properties"]["id"]) for f in expected}
            record("pan_loads_all_viewport_regions", region=name, rendered=len(actual))

        view(23.12, 113.27, 9, "district")
        coordinates = page.evaluate("""() => {
          const point=map.getSize().multiplyBy(.45), rect=map.getContainer().getBoundingClientRect();
          window.__wheelAnchor=map.containerPointToLatLng(point);
          window.__wheelPoint=point;
          window.__zoomSamples=[];
          window.__recordZoom=()=>__zoomSamples.push(map.getZoom());
          map.on('zoom',__recordZoom);
          return {x:rect.left+point.x,y:rect.top+point.y};
        }""")
        page.mouse.move(coordinates["x"], coordinates["y"])
        started = time.perf_counter()
        for _ in range(12):
            page.mouse.wheel(0, -60)
            page.wait_for_timeout(20)
        page.wait_for_timeout(650)
        wheel = page.evaluate("""() => {
          map.off('zoom',__recordZoom);
          return {samples:__zoomSamples.length, zoom:map.getZoom(),
            anchor_drift_px:map.latLngToContainerPoint(__wheelAnchor).distanceTo(__wheelPoint),
            fractional_frames:__zoomSamples.filter(z=>Math.abs(z-Math.round(z))>.01).length,
            backwards_steps:__zoomSamples.filter((z,i)=>i>0&&z<__zoomSamples[i-1]-.001).length};
        }""")
        assert wheel["samples"] >= 15 and wheel["fractional_frames"] >= 10, wheel
        assert wheel["anchor_drift_px"] < 3 and abs(wheel["zoom"] - 11) < .02, wheel
        assert wheel["backwards_steps"] == 0, wheel
        record("continuous_wheel_zoom_keeps_mouse_anchor", elapsed_ms=round((time.perf_counter()-started)*1000), **wheel)
        for _ in range(8):
            page.mouse.wheel(0, 90)
            page.wait_for_timeout(20)
        page.wait_for_timeout(650)
        assert abs(page.evaluate("map.getZoom()") - 9) < .02
        record("reverse_wheel_gesture_returns_smoothly")

        # A slow, old district response must not overwrite a later national view.
        page.evaluate("""() => {
          window.__nativeFetch=window.fetch;
          window.fetch=async (...args)=>{
            const response=await __nativeFetch(...args);
            if(String(args[0]).includes('/api/geo/district')) await new Promise(r=>setTimeout(r,600));
            return response;
          };
          map.setView([45.8,126.5],9,{animate:false});
        }""")
        page.wait_for_timeout(170)
        page.evaluate("() => { map.setView([35,106],4.2,{animate:false}); }")
        page.wait_for_timeout(950)
        assert page.evaluate("state.boundaryLevel === 'province' && [...boundaryLayers.keys()].every(k=>k.startsWith('province:'))")
        page.evaluate("() => { window.fetch=window.__nativeFetch; }")
        record("late_response_cannot_overwrite_newer_zoom")

        # UI click still flies to the actual event; no instant jump substitution.
        page.locator("#event-search").fill("遵义会议")
        page.wait_for_function("visibleEvents().length > 0 && state.search === '遵义会议'")
        page.evaluate("() => { window.__flightSamples=0; window.__sampleFlight=()=>{__flightSamples++;}; map.on('move',__sampleFlight); }")
        page.locator(".story-card").first.click()
        page.wait_for_timeout(1300)
        flight = page.evaluate("""() => {
          map.off('move',__sampleFlight);
          const e=state.selected.data;
          return {title:e.title,samples:__flightSamples,distance_metres:map.getCenter().distanceTo([e.coords[1],e.coords[0]])};
        }""")
        assert flight["samples"] > 15 and flight["distance_metres"] < 2
        record("event_click_uses_smooth_flight", **flight)
        page.locator("#clear-search").click()
        for mode in ["time", "person", "ordinary"]:
            page.locator(f'[data-mode="{mode}"]').click()
            page.wait_for_timeout(150)
            assert page.evaluate("state.mode") == mode
        record("all_three_modules_remain_usable")

        page.locator("#reset-view").click()
        page.wait_for_timeout(700)
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        assert page.locator("#map").bounding_box()["width"] == 390
        page.screenshot(path=str(ARTIFACTS / "map-mobile-after.png"))
        record("responsive_mobile_layout_remains_usable")
        assert not errors, errors
        assert not external, external
        assert not any("/api/geo/city" in url and "bbox=" not in url or "/api/geo/district" in url and "bbox=" not in url for url in geometry_requests)
        record("no_javascript_errors_external_requests_or_full_district_downloads")
        browser.close()

    report = {"checks": checks, "page_errors": errors, "external_requests": external}
    (ARTIFACTS / "map-interaction-acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: {len(checks)} browser checks", flush=True)


if __name__ == "__main__":
    main()
