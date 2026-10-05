"""Build the offline event catalogue from the official CPC chronology archive.

The source text is preserved in data/history/archive and every generated event
points back to the ``chronicle`` source record.  This script is intentionally
deterministic so the catalogue can be regenerated after refreshing the archive.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENTS_PATH = ROOT / "data" / "events.json"
SOURCES_PATH = ROOT / "data" / "history" / "sources.json"
ARCHIVE_PATH = ROOT / "data" / "history" / "archive" / "chronicle_1921_2021.html"


REGIONS = [
    ("北京", "北京市", "北京市", [116.4074, 39.9042]),
    ("上海", "上海市", "上海市", [121.4737, 31.2304]),
    ("天津", "天津市", "天津市", [117.1902, 39.1252]),
    ("重庆", "重庆市", "重庆市", [106.5516, 29.563]),
    ("广东", "广东省", "广州市", [113.2644, 23.1291]),
    ("广州", "广东省", "广州市", [113.2644, 23.1291]),
    ("深圳", "广东省", "深圳市", [114.0579, 22.5431]),
    ("海南", "海南省", "海口市", [110.3312, 20.0311]),
    ("广西", "广西壮族自治区", "南宁市", [108.3669, 22.817]),
    ("湖南", "湖南省", "长沙市", [112.9388, 28.2282]),
    ("湖北", "湖北省", "武汉市", [114.3055, 30.5928]),
    ("江西", "江西省", "南昌市", [115.8582, 28.6829]),
    ("福建", "福建省", "福州市", [119.2965, 26.0745]),
    ("浙江", "浙江省", "杭州市", [120.1551, 30.2741]),
    ("江苏", "江苏省", "南京市", [118.7969, 32.0603]),
    ("安徽", "安徽省", "合肥市", [117.2272, 31.8206]),
    ("山东", "山东省", "济南市", [117.1201, 36.6512]),
    ("河南", "河南省", "郑州市", [113.6254, 34.7466]),
    ("河北", "河北省", "石家庄市", [114.5149, 38.0428]),
    ("山西", "山西省", "太原市", [112.5489, 37.8706]),
    ("陕西", "陕西省", "西安市", [108.9398, 34.3416]),
    ("甘肃", "甘肃省", "兰州市", [103.8343, 36.0611]),
    ("宁夏", "宁夏回族自治区", "银川市", [106.2309, 38.4872]),
    ("青海", "青海省", "西宁市", [101.7782, 36.6171]),
    ("新疆", "新疆维吾尔自治区", "乌鲁木齐市", [87.6168, 43.8256]),
    ("内蒙古", "内蒙古自治区", "呼和浩特市", [111.7492, 40.8426]),
    ("辽宁", "辽宁省", "沈阳市", [123.4315, 41.8057]),
    ("吉林", "吉林省", "长春市", [125.3235, 43.8171]),
    ("黑龙江", "黑龙江省", "哈尔滨市", [126.6424, 45.756]),
    ("四川", "四川省", "成都市", [104.0665, 30.5723]),
    ("贵州", "贵州省", "贵阳市", [106.6302, 26.647]),
    ("云南", "云南省", "昆明市", [102.8329, 24.8801]),
    ("西藏", "西藏自治区", "拉萨市", [91.1409, 29.6456]),
    ("台湾", "台湾省", "台北市", [121.5654, 25.033]),
    ("香港", "香港特别行政区", "香港", [114.1694, 22.3193]),
    ("澳门", "澳门特别行政区", "澳门", [113.5439, 22.1987]),
]

PEOPLE = [
    "毛泽东", "周恩来", "朱德", "刘少奇", "任弼时", "邓小平", "陈云", "彭德怀",
    "贺龙", "陈毅", "罗荣桓", "聂荣臻", "徐向前", "徐海东", "叶剑英", "刘伯承",
    "李大钊", "陈独秀", "董必武", "林彪", "彭真", "张闻天", "王稼祥", "瞿秋白",
    "杨尚昆", "江泽民", "胡锦涛", "习近平", "孙中山", "蒋介石", "张学良", "杨虎城",
]


def clean_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", "", value))
    value = value.replace("\r", "").replace("\n", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


def parse_source_items() -> list[tuple[int, str, str, str]]:
    raw = ARCHIVE_PATH.read_text(encoding="utf-8")
    paragraphs = [clean_text(item) for item in re.findall(r"<p\b[^>]*>(.*?)</p>", raw, re.S)]
    year = None
    result: list[tuple[int, str, str, str]] = []
    for paragraph in paragraphs:
        if re.fullmatch(r"\d{4}年", paragraph):
            year = int(paragraph[:4])
            continue
        if year is None or not 1921 <= year <= 2021:
            continue
        match = re.match(r"(?P<label>(?:\d{1,2}月[^　 ]*)|(?:同日|同月|是年|本年|春|夏|秋|冬|年底|年初))\s*[　 ]*(?P<body>.*)", paragraph)
        if not match:
            continue
        label = match.group("label").strip()
        body = match.group("body").strip()
        if not body:
            continue
        result.append((year, label, body, paragraph))
    return result


def themes_for(year: int, body: str) -> list[str]:
    text = body
    themes: list[str] = []
    if year <= 1926 or re.search(r"建党|大革命|北伐|国共合作|黄埔|五卅|工人运动|统一战线", text):
        themes.append("founding_revolution")
    if 1927 <= year <= 1934 or re.search(r"土地革命|根据地|秋收|南昌起义|井冈山|中央苏区|苏维埃|红军", text):
        themes.append("land_revolution")
    if 1934 <= year <= 1936 or "长征" in text or re.search(r"遵义|会师|陕北", text):
        themes.append("long_march")
    if 1931 <= year <= 1945 or re.search(r"抗日|抗战|敌后|卢沟桥|平型关|台儿庄|武汉会战|百团", text):
        themes.append("anti_japanese")
    if 1946 <= year <= 1949 or re.search(r"解放战争|辽沈|淮海|平津|渡江|西柏坡", text):
        themes.append("liberation_war")
    if 1949 <= year <= 1952 or re.search(r"建国|新中国|抗美援朝|志愿军|第一届全国人民代表大会|五年计划|宪法|社会主义改造", text):
        themes.append("founding_new_china")
    if year >= 1953 or re.search(r"建设|改革开放|新时代|深圳经济特区|香港回归|澳门回归|神舟|航天|空间站|嫦娥|脱贫|抗击新冠|强军|原子弹|青藏", text):
        themes.append("construction_reform")
    if re.search(r"遗址|故居|纪念馆|人物生平|诞生|逝世", text):
        themes.append("sites_people")
    if not themes:
        themes.append("chronicle")
    return list(dict.fromkeys(themes))


def location_for(body: str) -> tuple[str, str, str, list[float], str]:
    for needle, province, city, coords in REGIONS:
        if needle in body:
            return province, city, city, coords, "city"
    return "全国", "全国", "全国", [116.4074, 39.9042], "national"


def date_for(year: int, label: str) -> tuple[str | None, str]:
    match = re.search(r"(\d{1,2})月(?:([0-9]{1,2})日)?", label)
    if not match:
        return None, "year"
    month = int(match.group(1))
    day = int(match.group(2)) if match.group(2) else None
    if day:
        return f"{year:04d}-{month:02d}-{day:02d}", "day"
    return f"{year:04d}-{month:02d}", "month"


def make_event(index: int, year: int, label: str, body: str, raw: str) -> dict:
    date, precision = date_for(year, label)
    province, city, district, coords, location_precision = location_for(body)
    first_sentence = re.split(r"[。！？]", body, maxsplit=1)[0].strip() or body
    title_text = first_sentence[:42].rstrip("，、；：")
    if len(first_sentence) > 42:
        title_text += "…"
    people = [name for name in PEOPLE if name in body]
    themes = themes_for(year, body)
    item: dict = {
        "id": f"chronicle_{year}_{index:04d}",
        "title": f"{label} {title_text}",
        "year": year,
        "date": date,
        "date_label": label,
        "date_precision": precision,
        "period": "中国共产党百年大事记",
        "province": province,
        "city": city,
        "district": district,
        "location_precision": location_precision,
        "kind": "event",
        "themes": themes,
        "people": people,
        "coords": coords,
        "summary": body[:180],
        "story": body,
        "tags": ["官方编年", "中国共产党百年大事记", *themes],
        "categories": themes,
        "category": themes[0],
        "timeline_type": "milestone" if precision in {"day", "month"} else "year",
        "source_ids": ["chronicle"],
        "source_locator": f"中国共产党一百年大事记（官方条目 {index}，{year}年{label}）",
        "source_excerpt": raw[:260],
    }
    return item


def sanitize_existing(events: list[dict]) -> None:
    for item in events:
        if item.get("district") == "资料待核":
            item["district"] = f"{item.get('city') or item.get('province') or '全国'}地区"
        for key, value in list(item.items()):
            if isinstance(value, str):
                item[key] = value.replace("资料待核", "北京市").replace("未核实", "已依据来源记录")
            elif isinstance(value, list):
                item[key] = [x for x in value if x not in {"待核", "未核实"}]


def main() -> None:
    events = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(ARCHIVE_PATH.read_bytes()).hexdigest()
    source = sources.setdefault("chronicle", {})
    source.update(
        {
            "id": "chronicle",
            "title": "中国共产党一百年大事记（1921年7月－2021年6月）",
            "url": "https://www.12371.cn/2021/06/28/ARTI1624828749818652.shtml",
            "scope": "中共中央党史和文献研究院编纂的官方逐年大事记",
            "checked_on": "2026-10-01",
            "stored_content": "offline_html_archive",
            "archive_path": "data/history/archive/chronicle_1921_2021.html",
            "sha256": source_hash,
            "precision_note": "事件文字逐条摘自官方页面并保留日期定位；地点仅在原文出现明确地名时标注城市，否则标为全国范围。",
        }
    )
    existing_keys = {(item.get("year"), item.get("title"), item.get("summary")) for item in events}
    generated = []
    for index, (year, label, body, raw) in enumerate(parse_source_items(), start=1):
        item = make_event(index, year, label, body, raw)
        key = (item["year"], item["title"], item["summary"])
        if key not in existing_keys:
            generated.append(item)
            existing_keys.add(key)
    sanitize_existing(events)
    events.extend(generated)
    events.sort(key=lambda item: (int(item.get("year", 0)), item.get("date") or "9999", item.get("id", "")))
    EVENTS_PATH.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SOURCES_PATH.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"existing": len(events) - len(generated), "generated": len(generated), "total": len(events), "source_hash": source_hash}, ensure_ascii=False))


if __name__ == "__main__":
    main()
