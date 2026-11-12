import type { VariantProps } from 'class-variance-authority';
import { cva } from 'class-variance-authority';

export { default as Badge } from './Badge.vue';

export const badgeVariants = cva(
  'tw:h-5 tw:gap-1 tw:rounded-4xl tw:border tw:border-transparent tw:px-2 tw:py-0.5 tw:text-xs tw:font-medium tw:transition-all tw:has-data-[icon=inline-end]:pr-1.5 tw:has-data-[icon=inline-start]:pl-1.5 tw:[&>svg]:size-3! tw:group/badge tw:inline-flex tw:w-fit tw:shrink-0 tw:items-center tw:justify-center tw:overflow-hidden tw:whitespace-nowrap tw:focus-visible:border-ring tw:focus-visible:ring-3 tw:focus-visible:ring-ring/50 tw:aria-invalid:border-destructive tw:aria-invalid:ring-destructive/20 tw:dark:aria-invalid:ring-destructive/40 tw:[&>svg]:pointer-events-none',
  {
    variants: {
      variant: {
        default: 'tw:bg-primary tw:text-primary-foreground tw:[a]:hover:bg-primary/80',
        secondary: 'tw:bg-secondary tw:text-secondary-foreground tw:[a]:hover:bg-secondary/80',
        destructive:
          'tw:bg-destructive/10 tw:[a]:hover:bg-destructive/20 tw:focus-visible:ring-destructive/20 tw:dark:focus-visible:ring-destructive/40 tw:text-destructive tw:dark:bg-destructive/20',
        outline:
          'tw:border-border tw:text-foreground tw:[a]:hover:bg-muted tw:[a]:hover:text-muted-foreground',
        ghost: 'tw:hover:bg-muted tw:hover:text-muted-foreground tw:dark:hover:bg-muted/50',
        link: 'tw:text-primary tw:underline-offset-4 tw:hover:underline',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);
export type BadgeVariants = VariantProps<typeof badgeVariants>;
