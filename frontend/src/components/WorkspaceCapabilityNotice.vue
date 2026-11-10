<template>
  <QBanner
    dense
    rounded
    class="workspace-capability-notice bg-amber-1 text-brown-10"
    role="status"
    aria-live="polite"
  >
    <strong>{{ label }}</strong> <slot />
  </QBanner>
</template>

<script setup lang="ts">
import { QBanner } from 'quasar';

defineProps<{ label: string }>();
</script>
