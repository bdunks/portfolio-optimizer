<template>
  <nav
    class="workspace-pagination tw:flex tw:min-w-0 tw:flex-wrap tw:items-center tw:justify-between tw:gap-2"
    :aria-label="label"
  >
    <Button
      type="button"
      variant="outline"
      size="sm"
      class="tw:shrink-0"
      aria-label="Previous page"
      :disabled="pending || offset <= 0"
      @click="requestPage(-1)"
    >
      Previous page
    </Button>
    <span
      class="workspace-pagination__status tw:min-w-0 tw:break-words tw:text-sm tw:tabular-nums tw:text-muted-foreground"
      aria-live="polite"
    >
      <slot name="status" :page-number="metadata.pageNumber" :page-count="metadata.pageCount">
        Page {{ metadata.pageNumber }} of {{ metadata.pageCount }}
      </slot>
    </span>
    <Button
      type="button"
      variant="outline"
      size="sm"
      class="tw:shrink-0"
      aria-label="Next page"
      :disabled="nextDisabled"
      @click="requestPage(1)"
    >
      Next page
    </Button>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Button } from '@/components/ui/button';
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
