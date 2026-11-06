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
    OptimizerExportJSONResponse,
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
                assert schema.get("$ref", "").endswith("/ErrorEnvelope"), (path, status_code, schema)
            if path == "/api/v1/optimizer/runs/{run_id}/export":
                export_response = operation["responses"]["200"]
                assert set(export_response["content"]) == {"application/json", "text/csv"}
                assert _response_schema(export_response)["$ref"].endswith("/OptimizerExportJSONResponse")
                assert export_response["content"]["text/csv"]["schema"]["type"] == "string"
                continue
            success_status = next((status for status in operation["responses"] if 200 <= int(status) < 300), None)
            if success_status is None:
                continue
            success_schema = _response_schema(operation["responses"][success_status])
            references = [
                branch.get("$ref", "").rsplit("/", 1)[-1]
                for branch in success_schema.get("anyOf", success_schema.get("oneOf", [success_schema]))
                if isinstance(branch, dict)
            ]
            assert references, (path, success_schema)
            assert all(name in schemas for name in references), (path, success_schema)
            if success_schema.get("type") == "object":
                assert success_schema.get("properties")

    disabled = specification["paths"]["/api/v1/orders/{leg_id}/preview"]["post"]["responses"]
    assert "503" in disabled
    assert "200" not in disabled
    disabled_schema = _response_schema(disabled["503"])
    assert disabled_schema["$ref"].endswith("/ErrorEnvelope")
    exact_decimal = schemas["PolicySettingsInput"]["properties"]["target_retained_net_loss_usd"]
    assert exact_decimal["type"] == "string"


def test_unseeded_and_seeded_response_dtos_validate(
    tmp_path: Path, seeded_contract_client: tuple[FastAPI, TestClient]
) -> None:
    unseeded = create_app(database_url=f"sqlite:///{tmp_path / 'unseeded.sqlite3'}", broker=FakeBroker())
    with TestClient(unseeded, base_url="http://localhost") as client:
        assert TypeAdapter(PortfolioResponse).validate_python(client.get("/api/v1/portfolio").json()).status == "not_synced"
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

    run_response = client.post("/api/v1/optimizer/runs", json={})
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
    selection = client.post(f"/api/v1/optimizer/runs/{run.run_id}/selection", json={})
    OptimizerRecommendationsResponse.model_validate(selection.json())
    exported = client.get(f"/api/v1/optimizer/runs/{run.run_id}/export?format=json")
    OptimizerExportJSONResponse.model_validate(exported.json())
    assert client.get(f"/api/v1/optimizer/runs/{run.run_id}/export?format=csv").headers[
        "content-type"
    ].startswith("text/csv")

    active = client.get("/api/v1/policy").json()["active"]
    draft_payload = {
        "source_revision_id": active["id"],
        "settings": active["settings"],
        "sleeves": active["sleeves"],
        "allowed_securities": active["allowed_securities"],
        "overrides": active["overrides"],
        "reassignments": {},
    }
    draft = client.post("/api/v1/policy/drafts", json=draft_payload)
    PolicyRevisionResponse.model_validate(draft.json())


def test_exact_decimal_openapi_input_and_runtime_float_rejection() -> None:
    assert PolicySettingsInput.model_json_schema(mode="validation")["properties"][
        "target_retained_net_loss_usd"
    ]["type"] == "string"
    with pytest.raises(ValidationError, match="exact strings or integers"):
        PolicySettingsInput(target_retained_net_loss_usd=12.5)
    assert OptimizerRunInput.model_validate({}).mode == "recommendations_only"


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
