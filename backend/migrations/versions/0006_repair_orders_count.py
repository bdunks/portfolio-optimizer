"""Repair run order counts after consolidated recommendation legs are upgraded."""

from __future__ import annotations

import json
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "0006_repair_orders_count"
down_revision = "0005_consolidated_recommendation_legs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    required_tables = {
        "optimizer_run",
        "recommendation_leg",
        "recommendation_group_leg",
        "recommendation_group",
    }
    if not required_tables <= set(sa.inspect(connection).get_table_names()):
        return
    runs = (
        connection.execute(sa.text("SELECT id, metrics FROM optimizer_run ORDER BY id"))
        .mappings()
        .all()
    )
    for run in runs:
        run_id = str(run["id"])
        legs = (
            connection.execute(
                sa.text(
                    "SELECT DISTINCT l.id, l.shares FROM recommendation_leg AS l "
                    "JOIN recommendation_group_leg AS gl ON gl.leg_id = l.id "
                    "JOIN recommendation_group AS g ON g.id = gl.group_id WHERE g.run_id = :run_id"
                ),
                {"run_id": run_id},
            )
            .mappings()
            .all()
        )
        # Consolidated BUY ownership may differ from the selected funding group; positive shares are authoritative.
        orders_count = sum(1 for leg in legs if Decimal(str(leg["shares"])) > 0)
        metrics_value = run["metrics"]
        metrics = (
            json.loads(metrics_value)
            if isinstance(metrics_value, str)
            else dict(metrics_value or {})
        )
        if metrics.get("orders_count") == orders_count:
            continue
        metrics["orders_count"] = orders_count
        connection.execute(
            sa.text("UPDATE optimizer_run SET metrics = :metrics WHERE id = :run_id"),
            {"metrics": json.dumps(metrics), "run_id": run_id},
        )


def downgrade() -> None:
    raise NotImplementedError("Run order-count repair is intentionally retained")
