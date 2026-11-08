import type {
  OptimizerRecommendationsResponse,
  OptimizerSelectionInput,
  RecommendationGroupResponse,
  RecommendationLegResponse,
} from '@/types/api';

export type RecommendationFilters = {
  sleeve: string;
  action: '' | 'BUY' | 'SELL';
  term: '' | 'ST' | 'LT';
  benefit: '' | 'unavailable';
  warning: '' | 'with' | 'without';
  groupType: string;
};

/** Return each canonical API leg once, ordered by the API execution sequence. */
export function canonicalLegs(run: OptimizerRecommendationsResponse): RecommendationLegResponse[] {
  const unique = new Map<string, RecommendationLegResponse>();
  for (const leg of run.consolidated_legs) {
    if (!unique.has(leg.leg_id)) unique.set(leg.leg_id, leg);
  }
  return [...unique.values()].sort((left, right) => left.sequence - right.sequence);
}

export function groupLegs(
  run: OptimizerRecommendationsResponse,
  group: RecommendationGroupResponse,
): RecommendationLegResponse[] {
  const legsById = new Map(canonicalLegs(run).map((leg) => [leg.leg_id, leg]));
  const seen = new Set<string>();
  return group.leg_ids.flatMap((legId) => {
    if (seen.has(legId)) return [];
    seen.add(legId);
    const leg = legsById.get(legId);
    return leg ? [leg] : [];
  });
}

export function groupSellLotIds(
  run: OptimizerRecommendationsResponse,
  group: RecommendationGroupResponse,
): string[] {
  return [
    ...new Set(
      groupLegs(run, group)
        .filter((leg) => leg.side === 'SELL')
        .flatMap((leg) => leg.selected_lots.map((lot) => lot.broker_lot_id)),
    ),
  ];
}

export function selectedSellLotIds(
  run: OptimizerRecommendationsResponse,
  group: RecommendationGroupResponse,
): string[] {
  return [
    ...new Set(
      groupLegs(run, group)
        .filter((leg) => leg.side === 'SELL')
        .flatMap((leg) =>
          leg.selected_lots.filter((lot) => lot.selected).map((lot) => lot.broker_lot_id),
        ),
    ),
  ];
}

/** Serialize only known, selected groups and their exact broker lot IDs. */
export function buildSelectionPayload(
  run: OptimizerRecommendationsResponse,
  selectedGroupIds: Iterable<string>,
  selectedLotsByGroup: Record<string, readonly string[]> = {},
): OptimizerSelectionInput {
  const requested = new Set(selectedGroupIds);
  const selected_group_ids: string[] = [];
  const selected_sell_lots: Record<string, string[]> = {};

  for (const group of run.groups) {
    if (!requested.has(group.group_id) || group.rejected) continue;
    const knownLotIds = groupSellLotIds(run, group);
    const requestedLotIds = Object.prototype.hasOwnProperty.call(
      selectedLotsByGroup,
      group.group_id,
    )
      ? (selectedLotsByGroup[group.group_id] ?? [])
      : knownLotIds;
    const known = new Set(knownLotIds);
    const lotIds = [...new Set(requestedLotIds)].filter((lotId) => known.has(lotId));
    // A group with no selected sell lot must be deselected, not sent as an empty group.
    if (lotIds.length === 0) continue;
    selected_group_ids.push(group.group_id);
    selected_sell_lots[group.group_id] = lotIds;
  }

  return { selected_group_ids, selected_sell_lots };
}

export function selectionFromRun(run: OptimizerRecommendationsResponse): OptimizerSelectionInput {
  return buildSelectionPayload(
    run,
    run.groups.filter((group) => group.selected && !group.rejected).map((group) => group.group_id),
    Object.fromEntries(run.groups.map((group) => [group.group_id, selectedSellLotIds(run, group)])),
  );
}

export function requestGroupSelection(
  run: OptimizerRecommendationsResponse,
  groupId: string,
  selected: boolean,
): OptimizerSelectionInput {
  const current = selectionFromRun(run);
  const selectedGroups = new Set(current.selected_group_ids ?? []);
  const selectedLots = { ...(current.selected_sell_lots ?? {}) };
  const group = run.groups.find((item) => item.group_id === groupId);
  if (!group || group.rejected) return current;

  if (selected) {
    const allKnownLotIds = groupSellLotIds(run, group);
    if (allKnownLotIds.length === 0) return current;
    selectedGroups.add(groupId);
    selectedLots[groupId] = allKnownLotIds;
  } else {
    selectedGroups.delete(groupId);
    delete selectedLots[groupId];
  }
  return buildSelectionPayload(run, selectedGroups, selectedLots);
}

export function requestLotSelection(
  run: OptimizerRecommendationsResponse,
  groupId: string,
  brokerLotId: string,
  selected: boolean,
): OptimizerSelectionInput {
  const current = selectionFromRun(run);
  const selectedGroups = new Set(current.selected_group_ids ?? []);
  const selectedLots = { ...(current.selected_sell_lots ?? {}) };
  const group = run.groups.find((item) => item.group_id === groupId);
  if (!group || group.rejected || !groupSellLotIds(run, group).includes(brokerLotId))
    return current;

  const lotIds = new Set(selectedLots[groupId] ?? []);
  if (selected) {
    lotIds.add(brokerLotId);
    selectedLots[groupId] = [...lotIds];
    selectedGroups.add(groupId);
  } else {
    lotIds.delete(brokerLotId);
    if (lotIds.size === 0) {
      selectedGroups.delete(groupId);
      delete selectedLots[groupId];
    } else {
      selectedLots[groupId] = [...lotIds];
    }
  }
  return buildSelectionPayload(run, selectedGroups, selectedLots);
}

export function filterGroups(
  run: OptimizerRecommendationsResponse,
  filters: RecommendationFilters,
  sort: 'rank-ascending' | 'rank-descending',
): RecommendationGroupResponse[] {
  const filtered = run.groups.filter((group) => {
    const legs = groupLegs(run, group);
    const lots = legs.filter((leg) => leg.side === 'SELL').flatMap((leg) => leg.selected_lots);
    const hasWarning = group.warnings.length > 0;
    return (
      (!filters.sleeve || group.sleeve_key === filters.sleeve) &&
      (!filters.action || legs.some((leg) => leg.side === filters.action)) &&
      (!filters.term || lots.some((lot) => lot.st_lt === filters.term)) &&
      (!filters.benefit || group.estimated_benefit_usd === null) &&
      (!filters.warning || (filters.warning === 'with' ? hasWarning : !hasWarning)) &&
      (!filters.groupType || group.group_type === filters.groupType)
    );
  });
  return filtered.sort((left, right) =>
    sort === 'rank-ascending' ? left.rank - right.rank : right.rank - left.rank,
  );
}

export function sharedLegs(run: OptimizerRecommendationsResponse): RecommendationLegResponse[] {
  return canonicalLegs(run).filter((leg) => leg.group_ids.length > 1);
}

export function unlinkedLegs(run: OptimizerRecommendationsResponse): RecommendationLegResponse[] {
  const groupIds = new Set(run.groups.map((group) => group.group_id));
  return canonicalLegs(run).filter((leg) => {
    const linkedGroupIds = new Set(leg.group_ids);
    const referencingGroups = run.groups.filter((group) => group.leg_ids.includes(leg.leg_id));
    if (
      leg.group_ids.length === 0 ||
      leg.group_ids.some((id) => !groupIds.has(id)) ||
      referencingGroups.some((group) => !linkedGroupIds.has(group.group_id))
    ) {
      return true;
    }
    return leg.group_ids.some((groupId) => {
      const group = run.groups.find((item) => item.group_id === groupId);
      return !group?.leg_ids.includes(leg.leg_id);
    });
  });
}

export function displayUsd(value: string | null | undefined): string {
  return value == null || value === '' ? 'Unavailable (not returned by API)' : `${value} USD`;
}

export function displayJson(value: unknown): string {
  if (value == null) return 'No reason was returned by the API.';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return 'The API returned a reason that could not be displayed.';
  }
}
