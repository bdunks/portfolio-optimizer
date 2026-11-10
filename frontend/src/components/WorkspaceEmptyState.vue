<template>
  <q-banner
    class="workspace-empty-state bg-blue-grey-1 text-blue-grey-10"
    dense
    rounded
    role="status"
    aria-live="polite"
  >
    <h2 class="q-ma-none text-primary text-subtitle1">{{ title }}</h2>
    <p class="q-ma-none text-blue-grey-7"><slot /></p>
    <slot name="details" />
    <slot name="action" />
  </q-banner>
</template>

<script setup lang="ts">
defineProps<{ title: string }>();
</script>
