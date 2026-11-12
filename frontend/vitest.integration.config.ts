import { defineConfig } from 'vitest/config';
import baseConfig from './vitest.config.ts';

export default defineConfig({
  ...baseConfig,
  test: {
    ...baseConfig.test,
    include: ['src/integration/backend-smoke.spec.ts'],
    exclude: [],
  },
});
