import { z } from 'zod';

const policySleeveFormRowSchema = z.object({
  sleeve_key: z.string(),
  display_name: z.string(),
  sort_order: z.number(),
  parent_sleeve_key: z.string().nullable(),
  target_pct: z.string(),
  drift_band_pp: z.string(),
  is_direct_index_container: z.boolean(),
  is_direct_index_sleeve: z.boolean(),
  is_transition_destination: z.boolean(),
  is_cash_sleeve: z.boolean(),
  enabled: z.boolean(),
});

export const policySleevesFormSchema = z.object({
  sleeves: z.array(policySleeveFormRowSchema),
  deletion: z.object({
    sleeveKey: z.string(),
    targetKey: z.string(),
    childReparents: z.record(z.string(), z.string().nullable()),
  }),
});

export type PolicySleeveFormRow = z.infer<typeof policySleeveFormRowSchema>;
export type PolicySleevesFormValues = z.infer<typeof policySleevesFormSchema>;
