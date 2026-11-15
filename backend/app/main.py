from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.broker.etrade_oauth import EtradeOAuthService
from app.broker.fake import FakeBroker
from app.broker.protocol import ReadOnlyBroker
from app.db.migrate import upgrade_database
from app.db.models import (
    Account,
    ActivityEvent,
    CurrentQuote,
    CurrentTaxLot,
    PolicyRevision,
    Security,
    SyncState,
)
from app.db.session import create_database_engine, make_session_factory
from app.domain.allocation import (
    SecurityIdentity,
    resolve_holding,
)
from app.domain.decimal_math import (
    exact_difference,
    exact_product,
    percentage,
)
from app.domain.portfolio_accounting import evaluate_portfolio
from app.domain.trade_dates import classify_holding_period, resolve_proposed_trade_date
from app.optimizer.runtime import ProcessSupervisor
from app.schemas import (
    ActivityPageResponse,
    ErrorEnvelope,
    EtradeAuthStartResponse,
    EtradeAuthStatusResponse,
    EtradeAuthVerifyInput,
    HealthResponse,
    LotPageResponse,
    OptimizerExportJSONResponse,
    OptimizerLotReviewIntentInput,
    OptimizerRecommendationsResponse,
    OptimizerRunInput,
    OptimizerRunResponse,
    OptimizerSelectionInput,
    PolicyDraftInput,
    PolicyResponse,
    PolicyRevisionResponse,
    PortfolioResponse,
    RecommendationAnnotationInput,
    SyncResponseDTO,
    WashSalesResponse,
)
from app.services.demo_optimizer import (
    annotate_group,
    apply_lot_review_intent,
    apply_selection,
    create_demo_run,
    export_run,
    get_run,
    run_recommendations,
    run_summary,
    wash_sales,
)
from app.services.errors import AppError
from app.services.financial_input_loader import load_allocation_policy, load_financial_inputs
from app.services.optimizer_service import (
    BoundedValidationExecutor,
    annotate_real_group,
    apply_real_lot_review_intent,
    apply_real_selection,
    create_production_run,
    real_run_recommendations,
    real_run_summary,
)
from app.services.policy import (
    activate_policy,
    create_policy_draft,
    policy_to_dict,
    validate_policy_revision,
)
from app.services.portfolio_presentation import present_portfolio_evaluation
from app.services.sync import sync_portfolio

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
DEFAULT_ORIGINS = [
    "http://localhost:9000",
    "http://127.0.0.1:9000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


API_ERROR_RESPONSES = {
    status_code: {"model": ErrorEnvelope, "description": "Consistent API error envelope"}
    for status_code in (403, 404, 409, 422, 500, 502, 503)
}


EXPORT_RESPONSES = {
    **API_ERROR_RESPONSES,
    200: {
        "model": OptimizerExportJSONResponse,
        "description": "JSON document or CSV download; selected by the format query parameter",
        "content": {"text/csv": {"schema": {"type": "string"}}},
    },
}


def _error_payload(request: Request, code: str, message: str, details: object) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details,
        "correlation_id": getattr(request.state, "correlation_id", str(uuid4())),
    }


def _normalized_local_origin(value: str | None) -> tuple[str, str, int] | None:
    if not value or value != value.strip() or any(char.isspace() for char in value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname
    if (
        scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.netloc.endswith(":")
        or "?" in value
        or "#" in value
        or hostname is None
        or hostname.lower() not in LOCAL_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    normalized_port = port if port is not None else (443 if scheme == "https" else 80)
    return scheme, hostname.lower(), normalized_port


def _local_hostname(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = _normalized_local_origin(f"http://{value}")
    return parsed[1] if parsed else None


def _request_origin(request: Request) -> tuple[str, str, int] | None:
    host = request.headers.get("host")
    if not host:
        return None
    return _normalized_local_origin(f"{request.url.scheme}://{host}")


def _origin_is_allowed(origin: str, allowed_origins: list[str], request: Request) -> bool:
    normalized_origin = _normalized_local_origin(origin)
    if normalized_origin is None:
        return False
    if normalized_origin == _request_origin(request):
        return True
    return normalized_origin in {
        normalized for configured in allowed_origins if (normalized := _normalized_local_origin(configured))
    }

def _whole_share_fields(shares: Decimal) -> dict[str, Any]:
    whole = shares.to_integral_value(rounding=ROUND_DOWN)
    return {
        "whole_shares_available": str(whole),
        "fractional_shares": str(exact_difference(shares, whole)),
        "fractional_cleanup_unsupported": shares != whole,
    }






def _demo_seed(factory: sessionmaker[Session], broker: ReadOnlyBroker) -> None:
    with factory() as session:
        has_policy = session.scalar(select(PolicyRevision.id).limit(1)) is not None
        has_account = session.get(Account, 1) is not None
    if has_account and has_policy:
        return
    if not has_account:
        sync_portfolio(factory, broker, correlation_id="demo-seed")
    seed_path = Path(__file__).resolve().parent / "seeds" / "demo_policy.json"
    payload = PolicyDraftInput.model_validate(json.loads(seed_path.read_text(encoding="utf-8")))
    with factory.begin() as session:
        revision = create_policy_draft(session, payload)
        activated, errors = activate_policy(session, revision.id)
        if errors:
            raise RuntimeError(f"Packaged demo policy failed validation: {errors}")
        activated.status = "ACTIVE"


def create_app(
    database_url: str | None = None,
    broker: ReadOnlyBroker | None = None,
    *,
    engine: Engine | None = None,
    seed_demo_data: bool = False,
    publication_hook: Callable[[], None] | None = None,
    allowed_origins: list[str] | None = None,
    etrade_oauth: EtradeOAuthService | None = None,
) -> FastAPI:
    """Create an isolated app with optional test OAuth service and explicit transport injection."""
    db_url = database_url or os.getenv("PORTFOLIO_DATABASE_URL", "sqlite:///data/portfolio.sqlite3")
    cors_origins = DEFAULT_ORIGINS if allowed_origins is None else allowed_origins
    owned_engine = engine is None
    db_engine = engine or create_database_engine(db_url)
    sessions = make_session_factory(db_engine)
    broker_source = broker or FakeBroker()
    if seed_demo_data and getattr(broker_source, "mode", "") != "fake":
        raise ValueError("demo seed data is only available with FakeBroker")
    optimizer_supervisor = ProcessSupervisor(max_workers=2)
    validation_executor = BoundedValidationExecutor(max_workers=2)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            upgrade_database(db_engine)
            if seed_demo_data:
                _demo_seed(sessions, broker_source)
            yield
        finally:
            await validation_executor.aclose()
            await optimizer_supervisor.aclose()
            if etrade_oauth is not None:
                etrade_oauth.close()
            if owned_engine:
                db_engine.dispose()

    application = FastAPI(title="Portfolio Optimizer API", version="1.0.0", lifespan=lifespan)
    application.state.engine = db_engine
    application.state.session_factory = sessions
    application.state.broker = broker_source
    application.state.broker_mode = getattr(broker_source, "mode", "unavailable")
    application.state.optimizer_supervisor = optimizer_supervisor
    application.state.etrade_oauth = etrade_oauth
    application.state.optimizer_validation_executor = validation_executor

    @application.middleware("http")
    async def correlation_and_local_write_boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_id = request.headers.get("x-correlation-id", "")
        try:
            correlation_id = str(UUID(raw_id))
        except (ValueError, TypeError, AttributeError):
            correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            hostname = _local_hostname(request.headers.get("host"))
            if hostname not in LOCAL_HOSTS:
                response = JSONResponse(
                    _error_payload(request, "local_host_required", "Writes are restricted to a local Host", {}),
                    status_code=403,
                )
                response.headers["X-Correlation-ID"] = correlation_id
                return response
            origin = request.headers.get("origin")
            if origin is not None and not _origin_is_allowed(origin, cors_origins, request):
                response = JSONResponse(
                    _error_payload(request, "local_origin_required", "Writes require a configured or actual same-origin local browser Origin", {}),
                    status_code=403,
                )
                response.headers["X-Correlation-ID"] = correlation_id
                return response
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Correlation-ID"],
    )

    def db_session() -> Generator[Session]:
        with sessions() as session:
            yield session

    session_dependency = Depends(db_session)

    @application.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            _error_payload(request, exc.code, exc.message, exc.details),
            status_code=exc.status_code,
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"location": list(error.get("loc", ())), "message": error.get("msg", "Invalid request")}
            for error in exc.errors()
        ]
        return JSONResponse(
            _error_payload(request, "request_validation_error", "Request payload is invalid", details),
            status_code=422,
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        del exc
        return JSONResponse(
            _error_payload(request, "internal_error", "The request could not be completed", {}),
            status_code=500,
        )

    @application.get("/health", response_model=HealthResponse, responses=API_ERROR_RESPONSES)
    def health(session: Session = session_dependency) -> dict[str, Any]:
        ready = False
        try:
            session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            ready = True
        except Exception:  # noqa: BLE001 - health reports migration readiness without exposing DB errors
            ready = False
        return {
            "status": "ok" if ready else "not_ready",
            "schema_ready": ready,
            "broker_mode": application.state.broker_mode,
            "live_broker_enabled": False,
            "order_submission_enabled": False,
        }

    @application.post("/api/v1/portfolio/sync", response_model=SyncResponseDTO, responses=API_ERROR_RESPONSES)
    def sync_endpoint(request: Request) -> dict[str, Any]:
        return sync_portfolio(
            sessions,
            broker_source,
            correlation_id=request.state.correlation_id,
            publication_hook=publication_hook,
        )

    @application.get("/api/v1/portfolio", response_model=PortfolioResponse, responses=API_ERROR_RESPONSES)
    def portfolio(session: Session = session_dependency) -> dict[str, Any]:
        account = session.get(Account, 1)
        state = session.get(SyncState, 1)
        if account is None:
            return {
                "status": "not_synced",
                "demo": broker_source.mode == "fake",
                "account": None,
                "as_of": None,
                "cash_usd": "0",
                "portfolio_total_usd": "0",
                "positions": [],
                "coverage": state.coverage if state else {},
                "sync": _sync_status(state),
                "allocation": {"current": None, "proposed": None, "target": None},
                "us_transition": None,
            }

        active_policy = session.scalar(
            select(PolicyRevision).where(PolicyRevision.status == "ACTIVE")
        )
        proposed_trade_date = resolve_proposed_trade_date(
            None, demo=account.source.upper() in {"DEMO", "FAKE"}
        )
        inputs = load_financial_inputs(
            session,
            account,
            state,
            active_policy,
            proposed_trade_date,
            include_tax_lots=False,
            include_transactions=False,
            require_resolved_assignments=False,
        )
        positions = inputs.positions
        quotes_by_ticker = {row.ticker: row for row in inputs.quotes}

        evaluation = evaluate_portfolio(inputs, allow_unassigned_current_positions=True)
        portfolio_total = evaluation.current.portfolio_total_usd
        total_positions = exact_difference(portfolio_total, account.cash_usd)
        position_rows: list[dict[str, Any]] = []
        unresolved: list[str] = []
        for position in positions:
            quote = quotes_by_ticker.get(position.ticker)
            assignment = position.assignment
            if assignment is None:
                unresolved.append(position.ticker)
            position_rows.append(
                {
                    "ticker": position.ticker,
                    "asset_type": position.asset_type,
                    "shares": str(position.shares),
                    "market_value_usd": str(position.market_value_usd),
                    "last_price_usd": str(quote.last_usd) if quote and quote.last_usd is not None else None,
                    "quote_source": quote.source if quote else None,
                    "quote_as_of": quote.as_of if quote else None,
                    "sleeve_key": assignment.sleeve_key if assignment is not None else None,
                    "sub_sleeve_key": assignment.sub_sleeve_key if assignment is not None else None,
                }
            )

        allocation: Any = {"current": None, "proposed": None, "target": None}
        us_transition: Any = None
        if active_policy:
            presentation = present_portfolio_evaluation(
                evaluation,
                transition_label="Percentages are shown both within the US sleeve and across the whole portfolio",
            )
            allocation = presentation["allocation"]
            us_transition = presentation["us_transition"]
        return {
            "status": "ready",
            "demo": account.source.upper() in {"DEMO", "FAKE"},
            "source": account.source,
            "account": {
                "display_name": account.display_name,
                "account_type": account.account_type,
                "tax_treatment": account.tax_treatment,
            },
            "as_of": account.as_of,
            "cash_usd": str(account.cash_usd),
            "settled_buying_power_usd": str(account.settled_buying_power_usd),
            "positions_market_value_usd": str(total_positions),
            "portfolio_total_usd": str(portfolio_total),
            "position_count": len(positions),
            "positions": position_rows,
            "active_policy_revision_id": active_policy.id if active_policy else None,
            "unassigned_tickers": sorted(set(unresolved)),
            "coverage": state.coverage if state else {},
            "sync": _sync_status(state),
            "allocation": allocation,
            "us_transition": us_transition,
        }
    @application.get("/api/v1/lots", response_model=LotPageResponse, responses=API_ERROR_RESPONSES)
    def lots(
        session: Session = session_dependency,
        ticker: str | None = None,
        term: str | None = Query(default=None, pattern="^(ST|LT)$"),
        fractional: bool | None = None,
        search: str | None = Query(
            default=None,
            max_length=128,
            description="Case-insensitive substring search across ticker and broker lot ID before pagination; combines with other filters.",
        ),
        sort_by: Literal[
            "ticker",
            "broker_lot_id",
            "acquired_date",
            "remaining_shares",
            "available_shares",
            "adjusted_unit_basis_usd",
            "adjusted_total_basis_usd",
            "current_price_usd",
            "unrealized_pl_usd",
            "unrealized_pl_pct",
            "term",
            "sleeve_key",
            "sub_sleeve_key",
        ] = Query(
            default="acquired_date",
            description="Account-wide sort field; ties use ticker and broker lot ID ascending, with null values last.",
        ),
        sort_direction: Literal["asc", "desc"] = Query(default="asc"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        sync_state = session.get(SyncState, 1)
        source_generation = (
            sync_state.current_generation if sync_state is not None and sync_state.complete else None
        )
        search_text = search.strip().casefold() if search else ""
        query = select(CurrentTaxLot).where(CurrentTaxLot.account_id == 1)
        if ticker:
            security = session.scalar(select(Security).where(Security.ticker == ticker.upper()))
            if security is None:
                return {
                    "items": [],
                    "total": 0,
                    "offset": offset,
                    "limit": limit,
                    "source_generation": source_generation,
                }
            query = query.where(CurrentTaxLot.security_id == security.id)
        rows = session.scalars(query).all()
        active = session.scalar(select(PolicyRevision).where(PolicyRevision.status == "ACTIVE"))
        securities = {s.id: s for s in session.scalars(select(Security)).all()}
        quotes = {q.security_id: q for q in session.scalars(select(CurrentQuote)).all()}
        account = session.get(Account, 1)
        proposed_trade_date = resolve_proposed_trade_date(
            None,
            demo=bool(account and account.source.upper() in {"DEMO", "FAKE"}),
        )
        allocation_policy = load_allocation_policy(session, active.id) if active else None
        assignments = {
            security.id: (
                resolve_holding(
                    allocation_policy,
                    SecurityIdentity(security.ticker, security.asset_type, security.is_completion_etf),
                ).assignment
                if allocation_policy is not None
                else None
            )
            for security in securities.values()
        }
        position_lot_counts: Counter[int] = Counter(lot.security_id for lot in rows)
        filtered: list[dict[str, Any]] = []
        for lot in rows:
            security = securities[lot.security_id]
            quote = quotes.get(security.id)
            price = quote.last_usd if quote else None
            basis_total = exact_product(lot.adjusted_unit_basis_usd, lot.shares)
            unrealized = (
                exact_product(exact_difference(price, lot.adjusted_unit_basis_usd), lot.shares)
                if price is not None
                else None
            )
            sleeve = assignments.get(security.id)
            lot_term = classify_holding_period(lot.acquired_date, proposed_trade_date)
            shares = lot.shares
            available = lot.available_shares
            lot_dict = {
                "ticker": security.ticker,
                "asset_type": security.asset_type,
                "broker_lot_id": lot.broker_lot_id,
                "acquired_date": lot.acquired_date,
                "remaining_shares": str(shares),
                "available_shares": str(available),
                "adjusted_unit_basis_usd": str(lot.adjusted_unit_basis_usd),
                "adjusted_total_basis_usd": str(basis_total),
                "current_price_usd": str(price) if price is not None else None,
                "unrealized_pl_usd": str(unrealized) if unrealized is not None else None,
                "unrealized_pl_pct": _percent(unrealized, basis_total) if unrealized is not None else None,
                "source": lot.source,
                "as_of": lot.as_of,
                "term": lot_term,
                "sleeve_key": sleeve.sleeve_key if sleeve else None,
                "sub_sleeve_key": sleeve.sub_sleeve_key if sleeve else None,
                "quality_flags": lot.quality_flags,
                "small_lot_cleanup_candidate": shares < 1,
                "position_cleanup_candidate": position_lot_counts[security.id] == 1,
                **_whole_share_fields(available),
            }
            if term and lot_term != term:
                continue
            if fractional is not None and lot_dict["fractional_cleanup_unsupported"] is not fractional:
                continue
            if (
                search_text
                and search_text not in security.ticker.casefold()
                and search_text not in lot.broker_lot_id.casefold()
            ):
                continue
            filtered.append(lot_dict)
        filtered.sort(key=lambda row: (row["ticker"], row["broker_lot_id"]))
        null_rows = [row for row in filtered if row[sort_by] is None]
        sortable_rows = [row for row in filtered if row[sort_by] is not None]
        numeric_sort_fields = {
            "remaining_shares",
            "available_shares",
            "adjusted_unit_basis_usd",
            "adjusted_total_basis_usd",
            "current_price_usd",
            "unrealized_pl_usd",
            "unrealized_pl_pct",
        }
        if sort_by in numeric_sort_fields:
            sortable_rows.sort(
                key=lambda row: Decimal(str(row[sort_by])),
                reverse=sort_direction == "desc",
            )
        else:
            sortable_rows.sort(key=lambda row: row[sort_by], reverse=sort_direction == "desc")
        filtered = sortable_rows + null_rows
        total = len(filtered)
        return {
            "items": filtered[offset : offset + limit],
            "total": total,
            "offset": offset,
            "limit": limit,
            "source_generation": source_generation,
        }

    @application.get("/api/v1/policy", response_model=PolicyResponse, response_model_exclude_unset=True, responses=API_ERROR_RESPONSES)
    def policy(session: Session = session_dependency) -> dict[str, Any]:
        revisions = session.scalars(
            select(PolicyRevision).order_by(PolicyRevision.revision_number.desc())
        ).all()
        serialized = {r.id: policy_to_dict(session, r) for r in revisions}
        for revision in revisions:
            if revision.status == "DRAFT":
                serialized[revision.id]["activation_errors"] = validate_policy_revision(session, revision)
        return {
            "active": next((serialized[r.id] for r in revisions if r.status == "ACTIVE"), None),
            "drafts": [serialized[r.id] for r in revisions if r.status == "DRAFT"],
            "superseded": [serialized[r.id] for r in revisions if r.status == "SUPERSEDED"],
        }

    @application.post("/api/v1/policy/drafts", status_code=201, response_model=PolicyRevisionResponse, response_model_exclude_unset=True, responses=API_ERROR_RESPONSES)
    def save_policy_draft(payload: PolicyDraftInput, session: Session = session_dependency) -> dict[str, Any]:
        with session.begin():
            revision = create_policy_draft(session, payload)
            result = policy_to_dict(session, revision)
            result["activation_errors"] = validate_policy_revision(session, revision)
        return result

    @application.post("/api/v1/policy/{revision_id}/activate", response_model=PolicyRevisionResponse, response_model_exclude_unset=True, responses=API_ERROR_RESPONSES)
    def activate_policy_endpoint(
        revision_id: str,
        request: Request,
        session: Session = session_dependency,
    ) -> dict[str, Any]:
        with session.begin():
            revision, errors = activate_policy(session, revision_id)
            if errors:
                raise AppError(
                    "policy_invalid",
                    "Policy draft cannot be activated until validation succeeds",
                    status_code=422,
                    details=errors,
                )
            session.add(
                ActivityEvent(
                    id=str(uuid4()),
                    created_at=datetime.now(UTC),
                    event_type="policy_activation",
                    status="complete",
                    correlation_id=request.state.correlation_id,
                    details={"revision_number": revision.revision_number},
                )
            )
            return policy_to_dict(session, revision)

    @application.get("/api/v1/activity", response_model=ActivityPageResponse, responses=API_ERROR_RESPONSES)
    def activity(
        session: Session = session_dependency,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
        event_type: str | None = Query(default=None, max_length=48),
        status: str | None = Query(default=None, max_length=24),
        correlation_id: str | None = Query(default=None, max_length=64),
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        query = select(ActivityEvent)
        if event_type:
            query = query.where(ActivityEvent.event_type == event_type)
        if status:
            query = query.where(ActivityEvent.status == status)
        if correlation_id:
            query = query.where(ActivityEvent.correlation_id == correlation_id)
        if since:
            query = query.where(ActivityEvent.created_at >= since)
        if until:
            query = query.where(ActivityEvent.created_at <= until)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        events = session.scalars(
            query.order_by(ActivityEvent.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return {
            "items": [
                {
                    "id": event.id,
                    "created_at": event.created_at,
                    "event_type": event.event_type,
                    "status": event.status,
                    "correlation_id": event.correlation_id,
                    "details": event.details,
                }
                for event in events
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @application.post("/api/v1/optimizer/runs", status_code=201, response_model=OptimizerRecommendationsResponse, responses=API_ERROR_RESPONSES)
    async def create_optimizer_run(
        payload: OptimizerRunInput,
        request: Request,
        session: Session = session_dependency,
    ) -> dict[str, Any]:
        if payload.mode == "real_optimizer":
            run = await create_production_run(
                session,
                payload,
                request.app.state.optimizer_supervisor,
                request.app.state.optimizer_validation_executor,
                correlation_id=request.state.correlation_id,
            )
            return real_run_recommendations(session, get_run(session, run.id))
        with session.begin():
            run = create_demo_run(
                session,
                payload,
                broker_mode=request.app.state.broker_mode,
                correlation_id=request.state.correlation_id,
            )
            return run_recommendations(session, run)

    @application.get("/api/v1/optimizer/runs/{run_id}", response_model=OptimizerRunResponse, responses=API_ERROR_RESPONSES)
    def optimizer_run_detail(run_id: str, session: Session = session_dependency) -> dict[str, Any]:
        run = get_run(session, run_id)
        if run.frozen_input_bundle.get("mode") != "real_optimizer":
            return run_summary(run, session=session)
        return real_run_summary(run, session)

    @application.get("/api/v1/optimizer/runs/{run_id}/recommendations", response_model=OptimizerRecommendationsResponse, responses=API_ERROR_RESPONSES)
    def optimizer_run_recommendations(run_id: str, session: Session = session_dependency) -> dict[str, Any]:
        run = get_run(session, run_id)
        if run.frozen_input_bundle.get("mode") != "real_optimizer":
            return run_recommendations(session, run)
        return real_run_recommendations(session, run)

    @application.post("/api/v1/optimizer/runs/{run_id}/selection", response_model=OptimizerRecommendationsResponse, responses=API_ERROR_RESPONSES)
    async def optimizer_run_selection(
        run_id: str,
        payload: OptimizerSelectionInput,
        request: Request,
        session: Session = session_dependency,
    ) -> dict[str, Any]:
        with session.begin():
            run = get_run(session, run_id)
            is_demo = run.frozen_input_bundle.get("mode") != "real_optimizer"
        if is_demo:
            with session.begin():
                run = apply_selection(session, run_id, payload, correlation_id=request.state.correlation_id)
                return run_recommendations(session, run)
        run = await apply_real_selection(
            session,
            run_id,
            payload,
            request.app.state.optimizer_supervisor,
            request.app.state.optimizer_validation_executor,
            correlation_id=request.state.correlation_id,
        )
        return real_run_recommendations(session, get_run(session, run.id))

    @application.post(
        "/api/v1/optimizer/runs/{run_id}/lot-review-intent",
        response_model=OptimizerRecommendationsResponse,
        responses=API_ERROR_RESPONSES,
        description=(
            "Atomically replace the confirmed DEMO or real optimizer basket with the requested broker lots. "
            "The source generation must match; requests are rejected without mutation when unsupported "
            "or infeasible. This request does not approve or place orders."
        ),
    )
    async def optimizer_run_lot_review_intent(
        run_id: str,
        payload: OptimizerLotReviewIntentInput,
        request: Request,
        session: Session = session_dependency,
    ) -> dict[str, Any]:
        with session.begin():
            run = get_run(session, run_id)
            is_demo = run.frozen_input_bundle.get("mode") != "real_optimizer"
        if is_demo:
            with session.begin():
                run = apply_lot_review_intent(
                    session,
                    run_id,
                    payload,
                    correlation_id=request.state.correlation_id,
                )
                return run_recommendations(session, run)
        run = await apply_real_lot_review_intent(
            session,
            run_id,
            payload,
            request.app.state.optimizer_supervisor,
            request.app.state.optimizer_validation_executor,
            correlation_id=request.state.correlation_id,
        )
        return real_run_recommendations(session, get_run(session, run.id))

    @application.patch("/api/v1/optimizer/runs/{run_id}/recommendations/{group_id}", response_model=OptimizerRecommendationsResponse, responses=API_ERROR_RESPONSES)
    async def annotate_recommendation_group(
        run_id: str,
        group_id: str,
        payload: RecommendationAnnotationInput,
        request: Request,
        session: Session = session_dependency,
    ) -> dict[str, Any]:
        with session.begin():
            run = get_run(session, run_id)
            is_demo = run.frozen_input_bundle.get("mode") != "real_optimizer"
        if is_demo:
            with session.begin():
                run = annotate_group(
                    session,
                    run_id,
                    group_id,
                    payload,
                    correlation_id=request.state.correlation_id,
                )
                return run_recommendations(session, run)
        run = await annotate_real_group(
            session,
            run_id,
            group_id,
            payload,
            request.app.state.optimizer_supervisor,
            request.app.state.optimizer_validation_executor,
            correlation_id=request.state.correlation_id,
        )
        return real_run_recommendations(session, get_run(session, run.id))

    @application.get("/api/v1/optimizer/runs/{run_id}/export", response_model=None, responses=EXPORT_RESPONSES)
    def export_optimizer_run(
        run_id: str,
        format: str = Query(default="json", pattern="^(json|csv)$"),
        session: Session = session_dependency,
    ) -> Response:
        run = get_run(session, run_id)
        media_type, content = export_run(session, run, format)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="optimizer-run-{run.id}.{format}"'},
        )

    @application.get("/api/v1/wash-sales", response_model=WashSalesResponse, responses=API_ERROR_RESPONSES)
    def wash_sales_endpoint(session: Session = session_dependency) -> dict[str, Any]:
        return wash_sales(session)

    @application.get(
        "/api/v1/auth/etrade/status",
        response_model=EtradeAuthStatusResponse,
        responses=API_ERROR_RESPONSES,
    )
    def etrade_auth_status() -> dict[str, Any]:
        if etrade_oauth is not None:
            return etrade_oauth.status()
        return {
            "status": "disabled",
            "available": False,
            "authenticated": False,
            "account_id_key": None,
            "phase": 3,
            "message": "E*TRADE OAuth is disabled; no broker connection was attempted.",
        }

    @application.post(
        "/api/v1/auth/etrade/start",
        response_model=EtradeAuthStartResponse,
        responses=API_ERROR_RESPONSES,
    )
    def etrade_auth_start() -> dict[str, str]:
        if etrade_oauth is None:
            raise AppError(
                "etrade_auth_unavailable",
                "E*TRADE OAuth is disabled; no broker connection was attempted.",
                status_code=503,
                details={"available": False, "phase": 3},
            )
        return etrade_oauth.start()

    @application.post(
        "/api/v1/auth/etrade/verify",
        response_model=EtradeAuthStatusResponse,
        responses=API_ERROR_RESPONSES,
    )
    def etrade_auth_verify(body: EtradeAuthVerifyInput) -> dict[str, object]:
        if etrade_oauth is None:
            raise AppError(
                "etrade_auth_unavailable",
                "E*TRADE OAuth is disabled; no broker connection was attempted.",
                status_code=503,
                details={"available": False, "phase": 3},
            )
        return etrade_oauth.verify(body.verifier)

    @application.post("/api/v1/orders/{leg_id}/preview", status_code=503, response_model=ErrorEnvelope, responses=API_ERROR_RESPONSES)
    def disabled_order_preview(leg_id: str) -> None:
        del leg_id
        raise AppError(
            "order_workflow_unavailable",
            "Order preview is disabled until the final implementation phase",
            status_code=503,
            details={"available": False, "actionable": False, "phase": 5},
        )

    @application.post("/api/v1/orders/{leg_id}/submit", status_code=503, response_model=ErrorEnvelope, responses=API_ERROR_RESPONSES)
    def disabled_order_submit(leg_id: str) -> None:
        del leg_id
        raise AppError(
            "order_workflow_unavailable",
            "Order submission is disabled until the final implementation phase",
            status_code=503,
            details={"available": False, "actionable": False, "phase": 5},
        )

    return application


def _percent(value: Decimal | None, denominator: Decimal) -> str | None:
    if value is None:
        return None
    return str(percentage(value, denominator))


def _sync_status(state: SyncState | None) -> dict[str, Any]:
    if state is None:
        return {
            "generation": 0,
            "complete": False,
            "started_at": None,
            "completed_at": None,
            "last_error_code": None,
            "last_error_summary": None,
        }
    return {
        "generation": state.current_generation,
        "complete": state.complete,
        "started_at": state.started_at,
        "completed_at": state.completed_at,
        "last_error_code": state.last_error_code,
        "last_error_summary": state.last_error_summary,
    }


app = create_app(seed_demo_data=os.getenv("PORTFOLIO_DEMO_SEED") == "1")
