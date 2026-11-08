export const workspaceLinks = [
  { label: 'Overview', caption: 'Account snapshot', icon: 'dashboard', to: '/' },
  {
    label: 'Recommendations',
    caption: 'Review a proposed batch',
    icon: 'auto_awesome',
    to: '/recommendations',
  },
  { label: 'Tax Lots', caption: 'Lot-level holdings', icon: 'view_list', to: '/lots' },
  {
    label: 'Allocation Policy',
    caption: 'Targets and allowed securities',
    icon: 'tune',
    to: '/policy',
  },
  {
    label: 'Wash Sales',
    caption: 'Acquisition restrictions',
    icon: 'do_not_disturb',
    to: '/wash-sales',
  },
  { label: 'Activity', caption: 'Recent account events', icon: 'history', to: '/activity' },
] as const;
