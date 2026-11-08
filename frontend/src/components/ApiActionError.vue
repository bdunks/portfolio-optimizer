<template>
  <div v-if="error" class="api-error" role="alert">
    <strong>{{ title }}</strong>
    <span
      ><code>{{ error.code }}</code
      >: {{ error.message }}</span
    >
    <small v-if="error.correlationId">Correlation ID: {{ error.correlationId }}</small>
  </div>
</template>

<script setup lang="ts">
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
  display: grid;
  gap: 0.3rem;
  padding: 0.8rem 1rem;
  border: 1px solid #efc2c2;
  border-radius: 0.65rem;
  background: #fff0f0;
  color: #812f36;
  overflow-wrap: anywhere;
}

.api-error code {
  font-weight: 700;
}

.api-error small {
  color: #68464a;
}
</style>
