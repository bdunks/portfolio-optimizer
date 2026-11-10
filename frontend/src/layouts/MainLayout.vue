<template>
  <q-layout view="lHh Lpr lFf" class="workspace-layout">
    <a class="skip-link q-py-sm q-px-md" href="#main-content" @click.prevent="focusMainContent">
      Skip to main content
    </a>
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
        <q-toolbar-title class="brand-title row no-wrap items-center q-gutter-sm">
          <span class="brand-mark row inline no-wrap flex-center" aria-hidden="true">PO</span>
          <span>Portfolio Optimizer</span>
        </q-toolbar-title>
        <span class="header-context">Single-account workspace</span>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="drawerOpen" show-if-above bordered :breakpoint="1024" class="bg-white">
      <div class="drawer-brand row no-wrap items-center q-gutter-sm q-py-lg q-px-md">
        <span class="brand-mark row inline no-wrap flex-center" aria-hidden="true">PO</span>
        <div class="column no-wrap">
          <strong>Portfolio Optimizer</strong>
          <small class="q-mt-xs">Local decision support</small>
        </div>
      </div>
      <nav aria-label="Primary navigation">
        <q-list padding>
          <q-item-label header class="text-overline text-weight-bold text-blue-grey-8"
            >Workspace</q-item-label
          >
          <q-item
            v-for="link in workspaceLinks"
            class="rounded-borders"
            :class="route.path === link.to ? 'text-white' : 'text-blue-grey-9'"
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
              <q-item-label
                caption
                :class="route.path === link.to ? 'text-white' : 'text-blue-grey-7'"
                >{{ link.caption }}</q-item-label
              >
            </q-item-section>
          </q-item>
        </q-list>
      </nav>
      <div class="drawer-footer q-mr-md q-mb-md q-ml-md q-pa-md column no-wrap q-gutter-y-xs">
        <strong>Local demo mode</strong>
        <span>No broker connection or order submission</span>
      </div>
    </q-drawer>

    <q-page-container>
      <q-banner
        dense
        rounded
        class="demo-banner bg-amber-1 text-brown-10"
        role="status"
        aria-label="Demo-only application notice"
      >
        <strong>DEMO ONLY</strong>
        <span
          >All analysis is non-actionable. No broker connection, OAuth, live writes, or
          trading.</span
        >
      </q-banner>
      <main id="main-content" ref="mainContent" class="workspace-main" tabindex="-1">
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

const mainContent = ref<HTMLElement | null>(null);

function focusMainContent(): void {
  mainContent.value?.focus();
}

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
  font-size: 1rem;
  font-weight: 800;
}

.brand-mark {
  width: 2rem;
  height: 2rem;
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

.drawer-brand strong {
  color: #10263d;
  font-size: 0.9rem;
}

.drawer-brand small {
  color: #546e7a;
  font-size: 0.68rem;
}

.workspace-nav-active {
  background: #2a4c67;
  box-shadow: inset 3px 0 0 #5bc5b7;
}

.drawer-footer {
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

.skip-link {
  position: fixed;
  z-index: 10000;
  top: 0.5rem;
  left: 0.5rem;
  transform: translateY(-160%);
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
}
</style>
