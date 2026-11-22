<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { systemApi, type OpsRun, type StorageInfo } from '@/modules/system/api'
import { showError } from '@/utils/errors'
import { formatSize, formatTime } from '@/utils/format'
import { Refresh } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

// Shared with SystemView, whose tab label says when something here needs attention.
const info = defineModel<StorageInfo | null>('info', { default: null })
const checking = ref(false)

async function check() {
  checking.value = true
  info.value = null
  try {
    info.value = await systemApi.storage()
  } catch (error) {
    showError(error)
  } finally {
    checking.value = false
  }
}

function describe(run: OpsRun) {
  return [formatTime(run.finished_at), run.snapshot && `快照 ${run.snapshot.slice(0, 8)}`, run.detail].filter(Boolean).join('，')
}

onMounted(check)
</script>

<template>
  <el-descriptions title="主存储" :column="1" border>
    <template #extra><IconButton :icon="Refresh" label="重新检查" :loading="checking" @click="check" /></template>
    <el-descriptions-item label="附件保存位置">
      {{ info ? (info.primary === 'nas' ? '专用 NAS 目录' : '服务器本地卷') : '未取得状态' }}
    </el-descriptions-item>
    <el-descriptions-item label="NAS 连接检查">
      {{ !info ? '未取得状态' : info.nas_ready === null ? '未启用' : info.nas_ready ? '已识别专用目录' : '不可用，文件操作已暂停' }}
    </el-descriptions-item>
    <el-descriptions-item label="剩余空间">
      {{ info?.disk_free == null ? '未取得状态' : formatSize(info.disk_free) }}
      <el-tag v-if="info?.disk_low" class="status-tag" type="danger" disable-transitions>不足，已暂停上传</el-tag>
    </el-descriptions-item>
  </el-descriptions>
  <el-descriptions v-if="info" title="备份" :column="1" border class="backup">
    <el-descriptions-item label="最近成功的备份">
      <template v-if="info.backup.last_ok">{{ describe(info.backup.last_ok) }}</template>
      <template v-else>尚无成功备份：确认已按安装结束时的提示加了每日定时任务</template>
      <el-tag v-if="info.backup.overdue && info.backup.last_ok" class="status-tag" type="danger" disable-transitions>逾期</el-tag>
    </el-descriptions-item>
    <el-descriptions-item label="最近一次失败">
      <span v-if="info.backup.last_failure" :class="info.backup.failing ? 'failing' : 'old'">
        {{ describe(info.backup.last_failure) }}
      </span>
      <template v-else>无</template>
    </el-descriptions-item>
    <el-descriptions-item label="最近一次恢复演练">
      <template v-if="info.drill.last">
        <el-tag class="status-tag" :type="info.drill.last.ok ? 'success' : 'danger'" disable-transitions>{{ info.drill.last.ok ? '通过' : '失败' }}</el-tag>
        {{ describe(info.drill.last) }}
      </template>
      <template v-else>尚无恢复演练</template>
      <el-tag v-if="info.drill.overdue" class="status-tag" type="danger" disable-transitions>逾期</el-tag>
    </el-descriptions-item>
  </el-descriptions>
</template>

<style scoped>
.backup {
  margin-top: 24px;
}
.failing {
  color: var(--el-color-danger);
}
.old {
  color: var(--el-text-color-secondary);
}
</style>
