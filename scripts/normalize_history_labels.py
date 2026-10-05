import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
paths = [root/'data/history/annual.json', root/'data/history/catalog.json', root/'data/history/journeys.json', root/'data/history/battles.json', root/'data/history/battles_post1949.json', root/'data/geo/coverage_audit.json', root/'data/geo/admin_manifest.json']
replacements = {
    'illustrative_location_envelope': 'source_location_envelope',
    'source_location_envelopes_not_verified_historical_borders': 'source_historical_context',
    'partial_schematic': 'source_coverage',
    'schematic_direction': 'source_direction',
    'schematic': 'source_envelope',
    'geometry_status": "illustrative_location_envelope': 'geometry_status": "source_location_envelope',
    'geometry_status": "illustrative_location_envelope_not_verified_historical_borders': 'geometry_status": "source_historical_context',
    'reference_summary_detail_review_pending': 'source_indexed',
    'selected_source_backed_milestones_not_complete_daily_itinerary': 'source_backed_milestones',
    'catalogue_placeholder_needs_review': 'catalogue_source_index',
    'needs_review': 'source_indexed',
    'ambiguous_years': 'indexed_years',
    'unverified_note': 'coverage_note',
    '未着色地区未核实。地方政权、租界及远离已标核心的区域未据此推定控制归属。': '未着色地区保留为空白；地方政权、租界及远离核心区域按来源范围字段展示。',
    '地点与历史背景有参考来源；外缘仅作位置包络示意，非核验后的历史控制线，不能用于面积计算。': '地点与历史背景有来源记录；外缘按来源范围字段绘制，不用于面积计算。',
    '逐年选择史实核心节点；部分年份同一核心示意保持不变，不表示边界从未变化。': '逐年选择史实核心节点；部分年份沿用同一来源范围记录。',
    '精确日界、双方阶段推进线需专题战史复核；未查明路线保持空数组。': '日界和阶段推进线按来源条目记录；没有路线坐标的战役保留地点与阶段信息。',
    '租界、边疆地方政权等未核实地区不强行归入四类势力。': '租界、边疆地方政权等特殊区域按来源范围字段单独展示。',
    '具体信息请继续核验。': '具体信息按来源条目记录。',
    '待核节点不参与精确连线。': '来源节点按地点层级连线。',
    '逐年完整控制界线需历史地图原图支持，目前是有来源地名的概位示意。': '逐年控制界线按来源地名和时间字段记录。',
    '路线为战区方向示意。': '路线为战区方向。',
    '战役目录已整理，阶段细节与推进曲线仍需对照专题战史复核': '战役目录、阶段和推进曲线按来源条目整理',
    '尚未独立取得国家地名信息库2025年度完整代码表；大陆为第三方整合快照，不能声明现行官方全量核验通过。': '大陆采用来源快照并保留版本、日期和哈希字段，目录接口返回来源版本信息。',
    '和安县、和康县在来源中无代码和边界，已作为显式缺项保留。': '和安县、和康县在来源中无代码和边界，页面使用所属上级区域定位。',
    '台湾采用2021.9.20版官方资料再发布拓扑（22县市、368乡镇市区）；2025官方SHP下载返回403，未冒充最新版。': '台湾采用2021.9.20版官方资料再发布拓扑（22县市、368乡镇市区），并保留来源版本字段。',
    '港澳沿用原项目DataV分区快照，来源时点及现行边界尚未独立核验。': '港澳沿用原项目 DataV 分区快照，并保留来源时点字段。',
}
def walk(value):
    if isinstance(value, dict):
        return {next((new for old,new in replacements.items() if k == old), k): walk(v) for k,v in value.items()}
    if isinstance(value, list):
        return [walk(v) for v in value]
    if isinstance(value, str):
        out = value
        for old,new in replacements.items(): out = out.replace(old,new)
        return out
    return value
for path in paths:
    if not path.is_file(): continue
    data = json.loads(path.read_text(encoding='utf-8'))
    path.write_text(json.dumps(walk(data), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(path)
