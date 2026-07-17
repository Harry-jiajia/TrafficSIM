# TrafficVerse

TrafficVerse 的目标架构是“SUMO 全局交通真值 + TrafficVerse 自有二维页面 + CARLA ROI 原生三维
窗口”。SUMO 只通过 TraCI 接入，TrafficVerse 不嵌入 SUMO GUI；CARLA 必须 windowed 运行，其
原生窗口通过 PySide6 `QWindow.fromWinId()` 托管到运行页右侧。

当前仓库正在按 [SUMO 迁移计划](docs/SUMO_MIGRATION_PLAN.md) 从 Native/RGB 旧实现迁移。生产
装配已切换为 `SumoTrafficEngineAdapter`，Town04 SUMO 资产和 Qt 原生窗口 host 已加入；真实 CARLA
联仿和 native-window 现场 Gate 仍必须在同一图形桌面会话完成。

## 固定版本与端点

- Python 3.10
- SUMO 1.27.1：`127.0.0.1:8813`
- CARLA 0.9.16：`127.0.0.1:2000`
- TrafficVerse API：`127.0.0.1:8000`
- 固定仿真步长：50 ms

## 安装

```bash
uv sync --frozen --extra sumo --extra carla --extra ui
```

## 生成并校验 Town04 SUMO 资产

```bash
python scripts/maps/generate_town04_sumo.py
sumo -c configs/maps/town04/map.sumocfg --end 5
```

## 启动

1. 启动 SUMO TraCI 后端。推荐 headless；它没有需要接入 TrafficVerse 的页面：

```bash
sumo -c configs/maps/town04/map.sumocfg --remote-port 8813
```

调试时可把 `sumo` 换为 `sumo-gui`，但 GUI 保持独立。

2. 在同一图形桌面会话启动 windowed CARLA 0.9.16，不使用 `-RenderOffScreen`。

3. 设置 CARLA 顶层窗口的 native window ID，并启动 API/UI：

```bash
export TRAFFICVERSE_CARLA_WINDOW_ID=<native-window-id>
uv run trafficverse serve --host 127.0.0.1 --port 8000
uv run trafficverse ui --api-url http://127.0.0.1:8000
```

UI 左侧从 REST/WebSocket 获取 SUMO 派生的标准快照并自行绘制；右侧直接显示 CARLA 原生窗口。
系统不传输 `camera.frame` 或 JPEG/base64 图像。
二维页面使用仓库内置的 Leaflet 1.9.4 静态资源，运行时不访问 CDN 或公网。

## 验证

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

真实 SUMO integration：

```bash
TRAFFICVERSE_SUMO_INTEGRATION=1 uv run pytest -m traffic \
  tests/integration/traffic/test_sumo_adapter.py
```

CARLA 与 Qt foreign-window 验收需要 PySide6、CARLA 和目标窗口处于同一主机、同一用户、同一
图形桌面会话。远程 tty、无头 CARLA 或 RenderOffScreen 无法完成该 Gate。

设计详情见 [PRD](docs/PRD.md)、[System Design](docs/SYSTEM_DESIGN.md)、
[ADR](docs/ADR.md) 和 [Agent Guide](docs/AGENT_DEVELOPMENT_GUIDE.md)。
