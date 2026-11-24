<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { projectsApi } from '@/modules/projects/api'
import type { MilestoneWrite, Project, ProjectMilestone, ProjectTask, TaskStatus, TaskWrite } from '@/api/types'
import { errorMessage } from '@/utils/errors'
import { formatTime, toDateStr } from '@/utils/format'
import FormDialog from '@/components/FormDialog.vue'
import PageToolbar from '@/components/PageToolbar.vue'

const props = defineProps<{ project: Project; sessionUserId?: number; canManage: boolean; tab: string }>()
const cols = [{ key: 'todo', name: '待办' }, { key: 'doing', name: '进行中' }, { key: 'done', name: '完成' }] as const
const CHANGE_LABELS: Record<string, string> = {
  title: '标题', description: '说明', status: '状态', assignee: '负责人', milestone: '里程碑', due_date: '截止日期',
}
const STATUS_NAMES: Record<string, string> = Object.fromEntries(cols.map((c) => [c.key, c.name]))
// A status by its column's name; an id (entries from before the history kept names) as 编号 n.
const shown = (field: string, v: unknown) =>
  v == null || v === '' ? '无' : field === 'status' ? (STATUS_NAMES[String(v)] ?? v) : typeof v === 'number' ? `编号 ${v}` : v
const canEdit = computed(() => props.canManage || props.project.members.some(m => m.id === props.sessionUserId))
const canDelete = (task: ProjectTask) => props.canManage || task.created_by === props.sessionUserId
const mine = ref(false)
const assignee = ref<number | ''>('')
const onMilestone = ref<number | ''>('')
// The board's filters: 只看我的 wins over a chosen assignee.
const taskQuery = () => ({ assignee: mine.value ? props.sessionUserId : assignee.value || undefined, milestone: onMilestone.value || undefined })
const error = ref('')
const busy = ref(false)
const lanes = reactive<Record<TaskStatus, { rows: ProjectTask[]; page: number; more: boolean }>>({
  todo: { rows: [], page: 1, more: false }, doing: { rows: [], page: 1, more: false }, done: { rows: [], page: 1, more: false },
})
const milestones = ref<ProjectMilestone[]>([])
const milestonePage = ref(0)
const moreMilestones = ref(false)
let version = 0
let milestoneVersion = 0

async function loadBoard() {
  const token = ++version
  try {
    const pages = await Promise.all(cols.map(({ key }) =>
      projectsApi.tasks(props.project.id, { status: key, ...taskQuery() })))
    if (token !== version) return
    cols.forEach(({ key }, i) => Object.assign(lanes[key], { rows: pages[i].results, page: 1, more: !!pages[i].next }))
  } catch (e) {
    if (token === version) error.value = errorMessage(e)
  }
}

async function nextTasks(key: TaskStatus) {
  const token = version
  const lane = lanes[key]
  const page = lane.page + 1
  busy.value = true
  error.value = ''
  try {
    const result = await projectsApi.tasks(props.project.id, { status: key, page, ...taskQuery() })
    if (token === version) Object.assign(lane, { rows: [...lane.rows, ...result.results], page, more: !!result.next })
  } catch (e) {
    if (token === version) error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

async function loadMilestones(reset = true) {
  const token = ++milestoneVersion
  const page = reset ? 1 : milestonePage.value + 1
  try {
    const res = await projectsApi.milestones(props.project.id, { page })
    if (token !== milestoneVersion) return
    milestones.value = reset ? res.results : [...milestones.value, ...res.results]
    milestonePage.value = page
    moreMilestones.value = !!res.next
  } catch (e) {
    if (token === milestoneVersion) error.value = errorMessage(e)
  }
}

watch(() => props.tab, tab => {
  error.value = ''
  if (tab === 'tasks') void loadBoard()
  if (tab === 'tasks' || tab === 'milestones') void loadMilestones() // the board filters by milestone
}, { immediate: true })
watch([mine, assignee, onMilestone], () => { error.value = ''; void loadBoard() })

const taskDialog = ref(false)
const selectedTask = ref<ProjectTask | null>(null)
const taskForm = reactive<TaskWrite>({ title: '', description: '', due_date: null, assignee_id: null, milestone_id: null, status: 'todo' })
const formError = ref('')
async function editTask(task: ProjectTask | null) {
  selectedTask.value = task
  Object.assign(taskForm, {
    title: task?.title ?? '', description: task?.description ?? '', due_date: task?.due_date ?? null,
    assignee_id: task?.assignee?.id ?? null, milestone_id: task?.milestone?.id ?? null, status: task?.status ?? 'todo',
  })
  formError.value = ''
  taskDialog.value = true
  await loadMilestones()
}
const memberChoices = computed(() => {
  const members = [...props.project.members]
  if (!members.some(m => m.id === props.project.leader.id)) members.unshift(props.project.leader)
  return members
})
const shownAssignee = computed(() => selectedTask.value?.assignee)
const shownMilestone = computed(() => selectedTask.value?.milestone)

async function saveTask() {
  const task = selectedTask.value
  const body: Partial<TaskWrite> = { ...taskForm }
  if (task) {
    // Preserve fields the editor did not change, including a departed assignee.
    delete body.status
    if (body.title === task.title) delete body.title
    if (body.description === task.description) delete body.description
    if (body.due_date === task.due_date) delete body.due_date
    if (body.assignee_id === (task.assignee?.id ?? null)) delete body.assignee_id
    if (body.milestone_id === (task.milestone?.id ?? null)) delete body.milestone_id
  }
  await mutate(async () => {
    if (task) { if (Object.keys(body).length) await projectsApi.updateTask(task.id, body) }
    else await projectsApi.addTask(props.project.id, body)
    taskDialog.value = false
  }, true)
}

const milestoneDialog = ref(false)
const selectedMilestone = ref<ProjectMilestone | null>(null)
const milestoneForm = reactive<MilestoneWrite>({ title: '', due_date: null, done: false })
function editMilestone(milestone: ProjectMilestone | null) {
  selectedMilestone.value = milestone
  Object.assign(milestoneForm, { title: milestone?.title ?? '', due_date: milestone?.due_date ?? null, done: !!milestone?.done_at })
  formError.value = ''
  milestoneDialog.value = true
}

async function saveMilestone() {
  const item = selectedMilestone.value
  const body: MilestoneWrite = { ...milestoneForm }
  await mutate(async () => {
    if (item) {
      // An unrelated edit must not overwrite another editor's completion or due date.
      const changes: Partial<MilestoneWrite> = {}
      if (body.title !== item.title) changes.title = body.title
      if (body.due_date !== item.due_date) changes.due_date = body.due_date
      if (body.done !== !!item.done_at) changes.done = body.done
      if (Object.keys(changes).length) await projectsApi.updateMilestone(item.id, changes)
    } else {
      await projectsApi.addMilestone(props.project.id, body)
    }
    milestoneDialog.value = false
  }, true)
}

async function mutate(action: () => Promise<unknown>, form = false) {
  busy.value = true
  error.value = formError.value = ''
  try {
    await action()
    if (props.tab === 'tasks') await loadBoard()
    else if (props.tab === 'milestones') await loadMilestones()
  } catch (e) {
    if (form) formError.value = errorMessage(e)
    else error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

async function remove(title: string, action: () => Promise<unknown>, note: string) {
  try {
    await ElMessageBox.confirm(note, `删除「${title}」？`, { type: 'warning' })
  } catch {
    return
  }
  await mutate(action)
}

const late = (task: ProjectTask) => task.status !== 'done' && task.due_date && task.due_date < toDateStr(new Date())
const transitions: Record<TaskStatus, { to: TaskStatus; label: string }[]> = {
  todo: [{ to: 'doing', label: '→ 进行中' }, { to: 'done', label: '→ 完成' }],
  doing: [{ to: 'todo', label: '↩ 待办' }, { to: 'done', label: '→ 完成' }],
  done: [{ to: 'todo', label: '↩ 待办' }, { to: 'doing', label: '→ 进行中' }],
}
</script>

<template>
  <el-alert v-if="error && tab !== 'progress'" :title="error" type="error" />
  <template v-if="tab === 'tasks'">
    <PageToolbar>
      <el-checkbox v-model="mine">只看我的</el-checkbox>
      <el-select v-if="!mine" v-model="assignee" placeholder="全部负责人" aria-label="负责人" clearable filterable>
        <el-option v-for="m in memberChoices" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-select v-model="onMilestone" placeholder="全部里程碑" aria-label="里程碑" clearable filterable>
        <el-option v-for="m in milestones" :key="m.id" :label="m.title" :value="m.id" />
      </el-select>
      <template #actions>
        <el-button v-if="canEdit" type="primary" :disabled="busy" @click="editTask(null)">新建任务</el-button>
      </template>
    </PageToolbar>
    <div class="board">
      <section v-for="col in cols" :key="col.key" :data-status="col.key">
        <h3>{{ col.name }}</h3>
        <p v-if="!lanes[col.key].rows.length">暂无任务</p>
        <el-card v-for="task in lanes[col.key].rows" :key="task.id" class="task" shadow="never">
          <strong>{{ task.title }}</strong>
          <p v-if="task.description" class="pre">{{ task.description }}</p>
          <p>{{ task.assignee?.name || '未分配' }}<span v-if="task.assignee && !task.assignee.current">（已不在项目中）</span></p>
          <p v-if="task.due_date" :class="{ late: late(task) }">截止 {{ task.due_date }}<template v-if="late(task)">，已逾期</template></p>
          <p v-if="task.milestone">里程碑：{{ task.milestone.title }}</p>
          <div class="actions">
            <template v-if="canEdit">
              <el-button v-for="move in transitions[task.status]" :key="move.to" link :disabled="busy"
                @click="mutate(() => projectsApi.updateTask(task.id, { status: move.to }))">{{ move.label }}</el-button>
              <el-button link :disabled="busy" @click="editTask(task)">编辑</el-button>
            </template>
            <el-button v-if="canDelete(task)" link type="danger" :disabled="busy"
              @click="remove(task.title, () => projectsApi.deleteTask(task.id), '任务及其修改历史将被删除。')">删除</el-button>
          </div>
          <details v-if="task.history.length">
            <summary>修改历史</summary>
            <ul>
              <li v-for="(entry, i) in task.history" :key="i">
                {{ entry.actor }} · {{ formatTime(entry.created_at) }}
                <div v-for="(change, field) in entry.changes" :key="field">
                  {{ CHANGE_LABELS[field as string] ?? field }}：{{ shown(field as string, change.before) }} → {{ shown(field as string, change.after) }}
                </div>
              </li>
            </ul>
          </details>
        </el-card>
        <el-button v-if="lanes[col.key].more" link :disabled="busy" @click="nextTasks(col.key)">加载更多{{ col.name }}</el-button>
      </section>
    </div>
  </template>

  <template v-if="tab === 'milestones'">
    <PageToolbar>
      <template #actions>
        <el-button v-if="canManage" type="primary" :disabled="busy" @click="editMilestone(null)">新建里程碑</el-button>
      </template>
    </PageToolbar>
    <el-empty v-if="!milestones.length" description="暂无里程碑" />
    <el-card v-for="item in milestones" :key="item.id" class="task milestone" shadow="never">
      <strong>{{ item.title }}</strong>
      <p>{{ item.due_date ?? '无截止日期' }} · {{ item.done_at ? '已完成' : '未完成' }} · 任务 {{ item.task_done }} / {{ item.task_total }}</p>
      <el-button v-if="canManage" link :disabled="busy" @click="editMilestone(item)">编辑</el-button>
      <el-button v-if="canManage" link type="danger" :disabled="busy"
        @click="remove(item.title, () => projectsApi.deleteMilestone(item.id), '只删除里程碑，关联任务会保留。')">删除</el-button>
    </el-card>
    <el-button v-if="moreMilestones" link @click="loadMilestones(false)">加载更多</el-button>
  </template>

  <FormDialog v-model="taskDialog" :title="selectedTask ? '编辑任务' : '新建任务'" :loading="busy" :disabled="!taskForm.title.trim()" @submit="saveTask">
    <el-form-item label="标题" required><el-input v-model="taskForm.title" maxlength="200" /></el-form-item>
    <el-form-item label="说明"><el-input v-model="taskForm.description" type="textarea" :autosize="{ minRows: 2 }" /></el-form-item>
    <div class="form-grid">
      <el-form-item label="负责人">
        <el-select v-model="taskForm.assignee_id" clearable :value-on-clear="null" placeholder="不分配">
          <el-option v-if="shownAssignee && !shownAssignee.current" :value="shownAssignee.id"
            :label="`${shownAssignee.name}（已不在项目中）`" disabled />
          <el-option v-for="m in memberChoices.filter(m => shownAssignee?.current !== false || m.id !== shownAssignee.id)"
            :key="m.id" :value="m.id" :label="m.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="截止日期"><el-date-picker v-model="taskForm.due_date" type="date" value-format="YYYY-MM-DD" :value-on-clear="null" /></el-form-item>
      <el-form-item label="里程碑">
        <el-select v-model="taskForm.milestone_id" :value-on-clear="null" clearable placeholder="不关联">
          <el-option v-if="shownMilestone && !milestones.some(m => m.id === shownMilestone?.id)"
            :value="shownMilestone.id" :label="shownMilestone.title" />
          <el-option v-for="m in milestones" :key="m.id" :value="m.id" :label="m.title" />
        </el-select>
        <el-button v-if="moreMilestones" link @click="loadMilestones(false)">加载更多里程碑</el-button>
      </el-form-item>
    </div>
    <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
  </FormDialog>

  <FormDialog v-model="milestoneDialog" :title="selectedMilestone ? '编辑里程碑' : '新建里程碑'" size="sm" :loading="busy" :disabled="!milestoneForm.title.trim()" @submit="saveMilestone">
    <el-form-item label="标题" required><el-input v-model="milestoneForm.title" maxlength="200" /></el-form-item>
    <el-form-item label="截止日期"><el-date-picker v-model="milestoneForm.due_date" type="date" value-format="YYYY-MM-DD" :value-on-clear="null" /></el-form-item>
    <el-form-item><el-checkbox v-model="milestoneForm.done">标为完成</el-checkbox></el-form-item>
    <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
  </FormDialog>
</template>

<style scoped>
.board { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(250px, 100%), 1fr)); gap: 12px; }
.board section { padding: 4px 12px 12px; border-radius: var(--lab-radius-lg); background: var(--lab-bg); }
.board h3 { margin: 10px 0 4px; font-size: 15px; }
.task { margin: 10px 0; overflow-wrap: anywhere; }
.late { color: var(--el-color-danger); }
/* on the page's white card, not a grey lane like the tasks: an edge of its own */
.milestone { --el-card-border-color: var(--lab-border); }
</style>
