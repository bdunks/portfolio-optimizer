import { defineStore } from 'pinia';

export const useUiStore = defineStore('ui', {
  state: () => ({
    sidebarOpen: true,
  }),
  actions: {
    setSidebarOpen(open: boolean): void {
      this.sidebarOpen = open;
    },
  },
});
