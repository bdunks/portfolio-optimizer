import { describe, expect, it } from 'vitest';
import { displayCount } from './overview-state';

describe('overview display helpers', () => {
  it('keeps missing counts unavailable and renders returned counts exactly', () => {
    expect(displayCount(null)).toBe('Unavailable');
    expect(displayCount(undefined)).toBe('Unavailable');
    expect(displayCount(0)).toBe('0');
    expect(displayCount(3)).toBe('3');
  });
});
