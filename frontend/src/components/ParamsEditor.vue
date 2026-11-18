<script setup lang="ts">
import { computed, ref, toRaw, watch } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { paramsProblem, toObject, toRows, type ParamRow } from '@/utils/params'

const model = defineModel<Record<string, unknown>>({ required: true })
defineProps<{ disabled?: boolean }>()

const rows = ref<ParamRow[]>(toRows(model.value))
let emitted: unknown = null
watch(
  rows,
  (r) => {
    emitted = toObject(r)
    model.value = emitted as Record<string, unknown>
  },
  { deep: true },
)
// Rebuild rows only when the parent replaces the object (e.g. a record was loaded), not on our own updates.
// toRaw: a reactive parent form hands our own object back wrapped in a proxy.
watch(model, (v) => {
  if (toRaw(v) !== emitted) rows.value = toRows(v)
})

const problem = computed(() => paramsProblem(rows.value))
defineExpose({ validate: () => !problem.value })
</script>

<template>
  <div class="params">
    <div v-for="(row, i) in rows" :key="i" class="row">
      <el-input v-model="row.key" placeholder="参数名" :disabled="disabled" aria-label="参数名" />
      <el-input v-model="row.value" placeholder="值" :disabled="disabled" aria-label="值" />
      <el-button v-if="!disabled" :icon="Delete" link aria-label="删除参数" @click="rows.splice(i, 1)" />
    </div>
    <div v-if="problem" class="problem">{{ problem }}</div>
    <el-button v-if="!disabled" size="small" @click="rows.push({ key: '', value: '' })">添加参数</el-button>
    <span v-else-if="!rows.length" class="empty">无</span>
  </div>
</template>

<style scoped>
.params {
  width: 100%;
}
.row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.problem {
  color: var(--el-color-danger);
  font-size: 12px;
  margin-bottom: 8px;
}
.empty {
  color: var(--el-text-color-secondary);
}
</style>
