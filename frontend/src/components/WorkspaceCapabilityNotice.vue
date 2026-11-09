<template>
  <QBanner rounded class="workspace-capability-notice" role="status" aria-live="polite">
    <strong>{{ label }}</strong> <slot />
  </QBanner>
</template>

<script setup lang="ts">
import { QBanner } from 'quasar';

defineProps<{ label: string }>();
</script>

<style scoped>
.workspace-capability-notice {
  border: 1px solid #f2dcad;
  background: #fff7e8;
  color: #765016;
  font-size: 0.82rem;
  line-height: 1.5;
}
</style>
