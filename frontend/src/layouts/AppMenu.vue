<script setup lang="ts">
import { computed, useTemplateRef, watch } from 'vue'
import type { MenuInstance } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { useNotificationsStore } from '@/stores/notifications'
import { pinGroup, pinnedGroups, useNav } from './nav'

const notifications = useNotificationsStore()
const { modules, page, current } = useNav()
const menu = useTemplateRef<MenuInstance>('menu')

// A module with several pages (for this role) is a group; its menu index is "g:<key>" so it never equals a page name.
const groupIndex = (key: string) => `g:${key}`
const currentGroup = computed(() => (current.value && current.value.pages.length > 1 ? groupIndex(current.value.key) : ''))
const openeds = [...pinnedGroups].map(groupIndex)
// Only the user's own clicks pin a group. Element Plus also "opens" the group of the active page by itself, and
// reports plain items as opened too (it files them with the groups), hence the g: check.
const isGroup = (index: string) => index.startsWith('g:')
const onOpen = (index: string) => isGroup(index) && index !== currentGroup.value && pinGroup(index.slice(2), true)
const onClose = (index: string) => isGroup(index) && pinGroup(index.slice(2), false)
watch(
  currentGroup,
  (next, prev) => {
    if (prev && prev !== next && !pinnedGroups.has(prev.slice(2))) menu.value?.close(prev)
    if (next) menu.value?.open(next)
  },
  { flush: 'post' },
)
const tint = (m: { key: string; color?: boolean }) => (m.color ? { '--c': `var(--lab-mod-${m.key})` } : undefined)
</script>

<template>
  <el-menu ref="menu" class="app-menu" :default-active="page" :default-openeds="openeds" router @open="onOpen" @close="onClose">
    <template v-for="m in modules" :key="m.key">
      <el-sub-menu v-if="m.pages.length > 1" :index="groupIndex(m.key)" :class="{ gap: m.gap }">
        <template #title>
          <!-- closed: the module's coloured icon; open: an arrow in its place (DESIGN.md) -->
          <span class="mod-icon" :class="{ colored: m.color }" :style="tint(m)">
            <el-icon class="glyph"><component :is="m.icon" /></el-icon>
            <el-icon class="arrow"><ArrowDown /></el-icon>
          </span>
          <span>{{ m.label }}</span>
        </template>
        <el-menu-item v-for="p in m.pages" :key="p.name" :index="p.name" :route="{ name: p.name }">{{ p.label }}</el-menu-item>
      </el-sub-menu>
      <el-menu-item v-else :index="m.pages[0]!.name" :route="{ name: m.pages[0]!.name }" :class="{ gap: m.gap }">
        <span class="mod-icon" :class="{ colored: m.color }" :style="tint(m)">
          <el-icon class="glyph"><component :is="m.icon" /></el-icon>
        </span>
        <span>{{ m.label }}</span>
        <!-- counts that need someone go on the menu item (DESIGN.md), not in a pop-up -->
        <span v-if="m.key === 'notifications' && notifications.unread" class="badge">{{ notifications.unread > 99 ? '99+' : notifications.unread }}</span>
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
/* The current page: a white pill on the grey sidebar, like the cards it opens. */
.app-menu .el-menu-item.is-active {
  background: var(--lab-bg-card);
  box-shadow: var(--lab-shadow-card);
  font-weight: 600;
}
.mod-icon {
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  margin-right: 10px;
  border-radius: 6px;
  color: var(--lab-text-2);
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
.el-sub-menu.is-opened .mod-icon .glyph {
  display: none;
}
.el-sub-menu.is-opened .mod-icon .arrow {
  display: inline-flex;
}
.el-sub-menu.is-opened .mod-icon.colored {
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
</style>
