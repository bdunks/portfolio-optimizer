<template>
  <q-page class="pending-page q-pa-md">
    <q-card flat bordered class="pending-card q-my-none q-mx-auto">
      <q-card-section>
        <p class="eyebrow q-mt-none q-mb-sm q-mx-none">Development in progress</p>
        <h1 class="q-ma-none">{{ title }}</h1>
        <p class="pending-message q-mt-sm q-mb-md q-mx-none">
          This workspace section is not implemented yet. No sample holdings, recommendations, or
          policy data are being presented here.
        </p>
        <q-btn color="primary" outline to="/" label="Return to overview" no-caps />
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
const route = useRoute();
const title = computed(() => {
  const value = route.meta.title;
  return typeof value === 'string' ? value : 'Workspace section';
});
</script>

<style scoped>
.pending-card {
  max-width: 52rem;
  border-radius: 0.85rem;
  background: #fff;
}

.eyebrow {
  color: #087f7d;
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

h1 {
  color: #10263d;
  font-size: clamp(1.6rem, 4vw, 2.2rem);
}

.pending-message {
  max-width: 42rem;
  color: #5d7686;
  line-height: 1.6;
}
</style>
