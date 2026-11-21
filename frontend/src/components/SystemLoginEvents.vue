<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { loginEventsApi, type LoginEventPage, type LoginOutcome } from '@/api/loginEvents'
import { showError } from '@/utils/errors'
import PageToolbar from './PageToolbar.vue'

const outcomeLabels: Record<LoginOutcome, string> = {
  success: '登录成功', failed: '认证失败', throttled: '限流发生分钟',
}
const filters = reactive({ username: '', outcome: '' as LoginOutcome | '', from: '', to: '' })
const active = ref({ ...filters })
const results = ref<LoginEventPage>()
const loading = ref(false)
const page = ref(1)
let requestId = 0

async function refresh(pageNumber = 1) {
  const id = ++requestId
  loading.value = true
  try {
    const result = await loginEventsApi.list({ ...active.value, page: pageNumber })
    if (id !== requestId) return
    results.value = result
    page.value = pageNumber
  } catch (error) {
    if (id === requestId) {
      results.value = undefined
      page.value = 1
      showError(error)
    }
  } finally {
    if (id === requestId) loading.value = false
  }
}

function apply() {
  active.value = { ...filters, username: filters.username.trim() }
  void refresh()
}

const displayTime = (value: string) => new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'medium',
}).format(new Date(value))

onMounted(() => refresh())
</script>

<template>
  <section aria-label="登录记录">
    <el-alert v-if="results && !results.audit_enabled" type="info" :closable="false" title="未启用登录记录采集" />
    <h3>近 24 小时失败最多的账号</h3>
    <ul v-if="results?.top_failed_24h.length">
      <li v-for="item in results.top_failed_24h" :key="item.user_id">{{ item.user__username }}：{{ item.failures }} 次</li>
    </ul>
    <p v-else>无</p>
    <!-- the list toolbar (DESIGN.md): every filter applies on change, like the other list pages -->
    <PageToolbar>
      <el-input v-model="filters.username" placeholder="学号 / 工号" aria-label="学号 / 工号" clearable maxlength="150" @change="apply" />
      <el-select v-model="filters.outcome" placeholder="全部结果" aria-label="结果" clearable @change="apply">
        <el-option v-for="(label, value) in outcomeLabels" :key="value" :label="label" :value="value" />
      </el-select>
      <el-date-picker v-model="filters.from" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss[+08:00]" placeholder="开始时间" aria-label="开始时间" @change="apply" />
      <el-date-picker v-model="filters.to" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss[+08:00]" placeholder="结束时间" aria-label="结束时间" @change="apply" />
    </PageToolbar>
    <el-table empty-text="暂无登录记录" v-loading="loading" :data="results?.results ?? []">
      <el-table-column label="时间" min-width="180">
        <template #default="{ row }">{{ displayTime(row.at) }}</template>
      </el-table-column>
      <el-table-column label="账号" min-width="120">
        <template #default="{ row }">{{ row.account?.username ?? '未归属' }}</template>
      </el-table-column>
      <el-table-column label="结果" min-width="120">
        <template #default="{ row }">{{ outcomeLabels[row.outcome as LoginOutcome] }}</template>
      </el-table-column>
      <el-table-column label="来源地址" min-width="130">
        <template #default="{ row }">{{ row.ip ?? '无' }}</template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="results" :current-page="page" :total="results.count" :page-size="20"
      layout="total, prev, pager, next" @current-change="refresh" hide-on-single-page />
  </section>
</template>
