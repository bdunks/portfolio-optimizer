export type PaginationMetadata = {
  pageNumber: number;
  pageCount: number;
  pageSize: number;
};

export function getPaginationMetadata(
  offset: number,
  limit: number,
  total: number,
): PaginationMetadata {
  const pageSize = Number.isFinite(limit) ? Math.max(1, Math.trunc(limit)) : 1;
  const currentOffset = Number.isFinite(offset) ? Math.max(0, Math.trunc(offset)) : 0;
  const itemTotal = Number.isFinite(total) ? Math.max(0, Math.trunc(total)) : 0;

  return {
    pageNumber: Math.floor(currentOffset / pageSize) + 1,
    pageCount: Math.max(1, Math.ceil(itemTotal / pageSize)),
    pageSize,
  };
}
