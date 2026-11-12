<script setup lang="ts">
import type { SidebarProps } from '.';
import { cn } from 'cn';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import SheetDescription from '@/components/ui/sheet/SheetDescription.vue';
import SheetHeader from '@/components/ui/sheet/SheetHeader.vue';
import SheetTitle from '@/components/ui/sheet/SheetTitle.vue';
import { SIDEBAR_WIDTH_MOBILE, useSidebar } from './utils';

defineOptions({
  inheritAttrs: false,
});

const props = withDefaults(defineProps<SidebarProps>(), {
  side: 'left',
  variant: 'sidebar',
  collapsible: 'offcanvas',
});

const { isMobile, state, openMobile, setOpenMobile, mobileCloseFocusTarget } = useSidebar();

function restoreMobileFocus(event: Event): void {
  event.preventDefault();
  const focusTarget = mobileCloseFocusTarget.value;
  mobileCloseFocusTarget.value = null;
  if (focusTarget) focusTarget.focus();
  else document.querySelector<HTMLElement>('[data-sidebar="trigger"]')?.focus();
}
</script>

<template>
  <div
    v-if="collapsible === 'none'"
    data-slot="sidebar"
    :class="
      cn(
        'tw:bg-sidebar tw:text-sidebar-foreground tw:flex tw:w-(--sidebar-width) tw:flex-col',
        props.class,
      )
    "
    v-bind="$attrs"
  >
    <slot />
  </div>

  <Sheet v-else-if="isMobile" :open="openMobile" v-bind="$attrs" @update:open="setOpenMobile">
    <SheetContent
      @close-auto-focus="restoreMobileFocus"
      data-sidebar="sidebar"
      data-slot="sidebar"
      data-mobile="true"
      :side="side"
      class="tw:bg-sidebar tw:text-sidebar-foreground tw:w-(--sidebar-width) tw:p-0 tw:[&>button]:hidden"
      :style="{
        '--sidebar-width': SIDEBAR_WIDTH_MOBILE,
      }"
    >
      <SheetHeader class="tw:sr-only">
        <SheetTitle>Sidebar</SheetTitle>
        <SheetDescription>Displays the mobile sidebar.</SheetDescription>
      </SheetHeader>
      <div class="tw:flex tw:h-full tw:w-full tw:flex-col">
        <slot />
      </div>
    </SheetContent>
  </Sheet>

  <div
    v-else
    class="tw:group tw:peer tw:text-sidebar-foreground tw:hidden tw:md:block"
    data-slot="sidebar"
    :data-state="state"
    :data-collapsible="state === 'collapsed' ? collapsible : ''"
    :data-variant="variant"
    :data-side="side"
  >
    <!-- This is what handles the sidebar gap on desktop  -->
    <div
      data-slot="sidebar-gap"
      :class="
        cn(
          'tw:transition-[width] tw:duration-200 tw:ease-linear tw:relative tw:w-(--sidebar-width) tw:bg-transparent',
          'tw:group-data-[collapsible=offcanvas]:w-0',
          'tw:group-data-[side=right]:rotate-180',
          variant === 'floating' || variant === 'inset'
            ? 'tw:group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+(--spacing(4)))]'
            : 'tw:group-data-[collapsible=icon]:w-(--sidebar-width-icon)',
        )
      "
    />
    <div
      data-slot="sidebar-container"
      :data-side="side"
      :class="
        cn(
          'tw:fixed tw:inset-y-0 tw:z-10 tw:hidden tw:h-svh tw:w-(--sidebar-width) tw:transition-[left,right,width] tw:duration-200 tw:ease-linear tw:md:flex',
          side === 'left'
            ? 'tw:left-0 tw:group-data-[collapsible=offcanvas]:left-[calc(var(--sidebar-width)*-1)]'
            : 'tw:right-0 tw:group-data-[collapsible=offcanvas]:right-[calc(var(--sidebar-width)*-1)]',
          // Adjust the padding for floating and inset variants.
          variant === 'floating' || variant === 'inset'
            ? 'tw:p-2 tw:group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+(--spacing(4))+2px)]'
            : 'tw:group-data-[collapsible=icon]:w-(--sidebar-width-icon) tw:group-data-[side=left]:border-r tw:group-data-[side=right]:border-l',
          props.class,
        )
      "
      v-bind="$attrs"
    >
      <div
        data-sidebar="sidebar"
        data-slot="sidebar-inner"
        class="tw:bg-sidebar tw:group-data-[variant=floating]:ring-sidebar-border tw:group-data-[variant=floating]:rounded-lg tw:group-data-[variant=floating]:shadow-sm tw:group-data-[variant=floating]:ring-1 tw:flex tw:size-full tw:flex-col"
      >
        <slot />
      </div>
    </div>
  </div>
</template>
