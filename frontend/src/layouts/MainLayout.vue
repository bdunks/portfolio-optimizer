<template>
  <div class="tw:min-h-svh tw:bg-background tw:text-foreground">
    <a class="skip-link tw:px-3 tw:py-2" href="#main-content" @click.prevent="focusMainContent">
      Skip to main content
    </a>

    <SidebarProvider v-model:open="ui.sidebarOpen">
      <WorkspaceSidebar />
      <SidebarInset class="tw:min-w-0 tw:bg-background">
        <header
          class="tw:flex tw:h-14 tw:shrink-0 tw:items-center tw:gap-3 tw:border-b tw:bg-background tw:px-4"
        >
          <SidebarTrigger />
          <Separator orientation="vertical" class="tw:h-5" />
          <div
            class="tw:flex tw:min-w-0 tw:flex-col tw:gap-0.5 tw:md:flex-row tw:md:items-baseline tw:md:gap-2"
          >
            <span class="tw:truncate tw:text-sm tw:font-semibold">Portfolio Optimizer</span>
            <span class="tw:truncate tw:text-sm tw:text-muted-foreground">
              Single-account workspace
            </span>
          </div>
        </header>

        <div id="main-content" tabindex="-1">
          <div class="tw:px-4 tw:pt-4">
            <Alert
              class="tw:box-border tw:m-0 tw:w-full"
              role="status"
              aria-label="Demo-only application notice"
            >
              <ShieldAlertIcon aria-hidden="true" />
              <AlertTitle>DEMO ONLY</AlertTitle>
              <AlertDescription>
                All analysis is non-actionable. No broker connection, OAuth, live writes, or
                trading.
              </AlertDescription>
            </Alert>
          </div>
          <router-view />
        </div>
      </SidebarInset>
    </SidebarProvider>
  </div>
</template>

<script setup lang="ts">
import { ShieldAlertIcon } from '@lucide/vue';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar';
import { useUiStore } from '@/stores/ui-store';
import WorkspaceSidebar from './WorkspaceSidebar.vue';

const ui = useUiStore();

function focusMainContent(): void {
  document.getElementById('main-content')?.focus();
}
</script>

<style scoped>
.skip-link {
  position: fixed;
  z-index: 10000;
  top: 0.5rem;
  left: 0.5rem;
  transform: translateY(calc(-100% - 0.5rem));
  border-radius: var(--radius);
  background: var(--background);
  color: var(--foreground);
  font-weight: 600;
}

.skip-link:focus-visible {
  transform: translateY(0);
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
</style>
