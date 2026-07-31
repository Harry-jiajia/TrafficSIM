"""Workspace-scoped API agent asset configuration."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.models import AgentApiSummary
from ui.views.components import PAGE_CONTENT_MARGIN, page_header, panel


class AgentAssetPage(QWidget):
    """Configure remote intelligent agents without storing API secrets."""

    configure_requested = Signal(str, str, str, str, str)
    delete_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("agentAssetPage")
        self._agents: tuple[AgentApiSummary, ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(
            page_header(
                "智能体",
                "通过 API 配置接入可复用的驾驶与交通智能体",
            )
        )

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(PAGE_CONTENT_MARGIN, 16, PAGE_CONTENT_MARGIN, 18)
        layout.setSpacing(12)
        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(self._configuration_panel(), 2)
        columns.addWidget(self._catalog_panel(), 3)
        layout.addLayout(columns, 1)
        root.addWidget(body, 1)

    def _configuration_panel(self) -> QFrame:
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(11)
        self.name_input = QLineEdit()
        self.name_input.setObjectName("agentNameInput")
        self.name_input.setPlaceholderText("例如：城市驾驶智能体")
        self.api_input = QLineEdit()
        self.api_input.setObjectName("agentApiUrlInput")
        self.api_input.setPlaceholderText("https://agents.example.com/v1")
        self.model_input = QLineEdit()
        self.model_input.setObjectName("agentModelInput")
        self.model_input.setPlaceholderText("模型或智能体 ID")
        self.credential_input = QLineEdit("TRAFFICVERSE_AGENT_API_KEY")
        self.credential_input.setObjectName("agentCredentialEnvInput")
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("用途说明（可选）")
        form.addRow("名称", self.name_input)
        form.addRow("API 地址", self.api_input)
        form.addRow("模型 ID", self.model_input)
        form.addRow("凭证环境变量", self.credential_input)
        form.addRow("说明", self.description_input)
        note = QLabel("这里只保存环境变量名称，不保存 API Key；凭证由部署环境注入。")
        note.setObjectName("caption")
        note.setWordWrap(True)
        form.addRow("", note)
        self.save_button = QPushButton("添加 API 智能体")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._emit_configuration)
        form.addRow("", self.save_button)
        return panel("API 配置", content, kicker="智能体接入")

    def _catalog_panel(self) -> QFrame:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName("agentAssetTable")
        self.table.setHorizontalHeaderLabels(("名称", "模型 ID", "API 地址", "凭证变量"))
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.delete_button = QPushButton("删除所选配置")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.clicked.connect(self._delete_selected)
        actions.addWidget(self.delete_button)
        layout.addLayout(actions)
        return panel("已配置智能体", content, kicker="工作区资源")

    def set_agents(self, agents: tuple[AgentApiSummary, ...]) -> None:
        self._agents = agents
        self.table.setRowCount(len(agents))
        for row, agent in enumerate(agents):
            values = (
                agent.name,
                agent.model_id,
                agent.api_base_url,
                agent.credential_env_var,
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _emit_configuration(self) -> None:
        self.configure_requested.emit(
            self.name_input.text().strip(),
            self.api_input.text().strip(),
            self.model_input.text().strip(),
            self.credential_input.text().strip(),
            self.description_input.text().strip(),
        )

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._agents):
            self.delete_requested.emit(self._agents[row].agent_api_id)
