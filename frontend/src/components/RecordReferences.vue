<script setup lang="ts">
import { computed } from 'vue'
import type { DatasetReferences } from '@/api/types'
import StatusTag from '@/components/StatusTag.vue'

// The records citing a record's files (GET /api/datasets/{id}/references/), as far as the viewer may see them.
// selfExperiment: the experiment on screen, not listed as citing its own raw data.
const props = defineProps<{ refs: DatasetReferences; selfExperiment?: number }>()

const ROLES = { input: '引用', script: '脚本', output: '结果' } as const
const experiments = computed(() => props.refs.experiments.filter((e) => e.id !== props.selfExperiment))
const empty = computed(() => !experiments.value.length && !props.refs.runs.length && !props.refs.reports.length)
</script>

<template>
  <div v-if="empty" class="muted">暂无引用</div>
  <div v-else class="refs">
    <section v-if="experiments.length" class="group">
      <div class="label">实验与原始数据（{{ experiments.length }}）</div>
      <div v-for="e in experiments" :key="e.id" class="actions">
        <RouterLink :to="{ name: 'experiment-edit', params: { id: e.id } }"><span class="code">{{ e.code }}</span> {{ e.title }}</RouterLink>
        <StatusTag :status="e.status" />
      </div>
    </section>
    <section v-if="refs.runs.length" class="group">
      <div class="label">数据处理（{{ refs.runs.length }}）</div>
      <div v-for="r in refs.runs" :key="r.id" class="actions">
        <RouterLink :to="{ name: 'run-edit', params: { id: r.id } }"><span class="code">{{ r.code }}</span> {{ r.title }}</RouterLink>
        <el-tag v-for="role in r.roles" :key="role" size="small" type="info" disable-transitions>{{ ROLES[role] }}</el-tag>
        <StatusTag :status="r.status" />
      </div>
    </section>
    <section v-if="refs.reports.length" class="group">
      <div class="label">周报（{{ refs.reports.length }}）</div>
      <div v-for="rep in refs.reports" :key="rep.id" class="actions">
        <RouterLink :to="{ name: 'report-edit', params: { id: rep.id } }">{{ rep.owner.name }} · {{ rep.week_start }} 这一周</RouterLink>
        <StatusTag :status="rep.status" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.refs {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.label {
  color: var(--lab-text-3);
  font-weight: 600;
}
</style>
