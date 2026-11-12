<script setup lang="ts">
import { computed } from 'vue';
import type { CollapsibleRootEmits, CollapsibleRootProps } from 'reka-ui';
import { CollapsibleRoot, useForwardPropsEmits } from 'reka-ui';

const props = defineProps<CollapsibleRootProps>();
const emits = defineEmits<CollapsibleRootEmits>();
const forwarded = useForwardPropsEmits(props, emits);
const rootProps = computed(() => ({ ...forwarded.value, as: props.as ?? 'div' }));
</script>

<template>
  <CollapsibleRoot #default="slotProps" data-slot="collapsible" v-bind="rootProps">
    <slot v-bind="slotProps" />
  </CollapsibleRoot>
</template>
