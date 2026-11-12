<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import type { BadgeVariants } from '.';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { Primitive } from 'reka-ui';
import { badgeVariants } from '.';

const props = withDefaults(
  defineProps<
    PrimitiveProps & {
      variant?: BadgeVariants['variant'];
      class?: HTMLAttributes['class'];
    }
  >(),
  {
    as: 'div',
    asChild: false,
    variant: 'default',
  },
);

const delegatedProps = reactiveOmit(props, 'class');
</script>

<template>
  <Primitive
    data-slot="badge"
    :data-variant="variant"
    :class="cn(badgeVariants({ variant }), props.class)"
    v-bind="omitUndefinedProps(delegatedProps)"
  >
    <slot />
  </Primitive>
</template>
