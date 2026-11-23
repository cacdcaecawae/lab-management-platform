<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch, watchPostEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, Close, Menu } from '@element-plus/icons-vue'
import { useNotificationPolling } from '@/composables/useNotificationPolling'
import { useAuthStore } from '@/stores/auth'
import RoutePage from './RoutePage.vue'
import SideNav from './SideNav.vue'
import PhoneTabBar from './PhoneTabBar.vue'
import { labelTableCells, pageHeaders, phone } from './phone'
import { closeAllTabs, closeOtherTabs, closeTab, neighborTab, openedTabs, pageColor, sidebarFolded, trackTab, type OpenedTab } from './nav'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const drawer = ref(false)
useNotificationPolling()
// Every page you open (lists and records) becomes a tab in one strip shared by all modules (DESIGN.md); none at first.
// The tab on screen is white and joins the card under it; each tab has its module's colour dot.
watch([() => route.fullPath, () => auth.user?.id], () => trackTab(auth.user?.id, route), { immediate: true })
const tabs = computed(() => openedTabs())
const onTab = computed(() => tabs.value.some((t) => t.path === route.path))
const dot = (t: OpenedTab) => {
  const r = router.resolve(t.full)
  return pageColor(String(r.meta.menu ?? r.name ?? ''))
}
// Closing the page on screen leaves it first; if "有未保存的修改" keeps you there, its tab stays too.
async function close(t: OpenedTab) {
  if (t.path === route.path && (await router.push(neighborTab(t.path)?.full ?? { name: 'workbench' }))) return
  closeTab(t.path)
}
async function closeAll() {
  if (onTab.value && (await router.push({ name: 'workbench' }))) return
  closeAllTabs()
}
// The ▾ menu at the right end: every open tab (handy once they no longer fit), then close others / close all.
function onMenu(command: string) {
  if (command === 'others') closeOtherTabs(route.path)
  else if (command === 'all') void closeAll()
  else router.push(command)
}
// When many tabs are open, bring the current one into view (the last tab would otherwise sit off-screen).
const tabsNav = useTemplateRef<HTMLElement>('tabsNav')
// Runs after each render that changes the page or the tabs.
watchPostEffect(() => {
  void route.path
  void tabs.value.length
  tabsNav.value?.querySelector('.on')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
})
// The workbench greets by name instead of repeating its title.
const title = computed(() => (route.name === 'workbench' ? '' : String(route.meta.title ?? '')))

// Phone (DESIGN.md "手机"): a bottom tab bar instead of the menu button (not for ops, whose pages are all in the menu), no tab strip,
// and the top bar only on list pages: the page name and the list's buttons (#phone-actions). Detail pages carry their
// own back + title in the card.
const tabBar = computed(() => phone.value && !!auth.user?.group)
const phoneBarHidden = computed(() => phone.value && tabBar.value && (!title.value || pageHeaders.value > 0))
// Tables become cards on a phone; the cards need each cell's column name. Dialogs live under <body>, so watch it all
// while on a phone (stopped on desktop so normal mutations do not trigger it).
let observer: MutationObserver | undefined
let queued = 0
const relabel = () => {
  if (!phone.value || queued) return
  queued = requestAnimationFrame(() => {
    queued = 0
    labelTableCells(document.body)
  })
}
function stopObserver() {
  observer?.disconnect()
  observer = undefined
  if (queued) {
    cancelAnimationFrame(queued)
    queued = 0
  }
}
function syncObserver(on: boolean) {
  stopObserver()
  if (!on) return
  observer = new MutationObserver(relabel)
  observer.observe(document.body, { childList: true, subtree: true, characterData: true })
  relabel()
}
onMounted(() => syncObserver(phone.value))
onBeforeUnmount(stopObserver)
watch(phone, syncObserver)

watch(
  () => route.fullPath,
  () => (drawer.value = false),
)
</script>

<template>
  <div class="shell" :class="{ 'with-tab-bar': tabBar }">
    <aside v-if="!phone" class="sidebar" :class="{ folded: sidebarFolded }"><SideNav foldable /></aside>
    <el-drawer v-if="phone" v-model="drawer" direction="ltr" size="260px" :with-header="false" class="nav-drawer">
      <SideNav @close="drawer = false" />
    </el-drawer>
    <div class="body">
      <header
        class="topbar"
        :class="{ bare: !tabs.length && !title, 'with-tabs': tabs.length, joined: onTab, 'phone-hidden': phoneBarHidden }"
      >
        <el-button v-if="!tabBar" class="menu-btn" :icon="Menu" text aria-label="打开菜单" @click="drawer = true" />
        <!-- with tabs, the page name is for screen readers only: its tab (or the card header) shows it; phones have no tabs -->
        <h1 v-if="title" :class="tabs.length && !phone ? 'sr-only' : 'title'">{{ title }}</h1>
        <nav v-if="tabs.length" ref="tabsNav" class="tabs" aria-label="打开的页面">
          <span v-for="t in tabs" :key="t.path" class="tab" :class="{ on: t.path === route.path }">
            <span class="dot" :style="{ background: dot(t) }" aria-hidden="true" />
            <RouterLink :to="t.full" class="tab-link" :title="t.title" :aria-current="t.path === route.path ? 'page' : undefined">{{
              t.title
            }}</RouterLink>
            <button type="button" class="tab-close" :aria-label="`关闭 ${t.title}`" @click="close(t)">
              <el-icon><Close /></el-icon>
            </button>
          </span>
        </nav>
        <el-dropdown v-if="tabs.length" trigger="click" placement="bottom-end" class="tabs-menu" @command="onMenu">
          <button type="button" class="tabs-menu-btn" aria-label="全部标签"><el-icon><ArrowDown /></el-icon></button>
          <template #dropdown>
            <el-dropdown-menu class="tabs-menu-list">
              <el-dropdown-item v-for="t in tabs" :key="t.path" :command="t.full" :class="{ current: t.path === route.path }">
                <span class="dot" :style="{ background: dot(t) }" aria-hidden="true" />{{ t.title }}
              </el-dropdown-item>
              <el-dropdown-item command="others" divided :disabled="!onTab || tabs.length < 2">关闭其他标签</el-dropdown-item>
              <el-dropdown-item command="all">关闭全部标签</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <!-- phone: the list page's buttons, moved here by PageToolbar -->
        <div id="phone-actions" class="phone-actions" />
      </header>
      <main class="main">
        <RoutePage />
      </main>
    </div>
    <PhoneTabBar v-if="tabBar" @menu="drawer = true" />
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
  box-sizing: border-box;
}
.sidebar.folded {
  flex-basis: 64px;
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
/* Browser / webmail-style tabs (DESIGN.md): grey with rounded top corners; the one on screen is white and joins the
   white card under it (the strip starts past the card's rounded corner). */
.topbar.with-tabs {
  align-items: flex-end;
}
.topbar.with-tabs .menu-btn {
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
@media (min-width: 769px) {
  .topbar.joined + .main {
    padding-top: 0;
  }
  /* tabs, none of them this page (the workbench, a -new form): leave room under the strip */
  .topbar.with-tabs:not(.joined) + .main {
    padding-top: 20px;
  }
  .phone-actions {
    display: none;
  }
}
/* A tab: module colour dot, title (cut off past 220px, full text on hover), close button. */
.tab {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 220px;
  height: 36px;
  padding: 0 8px 0 14px;
  border-radius: 10px 10px 0 0;
  background: var(--lab-bg-hover);
  color: var(--lab-text-2);
  white-space: nowrap;
}
.tab:hover {
  background: #dadbe0;
  color: var(--lab-text);
}
.tab.on {
  background: var(--lab-bg-card);
  color: var(--lab-text);
  font-weight: 600;
}
.dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.tab-link {
  overflow: hidden;
  color: inherit;
  text-overflow: ellipsis;
}
.tab-link:hover {
  text-decoration: none;
}
.tab-link:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
.tab-close {
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
.tab-close:hover,
.tab-close:focus-visible {
  background: rgba(0, 0, 0, 0.08);
  opacity: 1;
}
.tab-close:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 1px;
}
/* ▾ at the right end, level with the tabs; it does not scroll with them. */
.tabs-menu {
  flex: none;
  align-self: flex-end;
  margin: 0 0 4px 4px;
}
.tabs-menu-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--lab-text-2);
  cursor: pointer;
}
.tabs-menu-btn:hover,
.tabs-menu-btn:focus-visible {
  background: var(--lab-bg-hover);
  color: var(--lab-text);
}
.tabs-menu-btn:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 1px;
}
.tabs-menu-list .dot {
  margin-right: 8px;
}
/* :deep — the item's own element is rendered by Element Plus and carries no scope attribute */
.tabs-menu-list :deep(.current) {
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
  .sidebar,
  .tabs,
  .tabs-menu,
  .topbar.phone-hidden {
    display: none;
  }
  .menu-btn {
    display: inline-flex;
  }
  .topbar,
  .topbar.with-tabs {
    align-items: center;
    padding: 0 12px 0 16px; /* right edge in line with the cards */
  }
  .topbar .menu-btn {
    margin-left: -8px;
  }
  .phone-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .main {
    padding: 4px 12px 32px;
  }
  .topbar.phone-hidden + .main {
    padding-top: 12px;
  }
  /* room for the tab bar (56px) and the phone's home indicator */
  .with-tab-bar .main {
    padding-bottom: calc(72px + env(safe-area-inset-bottom));
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
