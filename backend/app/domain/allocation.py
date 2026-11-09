from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from decimal import Decimal

from app.domain.decimal_math import exact_sum, percentage


@dataclass(frozen=True, slots=True)
class AllocationSleeve:
    key: str
    parent_key: str | None
    enabled: bool
    direct_index_container: bool = False
    direct_index_sleeve: bool = False
    transition_destination: bool = False
    cash_sleeve: bool = False
    display_name: str = ""
    sort_order: int = 0
    target_pct: Decimal | None = None
    drift_band_pp: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AllowedSecurity:
    ticker: str
    sleeve_key: str
    sub_sleeve_key: str | None
    priority: int
    enabled: bool
    replacement_set_id: str = "default"
    exposure_suitability: str | None = None


@dataclass(frozen=True, slots=True)
class SecurityOverride:
    ticker: str
    sleeve_key: str
    sub_sleeve_key: str | None


@dataclass(frozen=True, slots=True)
class AllocationPolicy:
    sleeves: tuple[AllocationSleeve, ...]
    allowed_securities: tuple[AllowedSecurity, ...]
    overrides: tuple[SecurityOverride, ...]


@dataclass(frozen=True, slots=True)
class TransitionDestinationResolution:
    container: AllocationSleeve | None
    destination: AllocationSleeve | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class TransitionProgress:
    container_key: str | None
    destination_sleeve_key: str | None
    progress_pct: Decimal | None

@dataclass(frozen=True, slots=True)
class SecurityIdentity:
    ticker: str
    asset_type: str
    is_completion_etf: bool = False


@dataclass(frozen=True, slots=True)
class SleeveAssignment:
    sleeve_key: str
    sub_sleeve_key: str | None = None


@dataclass(frozen=True, slots=True)
class AssignmentResolution:
    assignment: SleeveAssignment | None
    source: str | None
    reason: str | None

    @property
    def resolved(self) -> bool:
        return self.assignment is not None


def assignment_path(
    policy: AllocationPolicy, sleeve_key: str, sub_sleeve_key: str | None = None
) -> tuple[str, ...] | None:
    """Return an enabled root-to-leaf path, rejecting missing, disabled, and cyclic ancestry."""
    sleeves_by_key = {sleeve.key: sleeve for sleeve in policy.sleeves}
    leaf = sub_sleeve_key or sleeve_key
    path: list[str] = []
    seen: set[str] = set()
    current: str | None = leaf
    while current is not None:
        sleeve = sleeves_by_key.get(current)
        if current in seen or sleeve is None or not sleeve.enabled:
            return None
        seen.add(current)
        path.append(current)
        current = sleeve.parent_key
    path.reverse()
    if sub_sleeve_key and (
        sleeve_key not in path or path.index(sub_sleeve_key) != path.index(sleeve_key) + 1
    ):
        return None
    return tuple(path)


def accumulate_sleeve_value(
    values: MutableMapping[str, Decimal], path: tuple[str, ...], amount: Decimal
) -> None:
    """Add a holding or trade amount once to each enabled sleeve ancestor."""
    for key in path:
        values[key] = exact_sum((values.get(key, Decimal(0)), amount))


def resolve_transition_destination(policy: AllocationPolicy) -> TransitionDestinationResolution:
    """Resolve the explicitly designated transition subtree, without asset-type inference."""
    enabled = [sleeve for sleeve in policy.sleeves if sleeve.enabled]
    containers = [sleeve for sleeve in enabled if sleeve.direct_index_container]
    destinations = [sleeve for sleeve in enabled if sleeve.transition_destination]
    if len(destinations) > 1:
        return TransitionDestinationResolution(None, None, "multiple_transition_destinations")
    if not destinations:
        return TransitionDestinationResolution(containers[0] if len(containers) == 1 else None, None, None)
    if len(containers) != 1:
        return TransitionDestinationResolution(
            None, destinations[0], "transition_destination_requires_unique_direct_index_container"
        )

    container = containers[0]
    destination = destinations[0]
    container_path = assignment_path(policy, container.key)
    destination_path = assignment_path(policy, destination.key)
    if container_path is None:
        return TransitionDestinationResolution(
            container, destination, "transition_destination_has_invalid_container_ancestry"
        )
    if (
        destination.key == container.key
        or destination_path is None
        or container.key not in destination_path
    ):
        return TransitionDestinationResolution(
            container, destination, "transition_destination_outside_direct_index_container"
        )

    for legacy_root in (sleeve for sleeve in enabled if sleeve.direct_index_sleeve):
        legacy_path = assignment_path(policy, legacy_root.key)
        if legacy_path is None or container.key not in legacy_path:
            continue
        if legacy_root.key in destination_path or destination.key in legacy_path:
            return TransitionDestinationResolution(
                container, destination, "transition_destination_overlaps_direct_index_branch"
            )
    return TransitionDestinationResolution(container, destination, None)


def transition_progress(
    policy: AllocationPolicy, sleeve_values: Mapping[str, Decimal]
) -> TransitionProgress:
    """Compute destination-subtree value as a percentage of the direct-index container."""
    resolution = resolve_transition_destination(policy)
    if resolution.reason is not None:
        raise ValueError(resolution.reason)
    if resolution.container is None or resolution.destination is None:
        return TransitionProgress(
            resolution.container.key if resolution.container is not None else None, None, None
        )
    return TransitionProgress(
        resolution.container.key,
        resolution.destination.key,
        percentage(
            sleeve_values.get(resolution.destination.key, Decimal(0)),
            sleeve_values.get(resolution.container.key, Decimal(0)),
        ),
    )


def _validated_assignment(
    policy: AllocationPolicy, sleeve_key: str, sub_sleeve_key: str | None, source: str
) -> AssignmentResolution:
    if assignment_path(policy, sleeve_key, sub_sleeve_key) is None:
        return AssignmentResolution(None, source, "assignment_target_missing_disabled_or_invalid_ancestry")
    return AssignmentResolution(SleeveAssignment(sleeve_key, sub_sleeve_key), source, None)


def resolve_holding(policy: AllocationPolicy, security: SecurityIdentity) -> AssignmentResolution:
    """Pure, deterministic override > enabled allowed candidate > direct-index default resolver."""
    overrides = [row for row in policy.overrides if row.ticker == security.ticker]
    if len(overrides) > 1:
        return AssignmentResolution(None, "override", "ambiguous_security_override")
    if overrides:
        row = overrides[0]
        return _validated_assignment(policy, row.sleeve_key, row.sub_sleeve_key, "override")

    allowed = [
        row for row in policy.allowed_securities if row.ticker == security.ticker and row.enabled
    ]
    if allowed:
        best_priority = min(row.priority for row in allowed)
        preferred = [row for row in allowed if row.priority == best_priority]
        destinations = {(row.sleeve_key, row.sub_sleeve_key) for row in preferred}
        if len(destinations) != 1:
            return AssignmentResolution(None, "allowed_security", "ambiguous_allowed_security_destination")
        sleeve_key, sub_sleeve_key = next(iter(destinations))
        return _validated_assignment(policy, sleeve_key, sub_sleeve_key, "allowed_security")

    if security.asset_type == "EQUITY" or (
        security.is_completion_etf and security.ticker in {"VB", "VXF"}
    ):
        containers = [
            sleeve
            for sleeve in policy.sleeves
            if sleeve.enabled and sleeve.direct_index_container
        ]
        if len(containers) != 1:
            reason = "direct_index_container_missing" if not containers else "ambiguous_direct_index_container"
            return AssignmentResolution(None, "direct_index_default", reason)
        container = containers[0]
        if assignment_path(policy, container.key) is None:
            return AssignmentResolution(
                None, "direct_index_default", "direct_index_container_has_invalid_ancestry"
            )
        children = [
            sleeve
            for sleeve in policy.sleeves
            if sleeve.enabled
            and sleeve.parent_key == container.key
            and sleeve.direct_index_sleeve
        ]
        if len(children) > 1:
            return AssignmentResolution(
                None, "direct_index_default", "ambiguous_direct_index_sleeve"
            )
        child_key = children[0].key if children else None
        return _validated_assignment(policy, container.key, child_key, "direct_index_default")

    return AssignmentResolution(None, None, "no_policy_assignment")


def resolve_cash(policy: AllocationPolicy) -> AssignmentResolution:
    """Resolve configured cash explicitly; an absent cash sleeve is a valid unallocated state."""
    cash_sleeves = [
        sleeve for sleeve in policy.sleeves if sleeve.enabled and sleeve.cash_sleeve
    ]
    if not cash_sleeves:
        return AssignmentResolution(None, "cash", "cash_sleeve_not_configured")
    if len(cash_sleeves) > 1:
        return AssignmentResolution(None, "cash", "ambiguous_cash_sleeve")
    sleeve = cash_sleeves[0]
    return _validated_assignment(policy, sleeve.key, None, "cash")


def resolve_holdings(
    policy: AllocationPolicy, securities: tuple[SecurityIdentity, ...]
) -> tuple[tuple[str, AssignmentResolution], ...]:
    """Resolve a batch of securities once, preserving deterministic input order."""
    return tuple((security.ticker, resolve_holding(policy, security)) for security in securities)
