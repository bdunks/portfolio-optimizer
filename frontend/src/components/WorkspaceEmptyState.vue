<template>
  <section
    class="workspace-empty-state empty-state column no-wrap q-gutter-y-sm"
    role="status"
    aria-live="polite"
  >
    <h2 class="q-mr-none q-mb-none q-ml-none">{{ title }}</h2>
    <p class="q-mr-none q-mb-none q-ml-none"><slot /></p>
    <slot name="details" />
    <slot name="action" />
  </section>
</template>

<script setup lang="ts">
defineProps<{ title: string }>();
</script>

<style scoped>
.workspace-empty-state h2 {
  color: #10263d;
  font-size: 1.05rem;
}

.workspace-empty-state p {
  color: #718795;
}
</style>
