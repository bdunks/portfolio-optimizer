<script setup lang="ts">
import type { CheckboxRootEmits, CheckboxRootProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { CheckIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from 'reka-ui';

const props = defineProps<CheckboxRootProps & { class?: HTMLAttributes['class'] }>();
const emits = defineEmits<CheckboxRootEmits>();

const delegatedProps = reactiveOmit(props, 'class');
const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <CheckboxRoot
    #default="slotProps"
    data-slot="checkbox"
    v-bind="omitUndefinedProps(forwarded)"
    :class="
      cn(
        'tw:border-input tw:dark:bg-input/30 tw:data-checked:bg-primary tw:data-checked:text-primary-foreground tw:dark:data-checked:bg-primary tw:data-checked:border-primary tw:aria-invalid:aria-checked:border-primary tw:aria-invalid:border-destructive tw:dark:aria-invalid:border-destructive/50 tw:focus-visible:border-ring tw:focus-visible:ring-ring/50 tw:aria-invalid:ring-destructive/20 tw:dark:aria-invalid:ring-destructive/40 tw:flex tw:size-4 tw:items-center tw:justify-center tw:rounded-[4px] tw:border tw:transition-colors tw:group-has-disabled/field:opacity-50 tw:focus-visible:ring-3 tw:aria-invalid:ring-3 tw:peer tw:relative tw:shrink-0 tw:outline-none tw:after:absolute tw:after:-inset-x-3 tw:after:-inset-y-2 tw:disabled:cursor-not-allowed tw:disabled:opacity-50',
        props.class,
      )
    "
  >
    <CheckboxIndicator
      data-slot="checkbox-indicator"
      class="tw:[&>svg]:size-3.5 tw:grid tw:place-content-center tw:text-current tw:transition-none"
    >
      <slot v-bind="slotProps">
        <CheckIcon />
      </slot>
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
