<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Bell, Calendar, House, Menu } from '@element-plus/icons-vue'
import { useNotificationsStore } from '@/stores/notifications'

// Phone only (DESIGN.md "手机"): the three pages people open most, then 菜单 for the sidebar (Phase and search, every
// module, the account). 菜单 is the current one on any other page.
const emit = defineEmits<{ menu: [] }>()
const route = useRoute()
const notes = useNotificationsStore()
const TABS = [
  { name: 'workbench', label: '工作台', icon: House },
  { name: 'bookings', label: '预约', icon: Calendar },
  { name: 'notifications', label: '通知', icon: Bell },
]
const current = computed(() => TABS.find((t) => t.name === route.name)?.name ?? 'menu')
</script>

<template>
  <nav class="tab-bar" aria-label="常用页面">
    <RouterLink
      v-for="t in TABS"
      :key="t.name"
      :to="{ name: t.name }"
      class="item"
      :class="{ on: current === t.name }"
      :aria-current="current === t.name ? 'page' : undefined"
    >
      <el-badge :value="notes.unread" :max="99" :hidden="t.name !== 'notifications' || !notes.unread">
        <el-icon class="icon"><component :is="t.icon" /></el-icon>
      </el-badge>
      <span>{{ t.label }}</span>
    </RouterLink>
    <!-- named like the top bar's menu button it replaces (verify-lab responsive.py finds the drawer by it) -->
    <button type="button" class="item" :class="{ on: current === 'menu' }" aria-label="打开菜单" @click="emit('menu')">
      <el-icon class="icon"><Menu /></el-icon>
      <span>菜单</span>
    </button>
  </nav>
</template>

<style scoped>
.tab-bar {
  position: fixed;
  inset: auto 0 0;
  z-index: 15;
  display: flex;
  padding-bottom: env(safe-area-inset-bottom);
  border-top: 1px solid var(--lab-border);
  /* frosted like the top bar; solid where blur is off or unwanted */
  background: rgba(242, 243, 245, 0.85);
  backdrop-filter: saturate(180%) blur(12px);
}
@media (prefers-reduced-transparency: reduce), (forced-colors: active) {
  .tab-bar { background: var(--lab-bg); backdrop-filter: none; }
}
.item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  height: 56px;
  justify-content: center;
  padding: 0;
  border: 0;
  background: none;
  color: var(--lab-text-3);
  font: inherit;
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
}
.item.on {
  color: var(--el-color-primary);
  font-weight: 600;
}
.item:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -4px;
  border-radius: var(--lab-radius);
}
.icon {
  font-size: 22px;
}
</style>
