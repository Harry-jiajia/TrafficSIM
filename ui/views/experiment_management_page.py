"""Experiment management and result overview page."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.views.components import PAGE_CONTENT_MARGIN, empty_state, metric_card, page_header, panel


class ExperimentManagementPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("experimentManagementPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(page_header("实验管理", "实验生命周期、运行状态与结果概览"))

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(PAGE_CONTENT_MARGIN, 16, PAGE_CONTENT_MARGIN, 18)
        layout.setSpacing(12)
        metrics = QHBoxLayout()
        self.status_card = metric_card("当前实验", "未创建", "等待实验会话")
        self.time_card = metric_card("仿真时间", "0.00 秒", "权威仿真时钟")
        metrics.addWidget(self.status_card)
        metrics.addWidget(self.time_card)
        metrics.addWidget(metric_card("已完成实验", "—", "结果接口待接入"))
        metrics.addWidget(metric_card("成功率", "—", "结果接口待接入"))
        layout.addLayout(metrics)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(self._experiment_table(), 3)
        columns.addWidget(
            panel(
                "结果洞察",
                empty_state("等待结果数据", "完成实验后，这里将呈现关键指标与跨实验对比。", "◫"),
                kicker="分析概览",
            ),
            2,
        )
        layout.addLayout(columns, 1)
        root.addWidget(body, 1)

    def _experiment_table(self) -> QFrame:
        table = QTableWidget(1, 4)
        table.setHorizontalHeaderLabels(("实验", "状态", "仿真时间", "数据来源"))
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().hide()
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        values = ("当前核心运行", "未创建", "0.00 秒", "实时会话")
        for column, value in enumerate(values):
            table.setItem(0, column, QTableWidgetItem(value))
        self.table = table
        return panel("最近实验", table, kicker="实验记录")

    def set_status(self, status: str) -> None:
        self._metric_value(self.status_card).setText(status)
        item = self.table.item(0, 1)
        if item is not None:
            item.setText(status)

    def set_time(self, simulation_time_ms: int) -> None:
        value = f"{simulation_time_ms / 1000:.2f} 秒"
        self._metric_value(self.time_card).setText(value)
        item = self.table.item(0, 2)
        if item is not None:
            item.setText(value)

    @staticmethod
    def _metric_value(card: QFrame) -> QLabel:
        return card.findChildren(QLabel, "metricValue")[0]
