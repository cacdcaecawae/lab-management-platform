<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Box,
  Calendar,
  ChatDotRound,
  Coin,
  Collection,
  DataAnalysis,
  Document,
  FolderOpened,
  House,
  Memo,
  Medal,
  Notebook,
  Monitor,
  Setting,
  ShoppingCart,
  Stamp,
  User,
  Wallet,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

// Menu (handbook §5). Only routes that exist, and that the role may open (meta.supervisor / meta.manager /
// meta.superuser), are shown. An ops account without a group only gets 系统管理.
const names = new Set(router.getRoutes().map((r) => r.name))
const allowed = (name: string) => {
  const meta = router.getRoutes().find((r) => r.name === name)?.meta ?? {}
  if (meta.superuser) return auth.isSuperuser
  return !!auth.user?.group && (!meta.supervisor || auth.isSupervisor) && (!meta.manager || auth.isManager)
}
const raw = [
  { group: '', items: [{ name: 'workbench', label: '工作台', icon: House }] },
  {
    group: '科研记录',
    items: [
      { name: 'experiments', label: '实验记录', icon: Memo },
      { name: 'datasets', label: '原始数据', icon: FolderOpened },
      { name: 'runs', label: '数据处理', icon: DataAnalysis },
      { name: 'reports', label: '周报', icon: Document },
    ],
  },
  {
    group: '设备耗材',
    items: [
      { name: 'equipment', label: '设备台账', icon: Monitor },
      { name: 'bookings', label: '设备预约', icon: Calendar },
      { name: 'consumables', label: '耗材库存', icon: Box },
    ],
  },
  {
    group: '采购经费',
    items: [
      { name: 'purchases', label: '采购申请', icon: ShoppingCart },
      { name: 'purchase-reviews', label: '我的审批', icon: Stamp },
      { name: 'reimbursements', label: '报销与统计', icon: Wallet },
      { name: 'funds', label: '经费来源', icon: Coin },
    ],
  },
  {
    group: '项目',
    items: [
      { name: 'projects', label: '项目列表', icon: Collection },
      { name: 'meetings', label: '组会', icon: ChatDotRound },
    ],
  },
  {
    group: '知识成果',
    items: [
      { name: 'knowledge', label: '知识库', icon: Notebook },
      { name: 'achievements', label: '成果归档', icon: Medal },
    ],
  },
  {
    group: '',
    items: [
      { name: 'members', label: '成员', icon: User },
      { name: 'system', label: '系统管理', icon: Setting },
    ],
  },
]
// computed: the role is known only after login, and this menu outlives a logout / login as someone else
const sections = computed(() =>
  raw.map((s) => ({ ...s, items: s.items.filter((i) => names.has(i.name) && allowed(i.name)) })).filter((s) => s.items.length),
)

const active = computed(() => String(route.meta.menu ?? route.name))
</script>

<template>
  <el-menu class="app-menu" :default-active="active" router>
    <template v-for="(s, i) in sections" :key="i">
      <li v-if="s.group" class="group-title" role="presentation">{{ s.group }}</li>
      <el-menu-item v-for="item in s.items" :key="item.name" :index="item.name" :route="{ name: item.name }">
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </el-menu-item>
    </template>
  </el-menu>
</template>

<style scoped>
.app-menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: #3d3d3d;
  --el-menu-active-color: var(--lab-text);
  --el-menu-hover-bg-color: var(--lab-bg-hover);
  --el-menu-item-height: 34px;
  --el-menu-item-font-size: 14px;
  border-right: none;
  padding: 0 10px;
}
.app-menu .el-menu-item {
  padding: 0 10px !important;
  margin: 1px 0;
  border-radius: var(--lab-radius);
  line-height: 34px;
}
.app-menu .el-menu-item.is-active {
  background: var(--lab-bg-active);
  font-weight: 500;
}
.app-menu .el-menu-item .el-icon {
  width: 16px;
  margin-right: 10px;
  font-size: 16px;
  color: var(--lab-text-3);
}
.app-menu .el-menu-item.is-active .el-icon {
  color: var(--lab-text);
}
.group-title {
  padding: 16px 10px 6px;
  font-size: 12px;
  color: var(--lab-text-3);
}
</style>
