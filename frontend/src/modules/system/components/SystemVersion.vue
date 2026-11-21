<script setup lang="ts">
import type { VersionInfo } from '@/api/types'
import { formatTime } from '@/utils/format'

// Loaded by SystemView, which also marks the tab when an update is available.
defineProps<{ info: VersionInfo }>()
</script>

<template>
  <el-descriptions :column="1" border class="facts">
    <el-descriptions-item label="当前版本">{{ info.current === 'local' ? '从源码构建（local）' : info.current }}</el-descriptions-item>
    <el-descriptions-item label="最新版本">
      <el-link v-if="info.latest" :href="info.url" target="_blank" type="primary">{{ info.latest }}（发布说明）</el-link>
      <span v-else-if="info.error">{{ info.error }}</span>
      <span v-else>还没有发布过正式版本</span>
    </el-descriptions-item>
    <el-descriptions-item label="检查时间">{{ formatTime(info.checked_at) }}</el-descriptions-item>
  </el-descriptions>

  <el-alert v-if="info.update_available" type="warning" :closable="false" show-icon :title="`有新版本 ${info.latest}`">
    <p>在服务器的仓库目录里运行：</p>
    <pre class="cmd">bash scripts/update.sh {{ info.latest }}</pre>
    <p>更新时网站会停止，先备份再切换。新版本起不来时：没改数据库结构的，自动退回 {{ info.current }}；改过或无法确认的，网站保持停止、保留当前数据，需要运维按 README"服务器部署"一节处理。</p>
  </el-alert>
  <p v-else-if="info.latest && info.current !== 'local'" class="note">已是最新版本。</p>
</template>

<style scoped>
.facts {
  max-width: 560px;
  margin-bottom: 16px;
}
.cmd {
  margin: 8px 0;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-family: ui-monospace, Consolas, monospace;
  user-select: all;
}
.note {
  color: var(--el-text-color-secondary);
}
</style>
