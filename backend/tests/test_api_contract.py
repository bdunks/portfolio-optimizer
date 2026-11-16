from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from app.broker.fake import FakeBroker
from app.main import app as default_app
from app.main import create_app
from app.schemas import (
    ActivityPageResponse,
    EtradeAuthStatusResponse,
    HealthResponse,
    LotPageResponse,
    LotResponse,
    OptimizerExportJSONResponse,
    OptimizerLotReviewIntentInput,
    OptimizerRecommendationsResponse,
    OptimizerRunInput,
    OptimizerRunResponse,
    PolicyResponse,
    PolicyRevisionResponse,
    PolicySettingsInput,
    PortfolioReadyResponse,
    PortfolioResponse,
    SyncResponseDTO,
    WashSalesResponse,
)


@pytest.fixture
def seeded_contract_client(tmp_path: Path) -> Iterator[tuple[FastAPI, TestClient]]:
    application = create_app(
        database_url=f"sqlite:///{tmp_path / 'contract.sqlite3'}",
        broker=FakeBroker(),
        seed_demo_data=True,
    )
    with TestClient(application, base_url="http://localhost") as client:
        yield application, client


def _response_schema(response: dict[str, object]) -> dict[str, object]:
    content = response.get("content")
    assert isinstance(content, dict)
    assert "application/json" in content
    json_content = content["application/json"]
    assert isinstance(json_content, dict)
    schema = json_content.get("schema")
    assert isinstance(schema, dict)
    return schema


def _schema_ref(schema: dict[str, object]) -> str:
    reference = schema.get("$ref")
    assert isinstance(reference, str)
    return reference


def test_openapi_has_named_phase_one_success_and_error_models() -> None:
    specification = default_app.openapi()
    schemas = specification["components"]["schemas"]
    for path, path_item in specification["paths"].items():
        if path != "/health" and not path.startswith("/api/v1/"):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "post", "patch"}:
                continue
            for status_code, response in operation["responses"].items():
                if int(status_code) < 400:
                    continue
                schema = _response_schema(response)
                assert _schema_ref(schema).endswith("/ErrorEnvelope"), (
                    path,
                    status_code,
                    schema,
                )
            if path == "/api/v1/optimizer/runs/{run_id}/export":
                export_response = operation["responses"]["200"]
                assert set(export_response["content"]) == {"application/json", "text/csv"}
                assert _schema_ref(_response_schema(export_response)).endswith(
                    "/OptimizerExportJSONResponse"
                )
                assert export_response["content"]["text/csv"]["schema"]["type"] == "string"
                continue
            success_status = next(
                (status for status in operation["responses"] if 200 <= int(status) < 300), None
            )
            if success_status is None:
                continue
            success_schema = _response_schema(operation["responses"][success_status])
            branches = success_schema.get("anyOf", success_schema.get("oneOf", [success_schema]))
            assert isinstance(branches, list)
            references = [
                _schema_ref(branch).rsplit("/", 1)[-1]
                for branch in branches
                if isinstance(branch, dict)
            ]
            assert references, (path, success_schema)
            assert all(name in schemas for name in references), (path, success_schema)
            if success_schema.get("type") == "object":
                assert success_schema.get("properties")

    lots_operation = specification["paths"]["/api/v1/lots"]["get"]
    lot_parameters = {parameter["name"]: parameter for parameter in lots_operation["parameters"]}
    assert any(
        branch.get("type") == "string" and branch.get("maxLength") == 128
        for branch in lot_parameters["search"]["schema"]["anyOf"]
    )
    assert lot_parameters["sort_by"]["schema"]["enum"] == [
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
    ]
    assert lot_parameters["sort_direction"]["schema"]["enum"] == ["asc", "desc"]
    lot_intent = specification["paths"]["/api/v1/optimizer/runs/{run_id}/lot-review-intent"]["post"]
    intent_schema = lot_intent["requestBody"]["content"]["application/json"]["schema"]
    assert _schema_ref(intent_schema).endswith("/OptimizerLotReviewIntentInput")
    assert "does not approve or place orders" in lot_intent["description"]
    parsed_intent = OptimizerLotReviewIntentInput.model_validate(
        {"source_generation": 1, "broker_lot_ids": ["LOT-1"]}
    )
    assert parsed_intent.source_generation == 1
    exact_identity = OptimizerLotReviewIntentInput.model_validate(
        {"source_generation": 1, "broker_lot_ids": [" LOT-1 "]}
    )
    assert exact_identity.broker_lot_ids == [" LOT-1 "]
    with pytest.raises(ValidationError):
        OptimizerLotReviewIntentInput.model_validate(
            {"source_generation": 1, "broker_lot_ids": ["LOT-1", "LOT-1"]}
        )
    with pytest.raises(ValidationError):
        OptimizerLotReviewIntentInput.model_validate(
            {"source_generation": True, "broker_lot_ids": list[str]()}
        )

    disabled = specification["paths"]["/api/v1/orders/{leg_id}/preview"]["post"]["responses"]
    assert "503" in disabled
    assert "200" not in disabled
    disabled_schema = _response_schema(disabled["503"])
    assert _schema_ref(disabled_schema).endswith("/ErrorEnvelope")
    exact_decimal = schemas["PolicySettingsInput"]["properties"]["target_retained_net_loss_usd"]
    assert exact_decimal["type"] == "string"


def test_lot_response_preserves_the_exact_broker_lot_id() -> None:
    lot = LotResponse.model_validate(
        {
            "ticker": "ABC",
            "asset_type": "EQUITY",
            "broker_lot_id": " LOT-1 ",
            "acquired_date": "2025-01-01",
            "remaining_shares": "1",
            "available_shares": "1",
            "adjusted_unit_basis_usd": "10.00",
            "adjusted_total_basis_usd": "10.00",
            "current_price_usd": None,
            "unrealized_pl_usd": None,
            "unrealized_pl_pct": None,
            "source": "DEMO",
            "as_of": "2026-11-05T00:00:00Z",
            "term": "ST",
            "sleeve_key": None,
            "sub_sleeve_key": None,
            "quality_flags": [],
            "small_lot_cleanup_candidate": False,
            "position_cleanup_candidate": True,
            "whole_shares_available": "1",
            "fractional_shares": "0",
            "fractional_cleanup_unsupported": False,
        }
    )
    assert lot.broker_lot_id == " LOT-1 "


def test_unseeded_and_seeded_response_dtos_validate(
    tmp_path: Path, seeded_contract_client: tuple[FastAPI, TestClient]
) -> None:
    unseeded = create_app(
        database_url=f"sqlite:///{tmp_path / 'unseeded.sqlite3'}", broker=FakeBroker()
    )
    with TestClient(unseeded, base_url="http://localhost") as client:
        assert (
            TypeAdapter(PortfolioResponse)
            .validate_python(client.get("/api/v1/portfolio").json())
            .status
            == "not_synced"
        )
        assert PolicyResponse.model_validate(client.get("/api/v1/policy").json()).active is None
        LotPageResponse.model_validate(client.get("/api/v1/lots").json())
        ActivityPageResponse.model_validate(client.get("/api/v1/activity").json())
        HealthResponse.model_validate(client.get("/health").json())
        EtradeAuthStatusResponse.model_validate(client.get("/api/v1/auth/etrade/status").json())
        sync = client.post("/api/v1/portfolio/sync")
        assert SyncResponseDTO.model_validate(sync.json()).demo is True
        ready = PortfolioReadyResponse.model_validate(client.get("/api/v1/portfolio").json())
        assert ready.active_policy_revision_id is None
    unseeded.state.engine.dispose()

    _, client = seeded_contract_client
    portfolio = PortfolioReadyResponse.model_validate(client.get("/api/v1/portfolio").json())
    assert portfolio.demo is True
    LotPageResponse.model_validate(client.get("/api/v1/lots").json())
    PolicyResponse.model_validate(client.get("/api/v1/policy").json())
    WashSalesResponse.model_validate(client.get("/api/v1/wash-sales").json())
    ActivityPageResponse.model_validate(client.get("/api/v1/activity").json())

    run_response = client.post("/api/v1/optimizer/runs", json=dict[str, object]())
    run = OptimizerRecommendationsResponse.model_validate(run_response.json())
    assert run.demo is True
    assert run.actionable is False
    recommendations = client.get(f"/api/v1/optimizer/runs/{run.run_id}/recommendations").json()
    typed_recommendations = OptimizerRecommendationsResponse.model_validate(recommendations)
    leg_ids = [leg.leg_id for leg in typed_recommendations.consolidated_legs]
    assert len(leg_ids) == len(set(leg_ids))
    known_legs = set(leg_ids)
    for group in typed_recommendations.groups:
        assert set(group.leg_ids) <= known_legs
    OptimizerRunResponse.model_validate(client.get(f"/api/v1/optimizer/runs/{run.run_id}").json())
    selection = client.post(
        f"/api/v1/optimizer/runs/{run.run_id}/selection", json=dict[str, object]()
    )
    OptimizerRecommendationsResponse.model_validate(selection.json())
    exported = client.get(f"/api/v1/optimizer/runs/{run.run_id}/export?format=json")
    OptimizerExportJSONResponse.model_validate(exported.json())
    assert (
        client.get(f"/api/v1/optimizer/runs/{run.run_id}/export?format=csv")
        .headers["content-type"]
        .startswith("text/csv")
    )

    active = client.get("/api/v1/policy").json()["active"]
    draft_payload = {
        "source_revision_id": active["id"],
        "settings": active["settings"],
        "sleeves": active["sleeves"],
        "allowed_securities": active["allowed_securities"],
        "overrides": active["overrides"],
        "reassignments": dict[str, str](),
    }
    draft = client.post("/api/v1/policy/drafts", json=draft_payload)
    PolicyRevisionResponse.model_validate(draft.json())


def test_exact_decimal_openapi_input_and_runtime_float_rejection() -> None:
    assert (
        PolicySettingsInput.model_json_schema(mode="validation")["properties"][
            "target_retained_net_loss_usd"
        ]["type"]
        == "string"
    )
    with pytest.raises(ValidationError, match="exact strings or integers"):
        PolicySettingsInput(target_retained_net_loss_usd=12.5)
    assert OptimizerRunInput.model_validate(dict[str, object]()).mode == "recommendations_only"


def test_errors_are_consistently_serialized_and_future_routes_fail_closed(
    seeded_contract_client: tuple[FastAPI, TestClient],
) -> None:
    _, client = seeded_contract_client
    invalid = client.post("/api/v1/optimizer/runs", json={"mode": "not-a-mode"})
    assert invalid.status_code == 422
    assert set(invalid.json()) == {"code", "message", "details", "correlation_id"}
    for route, payload in (
        ("/api/v1/auth/etrade/start", None),
        ("/api/v1/auth/etrade/verify", {"verifier": "12345"}),
        ("/api/v1/orders/demo-leg/preview", None),
        ("/api/v1/orders/demo-leg/submit", None),
    ):
        response = client.post(route, json=payload) if payload is not None else client.post(route)
        assert response.status_code == 503
        assert set(response.json()) == {"code", "message", "details", "correlation_id"}


def test_checked_in_contract_artifacts_are_current() -> None:
    backend = Path(__file__).resolve().parents[1]
    checked = subprocess.run(
        [sys.executable, "scripts/generate_api_contract.py", "--check"],
        cwd=backend,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
