<template>
  <nav class="workspace-pagination" :aria-label="label">
    <q-btn
      type="button"
      flat
      dense
      no-caps
      aria-label="Previous page"
      :disable="pending || offset <= 0"
      @click="requestPage(-1)"
    >
      Previous page
    </q-btn>
    <span class="workspace-pagination__status" aria-live="polite">
      <slot name="status" :page-number="metadata.pageNumber" :page-count="metadata.pageCount">
        Page {{ metadata.pageNumber }} of {{ metadata.pageCount }}
      </slot>
    </span>
    <q-btn
      type="button"
      flat
      dense
      no-caps
      aria-label="Next page"
      :disable="nextDisabled"
      @click="requestPage(1)"
    >
      Next page
    </q-btn>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { getPaginationMetadata } from './workspace-pagination-state';

const props = withDefaults(
  defineProps<{
    offset: number;
    limit: number;
    total: number;
    label: string;
    pending?: boolean;
  }>(),
  { pending: false },
);
const emit = defineEmits<{ page: [offset: number] }>();
const metadata = computed(() => getPaginationMetadata(props.offset, props.limit, props.total));
const nextDisabled = computed(
  () => props.pending || props.total <= 0 || props.offset + metadata.value.pageSize >= props.total,
);

function requestPage(direction: -1 | 1): void {
  if (props.pending) return;
  if (direction < 0) {
    if (props.offset <= 0) return;
    emit('page', Math.max(0, props.offset - metadata.value.pageSize));
    return;
  }
  if (nextDisabled.value) return;
  emit('page', props.offset + metadata.value.pageSize);
}
</script>

<style scoped>
.workspace-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
}

.workspace-pagination__status {
  color: #526c7c;
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
}
</style>
