# 地图资产目录与支持格式

> 状态：Implemented UI catalog / conversion scope constrained by PRD  
> 适用范围：TrafficVerse 资产中心、地图 manifest、MapLibre/deck.gl 预览

## 1. 目标与边界

资产中心把一张地图或一个原生 SUMO 场景作为可复用目录管理。Town04 文件列表来自已校验的
`manifest.yaml`；原生 SUMO 包文件列表来自服务端对 `.sumocfg` 显式输入的安全解析。UI 不扫描
任意本机路径。选择目录或文件时，右侧请求标准 GeoJSON；Town04 读取 `network.geojson`，原生
SUMO 包从同一 `.net.xml` 即时生成 display-only GeoJSON。

“支持格式”分为四个层级：

1. **目录收录**：文件可以由 manifest 跟踪并在资产目录中显示完整文件名和后缀；
2. **直接导入**：文件可以通过当前 `/api/v1/maps/import` 作为地图源上传；
3. **二维预览**：文件或其地图包可以生成当前 MapLibre/deck.gl 标准路网预览；
4. **三维预览**：复用同一标准路网和 deck.gl 图层，仅改变相机倾角与三维图层，不等同于 CARLA
   原生窗口。

目录收录不代表 TrafficVerse 会把任意格式自动转换成 SUMO/CARLA 地图。HTTP 上传接口仍以
OpenDRIVE 为权威入口；此外，仓库内 `configs/maps/<package>/*.sumocfg` 支持自动发现为纯二维
SUMO 运行包，这不扩大 CARLA 同源地图范围。

## 2. 支持格式矩阵

| 文件格式 | 主要消费者 | 目录收录 | 直接导入 | 2D/3D 预览 | 说明 |
|---|---|---:|---:|---:|---|
| `.xodr` | CARLA、SUMO 生成链 | 是 | 是 | 编译后 | 当前权威地图导入源；服务端编译并生成标准路网 |
| `.net.xml` | SUMO | 是 | 否 | 是 | 原生 SUMO 包由后端生成 display-only GeoJSON |
| `.sumocfg` | SUMO | 是 | 仓库目录发现 | 是 | 运行入口；解析 net/route/additional 和时间配置 |
| `.rou.xml` | SUMO | 是 | 否 | 不直接预览 | 路线、车流或车型文件 |
| `.add.xml` | SUMO | 是 | 否 | 不直接预览 | SUMO 附加定义 |
| `.geojson` | deck.gl、MapLibre | 是 | 否 | 是 | 地图包中 `network.geojson` 是当前标准预览资源 |
| `.json` | deck.gl、MapLibre | 是 | 否 | 视 schema | 可用于 `network.json`、MapLibre style 或 tileset 元数据 |
| `tileset.json`、`.b3dm` | deck.gl 3D Tiles | 是 | 否 | 需地图包显式引用 | 目录识别已支持，当前 Town04 Gate 不加载大型 3D Tiles |
| `.glb`、`.gltf`、`.bin` | deck.gl | 是 | 否 | 需地图包显式引用 | glTF 场景或外部缓冲区；不作为 CARLA 输入 |
| `.fbx` | CARLA/Unreal 导入链 | 是 | 否 | 不在 Web 中直接预览 | CARLA 自定义地图三维源资产 |
| `.yaml`、`.yml` | TrafficVerse 配置 | 是 | 否 | 不直接预览 | manifest、配准、信号和路线配置 |

当前不支持 OSM、Shapefile、Vissim 文件直接导入或转换。增加新的权威导入源必须先扩展地图编译器、
manifest 校验、REST 契约和对应 ADR，不能只在文件选择框中增加后缀。

## 3. 标准地图包目录

```text
Town04/
├── manifest.yaml
├── Town04.xodr
├── Town04.net.xml
├── Town04.rou.xml
├── vtypes.rou.xml
├── map.sumocfg
├── network.geojson
├── network.json
├── registration.yaml
├── routes.yaml
└── signals.yaml
```

`manifest.yaml` 是目录文件清单和 checksum 的权威来源。资产中心只展示 manifest 中受跟踪的文件；
未进入 manifest 的临时文件不会作为公共资产暴露。

原生 SUMO 包的最小结构为：

```text
image2road/
├── image2road.sumocfg
├── image2road.net.xml
├── image2road.rou.xml
└── image2road.add.xml        # 若 sumocfg 引用
```

不要求 `.xodr` 或 `manifest.yaml`。服务端只公开 `.sumocfg` 及其显式输入；历史 `outputs/` 不作为
运行输入或公共文件清单。每次实验在 artifacts 中 stage 运行副本，源目录保持只读。

## 4. 搜索与选择规则

- 搜索字段同时匹配地图名称、地图 ID、平台名称、完整文件名和复合后缀；
- 例如搜索 `SUMO`、`town04`、`geojson` 或 `.net.xml` 都会保留匹配目录；
- 选中文件等价于选中其所属地图包，右侧不会尝试把 `.xml`、`.fbx` 等文件直接交给 MapLibre；
- 清单尚未返回时先显示地图目录，收到 manifest 后增量填充文件；
- 资产预览请求与场景配置的运行地图选择分离，不会改变实验使用的地图 ID。

## 5. 公共 UI 组件

可复用组件为 `ui.widgets.AssetDirectoryWidget`。它只负责目录呈现、搜索过滤和选择事件，不访问
REST、不读取后端目录，也不持有业务真值。

- 输入：`Sequence[AssetDirectoryEntry]`；
- 输出信号：`asset_selected(str)`；
- 目录模型：`AssetDirectoryEntry`；
- 文件模型：`AssetFileEntry`；
- API/ViewModel 负责把 `MapSummary + MapManifest` 转换成目录模型；
- 使用方负责根据 `asset_id` 请求和展示预览。

该边界允许场景配置、实验模板或未来其他资产页复用目录组件，而不复制搜索和树形选择逻辑。
