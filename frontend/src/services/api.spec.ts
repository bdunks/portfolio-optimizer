import { describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from './api';

function jsonResponse(value: unknown, status = 200, headers: HeadersInit = {}): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

function bodyJson(init?: RequestInit): unknown {
  if (typeof init?.body !== 'string') throw new Error('Expected a serialized JSON request body');
  return JSON.parse(init.body) as unknown;
}

describe('typed local API transport', () => {
  it('encodes IDs and omits empty filters while preserving false and zero', async () => {
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({ run_id: 'ignored' })));
    const client = createApiClient(fetcher);

    await client.getRun('run/with space');
    await client.getLots({ ticker: '', term: null, fractional: false, offset: 0, limit: 50 });

    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/optimizer/runs/run%2Fwith%20space');
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      credentials: 'omit',
      mode: 'same-origin',
      redirect: 'error',
    });
    expect(fetcher.mock.calls[1]?.[0]).toBe('/api/v1/lots?fractional=false&offset=0&limit=50');
  });

  it('sends recommendation-only runs and preserves exact decimal strings in JSON', async () => {
    const fetcher = vi.fn<typeof fetch>(() =>
      Promise.resolve(jsonResponse({ run_id: 'demo-run' })),
    );
    const client = createApiClient(fetcher);
    const exactRate = '0.123456789012345678901234567890123456789';

    await client.createRun({ max_sell_lots_per_batch: 7 });
    await client.savePolicyDraft({
      settings: {
        short_term_tax_rate: exactRate,
        target_retained_net_loss_usd: '3000.0000000000001',
      },
      sleeves: [],
    });

    expect(bodyJson(fetcher.mock.calls[0]?.[1])).toEqual({
      max_sell_lots_per_batch: 7,
      mode: 'recommendations_only',
    });
    expect(bodyJson(fetcher.mock.calls[1]?.[1])).toEqual({
      settings: {
        short_term_tax_rate: exactRate,
        target_retained_net_loss_usd: '3000.0000000000001',
      },
      sleeves: [],
    });
  });

  it('submits the complete generation-bound lot intent to the saved DEMO run', async () => {
    const fullRun = { run_id: 'run-2', groups: [], consolidated_legs: [], orders_count: 0 };
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(fullRun)));
    const client = createApiClient(fetcher);

    const response = await client.applyLotReviewIntent('run/2', {
      source_generation: 19,
      broker_lot_ids: ['LOT-2', 'LOT-1'],
    });

    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/optimizer/runs/run%2F2/lot-review-intent');
    expect(fetcher.mock.calls[0]?.[1]?.method).toBe('POST');
    expect(bodyJson(fetcher.mock.calls[0]?.[1])).toEqual({
      source_generation: 19,
      broker_lot_ids: ['LOT-2', 'LOT-1'],
    });
    expect(response).toEqual(fullRun);
  });

  it('sends annotation patches and receives the complete recommendation snapshot', async () => {
    const fullRun = {
      run_id: 'run-1',
      groups: [{ group_id: 'group-1', selected: false, rejected: true, note: null }],
      consolidated_legs: [],
      orders_count: 0,
    };
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(fullRun)));
    const client = createApiClient(fetcher);

    const response = await client.annotateGroup('run/1', 'group 1', { note: null });

    expect(fetcher.mock.calls[0]?.[0]).toBe(
      '/api/v1/optimizer/runs/run%2F1/recommendations/group%201',
    );
    expect(fetcher.mock.calls[0]?.[1]?.method).toBe('PATCH');
    expect(bodyJson(fetcher.mock.calls[0]?.[1])).toEqual({ note: null });
    expect(response).toEqual(fullRun);
    expect(response.run_id).toBe('run-1');
    expect(response.groups[0]?.selected).toBe(false);
  });

  it('surfaces backend error details and correlation IDs', async () => {
    const client = createApiClient(
      vi.fn<typeof fetch>(() =>
        Promise.resolve(
          jsonResponse(
            {
              code: 'policy_invalid',
              message: 'Targets must sum exactly to 100%',
              details: [{ code: 'target_sum', message: 'Sum is 99.9%' }],
              correlation_id: 'corr-123',
            },
            422,
          ),
        ),
      ),
    );

    await expect(client.getPolicy()).rejects.toMatchObject({
      name: 'ApiError',
      code: 'policy_invalid',
      message: 'Targets must sum exactly to 100%',
      correlationId: 'corr-123',
      status: 422,
    });
  });

  it('fails clearly for network and invalid JSON responses', async () => {
    const networkClient = createApiClient(
      vi.fn<typeof fetch>(() => Promise.reject(new TypeError('offline'))),
    );
    const invalidJsonClient = createApiClient(
      vi.fn<typeof fetch>(() =>
        Promise.resolve(new Response('<html>not json</html>', { status: 200 })),
      ),
    );

    await expect(networkClient.getHealth()).rejects.toMatchObject({
      code: 'network_error',
      message: expect.stringContaining('Unable to reach the local API'),
    });
    await expect(invalidJsonClient.getHealth()).rejects.toMatchObject({
      code: 'invalid_json',
      message: expect.stringContaining('invalid JSON'),
    });
  });

  it('returns typed exports as blobs with safe filenames', async () => {
    const fetcher = vi.fn<typeof fetch>((_input, init) => {
      if (init?.method !== 'GET') return Promise.reject(new Error('unexpected method'));
      return Promise.resolve(
        new Response('run_id,record_type\nrun_1,metadata\n', {
          status: 200,
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename="../../unsafe.csv"',
          },
        }),
      );
    });
    const client = createApiClient(fetcher);

    const exported = await client.exportRun('run/1', 'csv');

    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/optimizer/runs/run%2F1/export?format=csv');
    expect(exported.filename).toBe('optimizer-run-run_1.csv');
    expect(exported.contentType).toContain('text/csv');
    expect(await exported.blob.text()).toContain('run_id,record_type');
    expect(exported.json).toBeUndefined();
  });

  it('does not convert API failures into empty data', async () => {
    const client = createApiClient(
      vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({ message: 'bad response' }, 503))),
    );
    await expect(client.getPortfolio()).rejects.toBeInstanceOf(ApiError);
  });
});
