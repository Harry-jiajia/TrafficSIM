"""Persistent navigation rail for the desktop shell."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QEnterEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.models import WorkspaceSummary
from ui.views.element_plus_icons import ICON_SIZE, render_element_plus_icon, render_svg_pixmap
from ui.views.theme import ThemeMode, load_icon_colors

_NAVIGATION = (
    ("live", "monitor.svg", "实时监控"),
    ("scene", "set-up.svg", "仿真配置"),
    ("experiments", "data-board.svg", "历史仿真"),
    ("analysis", "trend-charts.svg", "数据分析"),
    ("assets", "box.svg", "资产中心"),
    ("settings", "setting.svg", "系统设置"),
)
_ICON_ROOT = Path(__file__).resolve().parents[1] / "assets/icons/element-plus"
_BRAND_LOGO = Path(__file__).resolve().parents[1] / "assets/icons/logo.svg"


class NavigationRail(QWidget):
    page_selected = Signal(str)
    workspace_exit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navigationRail")
        self.setFixedWidth(236)
        self._buttons: dict[str, QPushButton] = {}
        self._icon_paths: dict[str, Path] = {}
        self._theme = ThemeMode.DARK

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(6)
        layout.addLayout(self._brand())
        layout.addSpacing(18)

        self.workspace_back = QPushButton("←  返回工作区")
        self.workspace_back.setObjectName("workspaceBackButton")
        self.workspace_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.workspace_back.clicked.connect(self.workspace_exit_requested)
        layout.addWidget(self.workspace_back)
        self.workspace_name = QLabel("尚未选择工作区")
        self.workspace_name.setObjectName("activeWorkspaceName")
        self.workspace_name.setWordWrap(True)
        layout.addWidget(self.workspace_name)
        layout.addSpacing(18)

        section = QLabel("控制中心")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)
        layout.addSpacing(5)
        for key, icon, label in _NAVIGATION[:5]:
            layout.addWidget(self._nav_button(key, icon, label))

        layout.addStretch(1)
        section = QLabel("系统")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)
        layout.addWidget(self._nav_button(*_NAVIGATION[5]))

        divider = QFrame()
        divider.setObjectName("navigationDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)
        version = QLabel("TrafficVerse  ·  v0.1\n核心运行控制台")
        version.setObjectName("brandCaption")
        version.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(version)
        self.set_active("live")

    def set_workspace(self, name: str) -> None:
        self.workspace_name.setText(name)

    def set_active(self, key: str) -> None:
        for button_key, button in self._buttons.items():
            button.setProperty("active", button_key == key)
            button.style().unpolish(button)
            button.style().polish(button)
        self.refresh_icons()

    def refresh_icons(self, theme: ThemeMode | None = None) -> None:
        if theme is not None:
            self._theme = theme
        colors = load_icon_colors(self._theme)
        for key, button in self._buttons.items():
            color_name = colors["active"] if button.property("active") else colors["normal"]
            color = QColor(color_name)
            button.setIcon(render_element_plus_icon(self._icon_paths[key], color))
            button.setIconSize(ICON_SIZE)

    def _brand(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("brandLogo")
        logo.setPixmap(
            render_svg_pixmap(
                _BRAND_LOGO,
                QSize(40, 40),
            )
        )
        logo.setFixedSize(40, 40)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel("TrafficVerse")
        name.setObjectName("brandName")
        caption = QLabel("交通仿真系统")
        caption.setObjectName("brandCaption")
        text.addWidget(name)
        text.addWidget(caption)
        row.addWidget(logo)
        row.addLayout(text)
        row.addStretch(1)
        return row

    def _nav_button(self, key: str, icon_file: str, label: str) -> QPushButton:
        button = QPushButton(label)
        button.setProperty("navKey", key)
        button.setAccessibleName(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False, page=key: self.page_selected.emit(page))
        self._buttons[key] = button
        self._icon_paths[key] = _ICON_ROOT / icon_file
        button.setObjectName(f"nav_{key}")
        button.setProperty("role", "navigation")
        return button


class _WorkspaceListRow(QWidget):
    delete_requested = Signal(object)

    def __init__(self, workspace: WorkspaceSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workspaceListRow")
        self.setProperty("active", False)
        self.setMinimumHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 4, 3)
        layout.setSpacing(6)
        self.name_label = QLabel(workspace.name)
        self.name_label.setObjectName("workspaceListName")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.name_label, 1)
        self.delete_button = QPushButton("删除")
        self.delete_button.setObjectName("workspaceListDeleteButton")
        self.delete_button.setAccessibleName(f"删除工作区 {workspace.name}")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.setFixedHeight(28)
        self.name_label.installEventFilter(self)
        self.delete_button.installEventFilter(self)
        self.delete_button.clicked.connect(
            lambda checked=False: self.delete_requested.emit(workspace)
        )
        self.delete_button.hide()
        layout.addWidget(self.delete_button, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def enterEvent(self, event: QEnterEvent) -> None:
        self.delete_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        QTimer.singleShot(0, self._hide_delete_when_pointer_left)
        super().leaveEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched in {self.name_label, self.delete_button}:
            if event.type() is QEvent.Type.Enter:
                self.delete_button.show()
            elif event.type() is QEvent.Type.Leave:
                QTimer.singleShot(0, self._hide_delete_when_pointer_left)
        return super().eventFilter(watched, event)

    def _hide_delete_when_pointer_left(self) -> None:
        if not self.underMouse() and not self.delete_button.underMouse():
            self.delete_button.hide()


class WorkspaceNavigationRail(QWidget):
    """Workspace browser shown before simulation-specific navigation."""

    workspace_selected = Signal(str)
    workspace_enter_requested = Signal()
    create_requested = Signal()
    delete_requested = Signal(object)
    search_changed = Signal(str)
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workspaceNavigationRail")
        self.setFixedWidth(260)
        self._workspace_ids: set[str] = set()
        self._rows: dict[str, _WorkspaceListRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(8)
        layout.addLayout(self._brand())
        layout.addSpacing(24)

        heading = QHBoxLayout()
        title = QLabel("工作区")
        title.setObjectName("workspaceSectionTitle")
        heading.addWidget(title)
        heading.addStretch(1)
        create = QPushButton("+")
        create.setObjectName("workspaceCreateButton")
        create.setAccessibleName("新建工作区")
        create.setToolTip("新建工作区")
        create.setFixedSize(30, 30)
        create.clicked.connect(self.create_requested)
        heading.addWidget(create)
        layout.addLayout(heading)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("workspaceSearchInput")
        self.search_input.setPlaceholderText("搜索工作区…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.search_changed)
        layout.addWidget(self.search_input)

        self.workspace_list = QListWidget()
        self.workspace_list.setObjectName("workspaceList")
        self.workspace_list.setSpacing(2)
        self.workspace_list.currentItemChanged.connect(self._selection_changed)
        self.workspace_list.itemDoubleClicked.connect(self._workspace_double_clicked)
        layout.addWidget(self.workspace_list, 1)

        settings = QPushButton("⚙  系统设置")
        settings.setObjectName("workspaceSettingsButton")
        settings.setProperty("role", "navigation")
        settings.clicked.connect(self.settings_requested)
        layout.addWidget(settings)

    def set_workspaces(
        self,
        workspaces: tuple[WorkspaceSummary, ...],
        selected_workspace_id: str | None = None,
    ) -> None:
        blocker = QSignalBlocker(self.workspace_list)
        previous_id = selected_workspace_id
        if previous_id is None and self.workspace_list.currentItem() is not None:
            previous_id = str(self.workspace_list.currentItem().data(Qt.ItemDataRole.UserRole))
        self.workspace_list.clear()
        self._workspace_ids = {str(workspace.workspace_id) for workspace in workspaces}
        self._rows.clear()
        selected_item: QListWidgetItem | None = None
        for workspace in workspaces:
            workspace_id = str(workspace.workspace_id)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, workspace_id)
            item.setToolTip(workspace.description or workspace.name)
            item.setSizeHint(QSize(0, 42))
            self.workspace_list.addItem(item)
            row = _WorkspaceListRow(workspace)
            row.delete_requested.connect(self.delete_requested)
            self.workspace_list.setItemWidget(item, row)
            self._rows[workspace_id] = row
            if workspace_id == previous_id:
                selected_item = item
        if selected_item is None and self.workspace_list.count():
            selected_item = self.workspace_list.item(0)
        if selected_item is not None:
            self.workspace_list.setCurrentItem(selected_item)
        blocker.unblock()
        self._refresh_active_rows()

    def set_selected(self, workspace_id: str | None) -> None:
        if workspace_id is None or workspace_id not in self._workspace_ids:
            self.workspace_list.clearSelection()
            return
        for index in range(self.workspace_list.count()):
            item = self.workspace_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole)) == workspace_id:
                self.workspace_list.setCurrentItem(item)
                return

    @Slot(QListWidgetItem, QListWidgetItem)
    def _selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        self._refresh_active_rows()
        if current is not None:
            self.workspace_selected.emit(str(current.data(Qt.ItemDataRole.UserRole)))

    def _refresh_active_rows(self) -> None:
        current = self.workspace_list.currentItem()
        current_id = str(current.data(Qt.ItemDataRole.UserRole)) if current is not None else None
        for workspace_id, row in self._rows.items():
            row.set_active(workspace_id == current_id)

    @Slot(QListWidgetItem)
    def _workspace_double_clicked(self, item: QListWidgetItem) -> None:
        self.workspace_list.setCurrentItem(item)
        self.workspace_enter_requested.emit()

    def _brand(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("brandLogo")
        logo.setPixmap(render_svg_pixmap(_BRAND_LOGO, QSize(40, 40)))
        logo.setFixedSize(40, 40)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel("TrafficVerse")
        name.setObjectName("brandName")
        caption = QLabel("交通仿真系统")
        caption.setObjectName("brandCaption")
        text.addWidget(name)
        text.addWidget(caption)
        row.addWidget(logo)
        row.addLayout(text)
        row.addStretch(1)
        return row
