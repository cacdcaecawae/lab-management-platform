<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storageApi, type GroupStorage } from '@/api/storageUsage'
import { showError } from '@/utils/errors'
import { formatSize as bytes } from '@/utils/format'

// The group's own raw data by member and by project (成员 page). Ops sees every group in 存储与备份 (SystemStorage).
const result = ref<GroupStorage>()
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    result.value = await storageApi.group()
  } catch (error) {
    showError(error)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section v-loading="loading" aria-label="存储用量">
    <template v-if="result">
      <h3>本组原始数据（按上传成员）</h3>
      <el-table empty-text="暂无文件" :data="result.by_member">
        <el-table-column prop="label" label="成员" />
        <el-table-column label="已知大小"><template #default="{ row }">{{ bytes(row.known_bytes) }}</template></el-table-column>
        <el-table-column prop="unknown_files" label="大小未知的文件数" />
      </el-table>
      <h3>本组原始数据（按项目）</h3>
      <el-table empty-text="暂无文件" :data="result.by_project">
        <el-table-column prop="label" label="项目" />
        <el-table-column label="已知大小"><template #default="{ row }">{{ bytes(row.known_bytes) }}</template></el-table-column>
        <el-table-column prop="unknown_files" label="大小未知的文件数" />
      </el-table>
    </template>
  </section>
</template>
