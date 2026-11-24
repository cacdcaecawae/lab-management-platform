<script setup lang="ts">
import { reactive } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import type { Page } from '@/api/client'
import { experimentsApi } from '@/modules/research/api'
import { datasetsApi } from '@/modules/datasets/api'
import { bookingsApi } from '@/modules/equipment/api'
import { specimensApi } from '@/modules/specimens/api'
import { consumablesApi } from '@/modules/inventory/api'
import { TXN_KIND_LABELS, formatPeriod, formatTime } from '@/utils/format'
import { errorMessage } from '@/utils/errors'

// The project's 资产: the latest 10 of each kind of record that names this project, each from its own module's list
// (the same scopes: a student sees their own experiments and datasets). Each block loads and fails on its own.
const props = defineProps<{ projectId: number }>()

interface Line { key: number; to?: RouteLocationRaw; code?: string; text: string; hint?: string }
interface Block { title: string; count: number; lines: Line[]; error: string; loading: boolean; all?: RouteLocationRaw }
const SHOW = 10
const q = { project: props.projectId, page_size: SHOW }

function block<T>(title: string, fetch: () => Promise<Page<T>>, line: (row: T) => Line, all?: RouteLocationRaw): Block {
  const b = reactive<Block>({ title, count: 0, lines: [], error: '', loading: true, all })
  fetch().then(
    (page) => Object.assign(b, { count: page.count, lines: page.results.map(line) }),
    (e) => (b.error = errorMessage(e)),
  ).finally(() => (b.loading = false))
  return b
}

const blocks = [
  block('实验记录', () => experimentsApi.list(q), (x) => ({
    key: x.id, to: { name: 'experiment-edit', params: { id: x.id } }, code: x.code, text: x.title, hint: `${x.owner.name} · ${x.date}`,
  }), { name: 'experiments', query: { project: props.projectId } }),
  block('数据集', () => datasetsApi.list(q), (d) => ({
    key: d.id, to: { name: 'dataset-detail', params: { id: d.id } }, code: d.code, text: d.name, hint: d.owner.name,
  }), { name: 'datasets', query: { project: props.projectId } }),
  block('设备预约', () => bookingsApi.page(q), (b) => ({
    key: b.id, to: { name: 'bookings', query: { booking: b.id } }, code: b.equipment.code, text: b.equipment.name,
    hint: `${b.user.name} · ${formatPeriod(b.start_at, b.end_at)}`,
  }), { name: 'bookings', query: { view: 'list', project: props.projectId } }),
  block('试件借用', () => specimensApi.allLoans(q), (l) => ({
    key: l.id, to: { name: 'specimen-detail', params: { id: l.specimen.id } }, code: l.specimen.code, text: l.specimen.name,
    hint: `${l.borrower.name} · ${l.returned_at ? `已归还 ${formatTime(l.returned_at)}` : '借用中'}`,
  })),
  block('耗材出入库', () => consumablesApi.ledger(q), (t) => ({
    key: t.id, text: `${t.consumable.name} ${TXN_KIND_LABELS[t.kind] ?? t.kind} ${t.quantity > 0 ? '+' : ''}${t.quantity} ${t.consumable.unit}`,
    hint: `${t.handler.name} · ${formatTime(t.created_at)}`,
  }), { name: 'consumables', query: { tab: 'ledger', project: props.projectId } }),
]
</script>

<template>
  <div class="assets">
    <section v-for="b in blocks" :key="b.title" v-loading="b.loading" class="block">
      <h3>{{ b.title }} <span class="muted">{{ b.count }}</span></h3>
      <el-alert v-if="b.error" :title="`${b.title}加载失败：${b.error}`" type="error" :closable="false" />
      <p v-else-if="!b.loading && !b.lines.length" class="muted">暂无</p>
      <ul v-else class="lines">
        <li v-for="l in b.lines" :key="l.key">
          <RouterLink v-if="l.to" :to="l.to"><span v-if="l.code" class="code">{{ l.code }}</span> {{ l.text }}</RouterLink>
          <span v-else>{{ l.text }}</span>
          <span v-if="l.hint" class="muted">{{ l.hint }}</span>
        </li>
      </ul>
      <RouterLink v-if="b.all && b.count > b.lines.length" :to="b.all" class="all">全部 {{ b.count }} 条</RouterLink>
    </section>
  </div>
</template>

<style scoped>
.assets {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px 24px;
}
.block h3 {
  margin: 0 0 8px;
  font-weight: 600;
}
.lines {
  margin: 0;
  padding: 0;
  list-style: none;
}
.lines li {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding: 6px 0;
  border-bottom: 1px solid var(--lab-border);
}
.muted {
  color: var(--lab-text-3);
}
.all {
  display: inline-block;
  margin-top: 8px;
}
</style>
