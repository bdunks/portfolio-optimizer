<template>
  <header class="page-header row items-start justify-between q-gutter-md">
    <div class="page-heading">
      <p class="eyebrow q-mt-none q-mb-xs q-mx-none">{{ eyebrow }}</p>
      <h1 class="q-ma-none" :id="titleId">{{ title }}</h1>
      <p class="page-subtitle q-mt-sm q-mb-none q-mx-none">{{ subtitle }}</p>
    </div>
    <div
      v-if="$slots.actions"
      class="page-actions row items-center justify-end q-gutter-sm"
      aria-label="Page actions"
    >
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  eyebrow: string;
  title: string;
  titleId: string;
  subtitle: string;
}>();
</script>

<style scoped>
.page-heading {
  min-width: 0;
  flex: 1 1 auto;
}

@media (max-width: 760px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .page-actions {
    justify-content: flex-start;
  }
}
</style>
