import { z } from 'zod';

export const policyRevisionSelectionValuesSchema = z.object({
  revisionId: z.string(),
});

export type PolicyRevisionFormValues = z.infer<typeof policyRevisionSelectionValuesSchema>;

export function createPolicyRevisionSelectionSchema(availableRevisionIds: () => readonly string[]) {
  return policyRevisionSelectionValuesSchema.extend({
    revisionId: z
      .string()
      .refine((revisionId) => revisionId === '' || availableRevisionIds().includes(revisionId), {
        message: 'Select a policy revision that is currently available.',
      }),
  });
}
