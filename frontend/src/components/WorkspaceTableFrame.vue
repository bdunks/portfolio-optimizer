<template>
  <div
    class="workspace-table-frame workspace-foundation tw:min-w-0 tw:max-w-full tw:overflow-x-auto tw:overscroll-x-contain tw:outline-none tw:focus-visible:ring-2 tw:focus-visible:ring-ring tw:focus-visible:ring-offset-2"
    data-workspace-foundation
    role="region"
    :aria-label="label"
    tabindex="0"
  >
    <slot />
  </div>
</template>

<style scoped>
.workspace-table-frame :deep([data-slot='table-container']) {
  overflow-x: visible;
}
</style>

<script setup lang="ts">
defineProps<{ label: string }>();
</script>
