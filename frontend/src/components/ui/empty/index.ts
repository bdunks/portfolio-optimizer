import type { VariantProps } from 'class-variance-authority';
import { cva } from 'class-variance-authority';

export { default as Empty } from './Empty.vue';
export { default as EmptyContent } from './EmptyContent.vue';
export { default as EmptyDescription } from './EmptyDescription.vue';
export { default as EmptyHeader } from './EmptyHeader.vue';
export { default as EmptyMedia } from './EmptyMedia.vue';
export { default as EmptyTitle } from './EmptyTitle.vue';

export const emptyMediaVariants = cva(
  'tw:mb-2 tw:flex tw:shrink-0 tw:items-center tw:justify-center tw:[&_svg]:pointer-events-none tw:[&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'tw:bg-transparent',
        icon: 'tw:bg-muted tw:text-foreground tw:flex tw:size-8 tw:shrink-0 tw:items-center tw:justify-center tw:rounded-lg tw:[&_svg:not([class*=size-])]:size-4',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export type EmptyMediaVariants = VariantProps<typeof emptyMediaVariants>;
