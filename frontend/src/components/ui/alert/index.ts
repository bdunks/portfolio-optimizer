import type { VariantProps } from 'class-variance-authority';
import { cva } from 'class-variance-authority';

export { default as Alert } from './Alert.vue';
export { default as AlertAction } from './AlertAction.vue';
export { default as AlertDescription } from './AlertDescription.vue';
export { default as AlertTitle } from './AlertTitle.vue';

export const alertVariants = cva(
  'tw:grid tw:gap-0.5 tw:rounded-lg tw:border tw:px-2.5 tw:py-2 tw:text-left tw:text-sm tw:has-data-[slot=alert-action]:relative tw:has-data-[slot=alert-action]:pr-18 tw:has-[>svg]:grid-cols-[auto_1fr] tw:has-[>svg]:gap-x-2 tw:*:[svg]:row-span-2 tw:*:[svg]:translate-y-0.5 tw:*:[svg]:text-current tw:*:[svg:not([class*=size-])]:size-4 tw:group/alert tw:relative tw:w-full',
  {
    variants: {
      variant: {
        default: 'tw:bg-card tw:text-card-foreground',
        destructive:
          'tw:text-destructive tw:bg-card tw:*:data-[slot=alert-description]:text-destructive/90 tw:*:[svg]:text-current',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export type AlertVariants = VariantProps<typeof alertVariants>;
