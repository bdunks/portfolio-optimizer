"""Adapt shared account evaluations to the existing portfolio and demo response shapes."""

from __future__ import annotations

from app.domain.portfolio_accounting import PortfolioEvaluation, TransitionSnapshot


def _snapshot_view(evaluation: PortfolioEvaluation, *, proposed: bool = False) -> dict[str, object]:
    state = evaluation.proposed if proposed else evaluation.current
    return {
        "total_portfolio_usd": str(state.portfolio_total_usd),
        "sleeve_weights_pct": {key: str(value) for key, value in state.sleeve_weights_pct},
    }


def _transition_snapshot_view(state: TransitionSnapshot) -> dict[str, object]:
    return {
        "us_sleeve_value_usd": str(state.us_sleeve_value_usd),
        "us_sleeve_whole_portfolio_pct": str(state.us_sleeve_whole_portfolio_pct),
        "etf_progress_pct": str(state.etf_progress_pct)
        if state.etf_progress_pct is not None
        else None,
        "children": {
            key: {
                "value_usd": str(child.value_usd),
                "within_us_sleeve_pct": str(child.within_us_sleeve_pct),
                "whole_portfolio_pct": str(child.whole_portfolio_pct),
            }
            for key, child in state.children
        },
    }


def present_portfolio_evaluation(
    evaluation: PortfolioEvaluation, *, transition_label: str
) -> dict[str, object]:
    """Serialize allocation and transition values without redoing financial calculations."""
    target_weights = {
        key: str(value) for key, value in evaluation.allocation.target.top_level_sleeve_weights_pct
    }
    allocation: dict[str, object] = {
        "current": _snapshot_view(evaluation),
        "proposed": _snapshot_view(evaluation, proposed=True),
        "target": {"sleeve_weights_pct": target_weights},
    }
    transition = evaluation.transition
    if transition is None:
        transition_view: dict[str, object] | None = None
    else:
        transition_view = {
            "sleeve_key": transition.sleeve_key,
            "transition_destination_sleeve_key": transition.destination_sleeve_key,
            "label": transition_label,
            "current": _transition_snapshot_view(transition.current),
            "proposed_basket": _transition_snapshot_view(transition.proposed_basket),
            "target": {
                "us_sleeve_whole_portfolio_pct": str(
                    transition.target.us_sleeve_whole_portfolio_pct
                ),
                "children": {
                    key: {
                        "within_us_sleeve_pct": str(child.within_us_sleeve_pct),
                        "whole_portfolio_pct": str(child.whole_portfolio_pct),
                    }
                    for key, child in transition.target.children
                },
            },
        }
    return {"allocation": allocation, "us_transition": transition_view}
