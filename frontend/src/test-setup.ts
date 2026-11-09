import { installQuasarForTests } from '@/test-utils/quasar-mount';

installQuasarForTests();

if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class implements ResizeObserver {
    disconnect(): void {}
    observe(): void {}
    unobserve(): void {}
  };
}
