<template>
  <Alert
    class="workspace-capability-notice workspace-foundation"
    data-workspace-foundation
    role="status"
    aria-live="polite"
  >
    <AlertTitle>{{ label }}</AlertTitle>
    <AlertDescription><slot /></AlertDescription>
  </Alert>
</template>

<script setup lang="ts">
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

defineProps<{ label: string }>();
</script>
