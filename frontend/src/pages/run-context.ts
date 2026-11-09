import type {
  FrozenRunDisplayContextResponse,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
} from '@/types/api';

type RunContextCarrier = Pick<
  OptimizerRecommendationsResponse | OptimizerRunResponse,
  'run_id' | 'frozen_display_context'
>;

/** Prefer the detailed run response; a saved summary is only a fallback when recommendations are absent. */
export function selectRunDisplayContext(
  run: RunContextCarrier | null | undefined,
  summary?: RunContextCarrier | null,
): FrozenRunDisplayContextResponse | null {
  return run?.frozen_display_context ?? summary?.frozen_display_context ?? null;
}

export function frozenRunSleeveLabels(
  context: FrozenRunDisplayContextResponse | null,
): Record<string, string> {
  if (!context?.available || context.sleeves === null) return {};
  return Object.fromEntries(
    context.sleeves.map((sleeve) => [sleeve.sleeve_key, sleeve.display_name]),
  );
}

export function frozenRunSleeveLabel(
  context: FrozenRunDisplayContextResponse | null,
  sleeveKey: string,
): string {
  if (!context?.available || context.sleeves === null) return 'Unavailable (frozen run context)';
  return (
    context.sleeves.find((sleeve) => sleeve.sleeve_key === sleeveKey)?.display_name ??
    'Unavailable (frozen sleeve label)'
  );
}

export function completeFrozenRunSleeveLabels(
  context: FrozenRunDisplayContextResponse | null,
  sleeveKeys: Iterable<string>,
): Record<string, string> {
  return Object.fromEntries(
    [...new Set(sleeveKeys)].map((key) => [key, frozenRunSleeveLabel(context, key)]),
  );
}
