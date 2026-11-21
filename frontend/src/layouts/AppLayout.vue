<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Menu } from '@element-plus/icons-vue'
import { useNotificationPolling } from '@/composables/useNotificationPolling'
import RoutePage from './RoutePage.vue'
import SideNav from './SideNav.vue'
import { useNav } from './nav'

const route = useRoute()
const drawer = ref(false)
useNotificationPolling()
const { current, page } = useNav()
const tabs = computed(() => (current.value && current.value.pages.length > 1 ? current.value.pages : []))
// The workbench greets by name instead of repeating its title.
const title = computed(() => (route.name === 'workbench' ? '' : String(route.meta.title ?? '')))

watch(
  () => route.fullPath,
  () => (drawer.value = false),
)
</script>

<template>
  <div class="shell">
    <aside class="sidebar"><SideNav /></aside>
    <el-drawer v-model="drawer" direction="ltr" size="260px" :with-header="false" class="nav-drawer">
      <SideNav />
    </el-drawer>
    <div class="body">
      <header class="topbar" :class="{ bare: !tabs.length && !title }">
        <el-button class="menu-btn" :icon="Menu" text aria-label="打开菜单" @click="drawer = true" />
        <template v-if="tabs.length">
          <h1 class="sr-only">{{ title }}</h1>
          <nav class="tabs" :aria-label="current!.label">
            <RouterLink
              v-for="p in tabs"
              :key="p.name"
              :to="{ name: p.name }"
              class="tab"
              :class="{ on: p.name === page }"
              :aria-current="p.name === page ? 'page' : undefined"
            >{{ p.label }}</RouterLink>
          </nav>
        </template>
        <h1 v-else class="title">{{ title }}</h1>
      </header>
      <main class="main">
        <RoutePage />
      </main>
    </div>
  </div>
</template>

<style scoped>
/* DESIGN.md: one grey ground for the sidebar and the page; the content sits on it in white cards. */
.shell {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  position: sticky;
  top: 0;
  /* sticky makes its own stacking layer: above the top bar, so the search panel opened from here covers the page */
  z-index: 20;
  flex: 0 0 240px;
  height: 100vh;
  overflow-y: auto;
  box-sizing: border-box;
  /* the menu is taller than a laptop screen: scroll it, but show the bar only while the pointer is over it */
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
.sidebar:hover {
  scrollbar-color: rgba(0, 0, 0, 0.2) transparent;
}
.body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 4px;
  height: 52px;
  padding: 0 24px 0 8px;
  /* The only frosted surface (DESIGN.md): cards scroll under it; solid where blur is off or unwanted. */
  background: rgba(242, 243, 245, 0.8);
  backdrop-filter: saturate(180%) blur(12px);
}
@supports not (backdrop-filter: blur(1px)) {
  .topbar { background: var(--lab-bg); }
}
@media (prefers-reduced-transparency: reduce), (forced-colors: active) {
  .topbar { background: var(--lab-bg); backdrop-filter: none; }
}
.menu-btn {
  display: none;
}
.title {
  margin: 0;
  padding-left: 4px;
  font-size: 17px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* A module's pages as pills; the current one is a white pill, like the current module in the sidebar. */
.tabs {
  display: flex;
  gap: 4px;
  min-width: 0;
  padding: 2px;
  overflow-x: auto;
  scrollbar-width: none;
}
.tab {
  flex: none;
  padding: 6px 14px;
  border-radius: 999px;
  color: var(--lab-text-2);
  white-space: nowrap;
}
.tab:hover {
  background: var(--lab-bg-hover);
  color: var(--lab-text);
  text-decoration: none;
}
.tab.on {
  background: var(--lab-bg-card);
  box-shadow: var(--lab-shadow-card);
  color: var(--lab-text);
  font-weight: 600;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
/* Nothing to show (the workbench): no empty bar on a computer; phones still need the menu button. */
@media (min-width: 769px) {
  .topbar.bare {
    display: none;
  }
  .topbar.bare + .main {
    padding-top: 24px;
  }
}
.main {
  box-sizing: border-box;
  padding: 4px 24px 48px 8px;
}
@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
  .menu-btn {
    display: inline-flex;
  }
  .topbar {
    padding: 0 8px;
  }
  .main {
    padding: 4px 12px 32px;
  }
}
</style>

<style>
.nav-drawer {
  --el-drawer-padding-primary: 0;
  background: var(--lab-bg);
}
.nav-drawer .el-drawer__body {
  scrollbar-width: thin;
}
</style>
