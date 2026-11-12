import type { VariantProps } from 'class-variance-authority';
import { cva } from 'class-variance-authority';

export const fieldVariants = cva(
  'tw:data-[invalid=true]:text-destructive tw:gap-2 tw:group/field tw:flex tw:w-full',
  {
    variants: {
      orientation: {
        vertical: 'tw:flex-col tw:*:w-full tw:[&>.sr-only]:w-auto',
        horizontal:
          'tw:flex-row tw:items-center tw:has-[>[data-slot=field-content]]:items-start tw:*:data-[slot=field-label]:flex-auto tw:has-[>[data-slot=field-content]]:[&>[role=checkbox],[role=radio]]:mt-px',
        responsive:
          'tw:flex-col tw:*:w-full tw:@md/field-group:flex-row tw:@md/field-group:items-center tw:@md/field-group:*:w-auto tw:@md/field-group:has-[>[data-slot=field-content]]:items-start tw:@md/field-group:*:data-[slot=field-label]:flex-auto tw:[&>.sr-only]:w-auto tw:@md/field-group:has-[>[data-slot=field-content]]:[&>[role=checkbox],[role=radio]]:mt-px',
      },
    },
    defaultVariants: {
      orientation: 'vertical',
    },
  },
);

export type FieldVariants = VariantProps<typeof fieldVariants>;

export { default as Field } from './Field.vue';
export { default as FieldContent } from './FieldContent.vue';
export { default as FieldDescription } from './FieldDescription.vue';
export { default as FieldError } from './FieldError.vue';
export { default as FieldGroup } from './FieldGroup.vue';
export { default as FieldLabel } from './FieldLabel.vue';
export { default as FieldLegend } from './FieldLegend.vue';
export { default as FieldSeparator } from './FieldSeparator.vue';
export { default as FieldSet } from './FieldSet.vue';
export { default as FieldTitle } from './FieldTitle.vue';
