import { installWorkspaceTestPlugin } from '@/test-utils/workspace-mount';

installWorkspaceTestPlugin();

if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class implements ResizeObserver {
    disconnect(): void {}
    observe(): void {}
    unobserve(): void {}
  };
}
