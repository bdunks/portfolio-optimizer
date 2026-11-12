<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { computed } from 'vue';

import { PanelLeftIcon } from '@lucide/vue';
import { cn } from 'cn';
import { Button } from '@/components/ui/button';
import { useSidebar } from './utils';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();

const { toggleSidebar, isMobile, open, openMobile } = useSidebar();
const isExpanded = computed(() => (isMobile.value ? openMobile.value : open.value));
</script>

<template>
  <Button
    data-sidebar="trigger"
    data-slot="sidebar-trigger"
    variant="ghost"
    size="icon-sm"
    :class="cn(props.class)"
    :aria-expanded="isExpanded"
    aria-label="Toggle workspace navigation"
    @click="toggleSidebar"
  >
    <PanelLeftIcon aria-hidden="true" />
    <span class="tw:sr-only">Toggle Sidebar</span>
  </Button>
</template>
