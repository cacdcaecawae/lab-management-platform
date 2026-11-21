<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Menu } from '@element-plus/icons-vue'
import { useNotificationPolling } from '@/composables/useNotificationPolling'
import RoutePage from './RoutePage.vue'
import SideNav from './SideNav.vue'

const route = useRoute()
const drawer = ref(false)
useNotificationPolling()

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
      <header class="topbar">
        <el-button class="menu-btn" :icon="Menu" text aria-label="打开菜单" @click="drawer = true" />
        <h1 class="title">{{ route.meta.title }}</h1>
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
  font-size: 17px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
