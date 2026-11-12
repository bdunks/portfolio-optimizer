import { z } from 'zod';
import type { ActivityQuery } from '@/services/api';

export const ACTIVITY_PAGE_LIMITS = [25, 50, 100, 250] as const;

export const activityFilterSchema = z.object({
  eventType: z.string(),
  status: z.string(),
  correlationId: z.string(),
  since: z.string(),
  until: z.string(),
  limit: z.union([z.literal(25), z.literal(50), z.literal(100), z.literal(250)]),
});

export type ActivityFilterValues = z.infer<typeof activityFilterSchema>;

export function activityFilterDefaults(filters: ActivityQuery): ActivityFilterValues {
  return {
    eventType: filters.event_type ?? '',
    status: filters.status ?? '',
    correlationId: filters.correlation_id ?? '',
    since: utcFilterToDateTimeLocal(filters.since),
    until: utcFilterToDateTimeLocal(filters.until),
    limit: isActivityPageLimit(filters.limit) ? filters.limit : 25,
  };
}

export function isActivityPageLimit(value: unknown): value is ActivityFilterValues['limit'] {
  return ACTIVITY_PAGE_LIMITS.some((limit) => limit === value);
}

export function utcFilterToDateTimeLocal(value: string | null | undefined): string {
  if (!value) return '';
  const timestamp = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  return Number.isNaN(timestamp.getTime())
    ? ''
    : timestamp
        .toISOString()
        .replace(/\.000Z$/, '')
        .replace(/Z$/, '');
}

export function dateTimeLocalToUtcFilter(value: string): string {
  return `${value.length === 16 ? `${value}:00` : value}Z`;
}

export function selectedDateTimeFilter(
  value: string,
  edited: boolean,
  savedBound: string | null,
): string | undefined {
  if (!edited && savedBound) return savedBound;
  return value ? dateTimeLocalToUtcFilter(value) : undefined;
}
