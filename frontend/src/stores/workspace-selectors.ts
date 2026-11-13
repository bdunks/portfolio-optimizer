import type {
  HealthResponse,
  LotPageResponse,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
  PolicyRevisionResponse,
} from '../types/api';
import type { PortfolioResponse } from '../services/api';
import { selectRunDisplayContext } from '../pages/run-context';
import type {
  ResourceFreshness,
  WorkspaceResourceFreshness,
  WorkspaceResourceKey,
} from '../types/workspace-resources';

type RunView = 'current' | 'saved' | 'stale' | null;
type ReadinessInput = {
  health: HealthResponse | null;
  portfolio: PortfolioResponse | null;
  activePolicy: PolicyRevisionResponse | null;
  resourceFreshness?: Partial<WorkspaceResourceFreshness>;
  syncPending?: boolean;
  runPending?: boolean;
  resourceReadsPending?: boolean;
  openSavedRunPending?: boolean;
};

type RunPresentationInput = {
  run: OptimizerRecommendationsResponse | null;
  summary: OptimizerRunResponse | null;
  view: RunView;
  proposedRunIsStale: boolean;
  health: HealthResponse | null;
  portfolio: PortfolioResponse | null;
  activePolicy: PolicyRevisionResponse | null;
  resourceFreshness?: Partial<WorkspaceResourceFreshness>;

  resourceReadsPending?: boolean;
  reviewMutationPending?: boolean;
};

function isConfirmed(
  freshness: Partial<WorkspaceResourceFreshness> | undefined,
  key: keyof WorkspaceResourceFreshness,
): boolean {
  const status = freshness?.[key]?.status;
  return status === 'fresh';
}

function allResourcesConfirmed(
  freshness: Partial<WorkspaceResourceFreshness> | undefined,
): boolean {
  return (
    isConfirmed(freshness, 'health') &&
    isConfirmed(freshness, 'portfolio') &&
    isConfirmed(freshness, 'policy')
  );
}

type PortfolioLabelContextInput = {
  portfolio: PortfolioResponse | null;
  activePolicy: PolicyRevisionResponse | null;
  sleeveKeys: readonly string[];
};

export function selectPortfolioLabelContext(input: PortfolioLabelContextInput) {
  const portfolioRevisionId =
    input.portfolio?.status === 'ready' ? input.portfolio.active_policy_revision_id : null;
  const policyRevisionId = input.activePolicy?.id ?? null;
  const revisionsMatch =
    portfolioRevisionId !== null &&
    policyRevisionId !== null &&
    portfolioRevisionId === policyRevisionId;
  const policyLabels = revisionsMatch
    ? Object.fromEntries(
        (input.activePolicy?.sleeves ?? []).map((sleeve) => [
          sleeve.sleeve_key,
          sleeve.display_name,
        ]),
      )
    : {};
  const labels = Object.fromEntries(
    [...new Set(input.sleeveKeys)].map((key) => [
      key,
      revisionsMatch ? (policyLabels[key] ?? 'Unavailable (active policy label)') : key,
    ]),
  );
  const revisionMismatch =
    input.portfolio?.status === 'ready' &&
    (portfolioRevisionId === null ||
      policyRevisionId === null ||
      portfolioRevisionId !== policyRevisionId);

  return { labels, revisionsMatch, revisionMismatch, portfolioRevisionId, policyRevisionId };
}

type PortfolioStructureInput = {
  health: HealthResponse | null;
  portfolio: PortfolioResponse | null;
  activePolicy: PolicyRevisionResponse | null;
  lots: LotPageResponse | null;
  lotFilters: Readonly<Record<string, unknown>>;
  freshness: Partial<WorkspaceResourceFreshness>;
  pending: boolean;
  lotsPending: boolean;
};

export function selectPortfolioStructureSummary(input: PortfolioStructureInput) {
  const sleeves = [...(input.activePolicy?.sleeves ?? [])]
    .sort((left, right) => left.sort_order - right.sort_order)
    .map((sleeve) => ({
      key: sleeve.sleeve_key,
      name: sleeve.display_name,
      enabled: sleeve.enabled,
    }));
  const portfolio = input.portfolio;
  const ready =
    input.health?.status === 'ok' &&
    input.health.schema_ready &&
    portfolio?.status === 'ready' &&
    portfolio.sync.complete &&
    input.activePolicy !== null &&
    portfolio.active_policy_revision_id === input.activePolicy.id &&
    (input.activePolicy.activation_errors?.length ?? 0) === 0 &&
    isConfirmed(input.freshness, 'health') &&
    isConfirmed(input.freshness, 'portfolio') &&
    isConfirmed(input.freshness, 'policy') &&
    !input.pending;
  const countsCurrent = ready && portfolio?.status === 'ready';
  const currentWeights = countsCurrent ? portfolio.allocation.current?.sleeve_weights_pct : null;
  const lotsCurrent =
    countsCurrent &&
    input.lots !== null &&
    isConfirmed(input.freshness, 'lots') &&
    !input.lotsPending &&
    Object.keys(input.lotFilters).length === 0 &&
    input.lots.source_generation === portfolio.sync.generation;

  return {
    sleeves,
    configurationAvailable: input.activePolicy !== null,
    configurationFresh:
      isConfirmed(input.freshness, 'policy') &&
      !input.pending &&
      input.activePolicy !== null &&
      (input.activePolicy.activation_errors?.length ?? 0) === 0 &&
      (portfolio?.status !== 'ready' ||
        portfolio.active_policy_revision_id === input.activePolicy.id),
    countsCurrent,
    positionCount: countsCurrent && portfolio?.status === 'ready' ? portfolio.position_count : null,
    directStockPositionCount:
      countsCurrent && portfolio?.status === 'ready'
        ? portfolio.positions.filter((position) => position.asset_type === 'EQUITY').length
        : null,
    allocationWeights: currentWeights ? Object.entries(currentWeights) : null,
    lotsCurrent,
    lotCount: lotsCurrent ? input.lots!.total : null,
    pending: input.pending || input.lotsPending,
  };
}

export function selectWorkspaceReadiness(input: ReadinessInput) {
  const { health, portfolio, activePolicy } = input;
  const dataReady =
    health?.status === 'ok' &&
    health.schema_ready &&
    portfolio?.status === 'ready' &&
    portfolio.sync.complete &&
    activePolicy !== null &&
    portfolio.active_policy_revision_id === activePolicy.id &&
    (activePolicy.activation_errors?.length ?? 0) === 0 &&
    allResourcesConfirmed(input.resourceFreshness);
  const pending = Boolean(
    input.syncPending ||
    input.runPending ||
    input.openSavedRunPending ||
    input.resourceReadsPending,
  );
  return {
    dataReady,
    pending,
    canRunOptimizer: dataReady && !pending,
    activePolicyRevisionId: activePolicy?.id ?? null,
    sourceGeneration: portfolio?.status === 'ready' ? portfolio.sync.generation : null,
  };
}

export function selectRunPresentation(input: RunPresentationInput) {
  const { run, summary, view } = input;
  const displayContext = selectRunDisplayContext(run, summary);
  let state: 'none' | 'current' | 'saved' | 'stale' | 'unverified' | 'pending' = 'none';

  if (run && input.reviewMutationPending) {
    state = 'pending';
  } else if (run && view === 'saved') {
    state = 'saved';
  } else if (run && (view === 'stale' || input.proposedRunIsStale)) {
    state = 'stale';
  } else if (run && view === 'current') {
    const portfolio = input.portfolio;
    const activePolicy = input.activePolicy;
    const resourcesConfirmed =
      isConfirmed(input.resourceFreshness, 'health') &&
      isConfirmed(input.resourceFreshness, 'portfolio') &&
      isConfirmed(input.resourceFreshness, 'policy');
    if (
      !resourcesConfirmed ||
      input.resourceReadsPending ||
      input.health?.status !== 'ok' ||
      !input.health.schema_ready ||
      portfolio?.status !== 'ready' ||
      !portfolio.sync.complete ||
      !activePolicy ||
      portfolio.active_policy_revision_id !== activePolicy.id
    ) {
      state = 'unverified';
    } else if (
      run.source_generation !== portfolio.sync.generation ||
      run.policy_revision_id !== activePolicy.id
    ) {
      state = 'stale';
    } else {
      state = 'current';
    }
  }

  const currentRunMatches = state === 'current';
  const effectsAvailable = state === 'current' || state === 'saved';
  const provenanceLabel =
    state === 'pending'
      ? 'Review update pending · prior run withheld'
      : state === 'saved'
        ? 'Saved run · frozen API context · read-only'
        : state === 'stale' || state === 'unverified'
          ? 'Stale/unverified run · read-only'
          : state === 'current'
            ? 'Current run · API context'
            : '';
  const effectsDescription =
    state === 'pending'
      ? 'A review update is awaiting API confirmation; prior run metrics and basket effects are withheld.'
      : state === 'saved'
        ? 'Frozen run effects and labels from this saved run; no current portfolio values or active-policy labels are overlaid.'
        : state === 'current'
          ? 'Effects and frozen labels returned by the current selected-basket API response. Missing values remain unavailable.'
          : 'Current portfolio API values with active-policy labels are shown. Stale or unverified run effects are not overlaid.';

  return {
    state,
    currentRunMatches,
    effectsAvailable,
    provenanceLabel,
    reviewMutationPending: Boolean(input.reviewMutationPending),
    effectsDescription,
    displayContext,
  };
}

export function selectResourceFreshnessNotices(
  freshness: Partial<WorkspaceResourceFreshness>,
  resources?: readonly WorkspaceResourceKey[],
): string[] {
  const labels: Array<[WorkspaceResourceKey, string]> = [
    ['health', 'API health'],
    ['portfolio', 'portfolio'],
    ['policy', 'active policy'],
    ['lots', 'tax lots'],
    ['washSales', 'wash-sale data'],
    ['activity', 'activity'],
  ];
  return labels.flatMap(([key, label]) => {
    if (resources && !resources.includes(key)) return [];
    const state: ResourceFreshness | undefined = freshness[key];
    if (!state || (state.status !== 'stale' && state.status !== 'error')) return [];
    if (state.status === 'stale') {
      const confirmed = state.confirmedAt ? ` Last confirmed ${state.confirmedAt}.` : '';
      return [`The latest ${label} request failed; cached data is being shown.${confirmed}`];
    }
    return [`${label} data is unavailable because the latest request failed.`];
  });
}
