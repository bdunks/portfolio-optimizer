import { z } from 'zod';

export const tradeGroupNoteSchema = z
  .string()
  .max(2000, 'Group notes must be 2,000 characters or fewer.');

export const tradeGroupRejectionReasonSchema = z
  .string()
  .refine((reason) => reason.trim().length > 0, 'Enter a rejection reason.')
  .refine(
    (reason) => reason.trim().length <= 500,
    'Rejection reasons must be 500 characters or fewer.',
  );
