<template>
  <q-layout view="lHh Lpr lFf" class="workspace-layout">
    <a class="skip-link" href="#main-content">Skip to main content</a>
    <q-header class="workspace-header" elevated>
      <q-toolbar>
        <q-btn
          flat
          dense
          round
          icon="menu"
          aria-label="Toggle workspace navigation"
          class="lt-md"
          :aria-expanded="drawerOpen"
          @click="toggleDrawer"
        />
        <q-toolbar-title class="brand-title">
          <span class="brand-mark" aria-hidden="true">PO</span>
          <span>Portfolio Optimizer</span>
        </q-toolbar-title>
        <span class="header-context">Single-account workspace</span>
      </q-toolbar>
    </q-header>

    <q-drawer
      v-model="drawerOpen"
      show-if-above
      bordered
      :breakpoint="1024"
      class="workspace-drawer"
    >
      <div class="drawer-brand">
        <span class="brand-mark" aria-hidden="true">PO</span>
        <div>
          <strong>Portfolio Optimizer</strong>
          <small>Local decision support</small>
        </div>
      </div>
      <nav aria-label="Primary navigation">
        <q-list padding>
          <q-item-label header>Workspace</q-item-label>
          <q-item
            v-for="link in workspaceLinks"
            :key="link.to"
            clickable
            :to="link.to"
            :active="route.path === link.to"
            active-class="workspace-nav-active"
            :aria-current="route.path === link.to ? 'page' : undefined"
            @click="closeDrawerOnSmallScreen"
          >
            <q-item-section avatar>
              <q-icon :name="link.icon" aria-hidden="true" />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ link.label }}</q-item-label>
              <q-item-label caption>{{ link.caption }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </nav>
      <div class="drawer-footer">
        <strong>Local demo mode</strong>
        <span>No broker connection or order submission</span>
      </div>
    </q-drawer>

    <q-page-container>
      <q-banner class="demo-banner" role="status" aria-label="Demo-only application notice">
        <strong>DEMO ONLY</strong>
        <span
          >All analysis is non-actionable. No broker connection, OAuth, live writes, or
          trading.</span
        >
      </q-banner>
      <main id="main-content" class="workspace-main" tabindex="-1">
        <router-view />
      </main>
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import { workspaceLinks } from '@/navigation/workspace-navigation';

const route = useRoute();
const drawerOpen = ref(false);

function toggleDrawer(): void {
  drawerOpen.value = !drawerOpen.value;
}

function closeDrawerOnSmallScreen(): void {
  if (window.matchMedia('(max-width: 1024px)').matches) drawerOpen.value = false;
}
</script>

<style scoped>
.workspace-layout {
  min-height: 100vh;
  background: #f3f7f9;
  color: #172e41;
}

.workspace-header {
  background: #10263d;
  color: #fff;
}

.brand-title {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  font-size: 1rem;
  font-weight: 800;
}

.brand-mark {
  display: inline-grid;
  width: 2rem;
  height: 2rem;
  place-items: center;
  border-radius: 0.55rem;
  background: linear-gradient(145deg, #31b8b0, #007775);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 850;
}

.header-context {
  color: #c3d6e1;
  font-size: 0.78rem;
}

.workspace-drawer {
  background: linear-gradient(170deg, #10263e, #132f49 70%, #0d263c);
  color: #d5e3eb;
}

.drawer-brand {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 1.4rem 1.2rem 1.8rem;
}

.drawer-brand strong,
.drawer-brand small {
  display: block;
}

.drawer-brand strong {
  color: #fff;
  font-size: 0.9rem;
}

.drawer-brand small {
  margin-top: 0.2rem;
  color: #9fb6c4;
  font-size: 0.68rem;
}

.workspace-drawer :deep(.q-item-label--header) {
  color: #83a2b3;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.workspace-drawer :deep(.q-item) {
  margin: 0.15rem 0.6rem;
  border-radius: 0.55rem;
  color: #cfdee7;
}

.workspace-drawer :deep(.workspace-nav-active) {
  background: #2a4c67;
  color: #fff;
  box-shadow: inset 3px 0 0 #5bc5b7;
}

.workspace-drawer :deep(.q-item__label--caption) {
  color: #9cb2c0;
}

.workspace-drawer :deep(.workspace-nav-active .q-item__label--caption) {
  color: #c3d9e1;
}

.drawer-footer {
  display: grid;
  gap: 0.35rem;
  margin: 1.2rem 0.8rem 0.8rem;
  padding: 0.9rem;
  border: 1px solid #3b5870;
  border-radius: 0.6rem;
  background: #1c3a53;
  font-size: 0.72rem;
}

.drawer-footer strong {
  color: #fff;
}

.drawer-footer span {
  color: #b9ced9;
  line-height: 1.45;
}

.demo-banner {
  display: flex;
  gap: 0.65rem;
  align-items: center;
  border: 1px solid #f2dcad;
  background: #fff7e8;
  color: #765016;
  font-size: 0.8rem;
}

.demo-banner strong {
  flex: 0 0 auto;
  font-size: 0.7rem;
  letter-spacing: 0.05em;
}

.workspace-main {
  min-height: calc(100vh - 3.15rem);
}

.skip-link {
  position: fixed;
  z-index: 10000;
  top: 0.5rem;
  left: 0.5rem;
  transform: translateY(-160%);
  padding: 0.7rem 1rem;
  border-radius: 0.4rem;
  background: #fff;
  color: #10263d;
  font-weight: 800;
}

.skip-link:focus {
  transform: translateY(0);
  outline: 3px solid #20a59f;
  outline-offset: 2px;
}

@media (max-width: 600px) {
  .header-context {
    display: none;
  }

  .demo-banner {
    align-items: flex-start;
  }
}
</style>
