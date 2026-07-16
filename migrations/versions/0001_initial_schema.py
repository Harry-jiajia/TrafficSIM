"""Create scenario, experiment, event, metric, and artifact tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

STATUS_SQL = (
    "'CREATED', 'PREPARING', 'READY', 'RUNNING', 'PAUSED', 'STOPPING', 'COMPLETED', 'FAILED'"
)


def upgrade() -> None:
    op.create_table(
        "map_asset",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("map_id", sa.String(200), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_format", sa.String(50), nullable=False),
        sa.Column("source_checksum", sa.String(71), nullable=False),
        sa.Column("network_schema_version", sa.String(100), nullable=False),
        sa.Column("manifest_uri", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("map_id", name="uq_map_asset_map_id"),
        sa.UniqueConstraint("source_checksum", name="uq_map_asset_source_checksum"),
        sa.CheckConstraint("status = 'VALIDATED'", name="ck_map_asset_status"),
    )
    op.create_table(
        "scenario",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "scenario_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scenario.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "map_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("map_asset.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("scenario_id", "version", name="uq_scenario_version_scenario_version"),
        sa.CheckConstraint("version >= 1", name="ck_scenario_version_positive"),
    )
    op.create_index("ix_scenario_version_map_asset_id", "scenario_version", ["map_asset_id"])
    op.create_table(
        "experiment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scenario_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("step_ms", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("current_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("failure_code", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(f"status IN ({STATUS_SQL})", name="ck_experiment_status"),
        sa.CheckConstraint("seed >= 0", name="ck_experiment_seed"),
        sa.CheckConstraint("step_ms > 0", name="ck_experiment_step_ms"),
        sa.CheckConstraint("duration_ms > 0", name="ck_experiment_duration_ms"),
        sa.CheckConstraint("current_time_ms >= 0", name="ck_experiment_current_time_ms"),
    )
    op.create_index("ix_experiment_scenario_version_id", "experiment", ["scenario_version_id"])
    op.create_index("ix_experiment_status_created_at", "experiment", ["status", "created_at"])
    op.create_table(
        "experiment_state_change",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experiment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(f"from_status IN ({STATUS_SQL})", name="ck_state_from_status"),
        sa.CheckConstraint(f"to_status IN ({STATUS_SQL})", name="ck_state_to_status"),
        sa.CheckConstraint("simulation_time_ms >= 0", name="ck_state_simulation_time_ms"),
    )
    op.create_index(
        "ix_state_change_experiment_occurred",
        "experiment_state_change",
        ["experiment_id", "occurred_at"],
    )
    op.create_table(
        "event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experiment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("simulation_time_ms >= 0", name="ck_event_simulation_time_ms"),
    )
    op.create_index("ix_event_experiment_time", "event", ["experiment_id", "simulation_time_ms"])
    op.create_table(
        "metric_sample",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experiment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("simulation_time_ms >= 0", name="ck_metric_simulation_time_ms"),
    )
    op.create_index(
        "ix_metric_experiment_name_time",
        "metric_sample",
        ["experiment_id", "metric_name", "simulation_time_ms"],
    )
    op.create_table(
        "artifact",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experiment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("format", sa.String(50), nullable=False),
        sa.Column("checksum", sa.String(71), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifact_size_bytes"),
    )
    op.create_index("ix_artifact_experiment_kind", "artifact", ["experiment_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_artifact_experiment_kind", table_name="artifact")
    op.drop_table("artifact")
    op.drop_index("ix_metric_experiment_name_time", table_name="metric_sample")
    op.drop_table("metric_sample")
    op.drop_index("ix_event_experiment_time", table_name="event")
    op.drop_table("event")
    op.drop_index("ix_state_change_experiment_occurred", table_name="experiment_state_change")
    op.drop_table("experiment_state_change")
    op.drop_index("ix_experiment_status_created_at", table_name="experiment")
    op.drop_index("ix_experiment_scenario_version_id", table_name="experiment")
    op.drop_table("experiment")
    op.drop_index("ix_scenario_version_map_asset_id", table_name="scenario_version")
    op.drop_table("scenario_version")
    op.drop_table("scenario")
    op.drop_table("map_asset")
