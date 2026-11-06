"""Add exact-text domain checks to databases already at the previous head."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_database_integrity_checks"
down_revision = "0003_demo_recommendation_state"
branch_labels = None
depends_on = None

_CHECKS = {
    "current_tax_lot": (
        ("ck_lot_available_nonnegative", "available_shares NOT LIKE '-%'"),
        ("ck_lot_shares_positive", "shares NOT LIKE '-%' AND shares <> '0'"),
    ),
    "current_quote": (
        ("ck_quote_bid_positive", "bid_usd IS NULL OR (bid_usd NOT LIKE '-%' AND bid_usd <> '0')"),
        ("ck_quote_ask_positive", "ask_usd IS NULL OR (ask_usd NOT LIKE '-%' AND ask_usd <> '0')"),
        ("ck_quote_last_positive", "last_usd IS NULL OR (last_usd NOT LIKE '-%' AND last_usd <> '0')"),
    ),
    "security_exposure": (
        ("ck_exposure_provider", "provider IN ('vanguard', 'ishares', 'manual_csv')"),
    ),
    "recommendation_selected_lot": (
        ("ck_selected_lot_shares_positive", "shares NOT LIKE '-%' AND shares <> '0'"),
        ("ck_selected_lot_term", "st_lt_term IN ('ST', 'LT')"),
    ),
}


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = set(inspector.get_table_names())
    pending: dict[str, list[tuple[str, str]]] = {}

    # Validate all existing rows before any SQLite table rebuild, so invalid legacy data
    # leaves the complete database untouched and reports the offending constraint.
    for table, checks in _CHECKS.items():
        if table not in existing_tables:
            continue
        current_names = {item["name"] for item in inspector.get_check_constraints(table)}
        missing = [(name, expression) for name, expression in checks if name not in current_names]
        for name, expression in missing:
            invalid = connection.execute(
                sa.text(f"SELECT 1 FROM {table} WHERE NOT ({expression}) LIMIT 1")
            ).first()
            if invalid is not None:
                raise RuntimeError(f"Cannot add {name}: existing {table} rows violate the check")
        if missing:
            pending[table] = missing

    for table, checks in pending.items():
        with op.batch_alter_table(table, recreate="always") as batch:
            for name, expression in checks:
                batch.create_check_constraint(name, expression)


def downgrade() -> None:
    raise NotImplementedError("Database integrity checks are intentionally retained")
