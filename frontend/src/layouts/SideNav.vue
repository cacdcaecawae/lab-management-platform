<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown, Lock, SwitchButton, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { ROLE_LABELS } from '@/utils/format'
import SiteSearch from '@/components/SiteSearch.vue'
import AppMenu from './AppMenu.vue'
import ProfileDialog from './ProfileDialog.vue'
import { clearTabs } from './nav'

// The sidebar (DESIGN.md): who is signed in, search, then the menu. Used by the desktop sidebar and the phone drawer.
const auth = useAuthStore()
const router = useRouter()
const name = computed(() => auth.user?.name || auth.user?.username || '')
// The account menu starts with who you are: role · group, then the login name.
const role = computed(() => (auth.user?.is_superuser ? '运维' : ROLE_LABELS[auth.user?.role ?? '']))
const roleLine = computed(() => [role.value, auth.user?.group?.name].filter(Boolean).join(' · '))
const profile = ref(false)

async function logout() {
  await auth.logout()
  clearTabs() // the next person on this computer does not see what was open
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="side-nav">
    <!-- opens beside the sidebar, so it never covers the search box and menu under the button -->
    <el-dropdown trigger="click" placement="right-start" class="me-menu">
      <button type="button" class="me">
        <span class="avatar" aria-hidden="true">{{ name.slice(0, 1) }}</span>
        <span class="who">
          <span class="name">{{ name }}</span>
          <span v-if="auth.user?.group" class="group">{{ auth.user.group.name }}</span>
        </span>
        <el-icon class="caret"><ArrowDown /></el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <li class="me-card" role="presentation">
            <span class="avatar lg" aria-hidden="true">{{ name.slice(0, 1) }}</span>
            <span class="who">
              <span class="name">{{ name }}</span>
              <span class="line">{{ roleLine }}</span>
              <span class="line">学号 / 工号 <span class="code">{{ auth.user?.username }}</span></span>
            </span>
          </li>
          <el-dropdown-item divided :icon="User" @click="profile = true">个人信息</el-dropdown-item>
          <el-dropdown-item :icon="Lock" @click="router.push({ name: 'password' })">修改密码</el-dropdown-item>
          <el-dropdown-item divided :icon="SwitchButton" @click="logout">退出登录</el-dropdown-item>
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
.avatar {
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
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
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 220px;
  padding: 10px 16px 12px;
  list-style: none;
}
.avatar.lg {
  width: 44px;
  height: 44px;
  font-size: 18px;
}
.me-card .name {
  font-size: 15px;
}
.me-card .line {
  color: var(--lab-text-3);
  font-size: 13px;
  line-height: 1.6;
  white-space: nowrap;
}
.me-card .code {
  color: var(--lab-text-2);
}
</style>
