<template>
  <q-banner
    v-for="notice in notices"
    :key="notice"
    dense
    rounded
    class="resource-freshness-notice q-my-sm bg-amber-1 text-brown-10"
    role="status"
    aria-live="polite"
  >
    {{ notice }}
  </q-banner>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import { selectResourceFreshnessNotices } from '@/stores/workspace-selectors';
import type { WorkspaceResourceKey } from '@/stores/workspace-resources';

const props = defineProps<{ resources?: readonly WorkspaceResourceKey[] }>();
const store = useWorkspaceStore();
const notices = computed(() =>
  selectResourceFreshnessNotices(store.resourceFreshness, props.resources),
);
</script>

<style scoped>
.resource-freshness-notice {
  overflow-wrap: anywhere;
}
</style>
