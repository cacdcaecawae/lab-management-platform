<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { projectsApi } from '@/modules/projects/api'
import type { Project, ProjectLog } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatTime, toDateStr } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import ProjectBoard from '@/components/ProjectBoard.vue'
import ProjectFormDialog from '@/modules/projects/components/ProjectFormDialog.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)

const project = ref<Project | null>(null)
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const editing = ref(false)
const boardTab = ref(route.query.tab === "tasks" ? "tasks" : "progress")
const canEdit = computed(() => !!project.value && (auth.isSupervisor || project.value.leader.id === auth.user?.id))

async function load() {
  try {
    project.value = await projectsApi.get(id)
  } catch (e) {
    loadError.value = errorMessage(e)
  }
}

// ---- progress logs ----
const logs = ref<ProjectLog[]>([])
const logPage = ref(1)
const hasMore = ref(false)

async function loadLogs(reset = false) {
  if (reset) logPage.value = 1
  try {
    const res = await projectsApi.logs(id, { page: logPage.value })
    logs.value = reset ? res.results : [...logs.value, ...res.results]
    hasMore.value = !!res.next
  } catch (e) {
    showError(e)
  }
}

function more() {
  logPage.value++
  loadLogs()
}

const logForm = reactive({ date: toDateStr(new Date()), content: '' })
const logErrors = useFieldErrors(['date', 'content'])
const addingLog = ref(false)

async function addLog() {
  addingLog.value = true
  try {
    await projectsApi.addLog(id, logForm)
    logForm.content = ''
    logErrors.clear()
    ElMessage.success('已添加进展')
    loadLogs(true)
  } catch (e) {
    logErrors.handle(e)
  } finally {
    addingLog.value = false
  }
}

load()
loadLogs(true)
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'projects' })">返回项目列表</el-button></template>
  </el-result>
  <template v-else-if="project">
    <el-card class="card">
      <template #header>
        <div class="actions">
          <el-page-header :content="project.name" @back="router.push({ name: 'projects' })" />
          <span style="flex: 1" />
          <el-button v-if="canEdit" type="primary" @click="editing = true">编辑项目</el-button>
        </div>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="负责人">{{ project.leader.name }}</el-descriptions-item>
        <el-descriptions-item label="状态"><StatusTag :status="project.status" /></el-descriptions-item>
        <el-descriptions-item label="当前阶段">{{ project.stage }}</el-descriptions-item>
        <el-descriptions-item label="成员">
          <div class="actions">
            <el-tag v-for="m in project.members" :key="m.id" type="info" disable-transitions>{{ m.name }}</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="说明"><pre class="pre">{{ project.description }}</pre></el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatTime(project.updated_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-tabs v-model="boardTab">
      <el-tab-pane label="进展" name="progress" />
      <el-tab-pane label="任务" name="tasks" />
      <el-tab-pane label="里程碑" name="milestones" />
    </el-tabs>
    <ProjectBoard :project="project" :session-user-id="auth.user?.id" :can-manage="canEdit" :tab="boardTab" />
    <el-card v-if="boardTab === 'progress'" class="card" header="项目进展">
      <el-form v-if="canEdit" label-position="top" class="log-form" @submit.prevent="addLog">
        <el-form-item label="日期" :error="logErrors.fe('date')">
          <el-date-picker v-model="logForm.date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
        </el-form-item>
        <el-form-item label="进展内容" :error="logErrors.fe('content')">
          <el-input v-model="logForm.content" type="textarea" :autosize="{ minRows: 2 }" />
        </el-form-item>
        <el-alert v-for="msg in logErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
        <el-button type="primary" :loading="addingLog" native-type="submit">添加进展</el-button>
      </el-form>
      <el-empty v-if="!logs.length" description="暂无进展" />
      <el-timeline>
        <el-timeline-item v-for="log in logs" :key="log.id" :timestamp="log.date" placement="top">
          <pre class="pre">{{ log.content }}</pre>
          <div class="meta">{{ log.author.name }} · {{ formatTime(log.created_at) }}</div>
        </el-timeline-item>
      </el-timeline>
      <el-button v-if="hasMore" link type="primary" @click="more">加载更多</el-button>
    </el-card>

    <ProjectFormDialog v-model="editing" :project="project" @saved="(p) => (project = p)" />
  </template>
</template>

<style scoped>
.log-form {
  margin-bottom: 24px;
}
.meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 4px;
}
</style>
