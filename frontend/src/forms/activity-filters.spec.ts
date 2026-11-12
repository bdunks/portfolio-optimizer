import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  activityFilterDefaults,
  activityFilterSchema,
  dateTimeLocalToUtcFilter,
  isActivityPageLimit,
  selectedDateTimeFilter,
  utcFilterToDateTimeLocal,
} from './activity-filters';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('activity filters', () => {
  it('accepts unrestricted exact API event type, status, and correlation text', () => {
    const values = {
      eventType: ' custom.Event / v2 ',
      status: 'pending-or-unlisted',
      correlationId: 'id/with spaces and punctuation',
      since: '',
      until: '',
      limit: 25,
    };

    expect(activityFilterSchema.safeParse(values).success).toBe(true);
    expect(activityFilterSchema.safeParse({ ...values, eventType: 12 }).success).toBe(false);
  });

  it('allows only the page-size choices exposed by the activity filter', () => {
    for (const limit of [25, 50, 100, 250]) {
      expect(
        activityFilterSchema.safeParse({
          eventType: '',
          status: '',
          correlationId: '',
          since: '',
          until: '',
          limit,
        }).success,
      ).toBe(true);
      expect(isActivityPageLimit(limit)).toBe(true);
    }

    expect(isActivityPageLimit(75)).toBe(false);
    expect(isActivityPageLimit('50')).toBe(false);
  });

  it('formats UTC date filters without using the browser timezone', () => {
    vi.stubEnv('TZ', 'America/Los_Angeles');

    expect(utcFilterToDateTimeLocal('2025-02-01T00:00:00Z')).toBe('2025-02-01T00:00:00');
    expect(utcFilterToDateTimeLocal('2025-02-01T00:00:00+05:30')).toBe('2025-01-31T18:30:00');
    expect(utcFilterToDateTimeLocal('not-a-date')).toBe('');
    expect(dateTimeLocalToUtcFilter('2025-02-01T00:00')).toBe('2025-02-01T00:00:00Z');
    expect(dateTimeLocalToUtcFilter('2025-02-01T00:00:45.123')).toBe('2025-02-01T00:00:45.123Z');
  });

  it('retains untouched saved bounds verbatim and only converts edited values', () => {
    const savedOffsetBound = '2025-02-03T12:30:45.123+05:30';
    const savedFractionBound = '2025-02-04T01:02:03.456789Z';

    expect(selectedDateTimeFilter('2025-02-03T07:00:45.123', false, savedOffsetBound)).toBe(
      savedOffsetBound,
    );
    expect(selectedDateTimeFilter('2025-02-04T01:02:03.456', false, savedFractionBound)).toBe(
      savedFractionBound,
    );
    expect(selectedDateTimeFilter('2025-02-05T06:07', true, savedOffsetBound)).toBe(
      '2025-02-05T06:07:00Z',
    );
    expect(selectedDateTimeFilter('2025-02-05T06:07:08.123', true, savedOffsetBound)).toBe(
      '2025-02-05T06:07:08.123Z',
    );
    expect(selectedDateTimeFilter('', true, savedOffsetBound)).toBeUndefined();
  });

  it('restores saved criteria and falls back to the default page size for unsupported values', () => {
    expect(
      activityFilterDefaults({
        event_type: 'sync',
        status: 'failed',
        correlation_id: 'restored-correlation',
        since: '2025-02-01T00:00:00Z',
        until: '2025-02-03T12:30:45.123Z',
        offset: 25,
        limit: 50,
      }),
    ).toEqual({
      eventType: 'sync',
      status: 'failed',
      correlationId: 'restored-correlation',
      since: '2025-02-01T00:00:00',
      until: '2025-02-03T12:30:45.123',
      limit: 50,
    });
    expect(activityFilterDefaults({ limit: 75 }).limit).toBe(25);
  });
});
