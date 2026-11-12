<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="card-content"
    :class="cn('tw:px-4 tw:group-data-[size=sm]/card:px-3', props.class)"
  >
    <slot />
  </div>
</template>
