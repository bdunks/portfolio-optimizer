import {
  HistoryIcon,
  LayoutDashboardIcon,
  ListChecksIcon,
  ShieldAlertIcon,
  SlidersHorizontalIcon,
  SparklesIcon,
} from '@lucide/vue';

export const workspaceLinks = [
  { label: 'Overview', caption: 'Account snapshot', icon: LayoutDashboardIcon, to: '/' },
  {
    label: 'Recommendations',
    caption: 'Review a proposed batch',
    icon: SparklesIcon,
    to: '/recommendations',
  },
  { label: 'Tax Lots', caption: 'Lot-level holdings', icon: ListChecksIcon, to: '/lots' },
  {
    label: 'Allocation Policy',
    caption: 'Targets and allowed securities',
    icon: SlidersHorizontalIcon,
    to: '/policy',
  },
  {
    label: 'Wash Sales',
    caption: 'Acquisition restrictions',
    icon: ShieldAlertIcon,
    to: '/wash-sales',
  },
  { label: 'Activity', caption: 'Recent account events', icon: HistoryIcon, to: '/activity' },
] as const;
