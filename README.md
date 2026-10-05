# 红色精神地图 v1.25 · 网站特殊版

这是面向个人网站的 v1.25 网站特殊版。网页使用 GitHub Pages 静态数据和 Leaflet Canvas 地图渲染；世界低分辨率底图、事件资料、人物节点和战役路线都随项目分发。公开网页不加载 AI 模型、不保存 API 卡密，也不向任何 AI 接口发起请求。

在线地址：https://avasubaru486.github.io/Red-Spirit-Map-v1.25/

## 在线使用

直接访问 <https://avasubaru486.github.io/Red-Spirit-Map-v1.25/> 可以浏览完整静态地图，无需购买服务器、安装运行环境或启动本地服务。页面只读取随站点发布的静态数据，地图和历史查询在浏览器内完成。

## 本地后端开发（可选）

完整解压后双击 `自动部署/启动本地网站.exe`。命令行也可使用包内运行时：

```powershell
Set-Location 'D:\CODEX\个人网站\Red-Spirit-Map-v1.25'
& '.\runtime\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

浏览器访问：<http://127.0.0.1:8010/>

如果没有 `runtime\python.exe`，也可以使用已安装的 Python 运行同一条 `uvicorn` 命令。该后端仅用于本地数据维护、接口回归和源码开发，GitHub Pages 网页不会调用它的 AI 接口。

## v1.1 功能

- “事件、时间、人物”三模块共用地图视图，长征筛选器包含中央红军、红二方面军、红四方面军和红二十五军四条独立线路。
- 地图覆盖世界底图和中国专题行政区，区域命中层扩大约 10 像素；悬停时区域会短暂上移、出现阴影，并显示名称、控制方、阵营和资料状态。
- 时间模块按年查看 1921 年至今的历史层；1921—1950有年度历史资料，1951年后使用现代行政底图并列出已收录的战役与军事行动目录，不宣称连续年度控制区。具备来源分段的路线支持小时、日、月粒度播放。
- 战役目录包含抗美援朝五次战役、长津湖、上甘岭、金城、一江山岛、金门炮战、中印边境自卫反击、珍宝岛、西沙海战、对越自卫反击和两山轮战等已收录项目；2024B按军事演习单独标注，未公开的兵力字段保持空置并显示资料说明。
- 人物目录扩展为二十人，带拼音和首字母字段，默认按拼音排序；每个节点附来源和位置层级字段，地图按地点坐标连线。
- 事件详情提供来源折叠区和离线事件资料，不包含 AI 问答入口。

### AI 说明

网站特殊版主动取消了网页端 AI 模型调用，避免首次加载等待、浏览器卡顿和密钥暴露。源码中的本地后端模块仅为历史开发兼容保留，不会被静态构建复制到网页，也不会由浏览器启动。

## 数据维护

- `data/events.json`：重大历史事件和红色地点。
- `data/persons.json`：人物故事线选项。
- `data/routes.json`：长征、抗战和人物路线。
- `data/history/battles_post1949.json`：建国后的战役和军事行动扩展数据。
- `data/geo/world.json`、`data/geo/world_manifest.json`：Natural Earth 低分辨率世界底图及来源、许可和版本记录。
- `data/history/sources.json`：事件、人物、战役和地图来源清单，含网址、资料日期和离线文件说明。
- `data/geo/`：本地省、市、区县行政边界及南海区域 inset。

重新生成精选数据：

```powershell
& '.\.venv\Scripts\python.exe' scripts\seed_content.py
```

如果需要重新下载并简化行政边界（仅构建阶段联网，运行时不联网）：

```powershell
& '.\.venv\Scripts\python.exe' scripts\download_boundaries.py
```

## 测试

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
```

地图和历史资料全部内置，静态网页不依赖 AI、API 卡密或本机运行时。

## 地图流畅性优化

- 滚轮使用连续的小数级缩放与鼠标锚点，缩放过程中复用 Canvas，停止后再加载细节。
- 市、区县通过 `/api/geo/{level}?bbox=西,南,东,北` 加载视野附近的数据；不传 `bbox` 返回该显示层全部有效几何，原始行政层级保留在 `properties.level`。
- `/api/geo-index` 提供省、市、区县轻量目录、名称路径和范围，不包含多边形。后端边界索引在首次请求时建立，源文件更改后自动重建。
- 保留一圈视野预加载范围、最近十个窗口的缓存及已有图层；拖动时增量更新，不重复创建全部边界和事件标记。
- 悬停文字共用一个提示框，通过动画帧移动；高亮绘制在单独的 Canvas，不触发整幅地图重绘。
- 保留广东大小的市级显示门槛、省名常显、市/区悬停全名、事件点击后的平滑飞行动画。

浏览器回归和性能复测（使用本机已安装的 Edge；网站需先启动）：

```powershell
& '.\.venv\Scripts\python.exe' scripts\verify_map_interactions.py
& '.\.venv\Scripts\python.exe' scripts\verify_map_performance.py --label after
```

测试脚本使用当前环境中已有的 `playwright`，不下载浏览器。报告和截图保存在 `自动部署/logs/`，浏览器临时文件保存在 `自动部署/cache/performance/`。性能数字取决于电脑、窗口大小和视野；复测用于对比，不代表所有设备都能维持固定帧率。

## 年度形势与人物行程

时间模式现在保留输入与搜索，同时支持年份滑块。1921—1950 年显示年度控制区图层和当年战役；1951 年起显示现代行政底图与当年战役。点击战役查看兵种、人数、领导人、来源范围字段及推进方向，可切换显示全部当年路线。人物模块提供二十个人物的拼音排序、国内分段路线、年份高亮和海外文字节点。

历史着色采用来源列明地区的现代省县几何载体，通过 `/api/control` 加载；红、蓝、黄分别表示共产党、国民党、日本及日伪。悬停显示范围说明；这些面不等同于当年的精确控制疆界。现有覆盖仍有限，不能解释为全国逐年的完整控制图。部队播放器按各自游标显示有日期的驻战或到达地点，点间虚线表示节点先后顺序。资料目录见 `data/history/military-sources.json`。

新增接口：`GET /api/history/{year}?bbox=...`、`GET /api/geo/world?bbox=...`、`GET /api/battles?year=&phase=&theater=&q=`、`GET /api/battles/{battle_id}`、`GET /api/battles/{battle_id}/timeline?at=&granularity=`、`GET /api/persons/{person_id}/timeline`、`GET /api/history-catalog`。区域故事接口可追加 `year`。旧接口保持兼容，原地图与事件文件没有被历史资料构建覆盖；AI 接口不属于公开网页运行链路。

```powershell
& '.\.venv\Scripts\python.exe' scripts\build_history_data.py
& '.\.venv\Scripts\python.exe' scripts\verify_history_interactions.py
& '.\.venv\Scripts\python.exe' -m pytest -q
```

新增历史浏览器报告保存在 `自动部署/logs/history-acceptance.json`。启动 EXE 会检查历史数据和人物行程接口是否可用，不需重新打包 Python 或下载外部地图。

## 行政区目录与覆盖审计

新增“行政区目录”，可按名称、代码或完整地区路径搜索，逐级浏览并平滑定位；事件搜索仍独立运行。东莞、中山、儋州、嘉峪关保持城市身份，明确标记“无县级下辖单位”；地图不会用城市外框替代区县层级。

当前离线快照含 **34 个省级、355 个地市／台湾县市、3239 个区县／港澳台对应分区的真实几何**。和安县、和康县保留为上级定位项。目录共 3630 项，其中 3628 项带边界；台湾采用已有官方数据再发布快照，港澳保留快照时点字段。详见 `data/geo/admin_manifest.json` 与 `data/geo/coverage_audit.json`。

新增接口：`GET /api/regions?query=&parent=&level=&offset=&limit=`、`GET /api/regions/{id}`、`GET /api/regions/{id}/geometry`、`GET /api/geo-status`。没有随快照分发的几何返回 `status: missing`、`geometry: null`，页面使用上级定位并保留真实层级。直辖市、港澳和省直辖县级单位在中间缩放层保留真实层级，不制造虚假地级市。

构建与测试均在项目 D 盘目录进行：

```powershell
$env:TEMP = "$PWD\自动部署\cache\tmp"
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = "$PWD\自动部署\cache\pip"
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-geo.txt
& '.\.venv\Scripts\python.exe' scripts\fetch_admin_sources.py
& '.\.venv\Scripts\python.exe' scripts\rebuild_admin_boundaries.py
& '.\.venv\Scripts\python.exe' scripts\audit_admin_bundle.py
& '.\.venv\Scripts\python.exe' scripts\verify_admin_interactions.py
```

仅 `fetch_admin_sources.py` 需要构建期联网；原始快照、许可、哈希、构建缓存和升级前备份均在 `data/geo/`。边界构建只使用缓存。严格审计会把目录项、几何数量和来源版本如实返回；`--allow-incomplete` 仅用于检查几何及层级结构，不改变报告中的覆盖统计。

报告和截图位于 `自动部署/logs/admin-*`，自动部署 EXE 兼容新接口。后续取得经核实的补充几何可写入 `data/geo/reviewed_supplements.json`（FeatureCollection，每项记录来源 URL、资料日期与被替换条目标识），再重新构建与严格审计；不得直接把审核标志改成通过。

## 本地便携工具（可选）

`new v1.1\红色精神离线地图_便携版.zip` 包含独立便携 Python 运行时和本地依赖。完整解压到任意文件夹后，直接双击解压所得的 `自动部署\启动本地网站.exe`；启动器使用包内运行时，不要求目标电脑先安装 Python、PyCharm 或下载运行依赖。运行日志、临时文件和浏览器配置保存在同一解压目录下的 `自动部署` 文件夹。目标 Windows 电脑需已有 Edge 或 Chrome 浏览器。打包脚本默认将压缩包写入项目同级 `new v1.1`，也可用 `REDMAP_OUTPUT_DIR` 指定其他目录。

重新制作便携包：

```powershell
$env:TEMP = "$PWD\自动部署\cache\tmp"
$env:TMP = $env:TEMP
& '.\.venv\Scripts\python.exe' scripts\package_portable.py
```

GitHub Pages 只发布 `build.py` 生成的 `dist/` 静态网站；v1.25 网页不调用 AI，模型文件、密钥和本地运行时均不会进入公开部署产物。
