"""Normalize run-level consolidated legs and link them to trade groups.

Revision ID: 0005_consolidated_recommendation_legs
Revises: 0004_database_integrity_checks
"""
from __future__ import annotations

import json
from decimal import Decimal, localcontext

import sqlalchemy as sa
from alembic import op

revision = "0005_consolidated_recommendation_legs"
down_revision = "0004_database_integrity_checks"
branch_labels = None
depends_on = None


def _repair_order_counts(connection: sa.Connection, run_ids: set[str]) -> None:
    for run_id in sorted(run_ids):
        legs = connection.execute(
            sa.text(
                "SELECT DISTINCT l.id, l.shares FROM recommendation_leg AS l "
                "JOIN recommendation_group_leg AS gl ON gl.leg_id = l.id "
                "JOIN recommendation_group AS g ON g.id = gl.group_id WHERE g.run_id = :run_id"
            ),
            {"run_id": run_id},
        ).mappings().all()
        # Consolidated BUY ownership may differ from the selected funding group; positive shares are authoritative.
        orders_count = sum(1 for leg in legs if Decimal(str(leg["shares"])) > 0)
        metrics_value = connection.execute(
            sa.text("SELECT metrics FROM optimizer_run WHERE id = :run_id"), {"run_id": run_id}
        ).scalar_one()
        metrics = json.loads(metrics_value) if isinstance(metrics_value, str) else dict(metrics_value or {})
        metrics["orders_count"] = orders_count
        connection.execute(
            sa.text("UPDATE optimizer_run SET metrics = :metrics WHERE id = :run_id"),
            {"metrics": json.dumps(metrics), "run_id": run_id},
        )


def upgrade() -> None:
    op.create_table(
        "recommendation_group_leg",
        sa.Column("group_id", sa.String(36), sa.ForeignKey("recommendation_group.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("leg_id", sa.String(36), sa.ForeignKey("recommendation_leg.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_recommendation_group_leg_leg", "recommendation_group_leg", ["leg_id"])
    connection = op.get_bind()
    if not {"recommendation_group", "recommendation_leg"} <= set(sa.inspect(connection).get_table_names()):
        return
    legs = connection.execute(
        sa.text(
            "SELECT l.id, l.group_id, g.run_id, l.security_id, l.side, l.shares, "
            "l.estimated_unit_price_usd, l.details "
            "FROM recommendation_leg AS l JOIN recommendation_group AS g ON g.id = l.group_id "
            "ORDER BY g.run_id, l.sequence, l.id"
        )
    ).mappings().all()
    grouped: dict[tuple[str, int], list[dict[str, object]]] = {}
    for leg in legs:
        connection.execute(
            sa.text("INSERT INTO recommendation_group_leg (group_id, leg_id) VALUES (:group_id, :leg_id)"),
            {"group_id": leg["group_id"], "leg_id": leg["id"]},
        )
        if leg["side"] == "BUY":
            grouped.setdefault((str(leg["run_id"]), int(leg["security_id"])), []).append(dict(leg))

    affected_run_ids: set[str] = set()
    for duplicates in grouped.values():
        if len(duplicates) < 2:
            continue
        affected_run_ids.add(str(duplicates[0]["run_id"]))
        canonical = duplicates[0]
        duplicate_ids = [str(row["id"]) for row in duplicates[1:]]
        group_ids = list(dict.fromkeys(str(row["group_id"]) for row in duplicates))
        sell_rows = connection.execute(
            sa.text(
                "SELECT id, shares FROM recommendation_leg WHERE group_id IN :group_ids AND side = 'SELL' "
                "ORDER BY sequence, id"
            ).bindparams(sa.bindparam("group_ids", expanding=True)),
            {"group_ids": group_ids},
        ).mappings().all()
        sell_ids = [str(row["id"]) for row in sell_rows if Decimal(str(row["shares"])) > 0]
        details = canonical["details"]
        if isinstance(details, str):
            details = json.loads(details)
        details = dict(details or {})
        details.pop("depends_on_leg_id", None)
        details["depends_on_leg_ids"] = [str(leg_id) for leg_id in sell_ids]
        share_values = tuple(Decimal(str(row["shares"])) for row in duplicates)
        min_exponent = min(value.as_tuple().exponent for value in share_values)
        max_adjusted = max(value.adjusted() if value else 0 for value in share_values)
        with localcontext() as context:
            context.prec = max(28, max_adjusted - min_exponent + len(str(len(share_values))) + 4)
            total_shares = sum(share_values, Decimal(0))
        connection.execute(
            sa.text("UPDATE recommendation_leg SET shares = :shares, details = :details WHERE id = :leg_id"),
            {"shares": str(total_shares), "details": json.dumps(details), "leg_id": canonical["id"]},
        )
        for group_id in group_ids:
            connection.execute(
                sa.text("INSERT OR IGNORE INTO recommendation_group_leg (group_id, leg_id) VALUES (:group_id, :leg_id)"),
                {"group_id": group_id, "leg_id": canonical["id"]},
            )
        connection.execute(
            sa.text("DELETE FROM recommendation_group_leg WHERE leg_id IN :leg_ids").bindparams(
                sa.bindparam("leg_ids", expanding=True)
            ),
            {"leg_ids": duplicate_ids},
        )
        connection.execute(
            sa.text("DELETE FROM recommendation_leg WHERE id IN :leg_ids").bindparams(
                sa.bindparam("leg_ids", expanding=True)
            ),
            {"leg_ids": duplicate_ids},
        )
    _repair_order_counts(connection, affected_run_ids)


def downgrade() -> None:
    raise NotImplementedError("Consolidated recommendation legs are intentionally retained")
