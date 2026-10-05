/* Static read-only equivalent of the preserved FastAPI queries. No network API. */
(() => {
  const base = new URL('../data/', document.currentScript.src);
  const cache = new Map();
  const geometryKeys = new Set();
  const MAX_GEOMETRY = 32;
  const intersects = (a, b) => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
  async function read(path) {
    if (cache.has(path)) {
      if (geometryKeys.has(path)) { geometryKeys.delete(path); geometryKeys.add(path); }
      return cache.get(path);
    }
    const request = fetch(new URL(path, base)).then(response => {
      if (!response.ok) throw new Error(`数据加载失败（${response.status}），请重试`);
      return response.json();
    }).catch(error => { cache.delete(path); geometryKeys.delete(path); throw error; });
    cache.set(path, request);
    if (path.startsWith('geo/')) {
      geometryKeys.add(path);
      while (geometryKeys.size > MAX_GEOMETRY) { const oldest = geometryKeys.values().next().value; geometryKeys.delete(oldest); cache.delete(oldest); }
    }
    return request;
  }
  function failure(message, status = 404) { const error = new Error(message); error.status = status; throw error; }
  function bbox(value) {
    if (value == null) return null;
    const b = value.split(',').map(Number);
    if (b.length !== 4 || b.some(n => !Number.isFinite(n)) || value.split(',').some(n => !n.trim()) || !(b[0] >= -180 && b[2] <= 180 && b[0] <= b[2] && b[1] >= -90 && b[3] <= 90 && b[1] <= b[3])) failure('bbox 必须是有效的西、南、东、北四个经纬度', 422);
    return b;
  }
  function yearValue(value, minimum = 1921, maximum = 2100) {
    if (value == null) return null;
    const number = Number(value);
    if (!/^\d+$/.test(value) || number < minimum || number > maximum) failure('年份不在有效范围内', 422);
    return number;
  }
  async function geo(level, bounds) {
    const manifest = await read('geo-manifest.json');
    const layer = manifest.levels[level];
    if (!layer) failure('无效行政层级', 422);
    const chunks = layer.chunks.filter(chunk => !bounds || intersects(chunk.bbox, bounds));
    // Limit concurrent requests, especially when testing the complete world view.
    const payloads = [];
    for (let i = 0; i < chunks.length; i += 6) payloads.push(...await Promise.all(chunks.slice(i, i + 6).map(chunk => read(chunk.path))));
    const order = new Map(layer.order.map((id,index) => [id,index]));
    const features = payloads.flatMap(chunk => chunk.features).filter(feature => !bounds || intersects(feature.bbox, bounds));
    features.sort((a,b) => order.get(a.properties.id)-order.get(b.properties.id));
    return {type:'FeatureCollection',features,source_count:layer.source_count,canonical_count:layer.canonical_count,version:manifest.version};
  }
  async function sourceRecords(ids) {
    const source = await read('history/sources.json');
    return [...new Set(ids)].filter(id => id in source).map(id => source[id]);
  }
  const compact = item => Object.fromEntries(['id','code','name','level','parent','full_name','ancestor_ids','bbox','label_point','child_count','geometry_status','coverage_status','aliases'].map(key => [key,item[key] ?? null]));
  const normalize = value => value.normalize('NFKC').replaceAll('臺','台').toLowerCase();
  async function query(url) {
    const {pathname, searchParams: params} = new URL(url, location.origin);
    const parts = pathname.split('/').filter(Boolean).map(decodeURIComponent);
    if (parts[0] !== 'api') failure('不支持的数据查询');
    const resource = parts[1], id = parts[2];
    if (resource === 'health') return {status:'ok',mode:'static'};
    if (resource === 'geo-index') return read('geo-index.json');
    if (resource === 'geo-status') return read('geo-status.json');
    if (resource === 'geo') return geo(id, bbox(params.get('bbox')));
    if (resource === 'history-catalog') return read('history/catalog.json');
    if (resource === 'events') {
      const all = await read('events.json');
      if (id) return all.find(event => event.id === id) || failure('未找到该历史内容');
      const mode = params.get('mode') || 'ordinary', year = yearValue(params.get('year'));
      if (!['ordinary','long_march','anti_japanese','time','person'].includes(mode)) failure('无效模式',422);
      const person = params.get('person'), region = params.get('region'), kind = params.get('kind');
      if (kind && !['event','residence','site','memorial','building'].includes(kind)) failure('无效类型',422);
      const items = all.filter(item => (!['long_march','anti_japanese'].includes(mode) || (item.themes || []).includes(mode)) && (year == null || item.year === year) && (mode !== 'person' || !person || (item.people || []).includes(person)) && (!region || [item.province,item.city,item.district].includes(region)) && (!kind || item.kind === kind));
      return {items,count:items.length,mode,year};
    }
    if (resource === 'persons') {
      if (!id) return {items:await read('persons.json')};
      const journeys = await read('history/journeys.json');
      const item = journeys[id];
      if (!item) failure('未找到该人物行程');
      return {...item,sources:await sourceRecords(item.nodes.flatMap(node => node.source_ids))};
    }
    if (resource === 'routes') {
      if (!['ordinary','long_march','anti_japanese','person'].includes(id)) failure('无效路线模式',422);
      return {routes:(await read('routes.json'))[id] || []};
    }
    if (resource === 'regions') {
      const regions = await read('regions.json');
      const item = regions[id];
      if (id && parts[3] === 'stories') {
        const name = item?.name || id, year = yearValue(params.get('year'),1860);
        const province = item?.ancestor_ids?.length ? regions[item.ancestor_ids[0]].name : null;
        const items = (await read('events.json')).filter(event => [event.province,event.city,event.district].includes(name) && (!province || event.province === province) && (year == null || event.year === year));
        return {region:id,items,count:items.length};
      }
      if (id) {
        if (!item) failure('未找到该行政区');
        if (parts[3] !== 'geometry') return item;
        if (item.geometry_status !== 'available') return {region:item,geometry:null,status:'missing',locate_parent:item.parent};
        const manifest = await read('geo-manifest.json');
        const path = manifest.regions[id];
        if (!path) failure('目录与边界不一致',503);
        const feature = (await read(path)).features.find(feature => feature.properties.id === id);
        if (!feature) failure('目录与边界不一致',503);
        return feature;
      }
      const text = params.get('query') || '', parent = params.get('parent'), level = params.get('level');
      if (parent && parent !== '100000' && !regions[parent]) failure('未找到该行政区');
      if (level && !['province','city','district'].includes(level)) failure('无效行政层级',422);
      const offset = Number(params.get('offset') || 0), limit = Number(params.get('limit') || 50);
      if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 200 || text.length > 100) failure('无效分页参数',422);
      const terms = normalize(text).trim().split(/\s+/).filter(Boolean);
      const selected = Object.values(regions).filter(item => (!parent || item.parent === parent) && (!level || item.level === level) && terms.every(term => normalize([item.id,item.code || '',item.full_name,...(item.aliases || [])].join(' ')).includes(term)));
      const rank = item => [item.id,item.name].includes(text.trim()) ? 0 : 1;
      const compare = (a,b) => a < b ? -1 : a > b ? 1 : 0;
      selected.sort((a,b) => rank(a)-rank(b) || compare(a.full_name,b.full_name) || compare(a.id,b.id));
      const manifest = await read('geo-manifest.json');
      return {items:selected.slice(offset,offset+limit).map(compact),count:selected.length,offset,limit,version:manifest.version};
    }
    if (resource === 'history') {
      const year = yearValue(id,1921,new Date().getFullYear()), bounds = bbox(params.get('bbox'));
      if (year >= 1951) return {year,display_mode:'modern',snapshot_date:null,territories:[],battles:[],sources:[],note:'1951年起恢复普通地图；此为展示规则，不表示此后不存在军事冲突。'};
      const annual = (await read('history/annual.json'))[String(year)];
      const territories = annual.territories.filter(region => !bounds || !region.bbox || intersects(region.bbox,bounds));
      const battles = (await read('history/battles.json')).filter(b => Number(b.start_date.slice(0,4)) <= year && year <= Number(b.end_date.slice(0,4))).map(({routes,stages,...summary}) => summary);
      return {...annual,display_mode:'historical',territories,battles,sources:await sourceRecords([...annual.source_ids,...territories.flatMap(region=>region.source_ids)]),total_territories:annual.territories.length};
    }
    if (resource === 'battles') {
      const item = (await read('history/battles.json')).find(item=>item.id===id);
      if (!item) failure('未找到该战役');
      return {...item,sources:await sourceRecords(item.source_ids)};
    }
    failure('不支持的数据查询');
  }
  // Match fetch().json(): each consumer gets its own object. The directory adds
  // searchText to rows, which must never mutate the shared source cache.
  window.RedMapData = {getJSON:async url => structuredClone(await query(url))};
})();
