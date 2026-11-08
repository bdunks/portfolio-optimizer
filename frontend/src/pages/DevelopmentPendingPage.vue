<template>
  <q-page class="pending-page">
    <q-card flat bordered class="pending-card">
      <q-card-section>
        <p class="eyebrow">Development in progress</p>
        <h1>{{ title }}</h1>
        <p class="pending-message">
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
.pending-page {
  padding: clamp(1rem, 3vw, 2rem);
}

.pending-card {
  max-width: 52rem;
  margin: 0 auto;
  border-radius: 0.85rem;
  background: #fff;
}

.eyebrow {
  margin: 0 0 0.4rem;
  color: #087f7d;
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: #10263d;
  font-size: clamp(1.6rem, 4vw, 2.2rem);
}

.pending-message {
  max-width: 42rem;
  margin: 0.7rem 0 1.2rem;
  color: #5d7686;
  line-height: 1.6;
}
</style>
