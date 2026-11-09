<template>
  <header class="page-header">
    <div class="page-heading">
      <p class="eyebrow">{{ eyebrow }}</p>
      <h1 :id="titleId">{{ title }}</h1>
      <p class="page-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="page-actions" aria-label="Page actions">
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
