<template>
  <q-page class="pending-page q-pa-md">
    <q-card flat bordered class="pending-card q-my-none q-mx-auto">
      <q-card-section>
        <p
          class="eyebrow q-mt-none q-mb-sm text-caption text-weight-bold text-teal-9 text-uppercase"
        >
          Development in progress
        </p>
        <h1 class="q-ma-none text-h4 text-blue-grey-10">{{ title }}</h1>
        <p class="pending-message q-mt-sm q-mb-md q-mx-none text-body1 text-blue-grey-8">
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
}

.eyebrow {
  letter-spacing: 0.1em;
}

.pending-message {
  max-width: 42rem;
}
</style>
