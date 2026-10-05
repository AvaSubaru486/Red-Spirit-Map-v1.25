import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data' / 'events.json'

def classify(item):
    year = int(item.get('year') or 0)
    text = ' '.join(str(item.get(k, '')) for k in ('title','period','summary','story','tags'))
    out=[]
    def add(key):
        if key not in out: out.append(key)
    if re.search(r'长征|遵义|会师|陕北', text) or 1934 <= year <= 1936: add('long_march')
    if re.search(r'抗日|抗战|敌后|卢沟桥|平型关|台儿庄|武汉会战|百团', text) or 1931 <= year <= 1945: add('anti_japanese')
    if re.search(r'建党|大革命|北伐|国共合作|黄埔|五卅|工人运动|统一战线', text) or 1921 <= year <= 1926: add('founding_revolution')
    if re.search(r'土地革命|根据地|秋收|南昌起义|井冈山|中央苏区|苏维埃|红军', text) or 1927 <= year <= 1934: add('land_revolution')
    if re.search(r'解放战争|辽沈|淮海|平津|渡江|西柏坡|解放', text) or 1946 <= year <= 1949: add('liberation_war')
    if re.search(r'建国|新中国|抗美援朝|志愿军|全国人民代表大会|五年计划|宪法|社会主义改造', text) or 1949 <= year <= 1952: add('founding_new_china')
    if re.search(r'建设|改革开放|新时代|深圳经济特区|香港回归|澳门回归|神舟|航天|空间站|嫦娥|脱贫|抗击新冠|强军|原子弹|青藏', text) or year >= 1953: add('construction_reform')
    if re.search(r'遗址|故居|纪念馆|人物生平|诞生|出生|逝世', text) or item.get('kind') != 'event': add('sites_people')
    if not out: out.append('chronicle')
    return out

data=json.loads(PATH.read_text(encoding='utf-8'))
for item in data:
    categories=classify(item)
    existing=item.get('themes') or []
    for value in existing:
        if value and value not in categories: categories.append(value)
    item['themes']=categories
    item['categories']=categories
    item['category']=categories[0]
PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print({'count':len(data), 'empty_themes':sum(not x['themes'] for x in data)})
