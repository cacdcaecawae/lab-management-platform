<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'
import type { VersionInfo } from '@/api/types'
import { systemApi } from '@/modules/system/api'
import { showError } from '@/utils/errors'
import { formatTime } from '@/utils/format'

// Shared with the sidebar (stores/ops), which marks 版本 when an update is available. null until the first check
// answers, or when it failed: 重新检查 is there either way.
const info = defineModel<VersionInfo | null>('info', { default: null })
const checking = ref(false)

async function check() {
  checking.value = true
  try {
    info.value = await systemApi.version(true)
  } catch (error) {
    showError(error)
  } finally {
    checking.value = false
  }
}

// 立即更新: scripts/update-agent.sh on the server runs update.sh and writes /update-status.json as it goes.
type Status = { state: 'running' | 'done' | 'failed'; step: number; target: string; started: number }
const STEPS = ['等待服务器开始更新', '拉取新版本', '停止网站并备份', '启动新版本并检查']
const PERCENT = [5, 20, 45, 75]
const status = ref<Status | null>(null)
const siteUp = ref(true)
let timer = 0
onBeforeUnmount(() => clearTimeout(timer))

async function update() {
  const { current, latest } = info.value! // its button shows only with an update available
  const target = latest!
  try {
    await ElMessageBox.confirm(
      `更新时网站会停止几分钟，先备份再切换。新版本起不来时：没改数据库结构的，自动退回 ${current}；改过的，网站保持停止，需要到服务器上处理。`,
      `更新到 ${target}`,
      { type: 'warning', confirmButtonText: '立即更新' },
    )
  } catch {
    return
  }
  try {
    const { requested_at } = await systemApi.update(target)
    status.value = { state: 'running', step: 0, target, started: requested_at }
    poll(target, requested_at)
  } catch (error) {
    showError(error)
  }
}

async function poll(target: string, since: number) {
  try {
    const res = await fetch('/update-status.json', { cache: 'no-store' })
    const s: Status | null = res.ok ? await res.json() : null
    // An earlier update's file stays there until the server picks this request up.
    if (s?.target === target && s.started >= since - 5) status.value = s
  } catch {
    // Nginx restarts with the new release.
  }
  if (status.value?.state === 'failed') {
    siteUp.value = await systemApi.version().then(
      (v) => ((info.value = v), true),
      () => false,
    )
  } else if (status.value?.state === 'done') reloadWhenRunning(target)
  else timer = window.setTimeout(() => poll(target, since), 2000)
}

async function reloadWhenRunning(target: string) {
  const v = await systemApi.version().catch(() => null)
  if (v?.current === target) window.location.reload()
  else timer = window.setTimeout(() => reloadWhenRunning(target), 2000)
}

const percent = computed(() => (status.value?.state === 'done' ? 100 : (PERCENT[status.value?.step ?? 0] ?? 5)))
const progressText = computed(() => {
  const s = status.value!
  if (s.state === 'done') return `已更新到 ${s.target}，正在重新载入`
  if (s.state === 'failed')
    return siteUp.value
      ? `没有更新，网站仍是 ${info.value!.current}。原因在服务器安装目录的 run/update/update.log`
      : '更新没有完成，网站已停止，需要到服务器上处理。原因在安装目录的 run/update/update.log'
  return s.step ? `第 ${s.step} 步，共 3 步：${STEPS[s.step]}` : STEPS[0]
})
</script>

<template>
  <el-descriptions :column="1" border class="facts">
    <template #extra>
      <IconButton :icon="Refresh" label="重新检查" :loading="checking" :disabled="!!status && status.state !== 'failed'" @click="check" />
    </template>
    <template v-if="info">
      <el-descriptions-item label="当前版本">{{ info.current === 'local' ? '从源码构建（local）' : info.current }}</el-descriptions-item>
      <el-descriptions-item label="最新版本">
        <el-link v-if="info.latest" :href="info.url" target="_blank" type="primary">{{ info.latest }}（发布说明）</el-link>
        <span v-else-if="info.error">{{ info.error }}</span>
        <span v-else>还没有发布过正式版本</span>
      </el-descriptions-item>
      <el-descriptions-item label="检查时间">{{ formatTime(info.checked_at) }}</el-descriptions-item>
    </template>
    <el-descriptions-item v-else label="当前版本">—</el-descriptions-item>
  </el-descriptions>

  <div v-if="status" class="progress">
    <el-progress
      :percentage="percent"
      :status="status.state === 'done' ? 'success' : status.state === 'failed' ? 'exception' : undefined"
    />
    <p>{{ progressText }}</p>
  </div>
  <el-alert v-else-if="info?.update_available" type="warning" :closable="false" show-icon :title="`有新版本 ${info.latest}`">
    <el-button v-if="info.agent" type="primary" class="update" @click="update">立即更新</el-button>
    <template v-else>
      <p>在服务器的仓库目录里运行：</p>
      <pre class="cmd">bash scripts/update.sh {{ info.latest }}</pre>
      <p>更新时网站会停止，先备份再切换。新版本起不来时：没改数据库结构的，自动退回 {{ info.current }}；改过或无法确认的，网站保持停止、保留当前数据，需要运维按 README"服务器部署"一节处理。</p>
      <p>在同一目录运行一次下面的命令，以后可以在这里直接点"立即更新"：</p>
      <pre class="cmd">bash scripts/update-agent.sh --install</pre>
    </template>
  </el-alert>
  <p v-else-if="info?.latest && info.current !== 'local'" class="note">已是最新版本。</p>
</template>

<style scoped>
.facts {
  max-width: 560px;
  margin-bottom: 16px;
}
.progress {
  max-width: 560px;
}
.update {
  margin-top: 8px;
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
