/* Local-only, paginated administrative directory. Separate from event search. */
class AdminDirectory {
  constructor() {
    this.items = new Map(); this.parent = '100000'; this.limit = 50;
    this.sequence = 0; this.audit = null; this.filtered = [];
    this.panel = document.querySelector('#region-directory');
    this.input = document.querySelector('#region-search');
    this.level = document.querySelector('#region-level');
    this.toggle = document.querySelector('#open-region-directory');
    map.createPane('adminSelection').style.zIndex = '435';
    map.getPane('adminSelection').style.pointerEvents = 'none';
    this.selection = L.geoJSON(null, { renderer: L.canvas({padding:.2,pane:'adminSelection'}), interactive:false,
      style:{color:'#a72a20',weight:2.1,fillColor:'#c65b42',fillOpacity:.14} }).addTo(map);
    this.toggle.addEventListener('click', () => this.open());
    document.querySelector('#close-region-directory').addEventListener('click', () => this.close());
    this.input.addEventListener('input', () => { this.limit = 50; this.render(); });
    this.level.addEventListener('change', () => { this.limit = 50; this.render(); });
    this.input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && this.filtered[0]) { event.preventDefault(); this.locate(this.filtered[0].id); }
    });
    this.panel.addEventListener('keydown', event => { if (event.key === 'Escape') this.close(); });
    document.querySelector('#region-show-all').addEventListener('click', () => { this.parent = null; this.input.value = ''; this.level.value = ''; this.limit = 50; this.render(); });
    document.querySelector('#region-load-more').addEventListener('click', () => { this.limit += 50; this.render(); });
    this.panel.addEventListener('click', event => {
      const locate = event.target.closest('[data-locate]');
      const browse = event.target.closest('[data-browse]');
      if (locate) this.locate(locate.dataset.locate);
      else if (browse) { this.parent = browse.dataset.browse; this.input.value = ''; this.level.value = ''; this.limit = 50; this.render(); }
    });
    L.DomEvent.disableClickPropagation(this.panel); L.DomEvent.disableScrollPropagation(this.panel);
    document.querySelector('#reset-view').addEventListener('click', () => { this.sequence++; this.selection.clearLayers(); });
  }
  setIndex(index) {
    for (const level of ['province','city','district']) for (const item of index[level] || []) {
      item.searchText = [item.id,item.code,item.full_name,...(item.aliases || [])].join(' ').normalize('NFKC').replace(/臺/g,'台').toLowerCase();
      this.items.set(item.id, item);
    }
    this.render();
  }
  async open() {
    this.panel.classList.remove('hidden'); this.toggle.setAttribute('aria-expanded','true');
    this.input.focus(); this.render();
    if (!this.audit) {
      try { this.audit = await getJson('/api/geo-status'); this.renderAudit(); }
      catch { document.querySelector('#region-audit-summary').textContent = '核验状态加载失败（重新打开可重试）'; }
    }
  }
  close() { this.panel.classList.add('hidden'); this.toggle.setAttribute('aria-expanded','false'); this.toggle.focus(); }
  renderAudit() {
    const a = this.audit;
    const missing = a.missing_geometry || [];
    document.querySelector('#region-audit-summary').textContent = a.complete ? '当前版本核验通过' : `已载入 ${a.available_geometry_count} 个边界 · ${missing.length} 个区域使用上级定位`;
    document.querySelector('#region-audit-details').innerHTML = `<p>版本 ${safeText(a.version)}</p><p>真实目录 ${a.catalog_count} 项；不把城市覆盖面计作区县。</p>${missing.length ? `<p class="region-warning">上级定位：${missing.map(r=>safeText(r.name)).join('、')}</p>` : ''}${(a.limitations || []).map(t=>`<p>${safeText(t)}</p>`).join('')}`;
  }
  render() {
    const query = this.input.value.trim().normalize('NFKC').replace(/臺/g,'台').toLowerCase();
    const terms = query.split(/\s+/).filter(Boolean);
    this.filtered = [...this.items.values()].filter(item =>
      (!terms.length ? !this.parent || item.parent === this.parent : terms.every(t=>item.searchText.includes(t))) &&
      (!this.level.value || item.level === this.level.value));
    this.filtered.sort((a,b)=>(query && a.name===query ? -1 : query && b.name===query ? 1 : a.id.localeCompare(b.id)));
    const parent = terms.length ? null : this.items.get(this.parent);
    const path = parent ? [...(parent.ancestor_ids || []),parent.id] : [];
    document.querySelector('#region-breadcrumbs').innerHTML = `<button type="button" data-browse="100000">全国</button>${path.map(id=>`<span>›</span><button type="button" data-browse="${safeText(id)}">${safeText(this.items.get(id)?.name || id)}</button>`).join('')}`;
    document.querySelector('#region-result-count').textContent = `${this.filtered.length} 项${query ? ' · 全国匹配' : ''}`;
    document.querySelector('#region-results').innerHTML = this.filtered.slice(0,this.limit).map(item=>{
      const missing = item.geometry_status !== 'available';
      const status = missing ? '使用上级定位 · 可查看所属区域' : item.coverage_status === 'no_county_level_units' ? '无县级下辖单位' : ({province:'省级',city:'地市／对应分区',district:'区县／对应分区'})[item.level];
      return `<div class="region-row"><button class="region-locate" type="button" data-locate="${safeText(item.id)}"><strong>${safeText(item.name)}</strong><span>${safeText(item.full_name)}</span><small class="${missing?'region-warning':''}">${safeText(status)}</small></button>${item.child_count ? `<button class="region-children" type="button" data-browse="${safeText(item.id)}" aria-label="浏览${safeText(item.name)}的${item.child_count}个下级">${item.child_count}<span>›</span></button>`:''}</div>`;
    }).join('') || '<p class="empty-state">没有匹配行政区；可调整关键词或层级。</p>';
    document.querySelector('#region-load-more').classList.toggle('hidden',this.filtered.length <= this.limit);
  }
  async locate(id) {
    const item = this.items.get(id); if (!item) return;
    const sequence = ++this.sequence;
    const status = document.querySelector('#region-location-status');
    status.textContent = `正在定位 ${item.full_name}…`;
    try {
      const payload = await getJson(`/api/regions/${encodeURIComponent(id)}/geometry`);
      if (sequence !== this.sequence) return;
      const missing = payload.status === 'missing';
      const target = missing ? this.items.get(payload.locate_parent) : item;
      if (!target?.bbox) throw new Error('该地区暂缺可定位范围');
      this.selection.clearLayers();
      if (!missing) this.selection.addData(payload);
      cancelWheelGesture(); map.stop();
      const [west,south,east,north] = target.bbox;
      const panelWidth = this.panel.classList.contains('hidden') ? 0 : this.panel.offsetWidth;
      const usableWidth = map.getSize().x;
      map.flyToBounds([[south,west],[north,east]], { animate:true,duration:.85,maxZoom:11.5,
        paddingTopLeft:[usableWidth > panelWidth + 350 ? panelWidth + 30 : 24,40],paddingBottomRight:[32,60] });
      const detail = missing ? payload.region : payload.properties;
      await selectRegion({...detail,displayName:item.full_name});
      if (sequence !== this.sequence) return;
      status.textContent = missing ? `${item.name}当前使用上级${target.name}定位；地图保留真实层级。` : `${item.full_name}${item.coverage_status==='no_county_level_units'?' · 无县级下辖单位':''}`;
      if (usableWidth <= panelWidth + 200) this.close();
    } catch (error) {
      if (sequence === this.sequence) status.textContent = `定位失败：${error.message}。可再次点击重试。`;
    }
  }
}
