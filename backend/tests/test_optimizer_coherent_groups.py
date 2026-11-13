from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Account,
    Base,
    OptimizerRun,
    PolicyRevision,
    RecommendationGroup,
    RecommendationGroupLeg,
    RecommendationLeg,
    RecommendationSelectedLot,
    Security,
)
from app.db.session import create_database_engine
from app.optimizer.core import _cohere_trade_group_legs, _group_priorities
from app.optimizer.validation import validate_candidate
from app.services import optimizer_service
from tests.test_optimizer_core import _shared_funding_case


def test_coherent_connected_group_persists_and_reads_back_as_one_selectable_opportunity(
    tmp_path: Path,
) -> None:
    inputs, baseline, screen, original_legs = _shared_funding_case()
    priorities, warnings = _group_priorities(
        inputs, screen, baseline, original_legs, time.monotonic() + 5
    )
    assert warnings == ()
    assert len(priorities) == 1
    candidate_legs = _cohere_trade_group_legs(original_legs)
    validation = validate_candidate(inputs, candidate_legs)
    assert validation.accepted, validation.reasons
    core_group_id = priorities[0].group_id
    assert {leg.group_ids for leg in candidate_legs} == {(core_group_id,)}

    engine = create_database_engine(f"sqlite:///{tmp_path / 'coherent-groups.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    now = datetime.now(UTC)
    run_id = "62f3eb8c-426c-4f64-a584-2d3b4ee6aa01"
    policy_id = "5a02c19f-8755-4da0-bb04-fd3d1b8dd681"
    persisted_group_id = optimizer_service._stable_id(run_id, "group", core_group_id)
    persisted_leg_ids = {
        leg.leg_id: optimizer_service._stable_id(run_id, "leg", leg.leg_id)
        for leg in candidate_legs
    }
    with session_factory.begin() as session:
        session.add(
            PolicyRevision(
                id=policy_id,
                revision_number=1,
                status="ACTIVE",
                created_at=now,
            )
        )
        session.add(
            Account(
                id=1,
                broker_account_id_key="coherent-test-account",
                display_name="Coherent test account",
                cash_usd=inputs.account.cash_usd,
                settled_buying_power_usd=inputs.account.settled_buying_power_usd,
                as_of=inputs.account.as_of,
            )
        )
        security_ids = {"AAPL": 1, "MSFT": 2, "NEWETF": 3}
        session.add_all(
            [
                Security(
                    id=security_id,
                    ticker=ticker,
                    asset_type="ETF" if ticker == "NEWETF" else "EQUITY",
                )
                for ticker, security_id in security_ids.items()
            ]
        )
        session.flush()
        run = OptimizerRun(
            id=run_id,
            policy_revision_id=policy_id,
            source_generation=inputs.source_generation,
            as_of=inputs.account.as_of,
            proposed_trade_date=inputs.proposed_trade_date,
            solver_version="coherent-group-test",
            status="COMPLETE",
            batch_settings={
                "max_sell_tickers_per_batch": 2,
                "max_sell_lots_per_batch": 2,
                "max_total_orders_per_batch": 3,
            },
            metrics={
                "optimizer_status": "ready",
                "selection_universe": {
                    core_group_id: ["loss-lot", "msft-loss-lot"],
                },
                "trade_group_priorities": [
                    {"core_group_id": core_group_id, "rank": priorities[0].rank},
                ],
            },
            warnings=[],
            input_fingerprint="coherent-group-test",
            frozen_input_bundle={"mode": "real_optimizer"},
        )
        session.add(run)
        session.flush()
        sell_leg_ids = [persisted_leg_ids["sell:AAPL"], persisted_leg_ids["sell:MSFT"]]
        group = RecommendationGroup(
            id=persisted_group_id,
            run_id=run_id,
            rank=priorities[0].rank,
            group_type="optimizer_trade",
            sleeve_key="equity",
            rationale=" ".join(priorities[0].rationale),
            estimated_benefit_usd=None,
            impact={
                "demo": False,
                "wash_status": "validated",
                "selected_sell_lots_count": 2,
                "sell_proceeds_usd": "200",
                "realized_st_usd": "0",
                "realized_lt_usd": "-20",
                "replacement_buy_shares": "2",
                "replacement_buy_cost_usd": "200",
                "core_group_id": core_group_id,
                "candidate_sell_lot_ids": ["loss-lot", "msft-loss-lot"],
            },
            dependencies=sell_leg_ids,
            selected=True,
            rejected=False,
        )
        session.add(group)
        session.flush()

        lots_by_id = {lot.broker_lot_id: lot for lot in inputs.lots}
        persisted_legs = []
        persisted_lots = []
        for leg in candidate_legs:
            realized_st = Decimal(0)
            realized_lt = Decimal(0)
            for allocation in leg.selected_lots:
                lot = lots_by_id[allocation.broker_lot_id]
                realized = (
                    leg.estimated_unit_price_usd - lot.adjusted_unit_basis_usd
                ) * allocation.shares
                term = optimizer_service.classify_holding_period(
                    lot.acquired_date, inputs.proposed_trade_date
                )
                if term == "ST":
                    realized_st += realized
                else:
                    realized_lt += realized
                persisted_lots.append(
                    RecommendationSelectedLot(
                        leg_id=persisted_leg_ids[leg.leg_id],
                        broker_lot_id=allocation.broker_lot_id,
                        shares=allocation.shares,
                        acquired_date=lot.acquired_date,
                        adjusted_basis_usd=lot.adjusted_unit_basis_usd,
                        st_lt_term=term,
                        realized_pl_usd=realized,
                        selected=True,
                    )
                )
            dependencies = [persisted_leg_ids[item] for item in leg.depends_on_leg_ids]
            persisted_legs.append(
                RecommendationLeg(
                    id=persisted_leg_ids[leg.leg_id],
                    group_id=persisted_group_id,
                    account_id=inputs.account.local_account_id,
                    security_id=security_ids[leg.ticker],
                    side=leg.side,
                    shares=leg.shares,
                    estimated_unit_price_usd=leg.estimated_unit_price_usd,
                    net_st_realized_usd=realized_st,
                    net_lt_realized_usd=realized_lt,
                    sequence=leg.sequence,
                    details={
                        "core_leg_id": leg.leg_id,
                        "group_ids": [persisted_group_id],
                        "depends_on_leg_ids": dependencies,
                        "core_group_ids": [core_group_id],
                    },
                )
            )
        session.add_all(persisted_legs)
        session.flush()
        session.add_all(
            RecommendationGroupLeg(group_id=persisted_group_id, leg_id=leg.id)
            for leg in persisted_legs
        )
        session.add_all(persisted_lots)
        session.flush()

    with session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        result = optimizer_service.real_run_recommendations(session, run)
        groups = result["groups"]
        assert isinstance(groups, list)
        assert len(groups) == 1
        group_response = groups[0]
        assert isinstance(group_response, dict)
        assert group_response["group_id"] == persisted_group_id
        assert group_response["rank"] == priorities[0].rank
        assert len(group_response["leg_ids"]) == 3

        legs = result["consolidated_legs"]
        assert isinstance(legs, list)
        assert len(legs) == 3
        assert {tuple(leg["group_ids"]) for leg in legs} == {(persisted_group_id,)}
        persisted_by_core_id = {leg["details"]["core_leg_id"]: leg for leg in legs}
        assert set(persisted_by_core_id) == {leg.leg_id for leg in candidate_legs}
        buy = persisted_by_core_id["buy:NEWETF"]
        assert set(buy["dependencies"]) == {
            persisted_by_core_id["sell:AAPL"]["leg_id"],
            persisted_by_core_id["sell:MSFT"]["leg_id"],
        }
        assert {lot["broker_lot_id"] for leg in legs for lot in leg["selected_lots"]} == {
            "loss-lot",
            "msft-loss-lot",
        }
        assert result["optimizer_metrics"]["selection_universe"][core_group_id] == [
            "loss-lot",
            "msft-loss-lot",
        ]
        assert len(result["optimizer_metrics"]["trade_group_priorities"]) == 1
        assert (
            result["optimizer_metrics"]["trade_group_priorities"][0]["core_group_id"]
            == core_group_id
        )
        assert (
            session.scalar(select(RecommendationGroup).where(RecommendationGroup.run_id == run_id))
            is not None
        )
        assert (
            len(
                session.scalars(
                    select(RecommendationGroupLeg).where(
                        RecommendationGroupLeg.group_id == persisted_group_id
                    )
                ).all()
            )
            == 3
        )
        assert (
            len(
                session.scalars(
                    select(RecommendationLeg).where(
                        RecommendationLeg.group_id == persisted_group_id
                    )
                ).all()
            )
            == 3
        )
        assert len(session.scalars(select(RecommendationSelectedLot)).all()) == 2
    engine.dispose()
