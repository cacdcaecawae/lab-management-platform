<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { notificationsApi, type SiteNotification } from '@/api/notifications'
import { usePagedList } from '@/composables/usePagedList'
import { useNotificationsStore } from '@/stores/notifications'
import { showError } from '@/utils/errors'
import { formatTime } from '@/utils/format'
import PageToolbar from '@/components/PageToolbar.vue'
import { Finished } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

const router = useRouter()
const store = useNotificationsStore()
const filters = reactive({ unread: '' as 1 | '' })
const busy = ref(false)
const { items, count, page, pageSize, loading, load } = usePagedList(notificationsApi.list, filters)

async function open(item: SiteNotification) {
  if (busy.value) return
  busy.value = true
  try {
    if (!item.read_at) await notificationsApi.read(item.id)
    void store.refresh()
    await router.push(item.link)
  } catch (err) {
    showError(err)
  } finally {
    busy.value = false
  }
}

async function readAll() {
  if (busy.value) return
  busy.value = true
  try {
    await notificationsApi.readAll()
    void store.refresh()
    if (page.value === 1) await load()
    else page.value = 1
  } catch (err) {
    showError(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card v-loading="loading" class="card">
    <PageToolbar>
      <el-checkbox v-model="filters.unread" :true-value="1" false-value="">仅未读</el-checkbox>
      <template #actions>
        <IconButton :icon="Finished" label="全部标为已读" :loading="busy" @click="readAll" />
      </template>
    </PageToolbar>
    <el-empty v-if="!items.length" description="暂无通知" />
    <ul v-else class="notifications">
      <li v-for="item in items" :key="item.id">
        <el-button link type="primary" :disabled="busy" @click="open(item)">{{ item.title }}</el-button>
        <el-tag v-if="!item.read_at" class="status-tag" type="primary" disable-transitions>未读</el-tag>
        <span>{{ formatTime(item.created_at) }}</span>
        <p v-if="item.body">{{ item.body }}</p>
      </li>
    </ul>
    <el-pagination v-if="count > pageSize" v-model:current-page="page" class="pager" layout="prev, pager, next" :page-size="pageSize" :total="count" />
  </el-card>
</template>

<style scoped>
.notifications { list-style: none; margin: 0; padding: 0; }
.notifications li { border-bottom: 1px solid var(--lab-border); padding: 12px 0; }
.notifications span { margin-left: 10px; color: var(--el-text-color-secondary); }
</style>
