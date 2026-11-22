<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import SiteSearch from '@/components/SiteSearch.vue'
import AccountCard from './AccountCard.vue'
import AppMenu from './AppMenu.vue'
import ProfileDialog from './ProfileDialog.vue'
import { leavePage } from '@/composables/useUnsavedGuard'
import { clearTabs } from './nav'

// The sidebar (DESIGN.md): who is signed in, search, then the menu. Used by the desktop sidebar and the phone drawer.
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore()
const router = useRouter()
const name = computed(() => auth.user?.name || auth.user?.username || '')
const profile = ref(false)

function openProfile() {
  profile.value = true
  emit('close')
}

async function logout() {
  try {
    // an edit page with unsaved changes asks first, and keeps asking if logging out fails
    if (!(await leavePage(() => auth.logout()))) return
  } catch {
    ElMessage.error('退出登录失败，仍处于登录状态')
    return
  }
  clearTabs() // the next person on this computer does not see what was open
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="side-nav">
    <!-- drops down under the button like Feishu's, over the search box and menu; a click outside closes it -->
    <el-dropdown trigger="click" placement="bottom-start" :show-arrow="false" :offset="4" popper-class="me-popper" class="me-menu">
      <button type="button" class="me">
        <el-avatar :size="32" :src="auth.user?.avatar_url ?? undefined" aria-hidden="true">{{ name.slice(0, 1) }}</el-avatar>
        <span class="who">
          <span class="name">{{ name }}</span>
          <span v-if="auth.user?.group" class="group">{{ auth.user.group.name }}</span>
        </span>
        <el-icon class="caret"><ArrowDown /></el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <li class="me-card" role="presentation"><AccountCard :size="56" /></li>
          <el-dropdown-item divided @click="openProfile">个人信息</el-dropdown-item>
          <el-dropdown-item @click="router.push({ name: 'password' })">修改密码</el-dropdown-item>
          <el-dropdown-item divided @click="logout">退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <ProfileDialog v-model="profile" />
    <SiteSearch v-if="auth.user?.group && !auth.user.must_change_password" class="side-search" />
    <AppMenu />
  </div>
</template>

<style scoped>
.side-nav {
  display: flex;
  flex-direction: column;
  padding: 12px 0 24px;
}
.me-menu {
  display: block;
  margin: 0 10px 10px;
}
.me {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--lab-radius);
  background: transparent;
  color: var(--lab-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.me:hover,
.me:focus-visible {
  background: var(--lab-bg-hover);
  outline: none;
}
.me .el-avatar {
  flex: none;
}
.who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}
.name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.group {
  color: var(--lab-text-3);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.caret {
  flex: none;
  color: var(--lab-text-3);
}
.side-search {
  margin: 0 10px 8px;
}
/* Top of the account menu: who you are (not clickable), like Feishu's card above its menu items. */
.me-card {
  padding: 12px 12px 14px;
  list-style: none;
}
</style>

<style>
/* The account menu (teleported, so not scoped): wider and airier than other menus, rows that highlight grey. */
.me-popper.el-popper {
  border: 0;
  border-radius: var(--lab-radius-lg);
  box-shadow: var(--el-box-shadow);
}
.me-popper .el-dropdown-menu {
  width: 296px;
  max-width: calc(100vw - 20px);
  padding: 8px;
  border-radius: var(--lab-radius-lg);
}
.me-popper .el-dropdown-menu__item {
  height: 40px;
  margin: 0;
  padding: 0 12px;
  border-radius: var(--lab-radius);
  color: var(--lab-text);
  font-size: 14px;
}
.me-popper .el-dropdown-menu__item:not(.is-disabled):hover,
.me-popper .el-dropdown-menu__item:not(.is-disabled):focus {
  background: var(--lab-bg);
  color: var(--lab-text);
}
.me-popper .el-dropdown-menu__item--divided {
  margin: 6px 12px;
}
</style>
