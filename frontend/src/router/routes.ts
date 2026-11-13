import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      {
        path: '',
        name: 'overview',
        component: () => import('@/pages/IndexPage.vue'),
        meta: { title: 'Overview' },
      },
      {
        path: 'recommendations',
        name: 'recommendations',
        component: () => import('@/pages/RecommendationsPage.vue'),
        meta: { title: 'Recommendations' },
      },
      {
        path: 'review',
        name: 'selected-basket-review',
        component: () => import('@/pages/SelectedBasketReviewPage.vue'),
        meta: { title: 'Selected Basket Review' },
      },
      {
        path: 'lots',
        name: 'lots',
        component: () => import('@/pages/TaxLotsPage.vue'),
        meta: { title: 'Tax Lots' },
      },
      {
        path: 'policy',
        name: 'policy',
        component: () => import('@/pages/PolicyPage.vue'),
        meta: { title: 'Allocation Policy' },
      },
      {
        path: 'wash-sales',
        name: 'wash-sales',
        component: () => import('@/pages/WashSalesPage.vue'),
        meta: { title: 'Wash Sales' },
      },
      {
        path: 'activity',
        name: 'activity',
        component: () => import('@/pages/ActivityPage.vue'),
        meta: { title: 'Activity' },
      },
    ],
  },

  // Always leave this as last one,
  {
    path: '/:catchAll(.*)*',
    component: () => import('@/pages/ErrorNotFound.vue'),
  },
];

export default routes;
