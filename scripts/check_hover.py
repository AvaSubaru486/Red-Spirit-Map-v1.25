"""Real-pointer regression check using installed Edge; all artifacts stay local."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'
CACHE.mkdir(exist_ok=True)
os.environ['TEMP'] = os.environ['TMP'] = str(CACHE)

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        headless=True,
    )
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8010/')
    page.wait_for_function('state.events.length > 0 && boundaryLayer.getLayers().length > 0')
    for zoom, level in [(8, 'city'), (10, 'district')]:
        page.evaluate('(zoom) => { map.setView([23.14, 113.3], zoom, {animate:false}); return true; }', zoom)
        page.wait_for_function('(level) => boundaryLayer.getLayers().some((layer) => layer.feature?.properties?.level === level)', arg=level, timeout=30000)
        page.wait_for_timeout(500)
        box = page.locator('#map').bounding_box()
        page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
        page.wait_for_timeout(300)
        print(json.dumps({'level': level, 'labels': page.locator('.hover-label').all_text_contents()}, ensure_ascii=True))
        page.mouse.move(10, 10)
    print(json.dumps({'errors': errors}))
    browser.close()
