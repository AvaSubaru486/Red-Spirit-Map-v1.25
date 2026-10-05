"""Build separately curated military records without changing existing catalogues."""
import json
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/history"
SOURCES = {
 "longmarch":{"title":"二万五千里长征", "url":"https://news.12371.cn/2014/10/15/ARTI1413359340883737.shtml"},
 "red25":{"title":"红二十五军长征", "url":"https://www.81.mil.cn/2018byzt/2018-07/31/content_8100052.htm"},
 "meeting":{"title":"为什么说三大主力红军会师宣告了长征胜利结束", "url":"https://www.12371.cn/2012/10/19/ARTI1350595776756879.shtml"},
 "jiangtai":{"title":"我们胜利会师了", "url":"https://www.mod.gov.cn/gfbw/gfjy_index/zyhd/4848435.html"},
 "davi":{"title":"红军达维会师", "url":"https://fuwu.12371.cn/2016/07/22/ARTI1469154834425831.shtml"},
 "huaihai":{"title":"淮海战役（1948年－1949年）", "url":"https://www.81.mil.cn/2018zt/2018-04/11/content_7992664.htm"},
 "soviet":{"title":"中央苏区的创建和中华苏维埃共和国的建立", "url":"https://www.12371.cn/2022/05/04/ARTI1651624701631282.shtml"},
 "tibet":{"title":"西藏和平解放与繁荣发展", "url":"https://www.neac.gov.cn/seac/xwzx/202105/1145433.shtml"},
 "chronicle":{"title":"中国共产党一百年大事记", "url":"https://www.12371.cn/2021/06/28/ARTI1624828749818652.shtml"},
 "nanjing":{"title":"外交史上的今天：南京沦陷", "url":"https://www.mfa.gov.cn/web/ziliao_674904/historytoday_674971/200312/t20031213_9284693.shtml"},
 "wuhan":{"title":"武汉沦陷时期档案史料丛编", "url":"https://www.whda.org.cn/dawh/bycg/202512/t20251203_2689132.html"},
 "northwest":{"title":"照金：点燃西北革命火种", "url":"https://www.12371.cn/2021/08/12/ARTI1628761662936749.shtml"},
 "liaoshen-control":{"title":"为什么说三大战役奠定了我党我军全国胜利的基础", "url":"https://www.12371.cn/2022/05/06/ARTI1651832095999612.shtml"},
 "nanjing-government":{"title":"南京历史沿革", "url":"https://www.njtb.gov.cn/njjj/lsyg/"},
 "shanghai-liberation":{"title":"百年瞬间：解放大上海", "url":"https://www.12371.cn/2021/05/27/VIDE1622071681623109.shtml"},
 "red-column":{"title":"长征中的会议：红军改编", "url":"https://fuwu.12371.cn/2012/06/11/ARTI1339400564382590_13.shtml"},
}
for value in SOURCES.values():
    value.update(checked_on="2026-10-02", stored_content="source_url", precision="Published historical dates; coordinates are place markers, not surveyed troop positions")
if "--archive" in sys.argv:
    archive = OUT / "archive/military"
    archive.mkdir(parents=True, exist_ok=True)
    for key, value in SOURCES.items():
        try:
            request = urllib.request.Request(value["url"], headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=12) as response:
                content = response.read()
            path = archive / f"{key}.html"
            path.write_bytes(content)
            value.update(stored_content="offline_html_archive", archive_path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(content).hexdigest())
        except Exception as error:
            value["archive_status"] = f"download_failed: {type(error).__name__}"

places = {
 "瑞金":[116.027,25.886], "于都":[115.415,25.952], "遵义":[106.927,27.725], "吴起镇":[108.176,36.927],
 "桑植刘家坪":[110.16,29.48], "甘孜":[99.99,31.62], "将台堡":[105.89,35.83], "会宁":[105.052,35.693],
 "茂县":[103.85,31.68], "达维":[102.81,30.97], "罗山何家冲":[114.20,31.96], "独树镇":[113.17,33.30],
 "隆德":[106.12,35.62], "泾川四坡":[107.37,35.32], "永坪":[110.00,36.98], "碾庄":[117.79,34.35],
 "双堆集":[116.80,33.62], "陈官庄":[116.59,34.04],
}
units=[]
def unit(uid, name, faction, rows, source, note="史料所述到达或作战地点；点间连线仅表示先后次序，不代表实测行军路径"):
    points=[{"at":at,"location":place,"coords":places[place],"source_ids":[source],"precision":"day" if len(at)==10 else "month","event_kind":"arrival_or_documented_presence"} for at,place in rows]
    units.append({"id":uid,"name":name,"faction":faction,"start_at":points[0]["at"],"end_at":points[-1]["at"],"granularity":"day" if all(p["precision"]=="day" for p in points) else "month","waypoints":points,"source_ids":[source],"precision_note":note,"categories":["long_march" if uid.startswith("red") else "liberation"],"battle_ids":["huaihai"] if source == "huaihai" else []})
unit("red1","红一方面军（中央红军）","ccp",[("1934-10","瑞金"),("1935-01-07","遵义"),("1935-10-19","吴起镇")],"longmarch")
unit("red2","红二方面军（前期为红二、六军团）","ccp",[("1935-11","桑植刘家坪"),("1936-06","甘孜"),("1936-10-22","将台堡")],"longmarch")
units[-1]["waypoints"][-1]["source_ids"]=["jiangtai"]
unit("red4","红四方面军","ccp",[("1935-05","茂县"),("1936-10-09","会宁")],"longmarch")
units[-1]["waypoints"][-1]["source_ids"]=["meeting"]
unit("red25","红二十五军","ccp",[("1934-11-16","罗山何家冲"),("1934-11-26","独树镇"),("1935-08-17","隆德"),("1935-08-21","泾川四坡"),("1935-09-15","永坪")],"red25")
unit("red30","红四方面军第三十军李先念部","ccp",[("1935-06-12","达维")],"davi")
for uid,name in [("red1-corps","陕甘支队第一纵队（原红一军团）"),("red3-corps","陕甘支队第二纵队（原红三军团）")]:
    unit(uid,name,"ccp",[("1935-10-19","吴起镇")],"longmarch")
    units[-1]['source_ids'].append('red-column')
unit("huang-baitao","国民党第七兵团（黄百韬）","kmt",[("1948-11-11","碾庄")],"huaihai","记录被华东野战军合围的驻战地点，不推断兵团各军营的具体位置")
unit("huang-wei","国民党第十二兵团（黄维）","kmt",[("1948-11-25","双堆集")],"huaihai","记录被中原野战军包围地点，不推断兵团各军营的具体位置")
unit("east-field","华东野战军（碾庄围歼部队）","ccp",[("1948-11-11","碾庄")],"huaihai","战役部队所在区域标记，不代表全军集中于同一坐标")
unit("central-field","中原野战军（双堆集围歼部队）","ccp",[("1948-11-25","双堆集")],"huaihai","战役部队所在区域标记，不代表全军集中于同一坐标")

catalog=json.loads((ROOT/"data/geo/admin_catalog.json").read_text(encoding="utf-8"))["items"]
records=[]
def record(uid, ids, level, faction, start, end, source, note, kind="control", owner=None):
    records.append({"id":uid,"admin_ids":ids,"level":level,"faction":faction,"owner":owner or {"ccp":"中国共产党领导的政权","kmt":"国民党政权","japan":"日本侵略军"}[faction],"kind":kind,"start_at":start,"end_at":end,"source_ids":[source],"precision_note":note})
county_names={"瑞金市","会昌县","于都县","安远县","信丰县","寻乌县","兴国县","宁都县","广昌县","石城县","黎川县","建宁县","泰宁县","宁化县","清流县","长汀县","连城县","上杭县","永定区"}
ids=[i["id"] for i in catalog if i["level"]=="district" and i["name"] in county_names and i["id"][:2] in {"35", "36"}]
record("central-soviet-named-counties",ids,"district","ccp","1933-01-01","1933-12-31","soviet","中央苏区发展时期的史料列举辖县概览；年内不提供逐日控制边界；以现代同名县面表示范围，不意味着县内每处同时完全受控")
record("nanjing-occupied-core",["320102","320104"],"district","japan","1937-12-13","1945-08-15","nanjing","日军攻陷南京城区；以现代玄武、秦淮两区表示主城地理载体，不扩展到现代南京市全部郊县")
record("wuhan-occupied-core",["420102","420103","420104","420105","420106"],"district","japan","1938-10-25","1945-08-15","wuhan","武汉三镇沦陷记录；只选择现代中心城区载体，非武汉现代全域沦陷边界复原")
record("northwest-six-counties",["610681","610621","610622","610603","610625","610824"],"district","ccp","1935-06-30","1935-12-31","northwest","史料列明西北红军占领安定、延长、延川、安塞、保安、靖边六座县城；县面仅承载地名和根据地概览，不表示县内全域同时受控",kind="base")
record("nanjing-nationalist-capital",["320102","320104"],"district","kmt","1927-04-18","1937-12-12","nanjing-government","南京国民政府首都中心城区载体，不推断江苏全省控制")
record("nanjing-nationalist-postwar",["320102","320104"],"district","kmt","1946-05-05","1949-04-22","nanjing-government","战后还都南京至南京解放前的中心城区行政载体")
record("nanjing-liberated",["320102","320104"],"district","ccp","1949-04-23","1951-12-31","nanjing-government","南京解放；现代中心城区面承载史料地点，不复原逐街控制线")
northeast_cities=[i['id'] for i in catalog if i['level']=='city' and i.get('parent') in {'210000','220000','230000'} and i['id']!='210200']
record("northeast-liberated",northeast_cities,"city","ccp","1948-11-02","1951-12-31","liaoshen-control","辽沈战役结束后东北解放的区域概览；现代地市载体不裁定边境，并排除现代大连市以免把旅大苏军驻留区归为本记录")
record("shanghai-liberated-core",["310101","310104","310105","310106","310107","310109","310110"],"district","ccp","1949-05-27","1951-12-31","shanghai-liberation","上海市区解放的来源记录；现代中心城区载体，不推断当时的全市郊县范围")
# Post-1951 provinces are explicit named administrative carriers, not proximity inference.
mainland=[i["id"] for i in catalog if i["level"]=="province" and i["id"] not in {"710000","810000","820000"}]
record("mainland-prc",mainland,"province","ccp","1952-01-01","2100-12-31","chronicle","现代省级面表示中国大陆行政管辖；边境争议区及历史行政变化不由此图裁定",owner="中华人民共和国")
record("hongkong-return",["810000"],"province","ccp","1997-07-01","2100-12-31","chronicle","表示香港特别行政区由中华人民共和国恢复行使主权，并非地方政党执政分类",owner="中华人民共和国香港特别行政区")
record("macao-return",["820000"],"province","ccp","1999-12-20","2100-12-31","chronicle","表示澳门特别行政区由中华人民共和国恢复行使主权，并非地方政党执政分类",owner="中华人民共和国澳门特别行政区")
for name,data in [("unit-movements.json",{"schema_version":1,"units":units}),("control-records.json",{"schema_version":1,"records":records}),("military-sources.json",SOURCES)]:
    if name == "military-sources.json" and "--archive" not in sys.argv:
        saved = OUT/name
        if saved.exists():
            previous = json.loads(saved.read_text(encoding="utf-8"))
            for key in SOURCES:
                if key in previous: SOURCES[key].update(previous[key])
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"Built {len(units)} units and {len(records)} sourced control records")
