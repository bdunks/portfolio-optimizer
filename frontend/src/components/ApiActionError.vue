<template>
  <Alert
    v-if="error"
    class="api-error workspace-foundation"
    data-workspace-foundation
    variant="destructive"
    role="alert"
    aria-live="assertive"
  >
    <AlertTitle>{{ title }}</AlertTitle>
    <AlertDescription>
      <code class="tw:font-bold">{{ error.code }}</code>: {{ error.message }}
      <small v-if="error.correlationId" class="tw:block">
        Correlation ID: {{ error.correlationId }}
      </small>
    </AlertDescription>
  </Alert>
</template>

<script setup lang="ts">
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import type { ApiError } from '@/services/api';

withDefaults(
  defineProps<{
    error: ApiError | null;
    title: string;
  }>(),
  { title: 'Request failed' },
);
</script>

<style scoped>
.api-error {
  overflow-wrap: anywhere;
}
</style>
