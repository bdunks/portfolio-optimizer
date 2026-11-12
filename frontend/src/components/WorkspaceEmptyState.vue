<template>
  <Alert
    class="workspace-empty-state workspace-foundation"
    data-workspace-foundation
    role="status"
    aria-live="polite"
  >
    <AlertTitle
      class="tw:text-base tw:font-semibold tw:text-foreground"
      role="heading"
      aria-level="2"
    >
      {{ title }}
    </AlertTitle>
    <AlertDescription><slot /></AlertDescription>
    <slot name="details" />
    <slot name="action" />
  </Alert>
</template>

<script setup lang="ts">
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

defineProps<{ title: string }>();
</script>
