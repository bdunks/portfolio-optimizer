import { createRouter, createWebHashHistory } from 'vue-router';
import routes from './routes';

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  scrollBehavior: (to) => {
    if (to.hash) {
      const target = document.getElementById(to.hash.slice(1));
      if (target) {
        target.focus({ preventScroll: true });
        return { el: target };
      }
    }
    return { left: 0, top: 0 };
  },
  routes,
});

export default router;
