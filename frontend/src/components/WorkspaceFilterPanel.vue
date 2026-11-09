<template>
  <form :aria-label="label" @submit.prevent="submit">
    <slot />
  </form>
</template>

<script setup lang="ts">
defineProps<{ label: string }>();
const emit = defineEmits<{ submit: [event: SubmitEvent] }>();

function submit(event: SubmitEvent): void {
  emit('submit', event);
}
</script>
