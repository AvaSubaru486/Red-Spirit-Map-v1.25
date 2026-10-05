"""End-to-end history acceptance; browser/cache/reports stay on the project disk."""
from __future__ import annotations
import json
import time
from verify_map_performance import ARTIFACTS, TEMP, PROBE, RESULT, sync_playwright

URL='http://127.0.0.1:8010/'


def main():
    checks=[]; errors=[]; external=[]
    def record(name,**details):
        checks.append({'name':name,'passed':True,**details})
        print(json.dumps(checks[-1],ensure_ascii=True),flush=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True,
            args=['--no-first-run','--disable-background-networking',f'--disk-cache-dir={TEMP / "history-cache"}'])
        page=browser.new_page(viewport={'width':1440,'height':900})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda req:external.append(req.url) if not req.url.startswith(URL) else None)
        page.goto(URL)
        page.wait_for_function("typeof state!=='undefined' && state.events.length && state.boundaryLevel==='province'")
        page.locator('[data-mode="time"]').click()
        page.wait_for_function("explorer.annual?.year===1935 && !explorer.loading")
        assert page.locator('#year-slider').input_value()=='1935'
        assert page.locator('#history-legend').is_visible()
        record('time_mode_initial_year_and_slider')

        def year(value):
            page.locator('#year-input').fill(str(value))
            page.locator('#year-input').press('Enter')
            page.wait_for_function('year=>explorer.annual?.year===year && !explorer.loading',arg=value)

        year(1948)
        assert page.locator('#year-slider').input_value()=='1948'
        assert page.locator('[data-battle="huaihai"]').count()==1
        assert page.locator('[data-battle="pingjin"]').count()==1
        assert page.evaluate('explorer.routeLines.getLayers().length')==0
        record('year_input_synchronises_slider_and_cross_year_battles')
        page.locator('[data-battle="huaihai"]').click()
        page.wait_for_function("state.selected?.data.name==='淮海战役' && explorer.routeLines.getLayers().length>0")
        page.wait_for_timeout(950)
        assert page.locator('#panel-content').inner_text().count('1949-01')>=1
        assert page.evaluate('explorer.routes.every(r=>r.start_year<=1948 && r.end_year>=1948)')
        page.screenshot(path=str(ARTIFACTS/'history-battle-detail.png'))
        record('battle_click_expands_only_current_year_routes_and_full_details')

        page.locator('#back-history').click()
        page.locator('#all-battle-routes').check()
        page.wait_for_function('explorer.routes.length>1')
        all_route_count=page.evaluate('explorer.routes.length')
        page.locator('#event-search').fill('淮海')
        page.wait_for_function("state.search==='淮海' && explorer.filteredBattles().length===1")
        page.wait_for_timeout(100)
        assert page.evaluate('explorer.annual.territories.length')>0
        assert page.locator('[data-battle]').count()==1
        record('all_routes_switch_and_search_leave_territories_intact',routes=all_route_count)
        page.locator('#clear-search').click()

        # Keyboard-accessible slider, using actual focus and key input.
        page.locator('#year-slider').focus()
        page.locator('#year-slider').press('ArrowRight')
        page.wait_for_function('explorer.annual?.year===1949 && !explorer.loading')
        assert page.locator('#year-input').input_value()=='1949'
        record('slider_keyboard_changes_year')
        year(1950)
        assert page.locator('[data-battle="hainan"]').count()==1
        year(1951)
        assert page.evaluate('explorer.areas.getLayers().length===0 && explorer.points.getLayers().length===0 && explorer.routes.length===0')
        assert not page.locator('#history-legend').is_visible()
        assert page.locator('#map-legend').is_visible()
        record('1951_restores_normal_map_without_military_layers')

        page.locator('#year-input').fill('1800'); page.locator('#year-input').press('Enter')
        page.wait_for_function('explorer.annual?.year===1921 && !explorer.loading')
        assert page.locator('#year-slider').input_value()=='1921'
        page.locator('#year-input').fill(''); page.locator('#year-input').press('Enter')
        assert page.locator('#year-input').input_value()=='1921'
        record('year_bounds_and_empty_input')

        # Deliberately delay a not-yet-cached request, then select a newer year.
        page.evaluate("""() => {
          window.__savedHistoryFetch=fetch;
          window.fetch=async(...args)=>{
            const response=await __savedHistoryFetch(...args);
            if(String(args[0]).includes('/api/history/1937'))await new Promise(r=>setTimeout(r,500));
            return response;
          };
          explorer.setYear(1937,true);
        }""")
        page.wait_for_timeout(70)
        page.evaluate('()=>{explorer.setYear(1945,true);}')
        page.wait_for_function('explorer.annual?.year===1945 && !explorer.loading')
        page.wait_for_timeout(650)
        assert page.evaluate('explorer.annual.year')==1945
        page.evaluate('()=>{window.fetch=window.__savedHistoryFetch;}')
        assert page.evaluate("explorer.annual.territories.every(a=>a.faction!=='japan')")
        record('stale_year_response_rejected_and_1945_no_japanese_control')

        year(1937)
        page.wait_for_timeout(350)
        year(1938)
        page.wait_for_timeout(350)
        elapsed=page.evaluate("""async()=>{
          const start=performance.now(); explorer.setYear(1937,true);
          while(explorer.loading||explorer.annual?.year!==1937)await new Promise(requestAnimationFrame);
          await new Promise(requestAnimationFrame);return performance.now()-start;
        }""")
        assert elapsed<300,elapsed
        record('cached_year_switch_under_300ms',milliseconds=round(elapsed,2))

        # Rapid input burst must settle on the last slider value with bounded cache.
        page.evaluate("""()=>{
          const slider=document.querySelector('#year-slider');
          for(let y=1921;y<=1950;y++){slider.value=y;slider.dispatchEvent(new Event('input',{bubbles:true}));}
          slider.dispatchEvent(new Event('change',{bubbles:true}));
        }""")
        page.wait_for_function('explorer.annual?.year===1950 && !explorer.loading')
        assert page.evaluate('explorer.cache.size')<=5
        record('rapid_slider_settles_on_latest_year_bounded_cache')

        year(1937)
        page.locator('#all-battle-routes').uncheck()
        page.evaluate('()=>{map.setView([23.12,113.27],9,{animate:false});}')
        page.wait_for_timeout(600)
        page.evaluate(PROBE)
        box=page.locator('#map').bounding_box()
        page.mouse.move(box['x']+box['width']*.45,box['y']+box['height']*.4)
        for _ in range(12):page.mouse.wheel(0,-60);page.wait_for_timeout(24)
        page.wait_for_timeout(650)
        wheel=page.evaluate(RESULT)
        record('historical_layer_continuous_zoom_measurement',**wheel)
        assert wheel['longest_frame_ms']<150,wheel

        page.locator('[data-mode="person"]').click()
        page.wait_for_function('explorer.journey?.id===state.person.id && !explorer.loading')
        assert page.evaluate('eventLayer.getLayers().length')==0
        for person in page.evaluate('state.persons.map(p=>p.id)'):
            page.locator('#person-select').select_option(person)
            page.wait_for_function('id=>explorer.journey?.id===id && !explorer.loading',arg=person)
            assert page.locator('[data-node]').count()>=10
            assert page.evaluate('explorer.routes.every(r=>r.coordinates.every(p=>p[0]>=73 && p[0]<=136 && p[1]>=18 && p[1]<=54))')
        record('ten_people_domestic_routes_correct_longitude_latitude')

        page.locator('#person-select').select_option('zhou_enlai')
        page.wait_for_function("explorer.journey?.id==='zhou_enlai' && !explorer.loading")
        overseas=page.evaluate('explorer.journey.nodes.find(n=>!n.domestic).id')
        before=page.evaluate('map.getCenter()')
        page.locator(f'[data-node="{overseas}"]').click()
        page.wait_for_timeout(120)
        assert page.evaluate('map.getCenter()')==before
        assert page.evaluate('explorer.journey.segments.every(s=>{const n=explorer.journey.nodes;return n.find(x=>x.id===s.from).domestic&&n.find(x=>x.id===s.to).domestic})')
        record('overseas_card_does_not_fly_map_or_draw_cross_border_route')

        page.locator('[data-journey-year="1936"]').click()
        page.wait_for_timeout(1000)
        assert page.evaluate("explorer.selectedNode==='year:1936' && explorer.routes.some(r=>r.active)")
        assert page.evaluate('map.getCenter().distanceTo([34.26,108.94])')<2
        page.screenshot(path=str(ARTIFACTS/'history-person-year.png'))
        record('person_year_highlight_and_smooth_location')
        page.locator('#event-search').fill('莫斯科')
        page.wait_for_timeout(120)
        assert all('莫斯科' in text for text in page.locator('[data-node]').all_inner_texts())
        record('person_search_preserves_complete_route_context')
        page.locator('#clear-search').click()

        # Region drawer must use year filtering while in time mode.
        page.locator('[data-mode="time"]').click()
        year(1935)
        page.evaluate("()=>{selectRegion({name:'贵州',level:'province'});}")
        page.wait_for_function("state.selected?.type==='region' && !state.selected.loading")
        assert page.evaluate('state.selected.stories.every(e=>e.year===1935)')
        record('region_stories_respect_selected_year')

        page.locator('[data-mode="ordinary"]').click()
        assert page.evaluate('explorer.areas.getLayers().length===0 && explorer.routes.length===0')
        page.locator('[data-mode="time"]').click()
        year(1949)
        page.locator('#reset-view').click()
        page.wait_for_timeout(650)
        page.screenshot(path=str(ARTIFACTS/'history-year-1949.png'))
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(450)
        assert page.locator('#year-slider').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=390')
        page.screenshot(path=str(ARTIFACTS/'history-mobile.png'))
        record('mobile_slider_layout_and_mode_cleanup')
        assert not errors,errors
        assert not external,external
        record('no_javascript_errors_or_external_runtime_requests')
        browser.close()
    report={'checks':checks,'errors':errors,'external_requests':external}
    (ARTIFACTS/'history-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(f'PASS: {len(checks)} checks',flush=True)


if __name__=='__main__':main()
