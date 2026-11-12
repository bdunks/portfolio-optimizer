import { z } from 'zod';

export const WASH_SALES_TRANSACTION_KINDS = ['BUY', 'SELL', 'DIVIDEND', 'OTHER'] as const;

export const washSalesFilterSchema = z.object({
  search: z.string(),
  transactionKind: z.union([z.literal(''), z.enum(WASH_SALES_TRANSACTION_KINDS)]),
});

export type WashSalesFilterValues = z.infer<typeof washSalesFilterSchema>;
export type WashSalesTransactionKind = (typeof WASH_SALES_TRANSACTION_KINDS)[number];

export function isWashSalesTransactionKind(value: string): value is WashSalesTransactionKind {
  return WASH_SALES_TRANSACTION_KINDS.some((kind) => kind === value);
}
