# TrafficVerse

TrafficVerse 的目标架构是“自研全局二维交通仿真 + 远程 CARLA ROI 局部三维镜像”。

Native Traffic Engine 负责路网、路线、车辆运动、基础交通行为和交通信号灯，并作为唯一交通真值源；CARLA 只负责 ROI 内车辆、环境和相机的三维表现。

## 当前状态

- T01 项目骨架已完成；
- T02 Map Compiler 与 Native Traffic Engine MVP 已实现；
- T03 远程 CARLA Adapter 已实现，真实远程 smoke 等待在目标服务器执行；
- T04 Scenario Manager、PostgreSQL Repository 和 Alembic 初始迁移已完成；
- T05 Simulation Manager 已完成，支持唯一固定时钟、串行生命周期、CARLA 降级和失败清理；
- T07 ROI、坐标配准和信号同步已完成离线实现，真实远程 CARLA 验收待执行；
- T09-live REST/WebSocket Gateway 已完成；
- T10-live PySide6 Core Run UI 已完成本地二维实现，真实远程 CARLA 视觉闭环待验收；
- `traffic-network/1.0` 已冻结，Town04 已生成原生 JSON/GeoJSON/manifest 资产；
- 原生引擎支持 50 ms 固定步进、基础跟驰、红灯停车、固定信号灯、批量控制和安全换道；
- macOS arm64 无需安装 CARLA 或外部交通仿真器即可完成地图编译、校验和二维 smoke。
- CARLA Adapter 支持严格版本握手、同步 fixed delta、批量 Actor、信号灯冻结/三色写入、
  BIRD_VIEW/FOLLOW JPEG 相机和退出恢复。

## 文档入口

- [PRD](docs/PRD.md)：MVP 产品范围和验收标准；
- [System Design](docs/SYSTEM_DESIGN.md)：原生路网、交通行为、类图、时序、协议和目录设计；
- [ADR](docs/ADR.md)：架构决策及从 SUMO 迁移到 Native Traffic Engine 的原因；
- [Agent Development Guide](docs/AGENT_DEVELOPMENT_GUIDE.md)：T01–T10 任务、依赖和验收；
- [Engineering Standards](AGENTS.md)：代码与目录规范。

## 当前可运行检查

```bash
uv sync --frozen
uv run trafficverse doctor
uv run trafficverse map compile configs/maps/town04/Town04.xodr configs/maps/town04
uv run trafficverse map validate configs/maps/town04/manifest.yaml
uv run trafficverse traffic smoke
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

PostgreSQL 16 Product Gate 初始化和验收：

```bash
export TRAFFICVERSE_DATABASE_URL=postgresql+psycopg://trafficverse:trafficverse@127.0.0.1:5432/trafficverse
uv run alembic -c migrations/alembic.ini upgrade head

export TRAFFICVERSE_TEST_DATABASE_URL=$TRAFFICVERSE_DATABASE_URL
uv run pytest -m postgres
```

迁移是唯一生产建表入口；应用启动时不会自动创建或修改数据库表。

带 CARLA 的 Simulation Runtime 与 Server 运行在远程 Linux GPU 主机；macOS 通过 TrafficVerse
API/WebSocket 控制实验并接收相机帧，不直接安装 CARLA SDK。CARLA 不影响 macOS 上的原生二维交通真值链路。

远程 Linux x86_64 主机安装和验收：

```bash
uv sync --frozen --extra carla
export TRAFFICVERSE_CARLA_HOST=127.0.0.1
export TRAFFICVERSE_CARLA_PORT=2000
export TRAFFICVERSE_CARLA_TIMEOUT_S=30
uv run trafficverse carla doctor
uv run trafficverse carla smoke
TRAFFICVERSE_CARLA_INTEGRATION=1 uv run pytest -m carla
```

建议 Simulation Runtime 与 CARLA Server 同主机部署，CARLA RPC 端口只在私网开放；公网访问只走后续
TrafficVerse API/WebSocket。`carla doctor/smoke` 在 macOS 上会明确提示 SDK 应在远程
Linux Runtime 安装和执行。

## 启动 Core Run

首次安装桌面 UI 依赖：

```bash
uv sync --frozen --extra ui
```

macOS 本地二维演示需要两个终端。第一个终端启动数据库无关的 Core API Runtime：

```bash
uv run trafficverse serve --carla-mode disabled
```

第二个终端启动 PySide6 UI：

```bash
uv run trafficverse ui --api-url http://127.0.0.1:8000
```

UI 可导入或选择 Town04、创建实验、开始、暂停、恢复、停止，显示全局车辆和信号灯，并对单车
设置速度、停车或发出安全换道命令。二维路网使用 Leaflet 1.9.4 `CRS.Simple`；当前开发版从带
完整性校验的固定 CDN 加载 Leaflet，因此首次运行地图视图需要网络访问。

远程 CARLA 模式在 Linux Runtime 上执行：

```bash
uv sync --frozen --extra carla
export TRAFFICVERSE_CARLA_HOST=127.0.0.1
export TRAFFICVERSE_CARLA_PORT=2000
export TRAFFICVERSE_CARLA_TIMEOUT_S=30
uv run trafficverse carla doctor
uv run trafficverse serve
```

Core Server 默认且仅监听 loopback。macOS 控制端应通过受控 SSH/VPN 隧道或带 TLS、鉴权和来源
限制的反向代理访问，不直接公开 CARLA RPC 或未鉴权 API。例如建立本地端口转发后，UI 仍连接
`http://127.0.0.1:8000`。

## 下一开发任务

Core Run 本地实现已到 T10-live。下一阶段按
[Agent Development Guide](docs/AGENT_DEVELOPMENT_GUIDE.md) 执行远程 CARLA Core Run 验收，
再进入 T06/T08 及 Dashboard、Replay Product Gate。
