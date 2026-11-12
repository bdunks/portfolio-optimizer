export type WorkspaceResourceKey =
  'health' | 'portfolio' | 'policy' | 'lots' | 'washSales' | 'activity';

export type ResourceFreshnessStatus = 'not-loaded' | 'fresh' | 'stale' | 'error';
export type ResourceFreshness = {
  status: ResourceFreshnessStatus;
  confirmedAt: string | null;
};
export type WorkspaceResourceFreshness = Record<WorkspaceResourceKey, ResourceFreshness>;
