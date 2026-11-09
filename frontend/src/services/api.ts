import type {
  ActivityPageResponse,
  ApiOperationName,
  ApiQuery,
  ApiRequest,
  ApiSuccessResponse,
  ErrorEnvelope,
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
  PortfolioNotSyncedResponse,
  PortfolioReadyResponse,
  RecommendationAnnotationInput,
  SyncResponseDTO,
  WashSalesResponse,
  JSONValue,
} from '../types/api';

export type PortfolioResponse = PortfolioNotSyncedResponse | PortfolioReadyResponse;
export type LotQuery = ApiQuery<'GET /api/v1/lots'>;
export type ActivityQuery = ApiQuery<'GET /api/v1/activity'>;
export type RecommendationsOnlyRunInput = Omit<OptimizerRunInput, 'mode'> & {
  mode?: 'recommendations_only';
};
export type ExportFormat = 'csv' | 'json';

export interface ExportDownload {
  blob: Blob;
  filename: string;
  contentType: string;
  format: ExportFormat;
  json?: OptimizerExportJSONResponse;
}

export class ApiError extends Error {
  readonly code: string;
  readonly details: JSONValue;
  readonly correlationId: string | null;
  readonly status: number | null;

  constructor(
    code: string,
    message: string,
    details: JSONValue = {},
    correlationId: string | null = null,
    status: number | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
    this.correlationId = correlationId;
    this.status = status;
  }
}

interface RequestSpec<K extends ApiOperationName> {
  operation: K;
  path: string;
  method: 'GET' | 'POST' | 'PATCH';
  query?: ApiQuery<K>;
  body?: ApiRequest<K>;
}

function assertLocalApiPath(path: string): void {
  if (
    path !== '/health' &&
    (!path.startsWith('/api/v1/') || path.startsWith('//') || path.includes('://'))
  ) {
    throw new ApiError('invalid_api_path', 'Only local application API routes are allowed');
  }
}

function buildUrl(path: string, query?: object): string {
  assertLocalApiPath(path);
  const params = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue;
      params.set(key, String(value));
    }
  }
  const search = params.toString();
  return search ? `${path}?${search}` : path;
}

function errorEnvelope(value: unknown): ErrorEnvelope | null {
  if (
    typeof value === 'object' &&
    value !== null &&
    'code' in value &&
    typeof value.code === 'string' &&
    'message' in value &&
    typeof value.message === 'string' &&
    'correlation_id' in value &&
    typeof value.correlation_id === 'string' &&
    'details' in value
  ) {
    return value as ErrorEnvelope;
  }
  return null;
}

function jsonValue(value: unknown): JSONValue {
  return value as JSONValue;
}

function parseJson(text: string, status: number, operation: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    if (status >= 400) {
      throw new ApiError(
        'http_error',
        `The API returned HTTP ${status} without a valid error response`,
        { status },
        null,
        status,
      );
    }
    throw new ApiError(
      'invalid_json',
      `The API returned invalid JSON for ${operation}`,
      { status },
      null,
      status,
    );
  }
}

function throwHttpError(status: number, payload: unknown): never {
  const envelope = errorEnvelope(payload);
  if (envelope) {
    throw new ApiError(
      envelope.code,
      envelope.message,
      envelope.details,
      envelope.correlation_id,
      status,
    );
  }
  throw new ApiError(
    'http_error',
    `The API request failed with HTTP ${status}`,
    jsonValue(payload),
    null,
    status,
  );
}

function safeRunId(runId: string): string {
  const safe = runId.replace(/[^A-Za-z0-9_-]/g, '_').replace(/^_+|_+$/g, '');
  return safe || 'saved-run';
}

function getFetch(override?: typeof fetch): typeof fetch {
  if (override) return override;
  return (input, init) => globalThis.fetch(input, init);
}

export function createApiClient(fetchOverride?: typeof fetch) {
  const fetcher = getFetch(fetchOverride);

  async function send<K extends ApiOperationName>(spec: RequestSpec<K>): Promise<Response> {
    const url = buildUrl(spec.path, spec.query);
    try {
      return await fetcher(url, {
        method: spec.method,
        credentials: 'omit',
        mode: 'same-origin',
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          ...(spec.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(spec.body === undefined ? {} : { body: JSON.stringify(spec.body) }),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'The local API could not be reached';
      throw new ApiError('network_error', `Unable to reach the local API: ${message}`);
    }
  }

  async function jsonRequest<K extends ApiOperationName>(
    spec: RequestSpec<K>,
  ): Promise<ApiSuccessResponse<K>> {
    const response = await send(spec);
    let text: string;
    try {
      text = await response.text();
    } catch {
      throw new ApiError('network_error', 'The local API response could not be read');
    }
    const payload = parseJson(text, response.status, spec.operation);
    if (!response.ok) throwHttpError(response.status, payload);
    return payload as ApiSuccessResponse<K>;
  }

  async function getHealth(): Promise<HealthResponse> {
    return jsonRequest({ operation: 'GET /health', path: '/health', method: 'GET' });
  }

  async function syncPortfolio(): Promise<SyncResponseDTO> {
    return jsonRequest({
      operation: 'POST /api/v1/portfolio/sync',
      path: '/api/v1/portfolio/sync',
      method: 'POST',
    });
  }

  async function getPortfolio(): Promise<PortfolioResponse> {
    return jsonRequest({
      operation: 'GET /api/v1/portfolio',
      path: '/api/v1/portfolio',
      method: 'GET',
    });
  }

  async function getLots(filters: LotQuery = {}): Promise<LotPageResponse> {
    return jsonRequest({
      operation: 'GET /api/v1/lots',
      path: '/api/v1/lots',
      method: 'GET',
      query: filters,
    });
  }

  async function getPolicy(): Promise<PolicyResponse> {
    return jsonRequest({
      operation: 'GET /api/v1/policy',
      path: '/api/v1/policy',
      method: 'GET',
    });
  }

  async function savePolicyDraft(payload: PolicyDraftInput): Promise<PolicyRevisionResponse> {
    return jsonRequest({
      operation: 'POST /api/v1/policy/drafts',
      path: '/api/v1/policy/drafts',
      method: 'POST',
      body: payload,
    });
  }

  async function activatePolicy(revisionId: string): Promise<PolicyRevisionResponse> {
    return jsonRequest({
      operation: 'POST /api/v1/policy/{revision_id}/activate',
      path: `/api/v1/policy/${encodeURIComponent(revisionId)}/activate`,
      method: 'POST',
    });
  }

  async function createRun(
    input: RecommendationsOnlyRunInput = {},
  ): Promise<OptimizerRecommendationsResponse> {
    const body: OptimizerRunInput = { ...input, mode: 'recommendations_only' };
    return jsonRequest({
      operation: 'POST /api/v1/optimizer/runs',
      path: '/api/v1/optimizer/runs',
      method: 'POST',
      body,
    });
  }

  async function getRun(runId: string): Promise<OptimizerRunResponse> {
    return jsonRequest({
      operation: 'GET /api/v1/optimizer/runs/{run_id}',
      path: `/api/v1/optimizer/runs/${encodeURIComponent(runId)}`,
      method: 'GET',
    });
  }

  async function getRecommendations(runId: string): Promise<OptimizerRecommendationsResponse> {
    return jsonRequest({
      operation: 'GET /api/v1/optimizer/runs/{run_id}/recommendations',
      path: `/api/v1/optimizer/runs/${encodeURIComponent(runId)}/recommendations`,
      method: 'GET',
    });
  }

  async function recalculateSelection(
    runId: string,
    selection: OptimizerSelectionInput,
  ): Promise<OptimizerRecommendationsResponse> {
    return jsonRequest({
      operation: 'POST /api/v1/optimizer/runs/{run_id}/selection',
      path: `/api/v1/optimizer/runs/${encodeURIComponent(runId)}/selection`,
      method: 'POST',
      body: selection,
    });
  }
  async function applyLotReviewIntent(
    runId: string,
    intent: OptimizerLotReviewIntentInput,
  ): Promise<OptimizerRecommendationsResponse> {
    return jsonRequest({
      operation: 'POST /api/v1/optimizer/runs/{run_id}/lot-review-intent',
      path: `/api/v1/optimizer/runs/${encodeURIComponent(runId)}/lot-review-intent`,
      method: 'POST',
      body: intent,
    });
  }

  async function annotateGroup(
    runId: string,
    groupId: string,
    annotation: RecommendationAnnotationInput,
  ): Promise<OptimizerRecommendationsResponse> {
    return jsonRequest({
      operation: 'PATCH /api/v1/optimizer/runs/{run_id}/recommendations/{group_id}',
      path: `/api/v1/optimizer/runs/${encodeURIComponent(
        runId,
      )}/recommendations/${encodeURIComponent(groupId)}`,
      method: 'PATCH',
      body: annotation,
    });
  }

  async function exportRun(runId: string, format: ExportFormat = 'json'): Promise<ExportDownload> {
    const response = await send({
      operation: 'GET /api/v1/optimizer/runs/{run_id}/export',
      path: `/api/v1/optimizer/runs/${encodeURIComponent(runId)}/export`,
      method: 'GET',
      query: { format },
    });
    const contentType = response.headers.get('content-type') ?? 'application/octet-stream';
    const filename = `optimizer-run-${safeRunId(runId)}.${format}`;

    if (!response.ok) {
      let text: string;
      try {
        text = await response.text();
      } catch {
        throw new ApiError('network_error', 'The local API error response could not be read');
      }
      throwHttpError(response.status, parseJson(text, response.status, 'run export'));
    }

    if (format === 'csv') {
      try {
        return { blob: await response.blob(), filename, contentType, format };
      } catch {
        throw new ApiError('network_error', 'The local CSV export could not be read');
      }
    }

    let text: string;
    try {
      text = await response.text();
    } catch {
      throw new ApiError('network_error', 'The local JSON export could not be read');
    }
    const payload = parseJson(text, response.status, 'run export');
    const blob = new Blob([text], { type: contentType });
    return {
      blob,
      filename,
      contentType,
      format,
      json: payload as OptimizerExportJSONResponse,
    };
  }

  async function getWashSales(): Promise<WashSalesResponse> {
    return jsonRequest({
      operation: 'GET /api/v1/wash-sales',
      path: '/api/v1/wash-sales',
      method: 'GET',
    });
  }

  async function getActivity(filters: ActivityQuery = {}): Promise<ActivityPageResponse> {
    return jsonRequest({
      operation: 'GET /api/v1/activity',
      path: '/api/v1/activity',
      method: 'GET',
      query: filters,
    });
  }

  return {
    getHealth,
    syncPortfolio,
    getPortfolio,
    getLots,
    getPolicy,
    savePolicyDraft,
    activatePolicy,
    createRun,
    getRun,
    getRecommendations,
    recalculateSelection,
    applyLotReviewIntent,
    annotateGroup,
    exportRun,
    getWashSales,
    getActivity,
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
export const api = createApiClient();
