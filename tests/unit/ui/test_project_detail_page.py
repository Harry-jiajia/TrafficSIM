from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget, QToolButton
from ui.models import WorkspaceOverview, WorkspaceSummary
from ui.views.project_detail_page import ProjectDetailPage


def _application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def _workspace(*, description: str = "核心路网") -> WorkspaceSummary:
    return WorkspaceSummary.model_validate(
        {
            "workspace_id": "10000000-0000-0000-0000-000000000001",
            "name": "北京亦庄项目",
            "description": description,
            "created_at": "2026-07-31T00:00:00Z",
            "updated_at": "2026-07-31T00:00:00Z",
        }
    )


def _overview(workspace: WorkspaceSummary) -> WorkspaceOverview:
    return WorkspaceOverview.model_validate(
        {
            "workspace_id": str(workspace.workspace_id),
            "map_count": 12,
            "agent_count": 250000,
            "scenario_count": 158,
            "simulation_count": 3,
            "automation_counts": [],
            "succeeded_simulations": 1,
            "failed_simulations": 1,
            "runtime_hours": 6.5,
            "activity": [],
            "recent_simulations": [
                {
                    "name": "早高峰联仿",
                    "status": "WARNING",
                    "occurred_at": "2026-07-19T08:30:00Z",
                    "duration_ms": 7200000,
                    "automation_summary": "L3 · 45%",
                },
                {
                    "name": "路口回归测试",
                    "status": "SUCCEEDED",
                    "occurred_at": "2026-07-18T22:15:00Z",
                    "duration_ms": 2700000,
                    "automation_summary": "L4 · 10%",
                },
                {
                    "name": "匝道压力测试",
                    "status": "FAILED",
                    "occurred_at": "2026-07-17T14:00:00Z",
                    "duration_ms": 5400000,
                    "automation_summary": "L2 · 60%",
                },
            ],
            "preview_region": "亦庄核心区",
        }
    )


def test_project_detail_renders_editable_information_and_simulation_actions() -> None:
    _application()
    page = ProjectDetailPage()
    workspace = _workspace()
    edits: list[str] = []
    creates: list[bool] = []
    actions: list[tuple[str, str, str]] = []
    page.edit_requested.connect(edits.append)
    page.create_simulation_requested.connect(lambda: creates.append(True))
    page.simulation_action_requested.connect(
        lambda name, action, parameters: actions.append((name, action, parameters))
    )

    page.set_workspace(workspace)
    page.set_overview(_overview(workspace))

    assert page.name_field.value_label.text() == "北京亦庄项目"
    assert page.description_field.value_label.text() == "核心路网"
    assert page.name_field.focusPolicy() == Qt.FocusPolicy.StrongFocus
    QTest.mouseClick(page.name_field, Qt.MouseButton.LeftButton)
    page.description_field.setFocus()
    QTest.keyClick(page.description_field, Qt.Key.Key_Return)

    table = page.findChild(QTableWidget, "projectSimulationTable")
    create_button = page.findChild(QPushButton, "projectCreateSimulationButton")
    assert table is not None
    assert create_button is not None
    assert table.rowCount() == 3
    statuses: list[tuple[str, str]] = []
    for row in range(3):
        status = table.cellWidget(row, 3)
        assert isinstance(status, QLabel)
        statuses.append((status.text(), str(status.property("state"))))
    assert statuses == [
        ("●  进行中", "running"),
        ("●  完成", "completed"),
        ("●  失败", "failed"),
    ]

    buttons = page.findChildren(QToolButton, "projectSimulationAction")
    button_actions = {str(button.property("action")) for button in buttons}
    assert {"view", "replay", "pause", "delete", "copy"} <= button_actions
    assert all(button.text() == "" and not button.icon().isNull() for button in buttons)
    pause = next(button for button in buttons if button.property("action") == "pause")
    pause.click()
    create_button.click()

    visible_labels = {label.text() for label in page.findChildren(QLabel)}
    assert "项目信息" in visible_labels
    assert "名称" in visible_labels
    assert "描述" in visible_labels
    assert "项目基础资料" not in visible_labels
    assert "点击编辑" not in visible_labels

    assert edits == ["name", "description"]
    assert creates == [True]
    assert actions == [("早高峰联仿", "pause", "L3 · 45%")]
    page.close()


def test_project_detail_uses_default_copy_for_new_project_description() -> None:
    _application()
    page = ProjectDetailPage()

    page.set_workspace(_workspace(description=""))

    description = page.findChild(QLabel, "projectDescriptionValue")
    assert description is not None
    assert description.text() == "暂无描述"
    page.close()
