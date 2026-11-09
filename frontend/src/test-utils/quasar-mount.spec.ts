import { mountWithQuasar } from './quasar-mount';
import { defineComponent } from 'vue';
import { describe, expect, it } from 'vitest';

describe('Quasar test mounts', () => {
  it('fails when an application component is unresolved', () => {
    const pageWithMissingWidget = defineComponent({
      template: '<PortfolioApplicationWidget />',
    });

    expect(() => mountWithQuasar(pageWithMissingWidget)).toThrow(
      /Unresolved component warning: Failed to resolve component: PortfolioApplicationWidget/,
    );
  });
});
