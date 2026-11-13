<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, RouterLink } from 'vue-router';
import { cn } from 'cn';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar';
import { workspaceLinks } from '@/navigation/workspace-navigation';
import { useWorkspace } from '@/composables/use-workspace';
import { selectPortfolioStructureSummary } from '@/stores/workspace-selectors';

const route = useRoute();
const { isMobile, setOpenMobile, mobileCloseFocusTarget } = useSidebar();
const store = useWorkspace();
const portfolioStructure = computed(() =>
  selectPortfolioStructureSummary({
    health: store.health,
    portfolio: store.portfolio,
    activePolicy: store.policy?.active ?? null,
    lots: store.lots,
    lotFilters: store.lotFilters,
    freshness: store.resourceFreshness,
    pending:
      store.initialWorkspacePending ||
      store.workspaceResourceLoadPending ||
      store.actionState.syncPortfolio.pending,
    lotsPending: store.actionState.loadLots.pending,
  }),
);

function closeOnMobileNavigation(): void {
  if (!isMobile.value) return;
  mobileCloseFocusTarget.value = document.getElementById('main-content');
  setOpenMobile(false);
}
</script>

<template>
  <Sidebar collapsible="icon">
    <SidebarHeader>
      <div class="workspace-brand tw:flex tw:items-center tw:gap-3 tw:px-2 tw:py-3">
        <Badge
          variant="secondary"
          class="tw:size-9 tw:shrink-0 tw:justify-center tw:p-0 tw:text-sm"
        >
          PO
        </Badge>
        <div class="tw:min-w-0 tw:flex-1 tw:leading-tight">
          <p class="tw:m-0! tw:truncate tw:text-sm tw:font-semibold">Portfolio Optimizer</p>
          <p class="tw:m-0! tw:truncate tw:text-xs tw:text-muted-foreground">
            Local decision support
          </p>
        </div>
      </div>
    </SidebarHeader>

    <SidebarContent>
      <nav class="workspace-sidebar" aria-label="Primary navigation">
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu class="tw:m-0 tw:list-none tw:p-0">
              <SidebarMenuItem v-for="link in workspaceLinks" :key="link.to">
                <SidebarMenuButton
                  as-child
                  size="lg"
                  class="tw:h-14"
                  :is-active="route.path === link.to"
                  :tooltip="link.label"
                >
                  <RouterLink
                    class="tw:text-sidebar-foreground tw:no-underline"
                    :to="link.to"
                    :aria-current="route.path === link.to ? 'page' : undefined"
                    @click="closeOnMobileNavigation"
                  >
                    <component :is="link.icon" aria-hidden="true" />
                    <span class="tw:min-w-0 tw:flex-1 tw:flex tw:flex-col tw:gap-0.5">
                      <span class="tw:truncate tw:font-medium">{{ link.label }}</span>
                      <span
                        :class="
                          cn(
                            'tw:truncate tw:text-xs tw:text-muted-foreground tw:group-hover/menu-button:text-sidebar-accent-foreground tw:group-active/menu-button:text-sidebar-accent-foreground',
                            route.path === link.to && 'tw:text-sidebar-accent-foreground',
                          )
                        "
                      >
                        {{ link.caption }}
                      </span>
                    </span>
                  </RouterLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </nav>
      <section
        class="tw:mx-2 tw:mb-3 tw:rounded-md tw:border tw:border-sidebar-border tw:p-3 tw:text-xs"
        aria-label="Portfolio structure context"
      >
        <h2 class="tw:m-0! tw:text-xs tw:font-semibold">Portfolio context</h2>
        <p class="tw:mb-1 tw:mt-2 tw:font-medium">Configured sleeves</p>
        <p
          v-if="!portfolioStructure.configurationAvailable"
          class="tw:m-0! tw:text-sidebar-foreground/70"
        >
          Active configuration unavailable.
        </p>
        <template v-else>
          <p class="tw:m-0! tw:text-sidebar-foreground/70">
            {{
              portfolioStructure.configurationFresh
                ? 'Active configuration'
                : 'Last confirmed configuration'
            }}
            · not holdings coverage
          </p>
          <ul class="tw:mb-0 tw:mt-1 tw:list-none tw:space-y-0.5 tw:p-0">
            <li v-for="sleeve in portfolioStructure.sleeves" :key="sleeve.key">
              {{ sleeve.name }} · {{ sleeve.enabled ? 'enabled' : 'disabled' }}
            </li>
          </ul>
        </template>
        <Separator class="tw:my-2" />
        <p class="tw:m-0! tw:font-medium">Current holdings</p>
        <template v-if="portfolioStructure.countsCurrent">
          <p class="tw:mb-0 tw:mt-1">
            {{ portfolioStructure.positionCount }} account positions ·
            {{ portfolioStructure.directStockPositionCount }} direct-stock positions
          </p>
          <ul
            v-if="portfolioStructure.allocationWeights?.length"
            class="tw:mb-0 tw:mt-1 tw:list-none tw:space-y-0.5 tw:p-0"
          >
            <li v-for="[key, weight] in portfolioStructure.allocationWeights" :key="key">
              {{ key }}: {{ weight }}% of portfolio (reported)
            </li>
          </ul>
          <p v-else class="tw:mb-0 tw:mt-1 tw:text-sidebar-foreground/70">
            Current holdings allocation unavailable.
          </p>
        </template>
        <p v-else class="tw:mb-0 tw:mt-1 tw:text-sidebar-foreground/70">
          Current position counts and holdings allocation unavailable{{
            portfolioStructure.pending
              ? ' while data is pending'
              : ' while data is stale or unverified'
          }}.
        </p>
        <p class="tw:mb-0 tw:mt-1">
          <template v-if="portfolioStructure.lotsCurrent"
            >{{ portfolioStructure.lotCount }} account tax lots</template
          >
          <template v-else>Account-wide tax-lot count unavailable</template>
        </p>
      </section>
    </SidebarContent>

    <SidebarFooter>
      <Separator />
      <div class="workspace-sidebar-footer tw:flex tw:flex-col tw:gap-2 tw:px-2 tw:pb-2">
        <Badge variant="outline" class="tw:w-fit">Local demo mode</Badge>
        <p class="tw:m-0! tw:text-xs tw:text-muted-foreground">
          No broker connection or order submission
        </p>
      </div>
    </SidebarFooter>
  </Sidebar>
</template>
