/* global L */

const state = {
  mode: "ordinary",
  eventTheme: "all",
  year: 1935,
  person: null,
  events: [],
  persons: [],
  personSpirit: "",
  search: "",
  selected: null,
  listLimit: 120,
  boundaryLevel: null,
  boundaryRequest: 0,
};

const $ = (selector) => document.querySelector(selector);
const LIST_PAGE_SIZE = 120;
const panelContent = $("#panel-content");
// Start with the bundled country layer in a true world overview.  Selecting
// an event still flies to its Chinese location, so the thematic China view is
// preserved while the first screen clearly shows the whole world basemap.
const map = L.map("map", { zoomControl: false, preferCanvas: true, minZoom: 1.5, maxZoom: 12, zoomSnap: 0, zoomDelta: .5, scrollWheelZoom: false, attributionControl: false }).setView([20, 10], 2.2);
L.control.zoom({ position: "topright" }).addTo(map);
function updateProvinceLabels() {
  // Province names are useful at the national view only. Once city or
  // district geometry is active they become a second, noisy label layer.
  const show = state.boundaryLevel === "province" && map.getZoom() >= 3.35;
  document.querySelectorAll(".province-label").forEach((label) => { label.style.display = show ? "" : "none"; });
}
map.on("zoomend", updateProvinceLabels);
// Keep the visible geometry on Canvas for performance, but give every region
// a generous pointer tolerance so thin county borders remain easy to hit.
// Leaflet's Canvas renderer uses `tolerance` in _containsPoint; 10px also
// covers the small pointer drift that happens while zooming or panning.
const renderer = L.canvas({ padding: .35, tolerance: 10 });
map.createPane("countryBase").style.zIndex = "190";
map.getPane("countryBase").style.pointerEvents = "none";
map.createPane("worldBase").style.zIndex = "100";
map.getPane("worldBase").style.pointerEvents = "auto";
const worldBaseLayer = L.geoJSON(null, {
  renderer: L.canvas({ pane: "worldBase", padding: .25, tolerance: 10 }), interactive: true,
  style: { color: "#aeb8b1", weight: .45, fillColor: "#e6e9e1", fillOpacity: 1 },
  onEachFeature: (feature, layer) => {
    const props = feature.properties || {};
    layer.on({
      mouseover: (event) => showWorldHover(feature, event.latlng, layer),
      mousemove: (event) => moveWorldHover(feature, event.latlng),
      mouseout: () => { worldBaseLayer.resetStyle(layer); hideRegionHover(); },
    });
    layer.bindTooltip(safeText(props.name || props.iso_a3 || "世界区域"), {
      className: "boundary-label world-label", sticky: false, opacity: .92,
    });
  },
}).addTo(map);
const countryBaseLayer = L.geoJSON(null, {
  renderer: L.canvas({ pane: "countryBase", padding: .25 }), interactive: false,
  style: { color: "#b3b9ae", weight: .4, fillColor: "#eeeae0", fillOpacity: 1 },
}).addTo(map);
const boundaryLayer = L.geoJSON(null, { renderer, smoothFactor: 1.4 }).addTo(map);
const boundaryLayers = new Map();
map.createPane("regionHighlight").style.pointerEvents = "none";
map.getPane("regionHighlight").style.zIndex = "470";
const highlightLayer = L.geoJSON(null, {
  // SVG paths can receive a compositor transform. This lets the active
  // region appear to lift a few pixels above the map without reprojecting
  // the source geometry or blocking pointer events.
  renderer: L.svg({ padding: .12, pane: "regionHighlight" }),
  interactive: false,
  style: { weight: 1.5, color: "#772019", fillColor: "#dbbeb2", fillOpacity: .46 },
}).addTo(map);
const eventLayer = L.layerGroup().addTo(map);
const eventMarkers = new Map();
map.createPane("eventMarkers").style.zIndex = "600";
map.getPane("eventMarkers").style.pointerEvents = "auto";
const routeLayer = L.layerGroup().addTo(map);
const routeRenderer = L.canvas({ padding: .35, tolerance: 14 });
const seaMap = L.map("south-sea-map", { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false }).setView([14, 116], 3);
const seaLayer = L.geoJSON(null, { style: { color: "#9f5441", weight: 1, fillColor: "#e3b89d", fillOpacity: .6 } }).addTo(seaMap);

const boundaryCache = new Map();
const boundaryRequests = new Map();
const boundaryIndexes = {
  province: new Map(),
  city: new Map(),
  district: new Map(),
};
let guangdongBounds = null;
let mapMoving = false;
let viewTimer = 0;
let wheelFrame = 0;
let wheelTarget = null;
let wheelPoint = null;
let wheelAnchor = null;

// A single compositor-positioned tooltip: moving it never repaints boundaries.
const hoverTooltip = document.createElement("div");
hoverTooltip.className = "boundary-label hover-label map-hover-label";
hoverTooltip.setAttribute("role", "tooltip");
hoverTooltip.hidden = true;
map.getContainer().appendChild(hoverTooltip);
let hoveredRegion = null;
let hoverFrame = 0;
let hoverGeneration = 0;
let pointerPosition = null;
let mapRect = map.getContainer().getBoundingClientRect();
let hoverWidth = 0;
let hoverRefreshTimer = 0;
let wheelIdleTimer = 0;
let hoverHitFrame = 0;

function positionHover() {
  if (hoverFrame || !pointerPosition || hoverTooltip.hidden) return;
  hoverFrame = requestAnimationFrame(() => {
    hoverFrame = 0;
    if (hoverTooltip.hidden || !pointerPosition) return;
    if (!hoverWidth) hoverWidth = hoverTooltip.offsetWidth;
    const x = Math.max(8, Math.min(pointerPosition.x + 16, mapRect.width - hoverWidth - 8));
    const y = Math.max(8, Math.min(pointerPosition.y + 18, mapRect.height - 42));
    hoverTooltip.style.transform = `translate3d(${x}px,${y}px,0)`;
  });
}

function hideRegionHover() {
  hoverGeneration += 1;
  if (hoverFrame) { cancelAnimationFrame(hoverFrame); hoverFrame = 0; }
  hoverTooltip.hidden = true;
  hoverTooltip.removeAttribute("data-info");
  if (hoveredRegion !== null) highlightLayer.clearLayers();
  hoveredRegion = null;
}

function regionInfo(properties, level) {
  const levelName = level === "province" ? "省级" : level === "city" ? "市级" : "区县级";
  const coverage = properties.coverage_status === "has_children"
    ? "含下辖地区"
    : properties.coverage_status === "county_unit"
      ? "县级单位"
      : properties.coverage_status === "no_county_level_units"
        ? "无县级下辖单位"
        : "行政区资料";
  return `${levelName} · ${coverage}`;
}

function markLiftedRegion() {
  const generation = hoverGeneration;
  // addData schedules the SVG path synchronously, but defer one frame so the
  // path element is available in every Leaflet version used by the bundle.
  requestAnimationFrame(() => {
    if (generation !== hoverGeneration || hoveredRegion === null || hoverTooltip.hidden) return;
    highlightLayer.getLayers().forEach((layer) => {
      const element = layer.getElement?.();
      if (element) element.classList.add("region-highlight-lift");
    });
  });
}

function showRegionHover(feature, level, latlng = null) {
  if (mapMoving) return;
  const key = `${level}:${feature.properties.id}`;
  if (hoveredRegion !== key) {
    hoverGeneration += 1;
    hoveredRegion = key;
    highlightLayer.clearLayers();
    highlightLayer.addData(feature);
    markLiftedRegion();
    const historical = latlng ? explorer.hoverText(latlng) : '';
    hoverTooltip.textContent = regionLabel(feature.properties, level) + (historical ? ` · ${historical}` : '');
    // Keep the compact textContent used by assistive tech and existing API
    // checks, while exposing level/coverage details visually via ::after.
    hoverTooltip.dataset.info = regionInfo(feature.properties, level);
    hoverTooltip.hidden = false;
    hoverWidth = 0;
  }
  positionHover();
}

function worldLabel(properties) {
  return properties.name || properties.name_en || properties.iso_a3 || "世界区域";
}

function moveWorldHover(feature, latlng = null) {
  if (mapMoving || hoverTooltip.hidden) return;
  const props = feature.properties || {};
  const historical = latlng ? explorer.hoverText(latlng) : "";
  const text = `${worldLabel(props)} · 世界国家${historical ? ` · ${historical}` : ""}`;
  if (hoverTooltip.textContent !== text) { hoverTooltip.textContent = text; hoverWidth = 0; }
  hoverTooltip.dataset.info = "世界国家 · Natural Earth 离线底图";
  hoverTooltip.hidden = false;
  positionHover();
}

function showWorldHover(feature, latlng = null, layer = null) {
  if (mapMoving) return;
  const props = feature.properties || {};
  const key = `world:${props.iso_a3 || props.id || props.name}`;
  if (hoveredRegion !== key) {
    hoverGeneration += 1;
    hoveredRegion = key;
    highlightLayer.clearLayers();
    highlightLayer.addData(feature);
    markLiftedRegion();
    if (layer?.setStyle) layer.setStyle({ weight: 1.15, color: "#68766e", fillColor: "#cbdccf", fillOpacity: .96 });
    const historical = latlng ? explorer.hoverText(latlng) : "";
    hoverTooltip.textContent = `${worldLabel(props)} · 世界国家${historical ? ` · ${historical}` : ""}`;
    hoverTooltip.dataset.info = "世界国家 · Natural Earth 离线底图";
    hoverTooltip.hidden = false;
    hoverWidth = 0;
  }
  positionHover();
}

map.getContainer().addEventListener("pointerenter", () => { mapRect = map.getContainer().getBoundingClientRect(); });
map.getContainer().addEventListener("pointermove", (event) => {
  pointerPosition = { x: event.clientX - mapRect.left, y: event.clientY - mapRect.top };
  positionHover();
  if (!hoverHitFrame && !event.target.closest('.leaflet-control,.leaflet-marker-icon')) {
    hoverHitFrame = requestAnimationFrame(() => {
      hoverHitFrame = 0;
      refreshHoverAtPointer();
    });
  }
}, { passive: true });
map.getContainer().addEventListener("pointerleave", hideRegionHover);
let resizeMapTimer = 0;
window.addEventListener("resize", () => {
  mapRect = map.getContainer().getBoundingClientRect(); hoverWidth = 0;
  clearTimeout(resizeMapTimer);
  resizeMapTimer = setTimeout(() => map.invalidateSize({ pan: false }), 90);
});
window.addEventListener("scroll", () => { mapRect = map.getContainer().getBoundingClientRect(); hideRegionHover(); }, { passive: true });

async function getJson(url) {
  if (window.RedMapData) return window.RedMapData.getJSON(url);
  // Keep the offline bundle immediately refreshable after boundary/data updates.
  // All requests remain local; the in-memory boundary cache still prevents
  // repeat downloads during a session.
  const response = await fetch(url, { cache: "default" });
  if (!response.ok) throw new Error(`加载失败: ${url}`);
  return response.json();
}

function safeText(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function regionLabel(properties, level) {
  if (properties.full_name) return properties.full_name + (properties.coverage_status === "no_county_level_units" ? "（无县级下辖单位）" : "");
  const name = properties.name || "未命名区域";
  if (level === "province") return name;

  const parentId = String(properties.parent || "");
  const province = level === "city"
    ? boundaryIndexes.province.get(parentId)
    : boundaryIndexes.province.get(String(boundaryIndexes.city.get(parentId)?.parent || parentId));
  const city = level === "city"
    ? properties
    : boundaryIndexes.city.get(parentId) || province;
  const provinceName = province?.name || "中国";
  const cityName = city?.name || "本市";
  if (level === "city") return `${provinceName} · ${name}`;
  if (city === province) return `${provinceName} · ${name}`;
  return `${provinceName} · ${cityName} · ${name}`;
}

function modeLabel(mode) {
  if (mode === "ordinary" && state.eventTheme !== "all") return eventThemeLabel(state.eventTheme);
  return ({ ordinary: "全国概览", time: `${state.year} 年`, person: state.person?.name || "人物故事线" })[mode];
}

function eventThemeLabel(theme) {
  return ({
    all: "全部事件",
    founding_revolution: "建党与大革命／北伐",
    land_revolution: "土地革命",
    long_march: "长征",
    anti_japanese: "抗日战争",
    liberation_war: "解放战争",
    founding_new_china: "建国后／抗美援朝",
    construction_reform: "建设改革新时代",
    sites_people: "遗址与人物",
  })[theme] || "全部事件";
}

function syncPersonOptions() {
  const filter = $("#person-spirit-filter");
  const select = $("#person-select");
  if (!filter || !select) return;
  const wanted = filter.value;
  const available = state.persons.filter((person) => !wanted || personSpiritProfile(person).includes(wanted));
  if (!available.length) return;
  const selected = available.find((person) => person.id === state.person?.id) || available[0];
  state.person = selected;
  select.innerHTML = available.map((person) =>
    `<option value="${safeText(person.id)}">${safeText(person.name)}</option>`
  ).join("");
  select.value = selected.id;
}

function spiritTags(event) {
  const text = [event.title, event.period, event.summary, event.story, ...(event.tags || []), ...(event.themes || [])].filter(Boolean).join(" ");
  const tags = [];
  if (/建党|大革命|北伐|国共合作|工人运动/.test(text)) tags.push("理想信念", "组织动员");
  if (/土地革命|根据地|反围剿|长征|红军/.test(text)) tags.push("实事求是", "艰苦奋斗");
  if (/抗日|抗战|敌后|百团|平型关|台儿庄/.test(text)) tags.push("团结抗战", "依靠人民");
  if (/解放战争|辽沈|淮海|平津|渡江|西柏坡/.test(text)) tags.push("敢于斗争", "人民立场");
  if (/建国|新中国|抗美援朝|志愿军|社会主义改造|五年计划/.test(text)) tags.push("为民担当", "自力更生");
  if (/建设|改革开放|新时代|航天|脱贫|强军|空间站/.test(text)) tags.push("改革创新", "建设担当");
  return [...new Set(tags)].slice(0, 4);
}

// Existing records use period/tags/themes rather than a single category field.
// Derive stable filter memberships locally so the event module can expose
// broad historical groupings without rewriting the offline source records.
function eventCategoryIds(event) {
  const categories = new Set(["all"]);
  const text = [event.title, event.period, event.summary, event.story, ...(event.tags || [])].filter(Boolean).join(" ");
  const year = Number(event.year) || 0;
  const hasYear = year > 0;
  const themes = Array.isArray(event.themes) ? event.themes : [];
  const kind = String(event.kind || "");
  if (themes.includes("long_march") || /长征/.test(text)) categories.add("long_march");
  // Annual records carry authoritative years; use text matching only for
  // imported records without a year so later context cannot leak backward.
  if ((hasYear && year >= 1937 && year <= 1945) || (!hasYear && themes.includes("anti_japanese"))) categories.add("anti_japanese");
  if ((hasYear && year >= 1921 && year <= 1926) || (!hasYear && /建党|大革命|北伐|国共合作|黄埔|五卅|工人运动|统一战线/.test(text))) categories.add("founding_revolution");
  if ((hasYear && year >= 1927 && year <= 1936) || (!hasYear && /土地革命|根据地|秋收|南昌起义|井冈山|中央苏区|苏维埃|红军/.test(text))) categories.add("land_revolution");
  if ((hasYear && year >= 1946 && year <= 1948) || (!hasYear && /解放战争|辽沈|淮海|平津|北平和平|渡江|西柏坡/.test(text))) categories.add("liberation_war");
  if ((hasYear && year >= 1949 && year <= 1952) || (!hasYear && /建国|新中国|抗美援朝|志愿军|第一届全国人民代表大会|五年计划|宪法|社会主义改造/.test(text))) categories.add("founding_new_china");
  if ((hasYear && year >= 1953) || (!hasYear && /建设|改革开放|新时代|深圳经济特区|香港回归|澳门回归|神舟|航天|空间站|嫦娥|脱贫|抗击新冠|强军|原子弹|青藏/.test(text))) categories.add("construction_reform");
  if (kind !== "event" || /遗址|故居|纪念馆|人物生平|诞生|逝世/.test(text)) categories.add("sites_people");
  return [...categories];
}

function visibleEvents() {
  return state.events.filter((event) => {
    const themes = Array.isArray(event.themes) ? event.themes : [];
    if (state.mode === "ordinary" && state.eventTheme !== "all" && !eventCategoryIds(event).includes(state.eventTheme)) return false;
    if (state.mode === "time" && event.year !== state.year) return false;
    if (state.mode === "person" && state.person && !(event.people || []).includes(state.person.name)) return false;
    if (state.search) {
      const haystack = [event.title, event.province, event.city, event.district, event.summary, event.story, ...(event.people || []), ...(event.tags || [])].join(" ").toLowerCase();
      if (!haystack.includes(state.search)) return false;
    }
    return true;
  });
}

function boundaryStyle(level) {
  return { className: `boundary-${level}`, fillColor: level === "province" ? "#dfe4dc" : level === "city" ? "#eee9df" : "#f7f3e9", fillOpacity: level === "province" ? .72 : level === "city" ? .33 : .08, color: level === "province" ? "#77837a" : level === "city" ? "#92988f" : "#b7b6ae", weight: level === "province" ? 1.1 : level === "city" ? .7 : .45 };
}

function drawBoundary(feature, layer, level) {
  layer.setStyle(boundaryStyle(level));
  layer.on({
    mouseover: (event) => showRegionHover(feature, level, event.latlng),
    mousemove: (event) => {
      if (state.mode !== 'time' || mapMoving) return;
      const text = `${regionLabel(feature.properties, level)} · ${explorer.hoverText(event.latlng)}`;
      if (hoverTooltip.textContent !== text) { hoverTooltip.textContent = text; hoverWidth = 0; }
      hoverTooltip.dataset.info = regionInfo(feature.properties, level);
      hoverTooltip.hidden = false; positionHover();
    },
    mouseout: hideRegionHover,
    click: () => selectRegion({ ...feature.properties, displayName: regionLabel(feature.properties, level) }),
  });
  if (level === "province" && !feature.properties.display_role) layer.bindTooltip(safeText(regionLabel(feature.properties, level)), {
    className: "boundary-label province-label",
    direction: "center",
    sticky: false,
    permanent: true,
    opacity: .96,
  });
}

function viewportFitsCurrentRegion() {
  const bounds = map.getBounds();
  const width = Math.abs(bounds.getEast() - bounds.getWest());
  const height = Math.abs(bounds.getNorth() - bounds.getSouth());
  const zoom = map.getZoom();
  const guangdongWidth = guangdongBounds ? Math.abs(guangdongBounds.getEast() - guangdongBounds.getWest()) : 4.5;
  const guangdongHeight = guangdongBounds ? Math.abs(guangdongBounds.getNorth() - guangdongBounds.getSouth()) : 3.2;
  const guangdongFits = width >= guangdongWidth * 1.1 && height >= guangdongHeight * 1.1;
  // At the national view the user can still see a whole province. Once the
  // viewport is narrower than a typical province, expose cities; the next
  // threshold exposes districts. Hysteresis prevents flicker near thresholds.
  if (guangdongFits) return "province";
  return zoom >= (state.boundaryLevel === "district" ? 8.15 : 8.35) ? "district" : "city";
}

function boundsArray(bounds) {
  return [
    Math.max(-180, Math.min(180, Math.floor(bounds.getWest() * 1000) / 1000)),
    Math.max(-90, Math.min(90, Math.floor(bounds.getSouth() * 1000) / 1000)),
    Math.max(-180, Math.min(180, Math.ceil(bounds.getEast() * 1000) / 1000)),
    Math.max(-90, Math.min(90, Math.ceil(bounds.getNorth() * 1000) / 1000)),
  ];
}

function intersectsBounds(a, b) {
  return !a || (a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1]);
}

async function loadBoundaryWindow(level, view) {
  const visible = boundsArray(view);
  for (const [key, entry] of boundaryCache) {
    const b = entry.bounds;
    if (entry.level === level && b[0] <= visible[0] && b[1] <= visible[1] && b[2] >= visible[2] && b[3] >= visible[3]) {
      boundaryCache.delete(key);
      boundaryCache.set(key, entry);
      return entry.payload;
    }
  }
  const bounds = level === "province" ? [-180, -90, 180, 90] : boundsArray(view.pad(.4));
  const key = `${level}:${bounds.join(",")}`;
  if (!boundaryRequests.has(key)) {
    const url = `/api/geo/${level}${level === "province" ? "" : `?bbox=${bounds.join(",")}`}`;
    boundaryRequests.set(key, getJson(url).then((payload) => {
      boundaryCache.set(key, { level, bounds, payload });
      while (boundaryCache.size > 10) boundaryCache.delete(boundaryCache.keys().next().value);
      return payload;
    }).finally(() => boundaryRequests.delete(key)));
  }
  return boundaryRequests.get(key);
}

async function updateBoundaries() {
  const level = viewportFitsCurrentRegion();
  const requestId = ++state.boundaryRequest;
  const hint = level === "province" ? "省级视图 · 滚轮或双指缩放查看市、区县" : level === "city" ? "市级视图 · 继续放大查看区县与红色地点" : "区县视图 · 红色地点已展开";
  try {
    const view = map.getBounds().pad(.12);
    const payload = await loadBoundaryWindow(level, view);
    if (requestId !== state.boundaryRequest) return;
    if (level === "province" && !countryBaseLayer.getLayers().length) countryBaseLayer.addData(payload);
    const viewport = boundsArray(view);
    const features = payload.features.filter((feature) => intersectsBounds(feature.bbox, viewport));
    const wanted = new Set(features.map((feature) => `${level}:${feature.properties.id}`));
    const additions = [];
    let started = performance.now();
    for (const feature of features) {
      const key = `${level}:${feature.properties.id}`;
      if (boundaryLayers.has(key)) continue;
      const layer = L.geoJSON(feature, {
        renderer, smoothFactor: 1.4,
        onEachFeature: (item, child) => drawBoundary(item, child, item.properties.level || level),
      }).getLayers()[0];
      if (layer) additions.push([key, layer]);
      // Yield large first-time views so input/animation never waits for a full batch.
      if (performance.now() - started > 5) {
        await new Promise(requestAnimationFrame);
        if (requestId !== state.boundaryRequest) return;
        started = performance.now();
      }
    }
    if (requestId !== state.boundaryRequest) return;
    hideRegionHover();
    // Commit the prepared batch in one frame. Keep the previous coverage until
    // every incoming layer is ready; yielding mid-commit could leave holes.
    for (const [key, layer] of additions) {
      boundaryLayer.addLayer(layer);
      boundaryLayers.set(key, layer);
    }
    for (const [key, layer] of boundaryLayers) {
      if (!wanted.has(key)) { boundaryLayer.removeLayer(layer); boundaryLayers.delete(key); }
    }
    state.boundaryLevel = level;
    updateProvinceLabels();
    $("#zoom-hint").textContent = hint;
  } catch (error) {
    if (requestId !== state.boundaryRequest) return;
    console.error(error);
    $("#zoom-hint").textContent = "边界数据加载失败，请运行 scripts/download_boundaries.py";
  }
}

function icon(kind, timelineType = null) {
  const timelineClass = timelineType === "birth" ? " person-start-marker" : timelineType === "death" ? " person-end-marker" : "";
  return L.divIcon({ className: `${kind === "event" ? "event-marker" : "site-marker"}${timelineClass}`, iconSize: [10, 10], iconAnchor: [5, 5] });
}

function eventClusterIcon(count) {
  return L.divIcon({
    className: "event-cluster-marker",
    html: `<span>${safeText(count)}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

function drawEvents() {
  // The time view already has its own visual grammar: faction coverage,
  // battle markers, dated routes, and troop arrivals. Keeping ordinary event
  // dots out of that layer prevents four independent timelines from merging
  // into an unreadable map while the complete annual list remains in the panel.
  if (state.mode === 'person' || state.mode === 'time') {
    eventLayer.clearLayers(); eventMarkers.clear(); return;
  }
  const items = visibleEvents();
  const zoom = map.getZoom();
  const bounds = map.getBounds().pad(.2);
  const wanted = new Set();
  const shouldCluster = state.mode === "ordinary" && (zoom < 6.4 || (items.length > 120 && zoom < 7.2));
  const cellSize = state.eventTheme === "all" ? 58 : 48;
  const coordinateCounts = new Map();
  items.forEach((event) => {
    const coordinateKey = event.coords.map((value) => Number(value).toFixed(5)).join(",");
    coordinateCounts.set(coordinateKey, (coordinateCounts.get(coordinateKey) || 0) + 1);
  });
  const groups = new Map();
  items.forEach((event) => {
    if ((zoom < 4.2 && state.mode === "ordinary") || !bounds.contains([event.coords[1], event.coords[0]])) return;
    const point = shouldCluster ? map.latLngToContainerPoint([event.coords[1], event.coords[0]]) : null;
    const coordinateKey = event.coords.map((value) => Number(value).toFixed(5)).join(",");
    const key = coordinateCounts.get(coordinateKey) > 1 && !shouldCluster
      ? `stack:${coordinateKey}`
      : shouldCluster
        ? `cluster:${Math.floor(point.x / cellSize)}:${Math.floor(point.y / cellSize)}`
        : `event:${event.id}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(event);
  });
  groups.forEach((group, key) => {
    const event = group[0];
    wanted.add(key);
    if (eventMarkers.has(key)) return;
    const isCluster = group.length > 1;
    const marker = L.marker([event.coords[1], event.coords[0]], {
      icon: isCluster ? eventClusterIcon(group.length) : icon(event.kind),
      keyboard: true,
      pane: "eventMarkers",
      title: isCluster ? `${group.length} 个事件` : event.title,
    });
    if (isCluster) {
      const samePlace = key.startsWith("stack:");
      marker.bindTooltip(`${group.length} 个事件 · ${samePlace ? "同一地点，点击查看列表" : "点击放大查看"}`, { direction: "top", offset: [0, -12] });
      marker.on("click", () => {
        if (samePlace) {
          renderEventListDrawer(group);
          setEventListDrawer(true);
          return;
        }
        const bounds = L.latLngBounds(group.map(item => [item.coords[1], item.coords[0]]));
        map.flyToBounds(bounds, { padding: [45, 45], maxZoom: Math.min(8.2, Math.max(7.2, map.getZoom() + 2)), duration: .65 });
      });
    } else {
      marker.on("click", () => selectEvent(event));
      const stage = event.timeline_type ? ` · ${safeText(event.tags?.find((tag) => ["出生", "逝世"].includes(tag)) || "重要节点")}` : "";
      marker.bindTooltip(`${safeText(event.title)} · ${event.year}${stage}`, { direction: "top", offset: [0, -7] });
    }
    marker.addTo(eventLayer);
    eventMarkers.set(key, marker);
  });
  for (const [key, marker] of eventMarkers) {
    if (!wanted.has(key)) { eventLayer.removeLayer(marker); eventMarkers.delete(key); }
  }
  if (!state.selected && state.mode !== 'time') $("#panel-count").textContent = `${items.length} 条内容`;
}

async function drawRoutes() {
  routeLayer.clearLayers();
  const mode = state.mode === "ordinary" ? state.eventTheme : "all";
  if (mode === "all" || state.mode === "time" || state.mode === "person") return;
  // Only these categories have dedicated multi-line route datasets.  Other
  // event categories remain valid filters and simply have no route overlay;
  // avoid requesting unsupported API literals and surfacing false errors.
  if (!(mode === "long_march" || mode === "anti_japanese")) return;
  let routes = [];
  const payload = await getJson(`/api/routes/${mode}`);
  if (state.mode !== "ordinary" || state.eventTheme !== mode) return;
  routes = payload.routes;
  routes.forEach((route) => {
    const points = route.coordinates.map((pair) => [pair[1], pair[0]]);
    L.polyline(points, { renderer: routeRenderer, color: route.color || "#a72a20", weight: 2.2, opacity: .68, dashArray: mode === "anti_japanese" ? "7 7" : null, lineCap: "round", lineJoin: "round" }).addTo(routeLayer);
  });
}

function selectEvent(event) {
  if (!event) return;
  cancelWheelGesture();
  hideRegionHover();
  state.selected = { type: "event", data: event };
  collapseMobileNavigation();
  map.flyTo([event.coords[1], event.coords[0]], window.innerWidth <= 680 ? 5.2 : Math.max(map.getZoom(), 7.2), {
    animate: true,
    duration: 0.85,
    easeLinearity: 0.22,
  });
  renderDetail();
}

async function selectRegion(properties) {
  collapseMobileNavigation();
  const selected = { type: "region", data: properties, loading: true };
  state.selected = selected;
  renderDetail();
  try {
    const result = await getJson(`/api/regions/${encodeURIComponent(properties.id || properties.name)}/stories${state.mode === 'time' ? `?year=${state.year}` : ''}`);
    if (state.selected !== selected) return;
    selected.loading = false;
    selected.stories = result.items;
    renderDetail();
  } catch (error) {
    console.error(error);
    if (state.selected !== selected) return;
    state.selected.loading = false;
    state.selected.stories = [];
    renderDetail();
  }
}

function setEventListDrawer(expanded) {
  const drawer = $("#event-list-drawer");
  const toggle = $("#event-list-toggle");
  if (!drawer || drawer.classList.contains("hidden")) return;
  drawer.classList.toggle("is-collapsed", !expanded);
  drawer.classList.toggle("is-expanded", expanded);
  toggle?.setAttribute("aria-expanded", String(expanded));
  if (toggle) toggle.textContent = expanded ? "收起事件列表" : "展开事件列表";
}
window.setEventListDrawer = setEventListDrawer;

function setEventListDrawerVisible(visible) {
  const drawer = $("#event-list-drawer");
  if (!drawer) return;
  drawer.classList.toggle("hidden", !visible);
  if (!visible) setEventListDrawer(false);
}

function renderEventListDrawer(items) {
  const drawer = $("#event-list-drawer");
  const content = $("#event-list-drawer-content");
  if (!drawer || !content) return;
  setEventListDrawerVisible(true);
  content.innerHTML = items.length ? items.slice().sort((a, b) => a.year - b.year).map((event) => `<article class="drawer-story" data-id="${safeText(event.id)}"><div class="story-meta"><span>${safeText(event.year)} · ${safeText(event.period)}</span><span>${safeText(event.kind === "event" ? "历史事件" : "红色地点")}</span></div><h3 class="story-title">${safeText(event.title)}</h3><p class="story-summary">${safeText(event.summary)}</p></article>`).join("") : '<p class="empty-state">当前筛选下没有其他事件。</p>';
  content.querySelectorAll("[data-id]").forEach((card) => card.addEventListener("click", () => selectEvent(state.events.find((event) => event.id === card.dataset.id))));
}

function focusEvent(event) {
  if (!event?.coords) return;
  map.flyTo([event.coords[1], event.coords[0]], window.innerWidth <= 680 ? 5.2 : 6.2, { animate: true, duration: .65, easeLinearity: .24 });
}

function collapseMobileNavigation() {
  if (window.innerWidth > 680) return;
  const controls = $("#main-controls");
  const toggle = $("#mobile-nav-toggle");
  controls?.classList.add("nav-collapsed");
  toggle?.setAttribute("aria-expanded", "false");
}

function renderList(items, heading = "重点脉络") {
  setEventListDrawerVisible(false);
  const orderedItems = items.slice().sort((a, b) => a.year - b.year);
  const shownItems = orderedItems.slice(0, state.listLimit);
  const remaining = orderedItems.length - shownItems.length;
  $("#panel-kicker").textContent = modeLabel(state.mode);
  $("#panel-title").textContent = state.search ? `搜索结果 · ${state.search}` : heading;
  $("#panel-count").textContent = remaining > 0 ? `${shownItems.length} / ${items.length} 条内容` : `${items.length} 条内容`;
  const cards = shownItems.length ? shownItems.map((event) => `<article class="story-card" data-id="${safeText(event.id)}"><div class="story-meta"><span>${safeText(event.year)} · ${safeText(event.period)}</span><span>${safeText(event.kind === "event" ? "历史事件" : "红色地点")}</span></div><h3 class="story-title">${safeText(event.title)}</h3><p class="story-summary">${safeText(event.summary)}</p></article>`).join("") : `<div class="empty-state">当前条件下还没有匹配的精选内容。</div>`;
  const loadMore = remaining > 0 ? `<button class="load-more-stories" id="load-more-stories" type="button">继续加载 ${Math.min(LIST_PAGE_SIZE, remaining)} 条（还剩 ${remaining} 条）</button>` : "";
  panelContent.innerHTML = `<div class="section-label">${safeText(heading)}</div><div class="story-list">${cards}${loadMore}</div>`;
}

panelContent.addEventListener("click", (event) => {
  const loadMore = event.target.closest("#load-more-stories");
  if (loadMore) {
    state.listLimit += LIST_PAGE_SIZE;
    renderDetail();
    return;
  }
  const card = event.target.closest(".story-card");
  if (!card) return;
  const selectedEvent = state.events.find((item) => item.id === card.dataset.id);
  if (selectedEvent) selectEvent(selectedEvent);
});

function renderDetail() {
  if (!state.selected || state.selected.type !== "event") setEventListDrawerVisible(false);
  if (explorer.renderPanel()) return;
  if (!state.selected) {
    renderList(visibleEvents(), "重点脉络");
    return;
  }
  if (state.selected.type === "region") {
    const region = state.selected.data;
    const stories = state.selected.stories || [];
    $("#panel-kicker").textContent = `${region.level === "province" ? "省级" : region.level === "city" ? "市级" : "区县级"}区域故事`;
    $("#panel-title").textContent = region.displayName || region.name;
    $("#panel-count").textContent = state.selected.loading ? "读取中" : `${stories.length} 条内容`;
    $("#panel-content").innerHTML = `<div class="detail-article"><button class="back-link" id="back-to-list" type="button">← 返回主题列表</button><p class="detail-story">${state.selected.loading ? "正在从本地资料库整理该区域的红色故事……" : stories.length ? `这里收录了 ${stories.length} 条与该区域相关的精选红色历史内容。点击下方条目阅读完整故事。` : "当前精选数据中暂未收录该区域的红色历史条目。"}</p><div class="section-label">区域内容</div><div class="story-list">${stories.map((event) => `<article class="story-card" data-id="${safeText(event.id)}"><div class="story-meta"><span>${safeText(event.year)} · ${safeText(event.period)}</span><span>${safeText(event.kind === "event" ? "历史事件" : "红色地点")}</span></div><h3 class="story-title">${safeText(event.title)}</h3><p class="story-summary">${safeText(event.summary)}</p></article>`).join("") || `<div class="empty-state">可切换普通、长征或抗战模式继续探索其他区域。</div>`}</div></div>`;
    $("#back-to-list").addEventListener("click", () => { state.selected = null; renderDetail(); });
    return;
  }
  const event = state.selected.data;
  renderEventListDrawer(visibleEvents());
  $("#panel-kicker").textContent = `${event.year} · ${event.period}`;
  $("#panel-title").textContent = event.title;
  $("#panel-count").textContent = event.kind === "event" ? "重大历史事件" : "红色地点";
  const chips = [event.province, event.city, event.kind === "event" ? "历史事件" : "红色建筑", ...(event.tags || [])].filter(Boolean);
  const spirit = spiritTags(event);
  const sourceNotes = (event.sources || []).map((source) => `<p>${safeText(source.title || "离线资料索引")}<br>${safeText(source.scope || "")}<br><span class="source-url">${safeText(source.url || "")}</span></p>`).join("");
  $("#panel-content").innerHTML = `<div class="detail-article"><button class="back-link" id="back-to-list" type="button">← 返回主题列表</button><div class="detail-chip-row">${chips.slice(0, 6).map((chip) => `<span class="detail-chip">${safeText(chip)}</span>`).join("")}</div><p class="detail-story">${safeText(event.story)}</p><div class="detail-facts"><div><span>发生地点</span><strong>${safeText(event.province)} · ${safeText(event.city)}</strong></div><div><span>关联人物</span><strong>${safeText((event.people || []).join("、") || "暂无人物关联")}</strong></div></div><p class="story-summary">${safeText(event.summary)}</p>${spirit.length ? `<section class="spirit-detail" aria-label="本事件体现的红色精神"><div class="section-label">本事件体现的红色精神</div><p>这些精神不是额外附会，而是从本事件的主题、叙述和行动线索中提炼：</p><div class="spirit-pillars">${spirit.map((tag) => `<span>${safeText(tag)}</span>`).join("")}</div></section>` : ""}<details class="source-notes"><summary>资料来源与精度说明</summary>${sourceNotes || "<p>来源索引</p>"}</details></div>`;
  $("#back-to-list").addEventListener("click", () => { state.selected = null; renderDetail(); });
}

async function setMode(mode) {
  state.mode = mode;
  state.selected = null;
  state.listLimit = LIST_PAGE_SIZE;
  hideRegionHover();
  // Historical and people layers are China-focused; keep the ordinary event
  // landing page global while making the colored annual control areas legible.
  if (mode === "time" || mode === "person") {
    map.setView([35, 106], 4.2, { animate: true, duration: .45 });
  } else if (mode === "ordinary") {
    // Returning to the event module restores the promised world overview,
    // even when the previous time/person module had flown into China.
    map.setView([20, 10], 2.2, { animate: true, duration: .45 });
  }
  document.querySelectorAll(".mode-tab").forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $("#year-control").classList.toggle("hidden", mode !== "time");
  $("#person-control").classList.toggle("hidden", mode !== "person");
  $("#event-category-control").classList.toggle("hidden", mode !== "ordinary");
  $("#person-legend").classList.toggle("hidden", mode !== "person");
  drawEvents();
  const explorerUpdate = explorer.switchMode();
  renderDetail();
  await drawRoutes();
  await explorerUpdate;
  renderDetail();
  refreshHoverAtPointer();
}

function applyEventTheme(theme) {
  const availableThemes = ["all", "founding_revolution", "land_revolution", "long_march", "anti_japanese", "liberation_war", "founding_new_china", "construction_reform", "sites_people"];
  state.eventTheme = availableThemes.includes(theme) ? theme : "all";
  document.querySelectorAll(".category-tab").forEach((button) => {
    const active = button.dataset.theme === state.eventTheme;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  hideRegionHover();
  state.selected = null;
  state.listLimit = LIST_PAGE_SIZE;
  drawEvents();
  renderDetail();
  focusEvent(visibleEvents()[0]);
  collapseMobileNavigation();
  drawRoutes().then(refreshHoverAtPointer);
}

function applyEventSearch(value) {
  state.search = String(value || "").trim().toLowerCase();
  $("#clear-search").classList.toggle("hidden", !state.search);
  state.selected = null;
  state.listLimit = LIST_PAGE_SIZE;
  hideRegionHover();
  drawEvents();
  explorer.onSearch();
  renderDetail();
  if (state.search) focusEvent(visibleEvents()[0]);
}

function resetView() {
  cancelWheelGesture();
  state.selected = null;
  state.listLimit = LIST_PAGE_SIZE;
  hideRegionHover();
  map.setView([20, 10], 2.2, { animate: true, duration: .45 });
  renderDetail();
}

async function init() {
  try {
    // Paint the lightweight basemap first while larger data payloads load.
    const [worldPayload, provincePayload] = await Promise.all([
      getJson("/api/geo/world").catch(() => null),
      loadBoundaryWindow("province", map.getBounds()),
    ]);
    if (worldPayload && !worldBaseLayer.getLayers().length) worldBaseLayer.addData(worldPayload);
    if (!countryBaseLayer.getLayers().length) countryBaseLayer.addData(provincePayload);

    const [eventPayload, personPayload, seaPayload, geoIndex] = await Promise.all([
      getJson("/api/events?mode=ordinary"),
      getJson("/api/persons"),
      getJson("/api/geo/south_china_sea").catch(() => null),
      getJson("/api/geo-index"),
    ]);
    state.events = eventPayload.items;
    // The API keeps its historical insertion order for compatibility. The
    // selector, however, is easier to scan when people are grouped by the
    // pinyin initial carried by the record (or its romanised id fallback).
    state.persons = personPayload.items.slice().map((person) => ({
      ...person,
      pinyinKey: String(person.pinyin || person.pinyin_key || person.id || person.name || "").toLowerCase(),
    })).sort((a, b) => a.pinyinKey.localeCompare(b.pinyinKey, "en", { sensitivity: "base" }));
    for (const level of ["province", "city", "district"]) {
      boundaryIndexes[level] = new Map(geoIndex[level].map((properties) => [String(properties.id), properties]));
    }
    adminDirectory.setIndex(geoIndex);
    const guangdong = boundaryIndexes.province.get("440000");
    if (guangdong?.bbox) {
      const [west, south, east, north] = guangdong.bbox;
      guangdongBounds = L.latLngBounds([south, west], [north, east]);
    }
    const currentYear = new Date().getFullYear();
    const yearInput = $("#year-input");
    yearInput.min = "1921";
    yearInput.max = String(currentYear);
    state.year = Math.min(Math.max(state.year, 1921), currentYear);
    yearInput.value = String(state.year);
    if (seaPayload) {
      seaLayer.addData(seaPayload);
      seaMap.fitBounds(seaLayer.getBounds(), { padding: [8, 8] });
    }
    $("#person-spirit-filter").innerHTML = '<option value="">全部精神</option>' + personSpiritFilters().map((spirit) => `<option value="${safeText(spirit)}">${safeText(spirit)}</option>`).join("");
    state.person = state.persons[0];
    syncPersonOptions();
    await updateBoundaries();
    drawEvents();
    renderDetail();
  } catch (error) {
    console.error(error);
    $("#panel-content").innerHTML = `<div class="empty-state">本地数据加载失败。请确认已从项目目录启动 FastAPI，并已运行边界下载脚本。</div>`;
  }
}

document.querySelectorAll(".mode-tab").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
document.querySelectorAll(".category-tab").forEach((button) => button.addEventListener("click", () => applyEventTheme(button.dataset.theme)));
$("#mobile-nav-toggle").addEventListener("click", () => {
  const controls = $("#main-controls");
  const toggle = $("#mobile-nav-toggle");
  const expanded = controls.classList.toggle("nav-collapsed") === false;
  toggle.setAttribute("aria-expanded", String(expanded));
});
$("#event-search").addEventListener("input", (event) => applyEventSearch(event.target.value));
$("#event-search").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    if (state.mode === 'person') { const node = explorer.filteredNodes()[0]; if (node) explorer.selectNode(node.id); return; }
    if (state.mode === 'time' && explorer.filteredBattles().length) { explorer.selectBattle(explorer.filteredBattles()[0].id); return; }
    const first = visibleEvents()[0];
    if (first) selectEvent(first);
  }
});
$("#clear-search").addEventListener("click", () => { $("#event-search").value = ""; applyEventSearch(""); $("#event-search").focus(); });
function applyYearInput(value) {
  explorer.setYear(value, true);
}
$("#year-input").addEventListener("change", (event) => applyYearInput(event.target.value));
$("#year-input").addEventListener("blur", (event) => applyYearInput(event.target.value));
$("#year-input").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); applyYearInput(event.target.value); event.target.blur(); } });
$("#person-spirit-filter").addEventListener("change", () => { syncPersonOptions(); state.selected = null; if (state.mode === "person") explorer.loadJourney(); });
$("#person-select").addEventListener("change", (event) => { state.person = state.persons.find((person) => person.id === event.target.value); state.selected = null; explorer.loadJourney(); });
$("#event-list-toggle").addEventListener("click", () => {
  const drawer = $("#event-list-drawer");
  setEventListDrawer(drawer.classList.contains("is-collapsed"));
});
$("#reset-view").addEventListener("click", resetView);

function scheduleViewUpdate() {
  mapMoving = false;
  map.getContainer().classList.remove("map-is-moving");
  wheelTarget = null;
  wheelAnchor = null;
  mapRect = map.getContainer().getBoundingClientRect();
  clearTimeout(viewTimer);
  // A zoom fires both zoomend and moveend. Coalesce them into ONE update,
  // and leave the previously rendered map visible while local data loads.
  viewTimer = setTimeout(() => {
    updateBoundaries().then(() => queueHoverRefresh(0));
    drawEvents();
    explorer.onViewEnd();
  }, 70);
}

function mapStillAnimating() {
  // Leaflet keeps these flags private, but they are stable across the bundled
  // 1.9.x build and cover both flyTo zooms and pan/touch inertia.  Reading
  // them avoids dispatching a synthetic mousemove onto a canvas that is still
  // being transformed, which otherwise drops the layer mouseover event.
  return mapMoving || Boolean(
    map._animatingZoom ||
    map._zooming ||
    map._panAnim?._inProgress,
  );
}

function queueHoverRefresh(delay = 0, attempts = 32) {
  if (hoverRefreshTimer) clearTimeout(hoverRefreshTimer);
  hoverRefreshTimer = setTimeout(() => {
    hoverRefreshTimer = 0;
    if (!pointerPosition || !map.getContainer()) return;
    if (mapStillAnimating() || wheelTarget !== null) {
      if (attempts > 0) queueHoverRefresh(45, attempts - 1);
      return;
    }
    refreshHoverAtPointer();
  }, delay);
}

// A flyTo or event filter can leave the pointer stationary while Leaflet's
// Canvas layer has no reason to emit another mouseover. Re-hit the current
// pointer after boundary data settles so the region tooltip and lifted fill
// recover without requiring the user to move the mouse by hand.
function refreshHoverAtPointer() {
  if (mapStillAnimating() || !pointerPosition || !map.getContainer()) return;
  mapRect = map.getContainer().getBoundingClientRect();
  // Canvas's own mouse-hover handler performs the spatial hit test.  Sending
  // the event only to the map container bypasses that handler in Leaflet 1.9,
  // so call the active boundary renderer directly; the DOM canvas remains a
  // fallback while the first boundary batch is still being created.
  const event = new MouseEvent("mousemove", {
    bubbles: true,
    clientX: mapRect.left + pointerPosition.x,
    clientY: mapRect.top + pointerPosition.y,
    buttons: 0,
  });
  if (typeof renderer._onMouseMove === "function") renderer._onMouseMove(event);
  else (renderer._container || map.getContainer()).dispatchEvent(event);
}

function cancelWheelGesture() {
  if (wheelFrame) { cancelAnimationFrame(wheelFrame); wheelFrame = 0; }
  if (wheelIdleTimer) { clearTimeout(wheelIdleTimer); wheelIdleTimer = 0; }
  wheelTarget = null;
  wheelAnchor = null;
}

map.on("zoomstart movestart", () => {
  mapMoving = true;
  map.getContainer().classList.add("map-is-moving");
  ++state.boundaryRequest;
  clearTimeout(viewTimer);
  hideRegionHover();
});
map.on("zoomend moveend", scheduleViewUpdate);

// Wheel gestures continuously adjust a fractional target instead of queuing
// integer zoom steps. Leaflet flyTo transforms the existing canvas each frame;
// geometry is projected/loaded only when the gesture's final animation ends.
map.getContainer().addEventListener("wheel", (event) => {
  if (event.target.closest(".leaflet-control")) return;
  event.preventDefault();
  const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? map.getSize().y : 1);
  if (!pixels) return;
  const point = map.mouseEventToContainerPoint(event);
  if (wheelTarget === null || !wheelPoint || point.distanceTo(wheelPoint) > 2) {
    wheelAnchor = map.containerPointToLatLng(point);
  }
  wheelPoint = point;
  wheelTarget = Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(),
    (wheelTarget ?? map.getZoom()) - Math.max(-.8, Math.min(.8, pixels / 360))));
  clearTimeout(wheelIdleTimer);
  // A burst of wheel events can interrupt one flyTo with the next one before
  // Leaflet emits the matching moveend.  Once input goes idle, schedule one
  // more settle pass so the pointer is re-hit even when that event sequence
  // was coalesced by the browser.
  wheelIdleTimer = setTimeout(() => {
    wheelIdleTimer = 0;
    // `mapMoving` can be left true when a new flyTo cancels the previous
    // animation before its moveend event.  The private Leaflet flags are the
    // reliable part here; scheduleViewUpdate() clears the stale CSS/state
    // flag before loading the final boundary window.
    const leafletAnimating = Boolean(map._animatingZoom || map._zooming || map._panAnim?._inProgress);
    if (!leafletAnimating) scheduleViewUpdate();
    queueHoverRefresh(80);
  }, 280);
  if (wheelFrame) return;
  wheelFrame = requestAnimationFrame(() => {
    wheelFrame = 0;
    if (wheelTarget === null) return;
    const center = map.unproject(map.project(wheelAnchor, wheelTarget)
      .subtract(wheelPoint.subtract(map.getSize().divideBy(2))), wheelTarget);
    map.flyTo(center, wheelTarget, { animate: true, duration: .24, noMoveStart: true });
  });
}, { passive: false });
map.getContainer().addEventListener("pointerdown", () => {
  const wasZooming = wheelTarget !== null;
  cancelWheelGesture();
  if (wasZooming) map.stop();
}, { capture: true, passive: true });
const explorer = new HistoryExplorer();
const adminDirectory = new AdminDirectory();
init();
