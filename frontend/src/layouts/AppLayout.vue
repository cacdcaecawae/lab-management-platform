<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Lock, Menu, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import AppMenu from './AppMenu.vue'
import RoutePage from './RoutePage.vue'
import SiteSearch from '@/components/SiteSearch.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const drawer = ref(false)
const displayName = computed(() => auth.user?.name || auth.user?.username || '')

watch(
  () => route.fullPath,
  () => (drawer.value = false),
)

async function logout() {
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand"><span class="logo" aria-hidden="true">课</span>课题组管理</div>
      <AppMenu />
    </aside>
    <el-drawer v-model="drawer" direction="ltr" size="240px" :with-header="false" class="nav-drawer">
      <div class="brand"><span class="logo" aria-hidden="true">课</span>课题组管理</div>
      <AppMenu />
    </el-drawer>
    <div class="body">
      <header class="topbar">
        <div class="left">
          <el-button class="menu-btn" :icon="Menu" text aria-label="打开菜单" @click="drawer = true" />
          <span class="title">{{ route.meta.title }}</span>
        </div>
        <SiteSearch />
        <el-dropdown trigger="click" placement="bottom-end">
          <span class="user">
            <span class="avatar" aria-hidden="true">{{ displayName.slice(0, 1) }}</span>{{ displayName }}<template v-if="auth.user?.group">（{{ auth.user.group.name }}）</template>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :icon="Lock" @click="router.push({ name: 'password' })">修改密码</el-dropdown-item>
              <el-dropdown-item divided :icon="SwitchButton" @click="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>
      <main class="main">
        <RoutePage />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  position: sticky;
  top: 0;
  flex: 0 0 232px;
  height: 100vh;
  overflow-y: auto;
  background: var(--lab-bg-subtle);
  border-right: 1px solid var(--lab-border);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 10px;
  font-size: 15px;
  font-weight: 600;
}
.logo {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: var(--lab-text);
  color: #fff;
  font-size: 13px;
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
  justify-content: space-between;
  gap: 8px;
  height: 52px;
  padding: 0 24px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: saturate(180%) blur(8px);
  border-bottom: 1px solid var(--lab-border);
}
.left {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.menu-btn {
  display: none;
}
.title {
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
}
.user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px 4px 4px;
  border-radius: 999px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  outline: none;
}
.user:hover,
.user:focus-visible {
  background: var(--lab-bg-hover);
}
.avatar {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--lab-bg-active);
  color: var(--lab-text);
  font-size: 12px;
  font-weight: 600;
}
.main {
  width: 100%;
  max-width: 1200px;
  box-sizing: border-box;
  margin: 0 auto;
  padding: 24px 32px 48px;
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
  .user {
    max-width: 60vw;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .main {
    padding: 16px 12px 32px;
  }
}
</style>

<style>
.nav-drawer {
  --el-drawer-padding-primary: 0;
  background: var(--lab-bg-subtle);
}
</style>
