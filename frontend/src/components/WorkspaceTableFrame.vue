<template>
  <div class="workspace-table-frame" role="region" :aria-label="label" tabindex="0">
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{ label: string }>();
</script>

<style scoped>
.workspace-table-frame {
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
  overscroll-behavior-inline: contain;
}

.workspace-table-frame:focus-visible {
  outline: 2px solid #087f7d;
  outline-offset: 2px;
}
</style>
