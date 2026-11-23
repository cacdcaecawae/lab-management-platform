<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'
import { storageApi, type OpsStorage, type Usage } from '@/api/storageUsage'
import { systemApi, type OpsRun, type StorageInfo } from '@/modules/system/api'
import { showError } from '@/utils/errors'
import { formatSize as size, formatTime } from '@/utils/format'

// 存储与备份 (ops): where the attachments are and how full that disk is, the backups and restore drills, and what each
// group keeps. The status is shared with the sidebar, which marks this page when it needs attention.
const info = defineModel<StorageInfo | null>('info', { default: null })
const usage = ref<OpsStorage | null>(null)
const checking = ref(false)

async function check() {
  checking.value = true
  await Promise.all([
    systemApi.storage().then((s) => (info.value = s), showError),
    storageApi.ops().then((u) => (usage.value = u), showError),
  ])
  checking.value = false
}
onMounted(check)

function describe(run: OpsRun) {
  return [formatTime(run.finished_at), run.snapshot && `快照 ${run.snapshot.slice(0, 8)}`, run.detail].filter(Boolean).join('，')
}

const disk = computed(() => usage.value?.disk.filesystem ?? null)
const usedPercent = computed(() => (disk.value ? Math.round((disk.value.used_bytes / disk.value.total_bytes) * 100) : 0))
// Uploads stop when either the attachment disk or the upload spool runs low (core.disk); the spool can sit on a smaller
// disk (always the server's own with a NAS). Shown only when it, not the attachment disk, is the one that limits.
const spool = computed(() => {
  const free = info.value?.disk_free
  return free != null && disk.value && disk.value.free_bytes - free > 1024 ** 3 ? free : null
})

const MODULES: Record<string, string> = {
  raw: '原始数据', knowledge: '知识库', meetings: '组会', procurement: '采购及报销', achievements: '成果全文', equipment: '设备使用照片',
}
const amount = (u?: Usage) => (u ? size(u.known_bytes) + (u.unknown_files ? `，另 ${u.unknown_files} 个大小未知` : '') : '—')
// Only months in which something still kept was uploaded: twelve empty columns say nothing.
const months = computed(() => usage.value?.month_keys.filter((m) => usage.value!.groups.some((g) => g.months[m])) ?? [])
</script>

<template>
  <el-descriptions title="主存储" :column="1" border label-width="140px">
    <template #extra><IconButton :icon="Refresh" label="重新检查" :loading="checking" @click="check" /></template>
    <el-descriptions-item label="附件保存位置">
      {{ info ? (info.primary === 'nas' ? '专用 NAS 目录' : '服务器本地卷') : '未取得状态' }}
    </el-descriptions-item>
    <el-descriptions-item v-if="info?.primary === 'nas'" label="NAS 连接检查">
      {{ info.nas_ready ? '已识别专用目录' : '不可用，文件操作已暂停' }}
    </el-descriptions-item>
    <el-descriptions-item label="磁盘">
      <template v-if="disk">
        <el-progress
          class="bar"
          :percentage="usedPercent"
          :stroke-width="8"
          :show-text="false"
          :status="info?.disk_low && spool == null ? 'exception' : undefined"
          :aria-label="`已用 ${usedPercent}%`"
        />
        已用 {{ size(disk.used_bytes) }}，共 {{ size(disk.total_bytes) }}，剩余 {{ size(disk.free_bytes) }}
      </template>
      <template v-else-if="usage?.disk.kind === 'non_local'">文件不在本机磁盘上，没有容量数据</template>
      <template v-else-if="info?.disk_free != null">剩余 {{ size(info.disk_free) }}</template>
      <template v-else>未取得状态</template>
      <el-tag v-if="info?.disk_low && spool == null" class="status-tag" type="danger" disable-transitions>不足，已暂停上传</el-tag>
    </el-descriptions-item>
    <el-descriptions-item v-if="spool != null" label="上传暂存目录">
      剩余 {{ size(spool) }}
      <el-tag v-if="info?.disk_low" class="status-tag" type="danger" disable-transitions>不足，已暂停上传</el-tag>
    </el-descriptions-item>
  </el-descriptions>

  <el-descriptions v-if="info" title="备份" :column="1" border label-width="140px" class="next">
    <el-descriptions-item label="最近成功">
      <template v-if="info.backup.last_ok">{{ describe(info.backup.last_ok) }}</template>
      <template v-else>尚无成功备份：确认已按安装结束时的提示加了每日定时任务</template>
      <el-tag v-if="info.backup.overdue && info.backup.last_ok" class="status-tag" type="danger" disable-transitions>逾期</el-tag>
    </el-descriptions-item>
    <el-descriptions-item label="最近失败">
      <span v-if="info.backup.last_failure" :class="info.backup.failing ? 'failing' : 'old'">
        {{ describe(info.backup.last_failure) }}
      </span>
      <template v-else>无</template>
    </el-descriptions-item>
    <el-descriptions-item label="恢复演练">
      <template v-if="info.drill.last">
        <el-tag class="status-tag" :type="info.drill.last.ok ? 'success' : 'danger'" disable-transitions>{{ info.drill.last.ok ? '通过' : '失败' }}</el-tag>
        {{ describe(info.drill.last) }}
      </template>
      <template v-else>尚无恢复演练</template>
      <el-tag v-if="info.drill.overdue" class="status-tag" type="danger" disable-transitions>逾期</el-tag>
    </el-descriptions-item>
  </el-descriptions>

  <template v-if="usage">
    <h3 class="section">各课题组的文件</h3>
    <el-table :data="usage.groups" empty-text="暂无课题组">
      <el-table-column prop="name" label="课题组" min-width="120" />
      <el-table-column v-for="(label, key) in MODULES" :key="key" :label="label" min-width="96" align="right">
        <template #default="{ row }">{{ amount(row.modules[key]) }}</template>
      </el-table-column>
      <el-table-column label="合计" min-width="96" align="right">
        <template #default="{ row }">{{ amount(row as Usage) }}</template>
      </el-table-column>
    </el-table>
    <h3 class="section">近 12 个月上传、现在还在的文件</h3>
    <el-table v-if="months.length" :data="usage.groups" empty-text="暂无课题组">
      <el-table-column prop="name" label="课题组" min-width="120" />
      <el-table-column v-for="m in months" :key="m" :label="m" min-width="90" align="right">
        <template #default="{ row }">{{ size(row.months[m] ?? 0) }}</template>
      </el-table-column>
    </el-table>
    <p v-else class="muted">近 12 个月没有上传过文件</p>
    <p v-if="usage.projection" class="muted">
      按 {{ usage.projection.basis_months.join('、') }} 估算，一年约 {{ size(usage.projection.annual_retained_known_bytes) }}
    </p>
    <p v-else-if="months.length" class="muted">不满三个完整月份，暂不估算一年的用量</p>
  </template>
</template>

<style scoped>
.next {
  margin-top: 24px;
}
.section {
  margin: 28px 0 12px;
  font-size: var(--el-font-size-medium);
}
.bar {
  max-width: 360px;
  margin-bottom: 6px;
}
.failing {
  color: var(--el-color-danger);
}
.old {
  color: var(--el-text-color-secondary);
}
</style>
