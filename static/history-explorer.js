/* global L, map, state, $, safeText, getJson, renderDetail, drawEvents, renderList,
   visibleEvents, routeLayer, cancelWheelGesture, hoverTooltip, hoverWidth,
   positionHover, mapMoving, boundsArray, intersectsBounds */
const HISTORY_PHASES = [
  { id: 'all', label: '全部时期', start: 1921, end: 0, description: '按年度查看全部历史资料' },
  { id: 'revolution', label: '建党之初和大革命时期', start: 1921, end: 1926, defaultYear: 1926, description: '1921—1926 · 建党、工运、国共合作与北伐' },
  { id: 'land_revolution', label: '土地革命战争时期', start: 1927, end: 1936, defaultYear: 1935, subtitle: '含长征', description: '1927—1936 · 根据地建设、反围剿和长征多路行军' },
  { id: 'anti_japanese', label: '抗日战争时期', start: 1937, end: 1945, defaultYear: 1938, description: '1937—1945 · 正面战场与敌后战场' },
  { id: 'liberation', label: '解放战争时期', start: 1946, end: 1948, defaultYear: 1948, description: '1946—1948 · 战略防御、进攻与决战' },
  { id: 'founding_korea', label: '新中国建立与社会主义革命、建设时期', start: 1949, end: 1977, defaultYear: 1951, subtitle: '新中国巩固时期（含抗美援朝）', description: '1949—1977 · 新中国建立、巩固与社会主义建设' },
  { id: 'construction', label: '改革开放和社会主义现代化建设新时期', start: 1978, end: 2011, defaultYear: 1978, description: '1978—2011 · 改革开放与社会主义现代化建设' },
  { id: 'new_era', label: '中国特色社会主义新时代', start: 2012, end: 0, defaultYear: 2018, description: '2012—至今 · 新时代发展与强军实践' },
];

const PERSON_SPIRITS = {
  '毛泽东': ['理想信念', '实事求是', '人民立场'],
  '周恩来': ['人民立场', '团结协作', '严谨务实'],
  '朱德': ['理想信念', '艰苦奋斗', '军民团结'],
  '邓小平': ['实事求是', '改革创新', '独立自主'],
  '鲁迅': ['民族担当', '思想启蒙', '敢于斗争'],
  '孙中山': ['民族复兴', '民主革命', '探索实践'],
  '刘少奇': ['理想信念', '人民立场', '组织建设'],
  '彭德怀': ['敢于斗争', '英勇担当', '军民团结'],
  '贺龙': ['理想信念', '敢于斗争', '军民团结'],
  '陈云': ['实事求是', '调查研究', '建设担当'],
  '陈毅': ['艰苦奋斗', '团结协作', '建设担当'],
  '董必武': ['理想信念', '人民立场', '法治建设'],
  '李大钊': ['理想信念', '民族担当', '敢于斗争'],
  '刘伯承': ['实事求是', '敢于斗争', '协同作战'],
  '罗荣桓': ['人民立场', '组织建设', '纪律严明'],
  '聂荣臻': ['改革创新', '团结协作', '建设担当'],
  '任弼时': ['理想信念', '人民立场', '艰苦奋斗'],
  '徐海东': ['敢于斗争', '艰苦奋斗', '军民团结'],
  '徐向前': ['实事求是', '敢于斗争', '艰苦奋斗'],
  '叶剑英': ['团结协作', '战略担当', '国防建设'],
};

const PERSON_SPIRIT_FILTERS = ['理想信念', '人民立场', '实事求是', '艰苦奋斗', '敢于斗争', '团结协作', '改革创新', '民族担当'];

function personSpiritProfile(person) {
  const name = String(person?.name || '');
  return PERSON_SPIRITS[name] || ['理想信念', '人民立场', '建设担当'];
}

function personSpiritFilters() { return PERSON_SPIRIT_FILTERS; }

function historyPhase(id) {
  return HISTORY_PHASES.find(phase => phase.id === id) || HISTORY_PHASES[0];
}

function isoCursor(value) {
  const text = String(value || '').trim();
  if (!text) return null;
  const normalized = text.length === 10 ? `${text}T00:00:00Z`
    : text.length === 16 && !/[zZ]|[+-]\d\d:?\d\d$/.test(text) ? `${text}:00Z` : text;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function cursorText(date) {
  return date.toISOString().slice(0, 16);
}

function stepCursor(value, granularity, direction) {
  const date = isoCursor(value) || new Date();
  if (granularity === 'hour') date.setUTCHours(date.getUTCHours() + direction);
  else if (granularity === 'month') {
    const day = date.getUTCDate();
    date.setUTCDate(1); date.setUTCMonth(date.getUTCMonth() + direction);
    const last = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
    date.setUTCDate(Math.min(day, last));
  }
  else date.setUTCDate(date.getUTCDate() + direction);
  return cursorText(date);
}

// Positions deliberately snap to dated source nodes; no interpolated location
// is presented as a recorded troop arrival.
class TroopPlayer {
  constructor(explorer) {
    this.explorer = explorer;
    this.revision = 0;
    this.models = new Map();
    this.layers = L.layerGroup().addTo(map);
    map.createPane('troopLayer').style.zIndex = 520;
    map.getPane('troopLayer').style.pointerEvents = 'none';
    this.renderer = L.canvas({ pane: 'troopLayer', padding: .35, tolerance: 16 });
    this.control = L.control({ position: 'topright' });
    this.control.onAdd = () => {
      this.el = L.DomUtil.create('section', 'troop-player-control');
      this.el.setAttribute('aria-label', '部队到达时间');
      this.el.hidden = true;
      L.DomEvent.disableClickPropagation(this.el);
      L.DomEvent.disableScrollPropagation(this.el);
      this.el.addEventListener('input', event => {
        const model = this.models.get(event.target.dataset.unit);
        if (!model || event.target.type !== 'range') return;
        model.at = Number(event.target.value); this.paint(); this.updateRow(model); this.followYear(model);
      });
      this.el.addEventListener('change', event => {
        if (event.target.matches('[data-sync-units]') && event.target.checked) {
          const active = [...this.models.values()].find(item => item.timer) || this.models.values().next().value;
          if (active) this.followYear(active);
          return;
        }
        const model = this.models.get(event.target.dataset.unit);
        if (model && event.target.tagName === 'SELECT') model.step = event.target.value;
      });
      this.el.addEventListener('click', event => {
        const toggle = event.target.closest('[data-toggle-troop-panel]');
        if (toggle) {
          const collapsed = this.el.classList.toggle('is-collapsed');
          toggle.textContent = collapsed ? '展开' : '收起';
          toggle.setAttribute('aria-expanded', String(!collapsed));
          return;
        }
        const button = event.target.closest('[data-play-unit]');
        const model = this.models.get(button?.dataset.playUnit);
        if (!model) return;
        if (model.timer) { clearInterval(model.timer); model.timer = 0; }
        else {
          if (model.at >= model.end) model.at = model.start;
          model.timer = setInterval(() => {
            const date = new Date(model.at);
            if (model.step === 'month') { date.setUTCDate(1); date.setUTCMonth(date.getUTCMonth() + 1); }
            else date.setUTCDate(date.getUTCDate() + 1);
            model.at = Math.min(model.end, date.getTime());
            if (model.at >= model.end) { clearInterval(model.timer); model.timer = 0; }
            this.paint(); this.updateRow(model); this.followYear(model);
          }, 350);
        }
        this.paint(); this.updateRow(model); this.followYear(model);
      });
      return this.el;
    };
    this.control.addTo(map);
    map.on('zoomend moveend resize', () => {
      if (state.mode === 'time' && this.models.size) this.paint();
    });
  }

  clear() {
    ++this.revision;
    for (const model of this.models.values()) clearInterval(model.timer);
    this.models.clear(); this.layers.clearLayers();
    if (map.hasLayer(this.renderer)) map.removeLayer(this.renderer);
    this.key = null; this.el.hidden = true; this.el.replaceChildren();
  }

  async load() {
    const battle = state.selected?.type === 'battle' ? state.selected.data.id : '';
    const key = `${state.year}|${battle}|${state.timePhase}`;
    if (key === this.key) return;
    this.clear(); this.key = key;
    const revision = this.revision;
    const query = new URLSearchParams({ year: String(state.year) });
    if (battle) query.set('battle_id', battle);
    if (state.timePhase === 'land_revolution' && state.year >= 1934 && state.year <= 1936) query.set('category', 'long_march');
    try {
      const payload = await getJson(`/api/units?${query}`);
      if (revision !== this.revision || state.mode !== 'time') return;
      const units = payload.units || payload.troops || [];
      for (const unit of units) {
        const nodes = (unit.waypoints || unit.arrivals || []).filter(node =>
          Array.isArray(node.coords) && node.coords.length === 2 && isoCursor(node.at || node.date))
          .map(node => {
            const value = node.at || node.date;
            const date = isoCursor(value);
            if (String(value).length === 7) { date.setUTCMonth(date.getUTCMonth() + 1, 0); date.setUTCHours(23,59,59,999); }
            return { ...node, place: node.place || node.location, time: date.getTime() };
          })
          .sort((a,b) => a.time - b.time);
        if (!nodes.length) continue;
        const start = nodes[0].time, end = nodes[nodes.length - 1].time;
        const at = Math.min(end, Math.max(start, Date.parse(`${state.year}-12-31T23:59:59Z`)));
        this.models.set(unit.id, { ...unit, nodes, start, end, at, step: unit.granularity === 'month' ? 'month' : 'day', timer: 0 });
      }
      const commonAt = Date.parse(`${state.year}-12-31T23:59:59Z`);
      for (const model of this.models.values()) model.at = commonAt;
      this.render(); this.paint();
      if (battle) renderDetail();
    } catch (error) {
      if (revision !== this.revision) return;
      this.key = null;
      this.el.hidden = false;
      this.el.innerHTML = '<strong>部队位置资料暂时无法载入</strong>';
    }
  }

  render() {
    this.el.hidden = !this.models.size;
    const compact = map.getZoom() < 6.5 && state.selected?.type !== 'battle';
    this.el.classList.toggle('is-collapsed', compact);
    this.el.innerHTML = `<div class="troop-player-heading"><span>部队到达记录 <b>${this.models.size} 支</b></span><button type="button" data-toggle-troop-panel aria-expanded="${String(!compact)}">${compact ? '展开' : '收起'}</button></div><label class="troop-sync"><input type="checkbox" checked data-sync-units>同步全部部队日期</label>` +
      [...this.models.values()].map(model => `<div class="troop-player-row" data-troop-row="${safeText(model.id)}">
        <strong>${safeText(model.name)}</strong><div class="troop-player-actions">
        <button type="button" data-play-unit="${safeText(model.id)}" aria-label="播放${safeText(model.name)}" title="播放">▶</button>
        <select data-unit="${safeText(model.id)}" aria-label="${safeText(model.name)}时间粒度"><option value="day" ${model.step === 'day' ? 'selected' : ''}>日</option><option value="month" ${model.step === 'month' ? 'selected' : ''}>月</option></select>
        <time></time></div><input type="range" data-unit="${safeText(model.id)}" min="${model.start}" max="${model.end}" step="86400000" value="${model.at}" aria-label="${safeText(model.name)}日期"><p></p></div>`).join('');
    for (const model of this.models.values()) this.updateRow(model);
  }

  arrival(model) { return model.nodes.filter(node => node.time <= model.at).at(-1); }

  async followYear(model) {
    if (this.el.querySelector('[data-sync-units]')?.checked) {
      for (const other of this.models.values()) {
        if (other === model) continue;
        if (other.timer) { clearInterval(other.timer); other.timer = 0; }
        other.at = model.at;
        this.updateRow(other);
      }
      this.paint();
    }
    const year = new Date(model.at).getUTCFullYear();
    if (year === state.year || state.mode !== 'time') return;
    const revision = this.revision;
    state.year = year;
    const battle = state.selected?.type === 'battle' ? state.selected.data.id : '';
    this.key = `${year}|${battle}|${state.timePhase}`;
    this.explorer.syncYearControls();
    drawEvents();
    try {
      const annual = await this.explorer.fetchYear(year);
      if (revision !== this.revision || state.year !== year || state.mode !== 'time') return;
      this.explorer.annual = annual;
      this.explorer.drawAnnual();
      renderDetail();
      $('#history-status').textContent = `${year} 年 · 部队来源到达节点`;
    } catch (error) {
      if (revision === this.revision) $('#history-status').textContent = `${year} 年形势资料暂时无法载入`;
    }
  }

  updateRow(model) {
    const row = [...this.el.querySelectorAll('[data-troop-row]')].find(item => item.dataset.troopRow === model.id);
    if (!row) return;
    const node = this.arrival(model);
    row.querySelector('time').textContent = new Date(model.at).toISOString().slice(0,10);
    row.querySelector('input').value = String(model.at);
    row.querySelector('button').textContent = model.timer ? 'Ⅱ' : '▶';
    row.querySelector('button').title = model.timer ? '暂停' : '播放';
    row.querySelector('button').setAttribute('aria-label', `${model.timer ? '暂停' : '播放'}${model.name}`);
    row.querySelector('p').textContent = node ? `${node.at || node.date} · ${node.place} · 最近来源节点` : '尚未到达首个来源节点';
  }

  paint() {
    this.layers.clearLayers();
    const positions = new Map();
    for (const model of this.models.values()) {
      const node = this.arrival(model);
      if (!node) continue;
      const past = model.nodes.filter(point => point.time <= model.at);
      const color = this.explorer.colors[model.faction] || '#5a6b42';
      const faction = this.explorer.names[model.faction] || model.faction || '来源记录';
      const tip = `<strong>${safeText(model.name)}</strong><br>${safeText(node.at || node.date)} 到达 ${safeText(node.place)}<br>${safeText(faction)} · ${node.precision === 'month' ? '月级日期' : '来源到达节点'}${node.source_locator ? `<br>${safeText(node.source_locator)}` : ''}`;
      if (past.length > 1) {
        const coords = past.map(point => [point.coords[1],point.coords[0]]);
        L.polyline(coords, { renderer: this.renderer, color, weight: 3, opacity: .9, interactive: false, dashArray: '6 4' }).addTo(this.layers);
        L.polyline(coords, { renderer: this.renderer, weight: 32, opacity: 0 }).bindTooltip(tip, { sticky: true }).addTo(this.layers);
      }
      const label = `<span class="troop-position-dot" style="--troop-color:${color}"></span><span class="troop-position-label">${safeText(model.name)}<small>${safeText(node.at || node.date)} · ${safeText(node.place)} · 到达记录</small></span>`;
      const key = node.coords.join(',');
      if (!positions.has(key)) positions.set(key, { coords: node.coords, labels: [], tips: [], titles: [] });
      const position = positions.get(key);
      position.labels.push(`<div class="troop-position-item">${label}</div>`);
      position.tips.push(tip);
      position.titles.push(`${model.name} ${node.at || node.date} ${node.place}`);
    }
    const occupied = [];
    const size = map.getSize();
    // At national or theater scale, labels occupy more pixels than the
    // historical positions themselves. Keep the source points and counts
    // visible, then restore full labels after zooming in or selecting a battle.
    if (map.getZoom() < 6.5 && state.selected?.type !== 'battle') {
      for (const position of positions.values()) {
        const latlng = L.latLng(position.coords[1], position.coords[0]);
        const tips = position.tips.join('<hr>');
        L.circleMarker(latlng, { renderer: this.renderer, radius: position.labels.length > 1 ? 7 : 5, color: '#33483a', fillColor: '#33483a', fillOpacity: 1 })
          .bindTooltip(tips).addTo(this.layers);
        if (position.labels.length > 1) {
          L.marker(latlng, { icon: L.divIcon({ className: 'troop-count-marker', html: `<span>${position.labels.length}</span>`, iconSize: [20,20], iconAnchor: [10,10] }), keyboard: true })
            .bindTooltip(tips).addTo(this.layers);
        }
      }
      return;
    }
    for (const position of positions.values()) {
      const latlng = L.latLng(position.coords[1], position.coords[0]);
      const point = map.latLngToContainerPoint(latlng);
      const height = 64 * position.labels.length, width = 180;
      const candidates = [];
      for (let x = -3; x <= 3; x++) for (let y = -5; y <= 5; y++) {
        const dx = x * (width + 12), dy = y * 70;
        candidates.push({ dx, dy, distance: dx * dx + dy * dy });
      }
      candidates.sort((a, b) => a.distance - b.distance);
      let placed;
      for (const candidate of candidates) {
        const left = point.x + candidate.dx - 7, top = point.y + candidate.dy - 7;
        const rect = { left, top, right: left + width, bottom: top + height };
        if (rect.left < 8 || rect.right > size.x - 8 || rect.top < 8 || rect.bottom > size.y - 8) continue;
        if (occupied.some(other => rect.left < other.right + 6 && rect.right > other.left - 6 && rect.top < other.bottom + 6 && rect.bottom > other.top - 6)) continue;
        placed = { ...candidate, rect }; break;
      }
      // Dense offscreen groups retain their source marker and tooltip; visible
      // labels are packed separately without moving the historical location.
      if (!placed) {
        L.circleMarker(latlng, { renderer: this.renderer, radius: 7, color: '#33483a', fillOpacity: 1 })
          .bindTooltip(position.tips.join('<hr>')).addTo(this.layers);
        continue;
      }
      occupied.push(placed.rect);
      const labelLatlng = map.containerPointToLatLng(point.add([placed.dx, placed.dy]));
      if (placed.dx || placed.dy) {
        L.polyline([latlng, labelLatlng], { renderer: this.renderer, color: '#586d61', weight: 1, opacity: .8, interactive: false })
          .addTo(this.layers);
        L.circleMarker(latlng, { renderer: this.renderer, radius: 5, color: '#33483a', fillOpacity: 1 })
          .bindTooltip(position.tips.join('<hr>')).addTo(this.layers);
      }
      L.marker(labelLatlng, {
        icon: L.divIcon({ className: 'troop-position-group', html: position.labels.join(''), iconSize: [width,height], iconAnchor: [7,7] }),
        title: position.titles.join('; '), keyboard: true,
      }).bindTooltip(position.tips.join('<hr>')).addTo(this.layers);
    }
  }
}

function battleBounds(battle) {
  const normalize = value => {
    const text = String(value || '');
    return text.length === 4 ? `${text}-01-01` : text.length === 7 ? `${text}-01` : text;
  };
  const start = isoCursor(normalize(battle.start_date));
  const end = isoCursor(normalize(battle.end_date));
  if (end && String(battle.end_date).length <= 10) end.setUTCHours(23, 59, 59, 999);
  return { start, end };
}

class HistoryExplorer {
  constructor() {
    this.revision = 0;
    this.routeRevision = 0;
    state.timePhase = state.timePhase || 'all';
    this.annual = null;
    this.journey = null;
    this.error = null;
    this.loading = false;
    this.yearTimer = 0;
    this.cache = new Map();
    this.journeyCache = new Map();
    this.battleCache = new Map();
    this.battleTimelineCache = new Map();
    this.battleCursor = null;
    this.battleGranularity = 'day';
    this.battleSpeed = 1;
    this.battlePlaying = false;
    this.battleTimer = 0;
    this.routes = [];
    this.lastPaintedYear = null;
    this.selectedNode = null;
    this.colors = { ccp: '#b42330', kmt: '#2567a3', japan: '#d3af18', warlord: '#81708b', other: '#c49a3a' };
    this.names = { ccp: '共产党', kmt: '国民党', japan: '日本及日伪', warlord: '地方军阀', other: '其他来源区域' };
    this.kinds = { control: '控制核心区', base: '根据地', guerrilla: '游击活动区', contested: '争夺区', other: '其他政权／特殊地区' };
    // Modern administrative faces carry explicitly sourced historical places.
    map.createPane('historyCoverage').style.zIndex = 360;
    map.getPane('historyCoverage').style.pointerEvents = 'none';
    this.coverageRenderer = L.canvas({ pane: 'historyCoverage', padding: .15 });
    this.coverageAreas = L.geoJSON(null, {
      renderer: this.coverageRenderer,
      interactive: false,
      style: feature => {
        const p = feature.properties || {};
        const color = this.colors[p.faction] || '#d8e0dd';
        return { color, fillColor: color, weight: .55, opacity: .7,
          fillOpacity: p.faction ? .58 : .15, dashArray: p.kind === 'guerrilla' ? '6 5' : null };
      },
    }).addTo(map);
    map.createPane('historyAreas').style.zIndex = 410;
    map.getPane('historyAreas').style.pointerEvents = 'none';
    this.areaRenderer = L.canvas({ pane: 'historyAreas', padding: .15 });
    this.areas = L.geoJSON(null, { renderer: this.areaRenderer, interactive: false,
      style: feature => {
        const p = feature.properties;
        const sourceRange = p.geometry_status === 'source_location_envelope';
        return { color: this.colors[p.faction], fillColor: this.colors[p.faction], weight: sourceRange ? 1 : 1.3,
          fillOpacity: sourceRange ? .14 : p.kind === 'control' ? .25 : p.kind === 'base' ? .21 : .11,
          dashArray: sourceRange ? '7 5' : p.kind === 'control' ? '3 4' : p.kind === 'base' ? '7 4' : '2 6' };
      } }).addTo(map);
    map.createPane('historyRoutes').style.zIndex = 430;
    map.getPane('historyRoutes').style.pointerEvents = 'auto';
    this.points = L.layerGroup().addTo(map);
    this.routeLines = L.layerGroup().addTo(map);
    this.arrows = L.layerGroup().addTo(map);
    this.routeRenderer = L.canvas({ pane: 'historyRoutes', padding: .35, tolerance: 14 });
    this.troopPlayer = new TroopPlayer(this);
    $('#year-slider').max = String(new Date().getFullYear());
    $('#year-slider-max').textContent = String(new Date().getFullYear());
    $('#year-slider').addEventListener('input', e => this.setYear(e.target.value, false));
    $('#year-slider').addEventListener('change', e => this.setYear(e.target.value, true));
    $('#all-battle-routes').addEventListener('change', () => this.drawBattleRoutes());
    document.querySelectorAll('.history-phase-tab').forEach(button => button.addEventListener('click', () => this.setPhase(button.dataset.phase)));
    this.syncPhaseControls();
  }

  phaseLabel() {
    return historyPhase(state.timePhase).label;
  }

  syncPhaseControls() {
    const phase = historyPhase(state.timePhase);
    const currentYear = new Date().getFullYear();
    const min = phase.start;
    const max = phase.end || currentYear;
    document.querySelectorAll('.history-phase-tab').forEach(button => {
      const active = button.dataset.phase === state.timePhase;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    const slider = $('#year-slider');
    if (slider) {
      slider.min = String(min); slider.max = String(max);
      slider.setAttribute('aria-valuemin', String(min));
      slider.setAttribute('aria-valuemax', String(max));
      const sliderStart = slider.parentElement?.querySelector('span:first-child');
      if (sliderStart) sliderStart.textContent = String(min);
      const sliderEnd = $('#year-slider-max');
      if (sliderEnd) sliderEnd.textContent = phase.end ? String(phase.end) : '至今';
    }
    const input = $('#year-input');
    if (input) { input.min = String(min); input.max = String(max); }
    const range = document.querySelector('.year-range');
    if (range) range.textContent = `${min}—${phase.end ? phase.end : '至今'}`;
    const description = $('#history-phase-description');
    if (description) description.textContent = phase.description;
  }

  async setPhase(id) {
    const phase = historyPhase(id);
    const currentYear = new Date().getFullYear();
    const max = phase.end || currentYear;
    const current = Number(state.year);
    state.timePhase = phase.id;
    state.selected = null;
    ++this.revision; ++this.routeRevision;
    this.annual = null;
    this.clearLayers();
    const nextYear = phase.id === 'all'
      ? Math.min(max, Math.max(1921, current))
      : (current >= phase.start && current <= max ? current : Math.min(max, phase.defaultYear || phase.start));
    this.syncPhaseControls();
    this.setYear(nextYear, true);
    if (typeof hideRegionHover === 'function') hideRegionHover();
  }

  battleMatchesPhase(battle) {
    const phase = historyPhase(state.timePhase);
    if (phase.id === 'all') return true;
    const start = Number(String(battle.start_date || '').slice(0, 4));
    const end = Number(String(battle.end_date || '').slice(0, 4));
    if (Number.isFinite(start) && Number.isFinite(end)) return start <= (phase.end || new Date().getFullYear()) && end >= phase.start;
    const phaseAliases = {
      revolution: ['北伐'], land_revolution: ['土地革命战争', '长征'], anti_japanese: ['抗日战争'],
      liberation: ['解放战争'], founding_korea: ['抗美援朝'],
    };
    return (phaseAliases[phase.id] || []).includes(String(battle.phase || ''));
  }

  clearLayers() {
    this.troopPlayer?.clear();
    this.coverageAreas.clearLayers(); this.areas.clearLayers(); this.points.clearLayers();
    this.routeLines.clearLayers(); this.arrows.clearLayers(); this.routes = [];
    if (map.hasLayer(this.routeRenderer)) map.removeLayer(this.routeRenderer);
  }

  async switchMode() {
    this.battlePlaying = false; clearInterval(this.battleTimer);
    ++this.revision; ++this.routeRevision;
    clearTimeout(this.yearTimer);
    this.clearLayers(); this.annual = null; this.journey = null;
    this.selectedNode = null; this.error = null; this.loading = false;
    $('#history-controls').classList.toggle('hidden', state.mode !== 'time');
    $('#history-legend').classList.toggle('hidden', state.mode !== 'time' || state.year >= 1951);
    $('#map-legend').classList.toggle('hidden', state.mode === 'time' && state.year <= 1950);
    document.querySelector('.map-note').classList.toggle('hidden', state.mode === 'time' && state.year <= 1950);
    this.coverageAreas.setStyle({ fillOpacity: state.mode === 'time' && state.year <= 1950 ? .33 : 0 });
    this.syncPhaseControls();
    this.syncYearControls();
    requestAnimationFrame(() => map.invalidateSize({ pan: false }));
    if (state.mode === 'time') await this.loadYear();
    if (state.mode === 'person') await this.loadJourney();
  }

  syncYearControls() {
    this.syncPhaseControls();
    $('#year-input').value = String(state.year);
    $('#year-slider').value = String(state.year);
    $('#year-slider-value').value = String(state.year);
    $('#year-slider').setAttribute('aria-valuetext', `${state.year}年`);
    $('#all-routes-control').classList.toggle('hidden', state.year >= 1951);
  }

  setYear(value, commit = true) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || String(value).trim() === '') { this.syncYearControls(); return; }
    const phase = historyPhase(state.timePhase);
    const phaseMax = phase.end || new Date().getFullYear();
    const year = Math.min(phaseMax, Math.max(phase.start, Math.trunc(parsed)));
    clearTimeout(this.yearTimer);
    if (year !== state.year) {
      this.battlePlaying = false; clearInterval(this.battleTimer);
      state.year = year; state.selected = null;
      ++this.revision; ++this.routeRevision;
      this.annual = null; this.clearLayers();
      this.loading = year <= 1950; this.error = null;
      $('#history-status').textContent = `${this.phaseLabel()} · ${year} 年资料读取中…`;
      $('#history-legend').classList.add('hidden');
      $('#map-legend').classList.toggle('hidden', year <= 1950);
      document.querySelector('.map-note').classList.toggle('hidden', year <= 1950);
      drawEvents(); renderDetail();
    }
    this.syncYearControls();
    if (state.mode === 'time') {
      if (commit) this.loadYear();
      else this.yearTimer = setTimeout(() => this.loadYear(), 100);
    }
  }

  fetchYear(year) {
    if (!this.cache.has(year)) {
      // Annual geometry is deliberately coarse and small. Cache at most five
      // years; the API also accepts bbox for larger future datasets.
      this.cache.set(year, Promise.all([getJson(`/api/history/${year}`), getJson(`/api/control?year=${year}`)])
        .then(([annual,control]) => ({...annual, control}))
        .catch(error => { this.cache.delete(year); throw error; }));
      while (this.cache.size > 5) this.cache.delete(this.cache.keys().next().value);
    }
    return this.cache.get(year);
  }

  async loadYear() {
    if (state.mode !== 'time') return;
    const id = ++this.revision, year = state.year;
    this.loading = true; this.error = null;
    try {
      const annual = await this.fetchYear(year);
      if (id !== this.revision || state.mode !== 'time' || year !== state.year) return;
      this.annual = annual; this.loading = false;
      $('#history-status').textContent = `${this.phaseLabel()} · ${annual.display_mode === 'historical'
        ? `${annual.snapshot_date} · 年度形势图` : '普通地图 · 年度事件'}`;
      const historical = annual.display_mode === 'historical';
      $('#history-legend').classList.remove('hidden');
      $('#map-legend').classList.toggle('hidden', historical);
      document.querySelector('.map-note').classList.toggle('hidden', historical);
      $('#history-legend').innerHTML = `<div class="faction-legend">${Object.entries(this.names).map(([key,name]) => `<span><i style="background:${this.colors[key]}"></i>${safeText(name)}</span>`).join('')}</div><p>红／蓝／黄表示来源记载的控制方；虚线为敌后或活动范围。使用现代省县面承载同名地区，范围说明见悬停资料。</p>`;
      this.drawAnnual();
      await this.drawBattleRoutes();
      if (id !== this.revision) return;
      renderDetail();
      // Delay prefetch until the selected year is usable. Never load 30 years.
      setTimeout(() => {
        if (state.mode !== 'time' || state.year !== year) return;
        for (const adjacent of [year - 1, year + 1]) if (adjacent >= 1921 && adjacent <= 1950) this.fetchYear(adjacent).catch(() => {});
      }, 220);
    } catch (error) {
      if (id !== this.revision) return;
      this.loading = false; this.error = '年度历史资料加载失败，可重新选择年份重试。';
      $('#history-status').textContent = this.error; renderDetail();
    }
  }

  filteredBattles() {
    return (this.annual?.battles || []).filter(b => this.battleMatchesPhase(b) && (!state.search || [b.name,b.location,b.summary,b.phase,...(b.participants || [])].join(' ').toLowerCase().includes(state.search)));
  }

  drawAnnual() {
    this.coverageAreas.clearLayers(); this.areas.clearLayers(); this.points.clearLayers();
    if (!this.annual || this.annual.year !== state.year || state.mode !== 'time') return;
    this.drawCoverage();
    const view = boundsArray(map.getBounds().pad(.2));
    for (const area of this.annual.territories) if ((area.geometry_status === 'verified_boundary' || area.geometry_status === 'source_location_envelope') && area.geometry && intersectsBounds(area.bbox, view)) {
      this.areas.addData({ type: 'Feature', properties: area, geometry: area.geometry });
    }
    const canvas = map.getPane('historyAreas').querySelector('canvas');
    if (canvas && this.lastPaintedYear !== state.year) {
      if (canvas.animate && !matchMedia('(prefers-reduced-motion: reduce)').matches) canvas.animate([{opacity:.35},{opacity:1}], {duration:160,easing:'ease-out'});
      this.lastPaintedYear = state.year;
    }
    for (const battle of this.filteredBattles()) {
      const marker = L.marker([battle.coords[1],battle.coords[0]], {
        icon: L.divIcon({ className: 'battle-marker', html: '<span>⚑</span>', iconSize: [24,24], iconAnchor: [12,12] }), title: battle.name,
      });
      marker.bindTooltip(safeText(`${battle.name} · ${battle.start_date}—${battle.end_date}`));
      marker.on('click', () => this.selectBattle(battle.id)); marker.addTo(this.points);
    }
  }

  geometryCenter(geometry) {
    const values = [];
    const visit = coords => {
      if (!coords) return;
      if (typeof coords[0] === 'number') values.push(coords);
      else coords.forEach(visit);
    };
    visit(geometry?.coordinates);
    if (!values.length) return [0, 0];
    return [values.reduce((sum, point) => sum + point[0], 0) / values.length,
      values.reduce((sum, point) => sum + point[1], 0) / values.length];
  }

  pointInRing(point, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > point[1]) !== (yj > point[1]) && point[0] < (xj - xi) * (point[1] - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }

  pointInGeometry(point, geometry) {
    if (!geometry) return false;
    const contains = rings => this.pointInRing(point, rings[0]) && !rings.slice(1).some(ring => this.pointInRing(point, ring));
    if (geometry.type === 'Polygon') return contains(geometry.coordinates);
    if (geometry.type === 'MultiPolygon') return geometry.coordinates.some(contains);
    return false;
  }

  drawCoverage() {
    if (!this.annual?.control) return;
    this.coverageAreas.addData(this.annual.control);
  }

  async getBattle(id) {
    if (!this.battleCache.has(id)) this.battleCache.set(id, getJson(`/api/battles/${encodeURIComponent(id)}`).catch(error => { this.battleCache.delete(id); throw error; }));
    return this.battleCache.get(id);
  }

  async selectBattle(id) {
    const revision = this.revision;
    const selection = { type: 'battle', loading: true, data: { id } };
    state.selected = selection; renderDetail();
    try {
      const battle = await this.getBattle(id);
      if (revision !== this.revision || state.mode !== 'time' || state.selected !== selection) return;
      selection.loading = false; selection.data = battle;
      const { start, end } = battleBounds(battle);
      this.battleCursor = cursorText(start);
      const spanDays = start && end ? Math.max(0, (end - start) / 86400000) : 365;
      const hourly = (battle.stages || []).some(stage => String(stage.date).includes('T'));
      this.battleGranularity = hourly ? 'hour' : spanDays <= 90 ? 'day' : 'month';
      this.battlePlaying = false; clearInterval(this.battleTimer);
      if (!battle.routes.length) $('#history-status').textContent = '该记录按地点与史料阶段展示';
      cancelWheelGesture();
      map.flyTo([battle.coords[1],battle.coords[0]], Math.max(6.2, map.getZoom()), { duration: .8 });
      this.drawBattleRoutes(); renderDetail();
    } catch (error) {
      if (state.selected === selection) { selection.loading = false; selection.error = '战役资料读取失败，请返回列表后重试。'; renderDetail(); }
    }
  }

  async getBattleTimeline(id, at, granularity) {
    const key = `${id}|${at}|${granularity}`;
    if (!this.battleTimelineCache.has(key)) {
      const query = `/api/battles/${encodeURIComponent(id)}/timeline?at=${encodeURIComponent(at)}&granularity=${granularity}`;
      this.battleTimelineCache.set(key, getJson(query).catch(error => { this.battleTimelineCache.delete(key); throw error; }));
    }
    return this.battleTimelineCache.get(key);
  }

  setBattleGranularity(value) {
    if (!['hour', 'day', 'month'].includes(value) || !state.selected?.data) return;
    this.battleGranularity = value;
    if (value === 'hour' && !(state.selected.data.stages || []).some(stage => String(stage.date).includes('T'))) return;
    this.battleCursor = cursorText(battleBounds(state.selected.data).start);
    this.drawBattleRoutes(); renderDetail();
  }

  stepBattle(direction) {
    const battle = state.selected?.data;
    if (!battle) return;
    const { start, end } = battleBounds(battle);
    const next = isoCursor(stepCursor(this.battleCursor || battle.start_date, this.battleGranularity, direction));
    if (!next || !start || !end) return;
    const bounded = new Date(Math.max(start.getTime(), Math.min(end.getTime(), next.getTime())));
    this.battleCursor = cursorText(bounded);
    this.drawBattleRoutes(); renderDetail();
  }

  toggleBattlePlayback() {
    if (!state.selected?.data) return;
    this.battlePlaying = !this.battlePlaying;
    clearInterval(this.battleTimer);
    if (this.battlePlaying) {
      this.battleTimer = setInterval(() => {
        const before = this.battleCursor;
        this.stepBattle(1);
        if (!state.selected || this.battleCursor === before || isoCursor(this.battleCursor) >= battleBounds(state.selected.data).end) {
          this.battlePlaying = false; clearInterval(this.battleTimer); renderDetail();
        }
      }, 650 / this.battleSpeed);
    }
    renderDetail();
  }

  setBattleSpeed(value) {
    const speed = Number(value);
    if (!Number.isFinite(speed) || speed <= 0) return;
    this.battleSpeed = speed;
    if (this.battlePlaying) { this.battlePlaying = false; this.toggleBattlePlayback(); }
  }

  async drawBattleRoutes() {
    const revision = ++this.routeRevision;
    if (state.mode !== 'time') return;
    if (!this.annual) { this.paintRoutes([]); return; }
    this.troopPlayer.load();
    const ids = $('#all-battle-routes').checked ? this.filteredBattles().map(b => b.id)
      : state.selected?.type === 'battle' ? [state.selected.data.id] : [];
    try {
      const results = await Promise.allSettled(ids.map(async id => {
        const battle = await this.getBattle(id);
        // Timeline responses clip dated segments to the current cursor and
        // also normalize legacy routes that only carry start/end years.
        const at = state.selected?.type === 'battle' && state.selected.data.id === id
          ? (this.battleCursor || `${battle.start_date}T00:00`)
          : `${state.year}-12-31T23:59`;
        const timeline = await this.getBattleTimeline(id, at, this.battleGranularity);
        return { ...battle, routes: timeline.routes || [] };
      }));
      if (revision !== this.routeRevision || state.mode !== 'time') return;
      const battles = results.filter(result => result.status === 'fulfilled').map(result => result.value);
      const failed = results.length - battles.length;
      this.paintRoutes(battles.flatMap(b => b.routes.flatMap(route => Array.isArray(route.paths)
        ? route.paths.map(coordinates => ({...route, coordinates})) : [route])
        .filter(r => Array.isArray(r.coordinates) && r.coordinates.length >= 2)
        .map(r => ({ ...r, color: this.colors[r.faction], label: `${b.name} · ${r.label} · 推进方向` }))));
      if (failed && battles.length === 0) $('#history-status').textContent = '战役路线暂时无法载入，请重新选择';
      else if (!failed && state.selected?.type === 'battle') $('#history-status').textContent = `${state.selected.data.name} · 路线已更新`;
    } catch (error) {
      if (revision === this.routeRevision) $('#history-status').textContent = '部分战役路线读取失败，请重新选择';
    }
  }

  paintRoutes(routes) {
    this.routes = routes; this.routeLines.clearLayers(); this.arrows.clearLayers();
    for (const route of routes) {
      if (route.coordinates.length < 2) continue;
      const line = L.polyline(route.coordinates.map(([lon,lat]) => [lat,lon]), {
        renderer: this.routeRenderer, color: route.color || '#b42330', weight: route.active ? 4 : 2.5,
        opacity: route.dim ? .2 : .85, dashArray: route.exact ? null : '7 5', smoothFactor: 1.2,
      }).bindTooltip(safeText(route.label));
      if (route.node_id) line.on('click', () => this.selectNode(route.node_id));
      line.addTo(this.routeLines);
      const hit = L.polyline(route.coordinates.map(([lon,lat]) => [lat,lon]), {
        renderer: this.routeRenderer, weight: 32, opacity: 0, interactive: true,
      }).bindTooltip(safeText(route.label), { sticky: true });
      if (route.node_id) hit.on('click', () => this.selectNode(route.node_id));
      hit.addTo(this.routeLines);
    }
    this.drawArrows();
  }

  drawArrows() {
    this.arrows.clearLayers();
    for (const route of this.routes) {
      const pairs = route.coordinates;
      for (let i=1;i<pairs.length;i++) {
        const a=map.latLngToLayerPoint([pairs[i-1][1],pairs[i-1][0]]), b=map.latLngToLayerPoint([pairs[i][1],pairs[i][0]]);
        const distance=a.distanceTo(b);
        if (distance<28) continue;
        const tip=a.add(b.subtract(a).multiplyBy(.64));
        const unit=b.subtract(a).divideBy(distance), base=tip.subtract(unit.multiplyBy(9));
        const normal=L.point(-unit.y,unit.x).multiplyBy(4);
        const latlng=map.layerPointToLatLng(tip);
        if (!map.getBounds().pad(.1).contains(latlng)) continue;
        L.polygon([tip,base.add(normal),base.subtract(normal)].map(p=>map.layerPointToLatLng(p)), {
          renderer:this.routeRenderer, interactive:false, weight:0, fillColor:route.color||'#b42330',fillOpacity:route.dim?.2:.95,
        }).addTo(this.arrows);
      }
    }
  }

  async loadJourney() {
    if (!state.person || state.mode !== 'person') return;
    const revision = ++this.revision, id = state.person.id;
    this.loading = true; this.error = null; this.selectedNode = null;
    this.journey = null; this.clearLayers(); renderDetail();
    try {
      if (!this.journeyCache.has(id)) this.journeyCache.set(id, getJson(`/api/persons/${id}/timeline`).catch(error => { this.journeyCache.delete(id); throw error; }));
      const journey = await this.journeyCache.get(id);
      if (revision !== this.revision || state.mode !== 'person' || state.person.id !== id) return;
      this.journey = journey; this.loading = false;
      this.drawJourney(); renderDetail();
    } catch (error) {
      if (revision !== this.revision) return;
      this.loading = false; this.error = '人物行程资料加载失败，请重新选择人物。'; renderDetail();
    }
  }

  filteredNodes() {
    return (this.journey?.nodes || []).filter(n => !state.search || [n.title,n.location,n.story,n.year].join(' ').toLowerCase().includes(state.search));
  }

  drawJourney() {
    this.points.clearLayers();
    if (!this.journey || state.mode !== 'person') return;
    const matching = new Set(this.filteredNodes().map(n => n.id));
    const nodes = new Map(this.journey.nodes.map(n => [n.id,n]));
    const activeYear = this.selectedNode?.startsWith('year:') ? Number(this.selectedNode.slice(5)) : null;
    const active = n => n && (n.id === this.selectedNode || n.year === activeYear);
    this.paintRoutes(this.journey.segments.map(segment => {
      const from=nodes.get(segment.from), to=nodes.get(segment.to);
      const highlighted=active(from)||active(to);
      return { coordinates:segment.coordinates,color:this.journey.color,node_id:to.id,
        active:highlighted,dim:!!this.selectedNode&&!highlighted,
        label:`${from.year} ${from.location} → ${to.year} ${to.location} · 节点连线，非精确道路` };
    }));
    const groups = new Map();
    for (const node of this.journey.nodes) {
      if (!node.domestic || !matching.has(node.id)) continue;
      const key=node.coords.join(',');
      if (!groups.has(key)) groups.set(key,[]);
      groups.get(key).push(node);
    }
    for (const group of groups.values()) {
      const node=group.find(active)||group[0];
      const color=group.some(n=>n.stage==='death')?'#1d4ed8':group.some(n=>n.stage==='birth')?'#15803d':this.journey.color;
      const marker=L.circleMarker([node.coords[1],node.coords[0]],{
        renderer:this.routeRenderer,radius:active(node)?8:5,color:'#fffefa',weight:2,fillColor:color,fillOpacity:1,
      });
      marker.bindTooltip(group.map(n=>safeText(`${n.year} · ${n.location} · ${n.title}`)).join('<br>'),{className:'journey-tooltip'});
      marker.on('click',()=>this.selectNode(node.id)); marker.addTo(this.points);
    }
  }

  selectNode(id) {
    this.selectedNode=id;
    const nodes=id.startsWith('year:')?this.journey.nodes.filter(n=>n.year===Number(id.slice(5))):this.journey.nodes.filter(n=>n.id===id);
    const domestic=nodes.filter(n=>n.domestic);
    this.drawJourney(); renderDetail();
    cancelWheelGesture();
    if (domestic.length>1) map.flyToBounds(L.latLngBounds(domestic.map(n=>[n.coords[1],n.coords[0]])),{maxZoom:7.5,padding:[45,45],duration:.8});
    else if(domestic.length) map.flyTo([domestic[0].coords[1],domestic[0].coords[0]],Math.max(7.2,map.getZoom()),{duration:.8});
    const card=[...document.querySelectorAll('[data-node]')].find(e=>e.dataset.node===id);
    if(card) card.scrollIntoView({block:'nearest',behavior:'smooth'});
  }

  onSearch() {
    if(state.mode==='time'){ this.drawAnnual(); this.drawBattleRoutes(); }
    if(state.mode==='person'){ this.selectedNode=null; this.drawJourney(); }
  }

  onViewEnd() {
    if(state.mode==='time') this.drawAnnual();
    if(state.mode==='person'||state.mode==='time') this.drawArrows();
  }

  hoverText(latlng) {
    if(state.mode!=='time'||!this.annual||this.annual.year!==state.year)return '';
    const controls = (this.annual.control?.features || []).filter(feature => this.pointInGeometry([latlng.lng,latlng.lat], feature.geometry));
    if (controls.length) return controls.map(feature => {
      const p = feature.properties;
      return `${p.owner || this.names[p.faction]} · ${p.kind === 'guerrilla' ? '敌后活动' : '控制'} · ${p.start_at}—${p.end_at} · ${p.precision_note}`;
    }).join('；');
    const hits=this.annual.territories.filter(a=>(a.geometry_status==='verified_boundary'||a.geometry_status==='source_location_envelope')&&a.geometry&&this.pointInGeometry([latlng.lng,latlng.lat], a.geometry));
    return hits.length?hits.map(a=>`${a.name} · ${this.names[a.faction]} · ${this.kinds[a.kind]} · 来源范围`).join('；'):'现代行政地理底图';
  }

  sourceHtml(sources) {
    return `<details class="source-notes"><summary>资料来源与精度说明</summary>${sources.map(s=>`<p>${safeText(s.title)}<br>${safeText(s.scope)}<br><span class="source-url">${safeText(s.url)}</span></p>`).join('')}<p>来源网址仅作书目记录，页面运行不访问外网。点位按来源地名定位，虚线连接节点并表示推进方向。</p></details>`;
  }

  renderPanel() {
    if(state.mode==='person') { this.renderJourney(); return true; }
    if(state.mode!=='time') return false;
    if(state.selected?.type==='battle') { this.renderBattle(); return true; }
    if(state.selected) return false;
    renderList(visibleEvents(),'年度事件');
    $('#panel-kicker').textContent=`${this.phaseLabel()} · ${state.year} 年 · ${state.year<=1950?'历史形势':'普通地图'}`;
    if(this.loading||this.error) {
      $('#panel-content').insertAdjacentHTML('afterbegin',`<p class="history-note">${safeText(this.error||'正在读取本地年度资料…')}</p>`); return true;
    }
    if(!this.annual)return true;
    const battles=this.filteredBattles();
    $('#panel-count').textContent=`${visibleEvents().length} 事件 · ${battles.length} 战役`;
    const summary=`<section class="year-overview"><p class="history-note">${safeText(this.annual.summary||this.annual.note)}</p>${state.year<=1950?'<p class="accuracy-note">彩色区域是来源地点组成的范围包络，不代替现代行政边界或主权认定；空白地区不作归属判断。</p>':''}${this.sourceHtml(this.annual.sources||[])}</section>`;
    const battleHtml=`<section class="battle-list"><div class="section-label">${state.year>=1951?'建国后主要战役与军事行动':'当年战役'} · 点击展开推进方向</div>${battles.map(b=>`<button class="battle-card" data-battle="${safeText(b.id)}"><span>${safeText(b.start_date)} — ${safeText(b.end_date)}</span><strong>${safeText(b.name)}</strong><small>${safeText(b.location)} · ${safeText(b.summary)}</small></button>`).join('')||'<p class="empty-state">当年或当前搜索下未收录匹配战役；不代表当年不存在战斗。</p>'}</section>`;
    $('#panel-content').insertAdjacentHTML('afterbegin',summary+battleHtml);
    $('#panel-content').querySelectorAll('[data-battle]').forEach(button=>button.addEventListener('click',()=>this.selectBattle(button.dataset.battle)));
    return true;
  }

  renderBattle() {
    const selected=state.selected,b=selected.data;
    const recordLabel = b.kind === 'military_exercise' ? '军事演习详情' : '战役详情';
    $('#panel-kicker').textContent=`${state.year} 年 · ${recordLabel}`;
    $('#panel-title').textContent=b.name||'读取战役资料'; $('#panel-count').textContent='推进方向';
    if (selected.loading || selected.error) {
      $('#panel-content').innerHTML=`<button class="back-link" id="back-history">← 返回年度形势</button>${selected.loading?'<p class="empty-state">读取中…</p>':`<p>${safeText(selected.error)}</p>`}`;
      $('#back-history').onclick=()=>{state.selected=null;this.drawBattleRoutes();renderDetail();};
      return;
    }
    const {start,end}=battleBounds(b), cursor=isoCursor(this.battleCursor||b.start_date);
    const total=start&&end?Math.max(1,end-start):1, done=start&&cursor?Math.max(0,Math.min(total,cursor-start)):0;
    const progress=Math.round(done/total*100);
    const forces=(b.forces||[]).map(force=>`<li><strong>${safeText(force.name)}</strong> · ${safeText(force.branch||b.branch||'兵种资料')} · ${safeText(force.strength || '公开资料未列明人数')} · ${safeText(force.role||'')}<small>${safeText(force.strength_precision === 'not_published' ? '人数精度：公开资料未列明' : force.strength_precision || '')}</small></li>`).join('');
    const hasPlayback = b.route_playback !== false && Array.isArray(b.routes) && b.routes.length > 0;
    const controls=hasPlayback ? `<div class="battle-player" aria-label="战役路线播放器"><button class="ai-button" id="battle-prev" type="button">上一步</button><button class="ai-button" id="battle-play" type="button">${this.battlePlaying?'暂停':'播放'}</button><button class="ai-button" id="battle-next" type="button">下一步</button><label>速度<select id="battle-speed"><option value="0.5" ${this.battleSpeed===.5?'selected':''}>0.5×</option><option value="1" ${this.battleSpeed===1?'selected':''}>1×</option><option value="2" ${this.battleSpeed===2?'selected':''}>2×</option><option value="4" ${this.battleSpeed===4?'selected':''}>4×</option></select></label><label>粒度<select id="battle-granularity"><option value="hour" ${this.battleGranularity==='hour'?'selected':''}>小时</option><option value="day" ${this.battleGranularity==='day'?'selected':''}>天</option><option value="month" ${this.battleGranularity==='month'?'selected':''}>月</option></select></label><progress max="100" value="${progress}"></progress><span>${safeText(this.battleCursor||b.start_date)} · ${progress}%</span></div>` : '';
    const routeNote = b.route_note || (b.routes?.length ? '地图显示来源中的方向线。' : '来源只给出战区或地点，地图不绘制逐段行军线。');
    $('#panel-content').innerHTML=`<button class="back-link" id="back-history">← 返回年度形势</button><article class="detail-article"><p class="history-note">${safeText(b.start_date)} — ${safeText(b.end_date)}<br>领导人：${safeText(Array.isArray(b.commanders)?b.commanders.join('、'):b.commanders||'来源记录')}<br>参战方：${safeText((b.participants||[]).join(' / '))} · 主兵种：${safeText(b.branch||'来源记录')}</p>${controls}<p class="detail-story">${safeText(b.summary)}</p><p class="detail-story">结果：${safeText(b.result)}</p>${forces?`<div class="section-label">兵种与人数</div><ul class="battle-force-list">${forces}</ul>`:''}<div class="section-label">完整战役阶段</div>${(b.stages||[]).map(s=>`<p class="timeline-stage"><strong>${safeText(s.date)} · ${safeText(s.location)}</strong><br>${safeText(s.description)}</p>`).join('')}<p class="accuracy-note">${safeText(b.precision_note)}；${safeText(routeNote)}</p>${this.sourceHtml(b.sources||[])}</article>`;
    $('#back-history').onclick=()=>{this.battlePlaying=false;clearInterval(this.battleTimer);state.selected=null;this.drawBattleRoutes();renderDetail();};
    if (this.troopPlayer.models.size) {
      const units = document.createElement('section');
      units.className = 'battle-unit-locations';
      units.innerHTML = '<div class="section-label">参战部队来源位置</div>' + [...this.troopPlayer.models.values()].map(unit => {
        const arrival = this.troopPlayer.arrival(unit);
        return `<p class="timeline-stage"><strong>${safeText(unit.name)}</strong> · ${safeText(this.names[unit.faction] || unit.faction || '')}<br>${arrival ? `${safeText(arrival.at || arrival.date)} · ${safeText(arrival.place)}` : '尚未到达来源节点'}<br><small>${safeText(arrival?.source_locator || '按来源记录的地点显示')}</small></p>`;
      }).join('');
      $('#panel-content .detail-article').append(units);
    }
    if (hasPlayback) {
      $('#battle-prev').onclick=()=>this.stepBattle(-1);
      $('#battle-next').onclick=()=>this.stepBattle(1);
      $('#battle-play').onclick=()=>this.toggleBattlePlayback();
      $('#battle-speed').onchange=(event)=>this.setBattleSpeed(event.target.value);
      $('#battle-granularity').onchange=(event)=>this.setBattleGranularity(event.target.value);
    }
  }

  renderJourney() {
    $('#panel-kicker').textContent='实际到访节点 · 国内行程';
    $('#panel-title').textContent=state.person?.name||'人物行程';
    $('#panel-count').textContent=this.journey?`${this.journey.nodes.length} 个节点`:'读取中';
    if(this.loading||this.error||!this.journey){$('#panel-content').innerHTML=`<p class="empty-state">${safeText(this.error||'正在读取人物行程…')}</p>`;return;}
    const nodes=this.filteredNodes();
    const years=[...new Set(nodes.map(n=>n.year))];
    const spirit = personSpiritProfile(state.person);
    const evidence = this.journey.nodes.slice(0, 3).map(node => `${node.year}年 ${node.location}·${node.title}`).join('；');
    $('#panel-content').innerHTML=`<section class="person-spirit" aria-label="人物代表的红色精神"><div class="section-label">代表性红色精神</div><p>结合 ${safeText(state.person?.name || '该人物')} 的生平节点与行动线索，提炼出可在地图中继续追踪的精神关键词：</p><div class="spirit-pillars">${spirit.map(tag=>`<span>${safeText(tag)}</span>`).join('')}</div><p class="person-spirit-evidence">对应行动节点：${safeText(evidence || '当前人物暂无可展示的节点')}</p></section><p class="history-note">已收录国内行程 · 点击年份或节点高亮。海外经历仅列在下方，并中断国内连接线。</p><p class="accuracy-note">按来源整理的到访记录；虚线连接时间节点，路线按地点坐标绘制。</p><div class="journey-list">${years.map(year=>`<section><button class="journey-year ${this.selectedNode===`year:${year}`?'selected':''}" data-journey-year="${year}">${year} 年</button>${nodes.filter(n=>n.year===year).map(n=>`<button class="journey-node ${this.selectedNode===n.id?'selected':''}" data-node="${safeText(n.id)}"><span>${safeText(n.date||`${n.year}年`)} · ${n.domestic?'国内':'海外 · 不在地图连线'}</span><strong>${safeText(n.location)} · ${safeText(n.title)}</strong><small>${safeText(n.story)}</small>${n.verification==='source_indexed'?'<em>来源节点 · 位置按记录层级显示</em>':''}</button>`).join('')}</section>`).join('')||'<p class="empty-state">没有匹配的行程记录。</p>'}</div>${this.sourceHtml(this.journey.sources)}`;
    $('#panel-content').querySelectorAll('[data-node]').forEach(button=>button.onclick=()=>this.selectNode(button.dataset.node));
    $('#panel-content').querySelectorAll('[data-journey-year]').forEach(button=>button.onclick=()=>this.selectNode(`year:${button.dataset.journeyYear}`));
  }
}
