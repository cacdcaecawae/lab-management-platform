<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit } from '@element-plus/icons-vue'
import { projectsApi } from '@/modules/projects/api'
import type { Project, ProjectFile, ProjectLog } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatTime, toDateStr } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import ProjectBoard from '@/modules/projects/components/ProjectBoard.vue'
import ProjectAssets from '@/modules/projects/components/ProjectAssets.vue'
import ProjectFormDialog from '@/modules/projects/components/ProjectFormDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import AttachmentList from '@/components/AttachmentList.vue'
import FormDialog from '@/components/FormDialog.vue'
import IconButton from '@/components/IconButton.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)

const project = ref<Project | null>(null)
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const editing = ref(false)
// ?tab= (the workbench links to 任务) is followed while the page stays open, and kept in the address.
const tabOf = (tab: unknown) => (tab === 'tasks' || tab === 'milestones' || tab === 'assets' ? tab : 'progress')
const boardTab = ref(tabOf(route.query.tab))
watch(() => route.query.tab, (tab) => (boardTab.value = tabOf(tab)))
watch(boardTab, (tab) => {
  if (tab !== tabOf(route.query.tab)) void router.replace({ query: { ...route.query, tab: tab === 'progress' ? undefined : tab } })
})
const canEdit = computed(() => !!project.value && (auth.isSupervisor || project.value.leader.id === auth.user?.id))
// progress logs and project files: also the project's current members
const canLog = computed(() => canEdit.value || !!project.value?.members.some((m) => m.id === auth.user?.id))
// a log is changed or deleted by whoever wrote it, the leader, advisors and managers
const canChangeLog = (log: ProjectLog) => canEdit.value || log.author.id === auth.user?.id

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

const logEdit = reactive({ open: false, id: 0, date: '', content: '' })
const logEditErrors = useFieldErrors(['date', 'content'])
const savingLog = ref(false)

function editLog(log: ProjectLog) {
  Object.assign(logEdit, { open: true, id: log.id, date: log.date, content: log.content })
  logEditErrors.clear()
}

async function saveLog() {
  savingLog.value = true
  try {
    const saved = await projectsApi.updateLog(logEdit.id, { date: logEdit.date, content: logEdit.content })
    logs.value = logs.value.map((l) => (l.id === saved.id ? saved : l))
    logEdit.open = false
    ElMessage.success('已保存')
  } catch (e) {
    logEditErrors.handle(e)
  } finally {
    savingLog.value = false
  }
}

async function removeLog(log: ProjectLog) {
  try {
    await ElMessageBox.confirm(`删除 ${log.date} 的这条进展？删除后无法恢复。`, '删除进展', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch {
    return
  }
  try {
    await projectsApi.removeLog(log.id)
    logs.value = logs.value.filter((l) => l.id !== log.id)
    ElMessage.success('已删除')
  } catch (e) {
    showError(e)
  }
}

// ---- project files (开题、中期、结题报告等) ----
const files = ref<ProjectFile[]>([])
async function loadFiles() {
  try {
    files.value = await projectsApi.files(id)
  } catch (e) {
    showError(e)
  }
}
const canDeleteFile = (f: ProjectFile) => canEdit.value || f.uploaded_by.id === auth.user?.id

load()
loadLogs(true)
loadFiles()
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'projects' })">返回项目列表</el-button></template>
  </el-result>
  <template v-else-if="project">
    <el-card class="card">
      <template #header>
        <PageHeader :back="{ name: 'projects' }" :title="project.name">
          <el-button v-if="canEdit" type="primary" @click="editing = true">编辑项目</el-button>
        </PageHeader>
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

    <el-card class="card" header="项目文件">
      <AttachmentList
        :attachments="files"
        :with-kinds="false"
        accept=""
        hint="开题、中期、结题报告等阶段资料，任意类型，单个不超过 2 GB"
        :upload="canLog ? (file, _kind, onProgress) => projectsApi.upload(project!.id, file, onProgress) : undefined"
        :can-delete="canDeleteFile"
        :remove="projectsApi.removeFile"
        @changed="loadFiles"
      />
    </el-card>

    <el-card class="card">
      <el-tabs v-model="boardTab">
        <el-tab-pane label="进展" name="progress" />
        <el-tab-pane label="任务" name="tasks" />
        <el-tab-pane label="里程碑" name="milestones" />
        <el-tab-pane label="资产" name="assets" />
      </el-tabs>
      <ProjectAssets v-if="boardTab === 'assets'" :project-id="project.id" />
      <ProjectBoard v-else :project="project" :session-user-id="auth.user?.id" :can-manage="canEdit" :tab="boardTab" />
      <template v-if="boardTab === 'progress'">
        <el-form v-if="canLog" label-position="top" class="log-form form-page" @submit.prevent="addLog">
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
            <div class="meta actions">
              <span>{{ log.author.name }} · {{ formatTime(log.created_at) }}</span>
              <template v-if="canChangeLog(log)">
                <IconButton :icon="Edit" label="编辑进展" @click="editLog(log)" />
                <el-button link type="danger" @click="removeLog(log)">删除</el-button>
              </template>
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-button v-if="hasMore" link type="primary" @click="more">加载更多</el-button>
      </template>
    </el-card>

    <ProjectFormDialog v-model="editing" :project="project" @saved="(p) => (project = p)" />
    <FormDialog v-model="logEdit.open" title="编辑进展" size="sm" :loading="savingLog" @submit="saveLog">
      <el-form-item label="日期" :error="logEditErrors.fe('date')" required>
        <el-date-picker v-model="logEdit.date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
      </el-form-item>
      <el-form-item label="进展内容" :error="logEditErrors.fe('content')" required>
        <el-input v-model="logEdit.content" type="textarea" :autosize="{ minRows: 3 }" />
      </el-form-item>
      <el-alert v-for="msg in logEditErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </FormDialog>
  </template>
</template>

<style scoped>
.log-form {
  margin-bottom: 24px;
}
.meta {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 4px;
}
</style>
