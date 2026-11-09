<template>
  <p
    v-for="notice in notices"
    :key="notice"
    class="resource-freshness-notice q-my-sm q-mx-none q-pa-sm"
    role="status"
  >
    {{ notice }}
  </p>
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
  border: 1px solid #e6cb8d;
  border-radius: 0.5rem;
  background: #fff8e9;
  color: #765016;
  font-size: 0.78rem;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
</style>
