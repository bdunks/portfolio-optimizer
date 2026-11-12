<template>
  <header
    class="page-header workspace-foundation tw:flex tw:items-start tw:justify-between tw:gap-4"
    data-workspace-foundation
  >
    <div class="page-heading tw:min-w-0 tw:flex-[1_1_auto]">
      <p class="eyebrow tw:mx-0 tw:mt-0 tw:mb-1 tw:text-primary tw:uppercase">{{ eyebrow }}</p>
      <h1
        class="tw:m-0 tw:text-foreground tw:text-[clamp(1.7rem,3vw,2rem)] tw:tracking-[-0.04em]"
        :id="titleId"
      >
        {{ title }}
      </h1>
      <p class="page-subtitle tw:mx-0 tw:mt-2 tw:mb-0 tw:max-w-[52rem] tw:text-muted-foreground">
        {{ subtitle }}
      </p>
    </div>
    <div
      v-if="$slots.actions"
      class="page-actions tw:flex tw:items-center tw:justify-end tw:gap-2"
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
@media (max-width: 760px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .page-actions {
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}
</style>
