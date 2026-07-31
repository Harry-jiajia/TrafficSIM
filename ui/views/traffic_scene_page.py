"""Workspace catalog of directly runnable traffic scenarios."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.models import MapSummary
from ui.views.components import PAGE_CONTENT_MARGIN, page_header, panel


class TrafficScenePage(QWidget):
    """Show validated SUMO packages separately from per-run configuration."""

    scene_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("trafficScenePage")
        self._maps: tuple[MapSummary, ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(page_header("交通场景", "管理工作区内可复用的交通场景包"))

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(PAGE_CONTENT_MARGIN, 16, PAGE_CONTENT_MARGIN, 18)
        layout.setSpacing(12)
        hint = QLabel("选择场景后会同步到“仿真配置”，启动时仍由后端校验场景包。")
        hint.setObjectName("caption")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("trafficSceneTable")
        self.table.setHorizontalHeaderLabels(("场景名称", "场景 ID", "SUMO 配置", "步长", "状态"))
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._select_row)
        layout.addWidget(panel("场景列表", self.table, kicker="工作区资源"), 1)
        root.addWidget(body, 1)

    def set_maps(self, maps: tuple[MapSummary, ...]) -> None:
        self._maps = tuple(item for item in maps if item.kind == "sumo")
        self.table.setRowCount(len(self._maps))
        for row, item in enumerate(self._maps):
            values = (
                item.display_name or item.map_id,
                item.map_id,
                item.sumo_config_file or "—",
                f"{item.sumo_step_ms} ms" if item.sumo_step_ms is not None else "—",
                "已验证" if item.validated else "校验失败",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _select_row(self, row: int, column: int) -> None:
        del column
        if 0 <= row < len(self._maps):
            self.scene_selected.emit(self._maps[row].map_id)
