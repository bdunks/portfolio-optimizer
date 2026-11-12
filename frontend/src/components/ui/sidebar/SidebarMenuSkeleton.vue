<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';
import { useId } from 'reka-ui';
import { computed } from 'vue';
import { Skeleton } from '@/components/ui/skeleton';

const props = defineProps<{
  showIcon?: boolean;
  class?: HTMLAttributes['class'];
}>();

// Derive the width from a stable id so server and client render the same value
const id = useId();
const width = computed(() => {
  let hash = 0;
  for (const char of id) hash = Math.imul(hash, 31) + char.charCodeAt(0);
  hash = Math.imul(hash ^ (hash >>> 16), 0x45d9f3b);
  hash ^= hash >>> 16;
  return `${((hash >>> 0) % 40) + 50}%`;
});
</script>

<template>
  <div
    data-slot="sidebar-menu-skeleton"
    data-sidebar="menu-skeleton"
    :class="cn('tw:h-8 tw:gap-2 tw:rounded-md tw:px-2 tw:flex tw:items-center', props.class)"
  >
    <Skeleton v-if="showIcon" class="tw:size-4 tw:rounded-md" data-sidebar="menu-skeleton-icon" />

    <Skeleton
      class="tw:h-4 tw:max-w-(--skeleton-width) tw:flex-1"
      data-sidebar="menu-skeleton-text"
      :style="{ '--skeleton-width': width }"
    />
  </div>
</template>
