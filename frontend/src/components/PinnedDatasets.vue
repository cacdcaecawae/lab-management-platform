<script setup lang="ts">
import { computed } from 'vue'
import type { DatasetBrief } from '@/api/types'

// Datasets cited by a submitted record, each with the version pinned at submit (git-style short code).
const props = defineProps<{ datasets: (DatasetBrief | null)[] }>()
const list = computed(() => [...new Map(props.datasets.filter((d): d is DatasetBrief => !!d).map((d) => [d.id, d])).values()])
</script>

<template>
  <div class="pinned">
    <div class="title">提交时的数据版本</div>
    <div v-for="d in list" :key="d.id" class="row">
      <RouterLink :to="{ name: 'dataset-detail', params: { id: d.id }, query: d.version ? { version: d.version } : {} }">
        {{ d.code }} {{ d.name }}
      </RouterLink>
      <span v-if="d.version" class="mono">@ {{ d.version.slice(0, 12) }}</span>
      <el-tag v-else size="small" type="info" disable-transitions>无版本（旧记录）</el-tag>
      <el-tag v-if="d.changed" size="small" type="warning" disable-transitions>提交后有新增</el-tag>
    </div>
    <span v-if="!list.length" class="empty">未关联数据集</span>
  </div>
</template>

<style scoped>
.pinned {
  margin-top: 8px;
}
.title {
  font-size: 14px;
  color: var(--el-text-color-regular);
  margin-bottom: 4px;
}
.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  line-height: 2;
}
.empty {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
