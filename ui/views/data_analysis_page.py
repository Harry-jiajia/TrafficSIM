"""Replay-oriented data analysis page shell."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QVBoxLayout, QWidget

from ui.views.components import PAGE_CONTENT_MARGIN, empty_state, page_header, panel


class DataAnalysisPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dataAnalysisPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(page_header("数据分析", "实验回放、指标趋势与事件定位"))

        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(PAGE_CONTENT_MARGIN, 16, PAGE_CONTENT_MARGIN, 18)
        layout.setSpacing(12)

        runs = QListWidget()
        runs.addItem("尚无可回放实验")
        runs.setEnabled(False)
        layout.addWidget(panel("实验记录", runs, kicker="回放库"), 2)
        layout.addWidget(
            panel(
                "时空回放",
                empty_state("等待回放数据", "选择已完成实验后，可在时间轴上定位交通事件。", "▶"),
                kicker="时间轴",
            ),
            5,
        )
        insight = QWidget()
        insight_layout = QVBoxLayout(insight)
        insight_layout.setContentsMargins(0, 0, 0, 0)
        for label in ("平均速度", "通行效率", "安全事件", "拥堵指数"):
            row = QLabel(f"{label}\n—")
            row.setObjectName("metricValue")
            insight_layout.addWidget(row)
        insight_layout.addStretch(1)
        layout.addWidget(panel("分析指标", insight, kicker="分析洞察"), 2)
        root.addWidget(body, 1)
