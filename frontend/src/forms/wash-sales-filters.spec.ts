import { describe, expect, it } from 'vitest';
import {
  isWashSalesTransactionKind,
  washSalesFilterSchema,
  WASH_SALES_TRANSACTION_KINDS,
} from './wash-sales-filters';

describe('wash-sales filters', () => {
  it('keeps accepted transaction-kind choices and validates each', () => {
    expect(WASH_SALES_TRANSACTION_KINDS).toEqual(['BUY', 'SELL', 'DIVIDEND', 'OTHER']);
    for (const transactionKind of WASH_SALES_TRANSACTION_KINDS) {
      expect(washSalesFilterSchema.safeParse({ search: '', transactionKind }).success).toBe(true);
      expect(isWashSalesTransactionKind(transactionKind)).toBe(true);
    }
    expect(washSalesFilterSchema.safeParse({ search: '', transactionKind: '' }).success).toBe(true);
  });

  it('rejects invalid filter values without coercing them into valid choices', () => {
    expect(washSalesFilterSchema.safeParse({ search: '', transactionKind: 'WASH' }).success).toBe(
      false,
    );
    const invalidSearch = washSalesFilterSchema.safeParse({
      search: 42,
      transactionKind: '',
    });
    expect(invalidSearch.success).toBe(false);
    expect(isWashSalesTransactionKind('buy')).toBe(false);
  });
});
