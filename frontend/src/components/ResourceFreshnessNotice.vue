<template>
  <Alert
    v-for="notice in notices"
    :key="notice"
    class="resource-freshness-notice workspace-foundation tw:my-2"
    data-workspace-foundation
    role="status"
    aria-live="polite"
  >
    <AlertDescription>{{ notice }}</AlertDescription>
  </Alert>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useWorkspace } from '@/composables/use-workspace';
import { selectResourceFreshnessNotices } from '@/stores/workspace-selectors';
import type { WorkspaceResourceKey } from '@/types/workspace-resources';

const props = defineProps<{ resources?: readonly WorkspaceResourceKey[] }>();
const store = useWorkspace();
const notices = computed(() =>
  selectResourceFreshnessNotices(store.resourceFreshness, props.resources),
);
</script>

<style scoped>
.resource-freshness-notice {
  overflow-wrap: anywhere;
}
</style>
