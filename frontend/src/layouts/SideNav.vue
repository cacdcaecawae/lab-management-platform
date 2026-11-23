<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowUp } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import icon from '@/assets/phase-icon.png'
import IconButton from '@/components/IconButton.vue'
import SiteSearch from '@/components/SiteSearch.vue'
import AccountCard from './AccountCard.vue'
import AppMenu from './AppMenu.vue'
import ProfileDialog from './ProfileDialog.vue'
import { leavePage } from '@/composables/useUnsavedGuard'
import { clearTabs, sidebarFolded } from './nav'

// The sidebar (DESIGN.md): Phase (back to the home page), search and fold on top, the menu, who is signed in at the
// bottom. Folded, the logo opens it again. Used by the computer's sidebar (foldable) and the phone drawer.
const props = defineProps<{ foldable?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const folded = computed(() => !!props.foldable && sidebarFolded.value)
const fold = () => (sidebarFolded.value = !sidebarFolded.value)
// A panel with its side bar, like Gemini's: Element Plus has no such icon.
const PanelIcon = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.8, 'stroke-linejoin': 'round' }, [
    h('rect', { x: 3.5, y: 4.5, width: 17, height: 15, rx: 3 }),
    h('path', { d: 'M9.5 4.5v15' }),
  ])
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
  <div class="side-nav" :class="{ folded }">
    <div class="head">
      <!-- folded, the logo opens the sidebar (showing the panel icon on hover); open, Phase goes to the home page -->
      <el-tooltip v-if="folded" content="展开侧栏" placement="right" :show-after="300">
        <button type="button" class="brand" aria-label="展开侧栏" @click="fold">
          <img :src="icon" alt="" /><el-icon class="open"><PanelIcon /></el-icon>
        </button>
      </el-tooltip>
      <RouterLink v-else :to="{ name: 'login' }" class="brand" aria-label="Phase 首页" @click="emit('close')">
        <img :src="icon" alt="" /><span>Phase</span>
      </RouterLink>
      <SiteSearch v-if="auth.user?.group && !auth.user.must_change_password" />
      <IconButton v-if="foldable && !folded" :icon="PanelIcon" label="收起侧栏" @click="fold" />
    </div>
    <div class="menu-scroll"><AppMenu :collapse="folded" /></div>
    <!-- pops up above the button, over the menu; a click outside closes it -->
    <el-dropdown trigger="click" placement="top-start" :show-arrow="false" :offset="4" popper-class="me-popper" class="me-menu">
      <button type="button" class="me" :aria-label="folded ? name : undefined">
        <el-avatar :size="32" :src="auth.user?.avatar_url ?? undefined" aria-hidden="true">{{ name.slice(0, 1) }}</el-avatar>
        <template v-if="!folded">
          <span class="who">
            <span class="name">{{ name }}</span>
            <span v-if="auth.user?.group" class="group">{{ auth.user.group.name }}</span>
          </span>
          <el-icon class="caret"><ArrowUp /></el-icon>
        </template>
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
  </div>
</template>

<style scoped>
/* Fills the sidebar's height: the top row and the account stay put, only the menu scrolls. */
.side-nav {
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  padding: 12px 0 calc(12px + env(safe-area-inset-bottom)); /* the phone drawer: clear of the home indicator */
}
.head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
  margin: 0 10px 12px;
}
.brand {
  min-width: 0;
  margin-right: auto; /* search and fold to the right; the hover covers only the logo and its name */
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 8px;
  border-radius: var(--lab-radius);
  color: var(--lab-text);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.brand:hover {
  background: var(--lab-bg-hover);
  text-decoration: none;
}
.brand:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 1px;
}
.brand img {
  width: 24px;
  height: 24px;
}
/* Folded (64px): the logo, then search under it. */
.folded .head {
  flex-direction: column;
  gap: 4px;
}
.folded .brand {
  flex: none;
  justify-content: center;
  width: 44px;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}
.folded .brand:hover {
  background: var(--lab-bg-hover);
}
.brand .open {
  display: none;
  color: var(--lab-text-2);
  font-size: 20px;
}
.folded .brand:is(:hover, :focus-visible) img {
  display: none;
}
.folded .brand:is(:hover, :focus-visible) .open {
  display: inline-flex;
}
.menu-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  /* the menu is taller than a laptop screen: scroll it, but show the bar only while the pointer is over it */
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
.menu-scroll:hover {
  scrollbar-color: rgba(0, 0, 0, 0.2) transparent;
}
.me-menu {
  flex: none;
  display: block;
  margin: 8px 10px 0;
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
.folded .me {
  justify-content: center;
  padding: 6px 0;
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
