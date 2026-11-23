<script setup lang="ts">
import { computed, useTemplateRef, watch } from 'vue'
import type { MenuInstance } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useOpsStore } from '@/stores/ops'
import { pinGroup, pinnedGroups, useNav } from './nav'

// collapse: the computer's sidebar folded to its icons (DESIGN.md). A name shows on hover; a group's pages pop out
// beside it.
const props = defineProps<{ collapse?: boolean }>()
const notifications = useNotificationsStore()
const ops = useOpsStore()
const auth = useAuthStore()
watch(() => auth.isSuperuser, (yes) => yes && ops.load(), { immediate: true }) // the menu outlives a change of user
const { modules, page, current } = useNav()
// What needs ops goes on its menu item too: red when something must be fixed, blue when there is something to do.
const mark = (name: string) =>
  name === 'system-storage' && ops.storage?.attention ? { text: '需处理', kind: '' }
  : name === 'system-version' && ops.version?.update_available ? { text: '有更新', kind: 'info' }
  : null
// Folded, the words have no room: a dot on the module's icon instead, red unless all it says is 有更新.
type Shown = (typeof modules.value)[number]
const dot = (m: Shown) =>
  m.key === 'notifications' && notifications.unread ? 'danger'
  : m.pages.some((p) => mark(p.name)?.kind === '') ? 'danger'
  : m.pages.some((p) => mark(p.name)) ? 'info'
  : ''
const menu = useTemplateRef<MenuInstance>('menu')

// A module with several pages (for this role) is a group; its menu index is "g:<key>" so it never equals a page name.
const groupIndex = (key: string) => `g:${key}`
const currentGroup = computed(() => (current.value && current.value.pages.length > 1 ? groupIndex(current.value.key) : ''))
// Read at each (re)mount: the menu is rebuilt when the sidebar folds or unfolds, and Element Plus forgets open groups
// on folding.
const openeds = () => (props.collapse ? [] : [...pinnedGroups].map(groupIndex))
// Only the user's own clicks pin a group. Element Plus also "opens" the group of the active page by itself, and
// reports plain items as opened too (it files them with the groups), hence the g: check.
const isGroup = (index: string) => index.startsWith('g:')
const onOpen = (index: string) => !props.collapse && isGroup(index) && index !== currentGroup.value && pinGroup(index.slice(2), true)
const onClose = (index: string) => !props.collapse && isGroup(index) && pinGroup(index.slice(2), false)
watch(
  currentGroup,
  (next, prev) => {
    if (props.collapse) return // folded, a group opens only as the pop-out under the pointer
    if (prev && prev !== next && !pinnedGroups.has(prev.slice(2))) menu.value?.close(prev)
    if (next) menu.value?.open(next)
  },
  { flush: 'post' },
)
const tint = (m: { key: string; color?: boolean }) => (m.color ? { '--c': `var(--lab-mod-${m.key})` } : undefined)
</script>

<template>
  <el-menu
    ref="menu"
    :key="String(collapse)"
    class="app-menu"
    :default-active="page"
    :default-openeds="openeds()"
    :collapse="collapse"
    :collapse-transition="false"
    router
    @open="onOpen"
    @close="onClose"
  >
    <template v-for="m in modules" :key="m.key">
      <!-- aria-label: folded, the words are hidden and would leave screen readers with nameless items -->
      <el-sub-menu
        v-if="m.pages.length > 1"
        :index="groupIndex(m.key)"
        :class="{ gap: m.gap }"
        popper-class="app-menu-popup"
        :aria-label="collapse ? m.label : undefined"
      >
        <template #title>
          <!-- closed: the module's coloured icon; open: an arrow in its place (DESIGN.md). An <i>: Element Plus hides
               the title's <span>s when folded. -->
          <i class="mod-icon" :class="{ colored: m.color }" :style="tint(m)">
            <el-icon class="glyph"><component :is="m.icon" /></el-icon>
            <el-icon class="arrow"><ArrowDown /></el-icon>
            <b v-if="collapse && dot(m)" class="dot" :class="dot(m)" />
          </i>
          <span>{{ m.label }}</span>
        </template>
        <li v-if="collapse" class="pop-title" role="presentation">{{ m.label }}</li>
        <el-menu-item v-for="p in m.pages" :key="p.name" :index="p.name" :route="{ name: p.name }">
          <span class="label">{{ p.label }}</span>
          <span v-if="mark(p.name)" class="badge" :class="mark(p.name)!.kind">{{ mark(p.name)!.text }}</span>
        </el-menu-item>
      </el-sub-menu>
      <el-menu-item
        v-else
        :index="m.pages[0]!.name"
        :route="{ name: m.pages[0]!.name }"
        :class="{ gap: m.gap }"
        :aria-label="collapse ? m.label : undefined"
      >
        <i class="mod-icon" :class="{ colored: m.color }" :style="tint(m)">
          <el-icon class="glyph"><component :is="m.icon" /></el-icon>
          <b v-if="collapse && dot(m)" class="dot" :class="dot(m)" />
        </i>
        <!-- the title slot is also the hover name when folded -->
        <template #title>
          <span class="label">{{ m.label }}</span>
          <!-- counts that need someone go on the menu item (DESIGN.md), not in a pop-up -->
          <span v-if="m.key === 'notifications' && notifications.unread" class="badge">{{ notifications.unread > 99 ? '99+' : notifications.unread }}</span>
          <span v-else-if="mark(m.pages[0]!.name)" class="badge" :class="mark(m.pages[0]!.name)!.kind">{{ mark(m.pages[0]!.name)!.text }}</span>
        </template>
      </el-menu-item>
    </template>
  </el-menu>
</template>

<style scoped>
.app-menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: var(--lab-text);
  --el-menu-active-color: var(--lab-text);
  --el-menu-hover-bg-color: var(--lab-bg-hover);
  --el-menu-item-height: 36px;
  --el-menu-sub-item-height: 36px;
  --el-menu-item-font-size: 14px;
  border-right: none;
  padding: 0 10px;
}
.app-menu .el-menu-item,
.app-menu :deep(.el-sub-menu__title) {
  height: 36px;
  padding: 0 10px !important;
  margin: 1px 0;
  border-radius: 10px;
  line-height: 36px;
}
.app-menu :deep(.el-sub-menu__icon-arrow) {
  display: none; /* the arrow takes the icon's place on the left instead */
}
/* A group's pages, indented to start under the group's name. */
.app-menu .el-sub-menu .el-menu-item {
  padding-left: 42px !important;
}
.app-menu > li.gap {
  margin-top: 14px;
}
/* The current page: a white pill on the grey sidebar, like the cards it opens. Folded, its group's icon gets it. */
.app-menu .el-menu-item.is-active,
.app-menu.el-menu--collapse .el-sub-menu.is-active :deep(.el-sub-menu__title) {
  background: var(--lab-bg-card);
  box-shadow: var(--lab-shadow-card);
  font-weight: 600;
}
.label {
  margin-right: 8px;
}
.mod-icon {
  position: relative;
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  margin-right: 10px;
  border-radius: 6px;
  color: var(--lab-text-2);
  font-style: normal;
}
.app-menu .mod-icon .el-icon {
  width: auto;
  margin: 0;
  font-size: 16px;
  color: inherit;
}
.mod-icon.colored {
  background: var(--c);
  color: #fff;
}
.mod-icon.colored .el-icon {
  font-size: 14px;
}
.app-menu .el-menu-item.is-active .mod-icon:not(.colored) {
  color: var(--lab-selected-fg);
}
.mod-icon .arrow,
.app-menu:not(.el-menu--collapse) .el-sub-menu.is-opened .mod-icon .glyph {
  display: none;
}
.app-menu:not(.el-menu--collapse) .el-sub-menu.is-opened .mod-icon .arrow {
  display: inline-flex;
}
.app-menu:not(.el-menu--collapse) .el-sub-menu.is-opened .mod-icon.colored {
  background: color-mix(in srgb, var(--c) 14%, transparent);
  color: var(--c);
}
.badge {
  margin-left: auto;
  min-width: 18px;
  padding: 0 6px;
  box-sizing: border-box;
  border-radius: 999px;
  background: var(--el-color-danger);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.badge.info {
  background: var(--el-color-primary);
}

/* Folded: icons only, centred in a 44px row. */
.app-menu.el-menu--collapse {
  width: auto;
}
.app-menu.el-menu--collapse .el-menu-item,
.app-menu.el-menu--collapse :deep(.el-sub-menu__title) {
  justify-content: center;
  padding: 0 !important;
}
.app-menu.el-menu--collapse :deep(.el-menu-tooltip__trigger) {
  width: 100%;
  justify-content: center;
  padding: 0;
}
.app-menu.el-menu--collapse .mod-icon {
  margin-right: 0;
}
.dot {
  position: absolute;
  top: -3px;
  right: -3px;
  width: 8px;
  height: 8px;
  border: 2px solid var(--lab-bg);
  border-radius: 50%;
  background: var(--el-color-danger);
}
.dot.info {
  background: var(--el-color-primary);
}
</style>

<style>
/* A folded group's pages, popped out beside its icon (teleported, so not scoped): the sidebar's rows on a white card. */
.app-menu-popup .el-menu--popup {
  min-width: 160px;
  padding: 6px;
  border-radius: var(--lab-radius-lg);
}
.app-menu-popup .pop-title {
  padding: 4px 12px 6px;
  color: var(--lab-text-3);
  font-size: 12px;
  line-height: 18px;
  list-style: none;
}
.app-menu-popup .el-menu-item {
  display: flex;
  height: 36px;
  padding: 0 12px;
  border-radius: 10px;
  color: var(--lab-text);
  font-size: 14px;
  line-height: 36px;
}
.app-menu-popup .el-menu-item:hover {
  background: var(--lab-bg-hover);
}
.app-menu-popup .el-menu-item.is-active {
  background: var(--lab-bg);
  color: var(--lab-text);
  font-weight: 600;
}
</style>
