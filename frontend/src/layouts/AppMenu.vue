<script setup lang="ts">
import { useNotificationsStore } from '@/stores/notifications'
import { useNav } from './nav'

const notifications = useNotificationsStore()
const { modules, current, target } = useNav()
</script>

<template>
  <el-menu class="app-menu" :default-active="current?.key" router>
    <el-menu-item
      v-for="m in modules"
      :key="m.key"
      :index="m.key"
      :route="target(m)"
      :class="{ gap: m.gap }"
    >
      <el-icon><component :is="m.icon" /></el-icon>
      <span>{{ m.label }}</span>
      <!-- counts that need someone go on the menu item (DESIGN.md), not in a pop-up -->
      <span v-if="m.key === 'notifications' && notifications.unread" class="badge">{{ notifications.unread > 99 ? '99+' : notifications.unread }}</span>
    </el-menu-item>
  </el-menu>
</template>

<style scoped>
.app-menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: var(--lab-text);
  --el-menu-active-color: var(--lab-text);
  --el-menu-hover-bg-color: var(--lab-bg-hover);
  --el-menu-item-height: 36px;
  --el-menu-item-font-size: 14px;
  border-right: none;
  padding: 0 10px;
}
.app-menu .el-menu-item {
  padding: 0 10px !important;
  margin: 1px 0;
  border-radius: 10px;
  line-height: 36px;
}
.app-menu .el-menu-item.gap {
  margin-top: 14px;
}
/* The current module: a white pill on the grey sidebar, like the cards it opens. */
.app-menu .el-menu-item.is-active {
  background: var(--lab-bg-card);
  box-shadow: var(--lab-shadow-card);
  font-weight: 600;
}
.app-menu .el-menu-item .el-icon {
  width: 16px;
  margin-right: 10px;
  font-size: 16px;
  color: var(--lab-text-2);
}
.app-menu .el-menu-item.is-active .el-icon {
  color: var(--lab-selected-fg);
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
