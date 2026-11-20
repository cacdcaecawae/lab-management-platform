<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import { notificationsApi, type SiteNotification } from '@/api/notifications'
import { useNotificationsStore } from '@/stores/notifications'
import { formatTime } from '@/utils/format'
import { showError } from '@/utils/errors'

const route = useRoute()
const router = useRouter()
const store = useNotificationsStore()
const visible = ref(false)
const loading = ref(false)
const items = ref<SiteNotification[]>([])
let poll: ReturnType<typeof setInterval> | undefined
let generation = 0

function refreshIfVisible() {
  if (document.visibilityState === 'visible') void store.refresh()
}

function restartPolling() {
  if (poll !== undefined) clearInterval(poll)
  poll = undefined
  if (document.visibilityState === 'visible') {
    refreshIfVisible()
    poll = setInterval(refreshIfVisible, 60_000)
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', restartPolling)
  restartPolling()
})
onUnmounted(() => {
  generation++
  if (poll !== undefined) clearInterval(poll)
  document.removeEventListener('visibilitychange', restartPolling)
  store.reset()
})
watch(() => route.fullPath, () => {
  visible.value = false
  refreshIfVisible()
})

async function loadRecent() {
  const active = ++generation
  loading.value = true
  try {
    const page = await notificationsApi.list({ page_size: 10 })
    if (active === generation) items.value = page.results
  } catch (err) {
    if (active === generation) showError(err)
  } finally {
    if (active === generation) loading.value = false
  }
}

async function open(item: SiteNotification) {
  if (loading.value) return
  loading.value = true
  try {
    if (!item.read_at) await notificationsApi.read(item.id)
    void store.refresh()
    visible.value = false
    await router.push(item.link)
  } catch (err) {
    showError(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-popover v-model:visible="visible" trigger="click" placement="bottom-end" :width="300" @show="loadRecent">
    <template #reference>
      <el-badge :value="store.unread" :max="99" :hidden="!store.unread">
        <el-button :icon="Bell" text :aria-label="`通知，${store.unread} 条未读`" />
      </el-badge>
    </template>
    <div v-loading="loading">
      <p v-if="!items.length">暂无通知</p>
      <ul v-else class="recent-notifications">
        <li v-for="item in items" :key="item.id">
          <button type="button" :disabled="loading" @click="open(item)">
            <strong v-if="!item.read_at">未读 · </strong>{{ item.title }}
            <small>{{ formatTime(item.created_at) }}</small>
          </button>
        </li>
      </ul>
      <RouterLink :to="{ name: 'notifications' }" @click="visible = false">查看全部</RouterLink>
    </div>
  </el-popover>
</template>

<style scoped>
.recent-notifications { list-style: none; margin: 0 0 8px; padding: 0; }
.recent-notifications button { display: block; width: 100%; text-align: left; color: inherit; background: none; border: 0; padding: 8px; cursor: pointer; }
.recent-notifications button:hover, .recent-notifications button:focus-visible { background: var(--el-fill-color-light); }
.recent-notifications small { display: block; color: var(--el-text-color-secondary); }
</style>
