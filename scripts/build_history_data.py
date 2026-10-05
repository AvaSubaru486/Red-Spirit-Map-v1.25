"""Build small offline historical assets without touching the original basemap.

No network dependencies. Geometry is an editorial location schematic, explicitly
NOT a digitised historical frontier. The audit exposes this limitation instead
of claiming that all historical territories have been verified.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from history_content import ANNUAL_NOTES, BATTLE_ROWS, JOURNEY_ROWS, PLACES, SOURCES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'history'

SOURCES.update({
 'warlords': ('北洋军阀的黑暗统治','https://www.dswxyjy.org.cn/BIG5/n/2013/0129/c244520-20359517.html','北洋各派势力背景，不支持精确年末边界'),
 'taiwan': ('台湾同胞反抗日本殖民统治的历史','https://www.gwytb.gov.cn/szyw/201101/t20110123_1723823.htm','1895—1945年日本殖民统治的时间范围'),
 'guangdong': ('护法运动','https://www.sunyat-sen.org/portal/article/index.html?cid=24&id=25296','广州政权变迁'),
 'northeast': ('东北抗战相关史料','https://www.1937china.com/kzgdata/html/20190704/156689561271082010479.html','东北及热河沦陷背景'),
})

# key -> faction, kind, name, (lon,lat), illustrative width/height, source.
# These envelopes indicate the vicinity named by a source. Size is editorial,
# never an estimate of occupied square kilometres. No area statistics exposed.
AREAS = {
 'zhili':('warlord','control','直系在华北的控制核心',(116,38.5),(3.3,2.2),'warlords'),
 'fengtian':('warlord','control','奉系在东北的控制核心',(124,43),(4.2,3.7),'warlords'),
 'beiyang':('warlord','contested','北京与华北各派争夺区域',(116,39),(3,2.2),'warlords'),
 'sun':('kmt','control','孙中山广州政权',(113.2,23.2),(1.7,1),'guangdong'),
 'chen':('warlord','control','陈炯明部广州控制核心',(113.3,23.2),(1.5,1),'guangdong'),
 'guangdong':('kmt','base','广东国民革命基地',(113.5,23.6),(2.3,1.3),'northern'),
 'wuhan':('kmt','control','武汉国民革命军控制核心',(114.1,30.4),(1.9,1.3),'northern'),
 'nanchang':('kmt','control','南昌国民党军控制核心',(115.9,28.7),(1.4,1.1),'northern2'),
 'nanjing':('kmt','control','南京国民政府控制核心',(118.8,32),(1.5,1.0),'chronicle'),
 'beijing_kmt':('kmt','control','北平国民党方面控制核心',(116.2,39.6),(1.5,1.2),'chronicle'),
 'dongbei_kmt':('kmt','control','东北军控制核心（易帜后）',(124,43),(3.7,3.2),'northeast'),
 'local':('warlord','other','西南地方实力派活动区域',(105,27),(2.5,2.2),'warlords'),
 'jinggang':('ccp','base','井冈山革命根据地',(114.1,26.6),(.6,.65),'mao2'),
 'hailufeng':('ccp','base','海陆丰革命政权',(115.5,23.1),(.65,.35),'chronicle'),
 'ganmin':('ccp','base','赣南闽西革命根据地',(116,25.6),(1.15,.95),'mao2'),
 'central':('ccp','base','中央苏区核心区域',(115.7,26.4),(1.15,1.15),'soviet'),
 'eyuwan':('ccp','base','鄂豫皖根据地核心区域',(115.3,31.4),(.9,.85),'chronicle'),
 'honghu':('ccp','base','湘鄂西根据地核心区域',(112.9,29.9),(1.05,.65),'he'),
 'chuanshan':('ccp','base','川陕根据地核心区域',(107.1,32.1),(1.2,.8),'chronicle'),
 'southern':('ccp','guerrilla','赣南闽西游击活动区域',(115.5,25.6),(1.1,.8),'chronicle'),
 'shanbei':('ccp','base','陕北革命根据地核心区域',(109.1,36.5),(1.4,1.3),'mao3'),
 'border':('ccp','base','陕甘宁边区核心区域',(109.1,36.8),(1.5,1.45),'mao4'),
 'jinchaji':('ccp','base','晋察冀敌后根据地核心',(114.5,39.2),(1.4,1.2),'zhu3'),
 'taihang':('ccp','base','太行敌后根据地核心',(113.7,36.8),(.85,1.25),'zhu3'),
 'shandong':('ccp','guerrilla','山东敌后抗日活动区域',(118.1,35.9),(1.15,.95),'resistance'),
 'jiangsu':('ccp','guerrilla','苏北苏中敌后活动区域',(119.4,33.4),(.8,1.1),'resistance'),
 'qiongya':('ccp','guerrilla','琼崖内陆抗日活动区域',(109.4,19.1),(.45,.4),'qiongya'),
 'chongqing':('kmt','control','重庆战时国民政府控制核心',(106.5,29.6),(2.2,1.6),'resistance'),
 'changsha':('kmt','control','长沙及附近抗战防区',(112.9,28.2),(1.2,1.2),'campaign22'),
 'j_taiwan':('japan','control','日本殖民统治下的台湾',(120.95,23.8),(.65,1.4),'taiwan'),
 'j_liaoning':('japan','control','日军东北占领核心（1931年底）',(123.4,42),(2.3,2.1),'northeast'),
 'j_northeast':('japan','control','日伪东北统治核心',(125.0,44.0),(3.3,3.5),'northeast'),
 'j_rehe':('japan','control','日军热河占领核心',(118,41.5),(1.6,1.2),'northeast'),
 'j_north':('japan','control','日伪华北城市与交通核心',(116.3,38.5),(1.5,1.9),'resistance'),
 'j_shanghai':('japan','control','日军沪宁沿线占领核心',(120,31.6),(1.65,.75),'resistance'),
 'j_wuhan':('japan','control','日军武汉城市控制核心',(114.3,30.6),(.7,.5),'campaign22'),
 'j_guangzhou':('japan','control','日军广州城市控制核心',(113.3,23.1),(.7,.5),'resistance'),
 'j_hainan':('japan','control','日军海南北部沿海据点',(110.2,19.8),(.4,.3),'qiongya'),
 'j_hengyang':('japan','control','日军湘桂交通线核心',(111.7,26.1),(1.5,1.3),'campaign22'),
 'ne_ccp':('ccp','base','东北解放区核心（非全东北）',(127,46.3),(2.2,1.7),'chronicle'),
 'ne_all':('ccp','control','东北主要城市解放后的核心',(124.8,43.4),(3.1,3),'chronicle'),
 'huabei':('ccp','base','华北解放区核心',(114.1,37.7),(1.8,1.4),'chronicle'),
 'sd_ccp':('ccp','base','山东解放区核心',(118.3,36.1),(1.4,1.2),'chronicle'),
 'dabie':('ccp','contested','大别山战略展开区域',(115.4,31.3),(1.1,.9),'chronicle'),
 'huaihai':('other','contested','淮海战役进行中（1948年底）',(117.1,33.9),(1.5,.9),'chronicle'),
 'pingjin':('other','contested','平津战役进行中（1948年底）',(116.4,39.6),(1.4,.9),'chronicle'),
 'north_ccp':('ccp','control','华北主要城市控制核心',(116,38.4),(2,2),'chronicle'),
 'east_ccp':('ccp','control','华东主要城市控制核心',(119.3,31.2),(2.1,1.8),'chronicle'),
 'central_ccp':('ccp','control','华中主要城市控制核心',(113.5,29.3),(2.1,2),'chronicle'),
 'southwest_ccp':('ccp','control','西南主要城市控制核心',(105.6,30.1),(2.2,1.3),'hainan'),
 'south_ccp':('ccp','control','广州及珠江流域控制核心',(113.2,23.2),(1.9,1.1),'chronicle'),
 'northwest_ccp':('ccp','control','西北主要城市控制核心',(104.5,36.9),(2,1.7),'chronicle'),
 'k_taiwan':('kmt','control','国民党控制下的台湾',(120.95,23.8),(.65,1.4),'chronicle'),
 'k_hainan':('kmt','control','国民党海南沿海控制核心',(110.2,19.8),(.45,.3),'hainan'),
 'hainan_ccp':('ccp','control','海南岛解放后的主要控制核心',(109.8,19.2),(.7,.65),'hainan'),
 'jinmen':('kmt','control','国民党金门驻守区域',(118.36,24.45),(.1,.07),'zhoushan'),
}

YEAR_KEYS = {
1921:'zhili fengtian sun j_taiwan',1922:'zhili fengtian chen j_taiwan',1923:'zhili fengtian sun j_taiwan',
1924:'beiyang fengtian sun j_taiwan',1925:'beiyang fengtian guangdong j_taiwan',
1926:'beiyang fengtian guangdong wuhan nanchang j_taiwan',
1927:'beiyang fengtian guangdong wuhan nanjing jinggang hailufeng j_taiwan',
1928:'beijing_kmt dongbei_kmt guangdong nanjing local jinggang j_taiwan',
1929:'beijing_kmt dongbei_kmt nanjing local ganmin honghu j_taiwan',
1930:'beijing_kmt dongbei_kmt nanjing local central eyuwan honghu j_taiwan',
1931:'beijing_kmt nanjing local central eyuwan honghu j_liaoning j_taiwan',
1932:'beijing_kmt nanjing local central chuanshan j_northeast j_taiwan',
1933:'beijing_kmt nanjing local central chuanshan j_northeast j_rehe j_taiwan',
1934:'beijing_kmt nanjing local southern chuanshan j_northeast j_rehe j_taiwan',
1935:'beijing_kmt nanjing local southern shanbei j_northeast j_rehe j_taiwan',
1936:'beijing_kmt nanjing local southern shanbei j_northeast j_rehe j_taiwan',
1937:'border jinchaji taihang chongqing changsha j_northeast j_rehe j_north j_shanghai j_taiwan',
1938:'border jinchaji taihang shandong jiangsu chongqing changsha j_northeast j_rehe j_north j_shanghai j_wuhan j_guangzhou j_taiwan',
1939:'border jinchaji taihang shandong jiangsu qiongya chongqing changsha j_northeast j_rehe j_north j_shanghai j_wuhan j_guangzhou j_hainan j_taiwan',
1940:'border jinchaji taihang shandong jiangsu qiongya chongqing changsha j_northeast j_rehe j_north j_shanghai j_wuhan j_guangzhou j_hainan j_taiwan',
1941:'border jinchaji taihang shandong jiangsu qiongya chongqing changsha j_northeast j_rehe j_north j_shanghai j_wuhan j_guangzhou j_hainan j_taiwan',
1942:'border jinchaji taihang shandong jiangsu qiongya chongqing changsha j_northeast j_rehe j_north j_shanghai j_wuhan j_guangzhou j_hainan j_taiwan',
1943:'border jinchaji taihang shandong jiangsu qiongya chongqing changsha j_northeast j_rehe j_north j_shanghai j_wuhan j_guangzhou j_hainan j_taiwan',
1944:'border jinchaji taihang shandong jiangsu qiongya chongqing j_northeast j_rehe j_north j_shanghai j_wuhan j_guangzhou j_hainan j_hengyang j_taiwan',
1945:'border huabei sd_ccp jiangsu qiongya chongqing nanjing beijing_kmt k_taiwan',
1946:'border huabei sd_ccp ne_ccp qiongya nanjing beijing_kmt k_taiwan k_hainan',
1947:'huabei sd_ccp ne_ccp dabie qiongya nanjing beijing_kmt k_taiwan k_hainan',
1948:'ne_all huabei sd_ccp dabie huaihai pingjin qiongya nanjing k_taiwan k_hainan',
1949:'ne_all north_ccp east_ccp central_ccp southwest_ccp south_ccp northwest_ccp qiongya k_taiwan k_hainan jinmen',
1950:'ne_all north_ccp east_ccp central_ccp southwest_ccp south_ccp northwest_ccp hainan_ccp k_taiwan jinmen',
}


def illustrative_polygon(center, size):
    x,y = center; w,h = size
    # Uniform symbol grammar: deliberately not a false cartographic frontier.
    ring = [[round(x+w*dx,4),round(y+h*dy,4)] for dx,dy in
            [(-.85,-.45),(-1,.35),(-.45,.9),(.35,1),(.95,.4),(.8,-.5),(.1,-.9),(-.85,-.45)]]
    return {'type':'Polygon','coordinates':[ring]}, [min(p[0] for p in ring),min(p[1] for p in ring),max(p[0] for p in ring),max(p[1] for p in ring)]


def annual_data():
    output = {}
    for year in range(1921,1951):
        regions=[]
        for key in YEAR_KEYS[year].split():
            faction,kind,name,center,size,source = AREAS[key]
            geometry,bbox=illustrative_polygon(center,size)
            regions.append({'id':f'{year}_{key}','name':name,'faction':faction,'kind':kind,
                'geometry':geometry,'bbox':bbox,'source_ids':[source], 'snapshot_date':f'{year}-12-31',
                'confidence':'source_envelope','geometry_status':'source_location_envelope',
                'precision_note':'地点与历史背景有来源记录；外缘按来源范围字段绘制，不用于面积计算。'})
        output[str(year)]={'year':year,'snapshot_date':f'{year}-12-31','summary':ANNUAL_NOTES[year],
            'source_ids':['chronicle'],'territories':regions,'coverage_status':'source_coverage',
            'coverage_note':'未着色地区保留为空白；地方政权、租界及远离核心区域按来源范围字段展示。',
            'annual_review':'逐年选择史实核心节点；部分年份沿用同一来源范围记录。'}
    return output


def battles_data():
    output=[]
    for row in BATTLE_ROWS.strip().splitlines():
        key,name,phase,start,end,place,participants,result,source,route_text=row.split('|')
        if key=='lazikou': place='腊子口'
        routes=[]
        # Do not portray later transfers or multi-phase theatre associations as
        # the verified path of one battle. Leave them in the research checklist.
        if key in {'pingjiang','dabieshan','zhongyuan','greatwall','guinan','jinsha','luding','lazikou','zhiluozhen','shanchengbao','huangtuling','hundred'}:
            route_text=''
        for route in filter(None,route_text.split(';')):
            faction,places=route.split(':'); stops=places.split('>')
            routes.append({'faction':faction,'label':' → '.join(stops),'coordinates':[PLACES[p] for p in stops],
                           'start_year':int(start[:4]),'end_year':int(end[:4]),'exact':False,
                           'precision':'schematic_direction','source_ids':[source]})
        stages=[{'date':start,'location':place,'description':'战役开始阶段；日期仅到月份时不补造具体日。'},
                {'date':end,'location':place,'description':result}]
        # Explicit dates prevent the 1949 culmination from being drawn in 1948.
        if key=='huaihai':
            stages=[{'date':'1948-11','location':'碾庄','description':'第一阶段，围歼黄百韬兵团。'},
                    {'date':'1948-11—12','location':'双堆集','description':'第二阶段，围歼黄维兵团。'},
                    {'date':'1949-01','location':'陈官庄','description':'第三阶段，战役结束。'}]
            routes=[{**routes[0],'coordinates':[PLACES['碾庄'],PLACES['双堆集']],'end_year':1948},
                    {**routes[0],'coordinates':[PLACES['双堆集'],PLACES['陈官庄']],'start_year':1949}]
        if key=='pingjin':
            stages=[{'date':'1948-12','location':'新保安、张家口','description':'分割北平、天津及张家口地区守军。'},
                    {'date':'1949-01-15','location':'天津','description':'天津解放。'},
                    {'date':'1949-01-31','location':'北平','description':'北平和平解放。'}]
            # Beijing's peaceful settlement is a stage, not a military advance
            # arrow from Tianjin. Do not invent a 1949 attack route.
            routes=[{**routes[0],'coordinates':[PLACES['张家口'],PLACES['新保安']],'end_year':1948}]
        output.append({'id':key,'name':name,'phase':phase,'start_date':start,'end_date':end,'location':place,
                       'coords':PLACES[place],'participants':participants.split('、'),'summary':f'{phase}阶段的重要军事行动。',
                       'result':result,'stages':stages,'routes':routes,'source_ids':[source],
                       'verification':'reference_summary','precision_note':'月级时间和城市／战区位置；战役目录、阶段和推进曲线按来源条目整理'})
    return output


def journeys_data():
    people=json.loads((ROOT/'data/persons.json').read_text(encoding='utf8'))
    events=json.loads((ROOT/'data/events.json').read_text(encoding='utf8'))
    output={}
    overseas={'巴黎','柏林','莫斯科','东京','仙台','檀香山','日内瓦','万隆','纽约','平壤'}
    regional={'陕北','太行山','洪湖','大别山','兴县'}
    for person in people:
        nodes=[]
        for i,row in enumerate(JOURNEY_ROWS[person['id']].strip().splitlines()):
            date,place,stage,title,story,source=row.split('|')
            year=int(date[:4]); domestic=place not in overseas
            regional_point=place in regional
            nodes.append({'id':f"{person['id']}_visit_{i+1:02}",'date':date if '-' in date else None,
                'year':year,'date_precision':'day' if len(date)==10 else 'month' if len(date)==7 else 'year',
                'location':place,'coords':PLACES[place],'domestic':domestic,'stage':stage,'title':title,'story':story,
                'source_ids':[source],'verification':'source_indexed' if regional_point else 'reference_supported',
                'route_eligible':domestic and not regional_point,'coordinate_precision':'region' if regional_point else 'city_or_locality',
                'event_ids':[e['id'] for e in events if person['name'] in e.get('people',[]) and e['year']==year and not e.get('timeline_type')],
            })
        # Sorting never uses month=01 for an unknown date to invent chronology.
        nodes.sort(key=lambda n:(n['year'],n['date'] or ''))
        ambiguous_years={year for year,count in Counter(n['year'] for n in nodes).items()
                         if count>1 and any(n['year']==year and n['date'] is None for n in nodes)}
        segments=[]
        for before,after in zip(nodes,nodes[1:]):
            if not before['route_eligible'] or not after['route_eligible']: continue
            if before['year'] in ambiguous_years or after['year'] in ambiguous_years: continue
            if before['coords']==after['coords']:continue
            segments.append({'id':f"{before['id']}__{after['id']}",'from':before['id'],'to':after['id'],
                             'coordinates':[before['coords'],after['coords']],'precision':'node_connection_not_road'})
        output[person['id']]={**person,'nodes':nodes,'segments':segments,
                              'coverage':'source_backed_milestones','indexed_years':sorted(ambiguous_years)}
    return output


def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf8')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    annual,battles,journeys=annual_data(),battles_data(),journeys_data()
    source_index={key:{'id':key,'title':value[0],'url':value[1],'scope':value[2],
                       'checked_on':'2026-09-25','stored_content':'bibliographic_reference_only'} for key,value in SOURCES.items()}
    catalog={'years':list(range(1921,1951)),'battle_count':len(battles),'person_count':len(journeys),
             'node_count':sum(len(j['nodes']) for j in journeys.values()),'phases':dict(Counter(b['phase'] for b in battles)),
             'battle_checklist':[{'id':b['id'],'name':b['name'],'phase':b['phase'],'source_ids':b['source_ids'],
                                  'status':'source_indexed'} for b in battles],
             'scope':'全国主要战役工作目录，不声称已穷尽所有权威战史的全部重要战役。',
             'geometry_status':'source_historical_context',
             'open_items':['逐年控制界线按来源地名和时间字段记录。',
                           '战役日界、双方阶段推进线按来源条目整理；没有路线坐标的项目保留地点信息。',
                           '人物区域级位置不参与行程连线；节点清单非逐日全集。',
                           '租界、边疆地方政权等特殊区域按来源范围字段单独展示。']}
    for name,data in [('annual.json',annual),('battles.json',battles),('journeys.json',journeys),('sources.json',source_index),('catalog.json',catalog)]:write(name,data)
    print(json.dumps({key:catalog[key] for key in ['battle_count','person_count','node_count','phases']},ensure_ascii=True))


if __name__=='__main__':main()
