<script setup lang="ts">
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

const route = useRoute();
const { isMobile, setOpenMobile, mobileCloseFocusTarget } = useSidebar();

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
