from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from pathlib import Path

from fastapi.testclient import TestClient

from app.broker.fake import FakeBroker
from app.db.models import OptimizerRun
from app.main import create_app
from app.optimizer.runtime import ProcessSupervisor
from app.schemas import BrokerSnapshot
from app.services.optimizer_service import BoundedValidationExecutor


TRADE_DATE = date(2026, 11, 15)
SOURCE_AS_OF = datetime(2026, 11, 14, 20, 0, tzinfo=UTC)
OLD_LOT_ID = "AAPL-OLD-001"
RECENT_LOT_ID = "AAPL-RECENT-001"


def _fee_adjusted_snapshot() -> BrokerSnapshot:
    template = FakeBroker.demo_snapshot()
    aapl_position = next(position for position in template.positions if position.ticker == "AAPL")
    aapl_lot = next(lot for lot in template.lots if lot.ticker == "AAPL")
    aapl_quote = next(quote for quote in template.quotes if quote.ticker == "AAPL")
    vti_quote = next(quote for quote in template.quotes if quote.ticker == "VTI")
    old_purchase = next(transaction for transaction in template.transactions if transaction.ticker == "AAPL")

    old_lot = aapl_lot.model_copy(
        update={
            "broker_lot_id": OLD_LOT_ID,
            "acquired_date": date(2025, 9, 1),
            "shares": Decimal(10),
            "available_shares": Decimal(10),
            "adjusted_unit_basis_usd": Decimal(110),
            "as_of": SOURCE_AS_OF,
        }
    )
    recent_lot = aapl_lot.model_copy(
        update={
            "broker_lot_id": RECENT_LOT_ID,
            "acquired_date": date(2026, 11, 5),
            "shares": Decimal(1),
            "available_shares": Decimal(1),
            "adjusted_unit_basis_usd": Decimal(95),
            "as_of": SOURCE_AS_OF,
        }
    )
    old_transaction = old_purchase.model_copy(
        update={
            "broker_transaction_key": "INTEGRATION-AAPL-OLD",
            "transaction_time": datetime(2025, 9, 1, 15, 0, tzinfo=UTC),
            "trade_date": date(2025, 9, 1),
            "shares": Decimal(10),
            "amount_usd": Decimal(1100),
            "broker_lot_id": OLD_LOT_ID,
        }
    )
    recent_transaction = old_purchase.model_copy(
        update={
            "broker_transaction_key": "INTEGRATION-AAPL-RECENT",
            "transaction_time": datetime(2026, 11, 5, 15, 0, tzinfo=UTC),
            "trade_date": date(2026, 11, 5),
            "shares": Decimal(1),
            "amount_usd": Decimal(95),
            "broker_lot_id": RECENT_LOT_ID,
        }
    )
    return template.model_copy(
        update={
            "as_of": SOURCE_AS_OF,
            "cash_usd": Decimal(0),
            "settled_buying_power_usd": Decimal(0),
            "positions": [
                aapl_position.model_copy(
                    update={"shares": Decimal(11), "market_value_usd": Decimal(1100), "as_of": SOURCE_AS_OF}
                )
            ],
            "lots": [old_lot, recent_lot],
            "quotes": [
                aapl_quote.model_copy(
                    update={
                        "bid_usd": Decimal(100),
                        "ask_usd": Decimal(100),
                        "last_usd": Decimal(100),
                        "as_of": SOURCE_AS_OF,
                    }
                ),
                vti_quote.model_copy(
                    update={
                        "bid_usd": Decimal(200),
                        "ask_usd": Decimal(200),
                        "last_usd": Decimal(200),
                        "as_of": SOURCE_AS_OF,
                    }
                ),
            ],
            "transactions": [old_transaction, recent_transaction],
        }
    )


def _activate_test_policy(client: TestClient) -> str:
    policy_response = client.get("/api/v1/policy")
    assert policy_response.status_code == 200, policy_response.text
    active = policy_response.json()["active"]
    settings = dict(active["settings"])
    settings.update(
        {
            "short_term_tax_rate": "0.30",
            "long_term_tax_rate": "0.15",
            "gain_budget_usd": "100",
            "max_incremental_tax_cost_usd": "100",
            "st_gain_limit_usd": "100",
            "lt_gain_limit_usd": "100",
            "max_sell_tickers_per_batch": 1,
            "max_sell_lots_per_batch": 2,
            "max_total_orders_per_batch": 2,
            "max_batch_turnover_pct": "100",
            "min_buy_order_notional_usd": "0",
            "cash_reserve_usd": "0",
            "allow_gain_sales": True,
            "objective_band_weight": "0",
            "objective_allocation_weight": "0",
            "objective_tax_weight": "1",
            "objective_trading_cost_weight": "0",
            "objective_turnover_weight": "0",
            "objective_cleanup_weight": "0",
            "estimated_spread_bps": "0",
            "estimated_fee_per_order_usd": "1",
        }
    )
    draft_response = client.post(
        "/api/v1/policy/drafts",
        json={
            "source_revision_id": active["id"],
            "sector_bands": [],
            "settings": settings,
            "sleeves": [
                {
                    "sleeve_key": "equity",
                    "display_name": "Synthetic equities",
                    "sort_order": 0,
                    "parent_sleeve_key": None,
                    "target_pct": "90",
                    "drift_band_pp": "10",
                    "is_direct_index_container": True,
                    "is_direct_index_sleeve": False,
                    "is_transition_destination": False,
                    "is_cash_sleeve": False,
                    "enabled": True,
                },
                {
                    "sleeve_key": "cash",
                    "display_name": "Synthetic cash",
                    "sort_order": 1,
                    "parent_sleeve_key": None,
                    "target_pct": "10",
                    "drift_band_pp": "10",
                    "is_direct_index_container": False,
                    "is_direct_index_sleeve": False,
                    "is_transition_destination": False,
                    "is_cash_sleeve": True,
                    "enabled": True,
                },
            ],
            "allowed_securities": [
                {
                    "ticker": "VTI",
                    "sleeve_key": "equity",
                    "sub_sleeve_key": None,
                    "replacement_set_id": "integration-us-market",
                    "priority": 1,
                    "enabled": True,
                    "exposure_suitability": "Deterministic integration fixture",
                }
            ],
            "overrides": [],
            "reassignments": {},
        },
    )
    assert draft_response.status_code == 201, draft_response.text
    revision_id = draft_response.json()["id"]
    activation_response = client.post(f"/api/v1/policy/{revision_id}/activate")
    assert activation_response.status_code == 200, activation_response.text
    return revision_id


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _to_eight_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"))


def test_real_optimizer_http_pipeline_persists_fee_adjusted_reviewed_lots_and_reopens(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "native-api-integration.sqlite3"
    database_url = f"sqlite:///{database_path}"
    snapshot = _fee_adjusted_snapshot()
    broker = FakeBroker(snapshot)
    app = create_app(database_url=database_url, broker=broker, seed_demo_data=True)

    with TestClient(app, base_url="http://localhost") as client:
        assert isinstance(app.state.optimizer_supervisor, ProcessSupervisor)
        assert isinstance(app.state.optimizer_validation_executor, BoundedValidationExecutor)
        policy_revision_id = _activate_test_policy(client)

        create_response = client.post(
            "/api/v1/optimizer/runs",
            json={"mode": "real_optimizer", "proposed_trade_date": TRADE_DATE.isoformat()},
        )
        assert create_response.status_code == 201, create_response.text
        initial = create_response.json()
        run_id = initial["run_id"]
        assert initial["status"] == "COMPLETE"
        assert initial["mode"] == "real_optimizer"
        assert initial["demo"] is False
        assert initial["solver_version"] != "DEMO"
        assert initial["proposed_trade_date"] == TRADE_DATE.isoformat()
        assert initial["policy_revision_id"] == policy_revision_id
        assert initial["constraints_satisfied"] is True
        assert initial["orders_count"] == 2

        legs = initial["consolidated_legs"]
        sells = [leg for leg in legs if leg["side"] == "SELL"]
        buys = [leg for leg in legs if leg["side"] == "BUY"]
        assert len(sells) == len(buys) == 1
        sell, buy = sells[0], buys[0]
        assert sell["ticker"] == "AAPL"
        assert buy["ticker"] == "VTI"
        assert buy["dependencies"] == [sell["leg_id"]]
        assert all(_decimal(leg["shares"]).to_integral_value() == _decimal(leg["shares"]) for leg in legs)
        assert sell["estimated_unit_price_usd"] == "100"
        assert buy["estimated_unit_price_usd"] == "200"

        selected_lots = {lot["broker_lot_id"]: lot for lot in sell["selected_lots"]}
        assert set(selected_lots) == {OLD_LOT_ID, RECENT_LOT_ID}
        assert _decimal(selected_lots[OLD_LOT_ID]["shares"]) == Decimal(10)
        assert _decimal(selected_lots[RECENT_LOT_ID]["shares"]) == Decimal(1)
        assert selected_lots[OLD_LOT_ID]["st_lt"] == "LT"
        assert selected_lots[RECENT_LOT_ID]["st_lt"] == "ST"

        with localcontext() as context:
            context.prec = 100
            old_fee = Decimal(1) * Decimal(10) / Decimal(11)
            recent_fee = Decimal(1) - old_fee
            expected_old_realized = (Decimal(100) - Decimal(110)) * Decimal(10) - old_fee
            expected_recent_realized = (Decimal(100) - Decimal(95)) - recent_fee
        assert _to_eight_places(_decimal(selected_lots[OLD_LOT_ID]["realized_pl_usd"])) == _to_eight_places(
            expected_old_realized
        )
        assert _to_eight_places(_decimal(selected_lots[RECENT_LOT_ID]["realized_pl_usd"])) == _to_eight_places(
            expected_recent_realized
        )
        assert sum((_decimal(lot["realized_pl_usd"]) for lot in selected_lots.values()), Decimal(0)) == Decimal(-96)
        assert _to_eight_places(_decimal(sell["net_lt_realized_usd"])) == _to_eight_places(
            expected_old_realized
        )
        assert _to_eight_places(_decimal(sell["net_st_realized_usd"])) == _to_eight_places(
            expected_recent_realized
        )

        sell_notional = _decimal(sell["shares"]) * _decimal(sell["estimated_unit_price_usd"])
        buy_notional = _decimal(buy["shares"]) * _decimal(buy["estimated_unit_price_usd"])
        expected_cash_after = _decimal(initial["cash_before_usd"]) + sell_notional - buy_notional - Decimal(2)
        assert _decimal(initial["cash_after_usd"]) == expected_cash_after
        assert _decimal(initial["optimizer_metrics"]["estimated_trading_cost_usd"]) == Decimal(2)

        with app.state.session_factory() as session:
            saved_run = session.get(OptimizerRun, run_id)
            assert saved_run is not None
            assert saved_run.policy_revision_id == policy_revision_id
            assert saved_run.source_generation == initial["source_generation"]
            assert saved_run.input_fingerprint == initial["input_fingerprint"]
            assert saved_run.as_of == SOURCE_AS_OF
            assert saved_run.proposed_trade_date == TRADE_DATE
            provenance = saved_run.frozen_input_bundle
            assert provenance["mode"] == "real_optimizer"
            assert provenance["proposed_trade_date"] == TRADE_DATE.isoformat()
            assert provenance["input_fingerprint"] == saved_run.input_fingerprint
            policy_provenance = provenance["policy"]
            assert policy_provenance["settings"]["estimated_fee_per_order_usd"] == "1"
            assert policy_provenance["settings"]["short_term_tax_rate"] == "0.3"
            assert {lot["broker_lot_id"] for lot in provenance["lots"]} == {
                OLD_LOT_ID,
                RECENT_LOT_ID,
            }

        summary_response = client.get(f"/api/v1/optimizer/runs/{run_id}")
        recommendations_response = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations")
        assert summary_response.status_code == 200, summary_response.text
        assert recommendations_response.status_code == 200, recommendations_response.text
        assert summary_response.json()["input_fingerprint"] == initial["input_fingerprint"]
        assert recommendations_response.json()["consolidated_legs"] == legs

        intent_response = client.post(
            f"/api/v1/optimizer/runs/{run_id}/lot-review-intent",
            json={
                "source_generation": initial["source_generation"],
                "broker_lot_ids": [OLD_LOT_ID, RECENT_LOT_ID],
            },
        )
        assert intent_response.status_code == 200, intent_response.text
        confirmed = intent_response.json()
        confirmed_sell = next(leg for leg in confirmed["consolidated_legs"] if leg["side"] == "SELL")
        confirmed_buy = next(leg for leg in confirmed["consolidated_legs"] if leg["side"] == "BUY")
        assert {lot["broker_lot_id"] for lot in confirmed_sell["selected_lots"]} == {
            OLD_LOT_ID,
            RECENT_LOT_ID,
        }
        assert confirmed_buy["dependencies"] == [confirmed_sell["leg_id"]]
        confirmed_recommendations = client.get(
            f"/api/v1/optimizer/runs/{run_id}/recommendations"
        )
        assert confirmed_recommendations.status_code == 200, confirmed_recommendations.text
        assert confirmed_recommendations.json() == confirmed
        assert broker.fetch_count == 1
        assert not hasattr(broker, "preview_order")
        assert not hasattr(broker, "submit_approved_order")

    reopened_app = create_app(database_url=database_url, broker=FakeBroker(snapshot), seed_demo_data=False)
    with TestClient(reopened_app, base_url="http://localhost") as reopened_client:
        reopened_summary = reopened_client.get(f"/api/v1/optimizer/runs/{run_id}")
        reopened_recommendations = reopened_client.get(
            f"/api/v1/optimizer/runs/{run_id}/recommendations"
        )
        assert reopened_summary.status_code == 200, reopened_summary.text
        assert reopened_recommendations.status_code == 200, reopened_recommendations.text
        assert reopened_recommendations.json() == confirmed
        assert reopened_summary.json()["policy_revision_id"] == policy_revision_id
        assert reopened_summary.json()["source_generation"] == initial["source_generation"]
        assert reopened_summary.json()["input_fingerprint"] == initial["input_fingerprint"]
        assert reopened_summary.json()["proposed_trade_date"] == TRADE_DATE.isoformat()
        assert reopened_app.state.broker.fetch_count == 0
