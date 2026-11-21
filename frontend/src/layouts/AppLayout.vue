<script setup lang="ts">
import { computed, ref, useTemplateRef, watch, watchPostEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Close, Menu } from '@element-plus/icons-vue'
import { useNotificationPolling } from '@/composables/useNotificationPolling'
import { useAuthStore } from '@/stores/auth'
import RoutePage from './RoutePage.vue'
import SideNav from './SideNav.vue'
import { closeTab, openedTabs, trackTab, useNav, type OpenedTab } from './nav'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const drawer = ref(false)
useNotificationPolling()
const { current, page } = useNav()
const tabs = computed(() => (current.value && current.value.pages.length > 1 ? current.value.pages : []))
// Records opened anywhere stay as tabs on every page, after the current module's pages (webmail-style); while one is
// shown, its list page is not highlighted. The current tab joins the card under it.
watch([() => route.fullPath, () => auth.user?.id], () => trackTab(auth.user?.id, route), { immediate: true })
const docs = computed(() => openedTabs())
const onDoc = computed(() => docs.value.some((t) => t.path === route.path))
const joined = computed(() => tabs.value.length > 0 || onDoc.value)
function close(t: OpenedTab) {
  closeTab(t.path)
  if (t.path === route.path) router.push({ name: String(route.meta.menu) })
}
// On a phone the tabs scroll sideways: bring the current one into view (the last tab would otherwise sit off-screen).
const tabsNav = useTemplateRef<HTMLElement>('tabsNav')
// Runs after each render that changes the page or brings the tabs in (they wait for the signed-in user).
watchPostEffect(() => {
  void page.value
  tabsNav.value?.querySelector('.on')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
})
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
      <header class="topbar" :class="{ bare: !tabs.length && !docs.length && !title, 'with-tabs': tabs.length || docs.length, joined }">
        <el-button class="menu-btn" :icon="Menu" text aria-label="打开菜单" @click="drawer = true" />
        <!-- a module with its own page tabs names itself only for screen readers -->
        <h1 v-if="title" :class="tabs.length ? 'sr-only' : 'title'">{{ title }}</h1>
        <template v-if="tabs.length || docs.length">
          <nav ref="tabsNav" class="tabs" :aria-label="tabs.length ? `${current!.label}和打开的记录` : '打开的记录'">
            <RouterLink
              v-for="p in tabs"
              :key="p.name"
              :to="{ name: p.name }"
              class="tab"
              :class="{ on: p.name === page && !onDoc }"
              :aria-current="p.name === page && !onDoc ? 'page' : undefined"
            >{{ p.label }}</RouterLink>
            <span v-if="tabs.length && docs.length" class="tabs-sep" aria-hidden="true" />
            <span v-for="t in docs" :key="t.path" class="tab doc" :class="{ on: t.path === route.path }">
              <RouterLink :to="t.full" class="doc-link" :title="t.title" :aria-current="t.path === route.path ? 'page' : undefined">{{
                t.title
              }}</RouterLink>
              <button type="button" class="doc-close" :aria-label="`关闭 ${t.title}`" @click="close(t)">
                <el-icon><Close /></el-icon>
              </button>
            </span>
          </nav>
        </template>
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
/* Webmail / browser-style tabs (DESIGN.md): grey tabs with rounded top corners; the current one is white and joins
   the white card under it (the strip starts past the card's rounded corner). A module's pages first, then the
   records opened in it. */
.topbar.with-tabs {
  align-items: flex-end;
}
.topbar.with-tabs .menu-btn,
.topbar.with-tabs .title {
  align-self: center;
}
.tabs {
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 2px;
  min-width: 0;
  padding-left: 16px;
  overflow-x: auto;
  scroll-padding-inline: 16px; /* scrolling the current tab into view keeps it off the card's rounded corners */
  scrollbar-width: none;
}
/* the same clearance at the end, so the last tab also lands on the card's straight edge */
.tabs::after {
  content: '';
  flex: none;
  width: 16px;
}
.topbar.joined + .main {
  padding-top: 0;
}
/* only opened records, none of them current (the workbench, 通知, 成员): leave room under the strip */
.topbar.with-tabs:not(.joined) + .main {
  padding-top: 20px;
}
.tab {
  flex: none;
  height: 36px;
  padding: 0 18px;
  border-radius: 10px 10px 0 0;
  background: var(--lab-bg-hover);
  color: var(--lab-text-2);
  line-height: 36px;
  white-space: nowrap;
}
.tab:hover {
  background: #dadbe0;
  color: var(--lab-text);
  text-decoration: none;
}
.tab.on {
  background: var(--lab-bg-card);
  color: var(--lab-text);
  font-weight: 600;
}
.tab:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -4px;
}
.tabs-sep {
  flex: none;
  width: 10px;
}
/* An opened record: its title (cut off past 220px, full text on hover) and a close button. */
.tab.doc {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 220px;
  padding-right: 8px;
}
.doc-link {
  overflow: hidden;
  color: inherit;
  text-overflow: ellipsis;
}
.doc-link:hover {
  text-decoration: none;
}
.doc-close {
  flex: none;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font-size: 12px;
  opacity: 0.7;
  cursor: pointer;
}
.doc-close:hover,
.doc-close:focus-visible {
  background: rgba(0, 0, 0, 0.08);
  opacity: 1;
}
.doc-close:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 1px;
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
    padding: 0 12px 0 8px; /* right edge in line with the cards */
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
