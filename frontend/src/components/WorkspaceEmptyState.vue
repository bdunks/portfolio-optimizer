<template>
  <section class="workspace-empty-state empty-state" role="status" aria-live="polite">
    <h2>{{ title }}</h2>
    <p><slot /></p>
    <slot name="details" />
    <slot name="action" />
  </section>
</template>

<script setup lang="ts">
defineProps<{ title: string }>();
</script>

<style scoped>
.workspace-empty-state {
  display: grid;
  gap: 0.45rem;
}

.workspace-empty-state h2 {
  margin: 0;
  color: #10263d;
  font-size: 1.05rem;
}

.workspace-empty-state p {
  margin: 0;
  color: #718795;
}
</style>
