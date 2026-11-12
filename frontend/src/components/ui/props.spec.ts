import { describe, expect, it } from 'vitest';
import { omitUndefinedProps } from './props';

describe('omitUndefinedProps', () => {
  it('removes undefined values without dropping meaningful falsy values', () => {
    expect(
      omitUndefinedProps({
        absent: undefined,
        enabled: false,
        count: 0,
        label: '',
        nullable: null,
      }),
    ).toEqual({
      enabled: false,
      count: 0,
      label: '',
      nullable: null,
    });
  });
});
