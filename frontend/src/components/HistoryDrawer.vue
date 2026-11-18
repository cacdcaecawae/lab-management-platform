<script setup lang="ts">
import { ref, watch } from 'vue'
import type { HistoryEntry } from '@/api/types'
import { FIELD_LABELS, STATUS, formatTime } from '@/utils/format'
import { showError } from '@/utils/errors'

const visible = defineModel<boolean>({ required: true })
// values: labels for coded values, by field (default: status from STATUS); labels: field names that differ on this page
const props = defineProps<{
  load: () => Promise<HistoryEntry[]>
  values?: Record<string, Record<string, string>>
  labels?: Record<string, string>
}>()

const entries = ref<HistoryEntry[]>([])
const loading = ref(false)
const TYPES = { created: '创建', changed: '修改', deleted: '删除' }

watch(visible, async (v) => {
  if (!v) return
  loading.value = true
  try {
    entries.value = await props.load()
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
})

function show(field: string, v: unknown): string {
  if (v === null || v === undefined || v === '') return '（空）'
  if (typeof v === 'boolean') return v ? '是' : '否'
  const label = typeof v === 'string' ? props.values?.[field]?.[v] : undefined
  if (label) return label
  if (field === 'status' && typeof v === 'string') return STATUS[v]?.label ?? v
  // datetimes arrive as Python's str(): "2026-11-18 00:54:54.129721+00:00"; show local time like the rest of the page
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(v)) {
    return formatTime(v.replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1'))
  }
  return typeof v === 'string' ? v : JSON.stringify(v)
}
</script>

<template>
  <el-drawer v-model="visible" title="修改历史" size="min(480px, 100%)">
    <div v-loading="loading">
      <el-empty v-if="!loading && !entries.length" description="暂无记录" />
      <el-timeline>
        <el-timeline-item v-for="h in entries" :key="h.id" :timestamp="formatTime(h.date)" placement="top">
          <div>{{ h.user?.name ?? '系统' }} {{ TYPES[h.type] }}</div>
          <div v-if="h.reason" class="reason">原因：{{ h.reason }}</div>
          <ul v-if="h.changes.length" class="changes">
            <li v-for="c in h.changes" :key="c.field">
              {{ labels?.[c.field] ?? FIELD_LABELS[c.field] ?? c.field }}：{{ show(c.field, c.old) }} → {{ show(c.field, c.new) }}
            </li>
          </ul>
        </el-timeline-item>
      </el-timeline>
    </div>
  </el-drawer>
</template>

<style scoped>
.reason {
  color: var(--el-color-danger);
  margin-top: 4px;
}
.changes {
  margin: 4px 0 0;
  padding-left: 18px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-text-color-regular);
}
</style>
