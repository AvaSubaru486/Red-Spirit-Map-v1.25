"""Export deterministic static data for Pages. Uses only Python's standard library."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import json
import re
import shutil
import gzip

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'dist'
DATA = ROOT / 'data'
COMPACT = ('id','code','name','level','parent','full_name','ancestor_ids','bbox','label_point','child_count','geometry_status','coverage_status','aliases')

def read(path):
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8-sig'))
    compressed = path.with_name(path.name + '.gz')
    if compressed.exists():
        with gzip.open(compressed, 'rt', encoding='utf-8-sig') as handle:
            return json.load(handle)
    parts = sorted(path.parent.glob(path.name + '.gz.part*'))
    if parts:
        compressed_bytes = b''.join(part.read_bytes() for part in parts)
        return json.loads(gzip.decompress(compressed_bytes).decode('utf-8-sig'))
    raise FileNotFoundError(path)

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

def bounds(geometry):
    result = [float('inf'), float('inf'), -float('inf'), -float('inf')]
    def walk(points):
        if not points: return
        if isinstance(points[0], (int, float)):
            x, y = points[:2]
            result[0] = min(result[0], x); result[1] = min(result[1], y)
            result[2] = max(result[2], x); result[3] = max(result[3], y)
        else:
            for child in points: walk(child)
    walk(geometry['coordinates'])
    return result

def build():
    if OUT.exists():
        if OUT.is_symlink() or OUT.resolve().parent != ROOT.resolve() or OUT.name != 'dist':
            raise ValueError('Refusing to clean an unexpected build directory')
        shutil.rmtree(OUT)
    OUT.mkdir(exist_ok=True)
    shutil.copytree(ROOT / 'static', OUT / 'static', dirs_exist_ok=True, ignore=shutil.ignore_patterns('index.html'))
    # Source index remains compatible with the preserved Python server.
    page = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    page = page.replace('href="/static/', 'href="static/').replace('src="/static/', 'src="static/')
    page = page.replace('<script src="static/vendor/leaflet.js">', '<script src="static/data-client-v11.js"></script>\n    <script src="static/site-integration.js"></script>\n    <script src="static/vendor/leaflet.js">')
    page = page.replace('本地离线资料库', '静态历史资料库')
    (OUT / 'index.html').write_text(page, encoding='utf-8')
    # Do not publish the redundant backend-only entrypoint.
    (OUT / '.nojekyll').touch()
    catalog = read(DATA / 'geo/admin_catalog.json')
    items = catalog['items']
    version = catalog['version']
    write(OUT / 'data/geo-index.json', {level: [{key: item.get(key) for key in COMPACT} for item in items if item['level'] == level] for level in ('province','city','district')})
    for name in ('events.json','persons.json','routes.json'):
        write(OUT / 'data' / name, read(DATA / name))
    for name in ('annual.json','battles.json','battles_post1949.json','journeys.json','sources.json','catalog.json','control-records.json','military-sources.json','unit-movements.json'):
        write(OUT / 'data/history' / name, read(DATA / 'history' / name))
    write(OUT / 'data/geo-status.json', read(DATA / 'geo/coverage_audit.json'))
    write(OUT / 'data/world.json', read(DATA / 'geo/world.json'))
    write(OUT / 'data/regions.json', {item['id']: item for item in items})
    shutil.copytree(DATA / 'geo/licenses', OUT / 'data/licenses', dirs_exist_ok=True)
    source = {}
    for level in ('province','city','district','south_china_sea'):
        source[level] = [{**feature, 'bbox': bounds(feature['geometry'])} for feature in read(DATA / f'geo/{level}.json')['features']]
    display = {level: list(features) for level, features in source.items()}
    display['city'] += [{**f,'properties':{**f['properties'],'display_role':'direct_province'}} for f in source['province'] if f['properties']['id'] in ('110000','120000','310000','500000','810000','820000')]
    display['city'] += [f for f in source['district'] if f['properties']['parent'] in ('410000','420000','460000','650000')]
    display['district'] += [{**f,'properties':{**f['properties'],'display_role':'terminal_city'}} for f in source['city'] if f['properties'].get('coverage_status') == 'no_county_level_units']
    manifest = {'version': version, 'levels': {}, 'regions': {}}
    for level, features in display.items():
        groups = defaultdict(list)
        for feature in features:
            group = 'all' if level in ('province','south_china_sea') else feature['properties'].get('parent', '100000')
            groups[group].append(feature)
        chunks = []
        for group, rows in sorted(groups.items()):
            slug = re.sub(r'[^A-Za-z0-9_-]', '_', str(group))
            path = f'geo/{level}/{slug}.json'
            extent = [min(f['bbox'][0] for f in rows), min(f['bbox'][1] for f in rows), max(f['bbox'][2] for f in rows), max(f['bbox'][3] for f in rows)]
            write(OUT / 'data' / path, {'type':'FeatureCollection','features':rows})
            chunks.append({'path':path,'bbox':extent,'count':len(rows)})
            for feature in rows:
                props = feature['properties']
                if props.get('level') == level:
                    manifest['regions'][str(props['id'])] = path
        manifest['levels'][level] = {'chunks':chunks,'order':[f['properties']['id'] for f in features],'source_count':len(features),'canonical_count':len(source[level])}
    write(OUT / 'data/geo-manifest.json', manifest)
    total = sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())
    print(f'Static map built: {sum(len(v["chunks"]) for v in manifest["levels"].values())} chunks, {total/1e6:.1f} MB. No Python server needed.')

if __name__ == '__main__':
    build()
