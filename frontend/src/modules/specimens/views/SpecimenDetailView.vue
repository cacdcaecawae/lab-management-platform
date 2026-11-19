<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { specimensApi } from '../api'
import { projectsApi } from '@/api/projects'
import type { Specimen, SpecimenLoan } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { DEFECT_KIND_LABELS, SPECIMEN_KIND_LABELS, formatTime, toDateStr } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import SpecimenFormDialog from '../components/SpecimenFormDialog.vue'

// The history uses the model's field names; these differ from the shared labels (code there is 设备编号).
const HISTORY_LABELS = { code: '编号', kind: '类别', material: '材料', dimensions: '尺寸', defects_public: '缺陷参数对学生公开' }
const HISTORY_VALUES = { kind: SPECIMEN_KIND_LABELS }

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const specimen = ref<Specimen | null>(null)
const loans = ref<SpecimenLoan[]>([])
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const editing = ref(false)
const historyOpen = ref(false)

async function load() {
  try {
    specimen.value = await specimensApi.get(id)
    loans.value = (await specimensApi.loans(id)).results // shortcut: the latest 20 loans
  } catch (e) {
    loadError.value = errorMessage(e)
  }
}

const loan = computed(() => specimen.value?.current_loan ?? null)
const canBorrow = computed(() => specimen.value?.status === 'available' && !loan.value)
const canReturn = computed(() => !!loan.value && (loan.value.borrower.id === auth.user?.id || auth.isManager))
const today = toDateStr(new Date())
const overdue = (l: SpecimenLoan) => !l.returned_at && !!l.due_date && l.due_date < today

const borrowing = ref(false)
const borrowForm = reactive({ project_id: null as number | null, purpose: '', due_date: null as string | null })
const borrowErrors = useFieldErrors(['project_id', 'purpose', 'due_date'])
const projects = useOptions(() => projectsApi.list({ page_size: 100 }))
const saving = ref(false)

function openBorrow() {
  Object.assign(borrowForm, { project_id: null, purpose: '', due_date: null })
  borrowErrors.clear()
  borrowing.value = true
}

async function borrow() {
  saving.value = true
  try {
    await specimensApi.borrow(id, { ...borrowForm, due_date: borrowForm.due_date || null })
    borrowing.value = false
    ElMessage.success('已登记借用')
  } catch (e) {
    borrowErrors.handle(e)
  } finally {
    saving.value = false
  }
  load()
}

async function giveBack() {
  const loanIdSeen = loan.value?.id // capture before the asynchronous confirmation, not when it resolves
  if (!loanIdSeen) return
  let note = ''
  try {
    ;({ value: note } = await ElMessageBox.prompt('归还时试件的状况，例如"完好""表面有划痕"，可不填。', `归还 ${specimen.value!.code}`, {
      inputPlaceholder: '归还说明',
      inputValidator: (v) => (v ?? '').length <= 200 || '不超过 200 字',
    }))
  } catch {
    return
  }
  try {
    await specimensApi.giveBack(id, loanIdSeen, (note ?? '').trim())
    ElMessage.success('已登记归还')
  } catch (e) {
    showError(e)
  }
  load()
}

load()
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'specimens' })">返回试样与标准件</el-button></template>
  </el-result>
  <template v-else-if="specimen">
    <el-card class="card">
      <template #header>
        <div class="actions">
          <el-page-header @back="router.push({ name: 'specimens' })">
            <template #content><span class="code">{{ specimen.code }}</span> {{ specimen.name }}</template>
          </el-page-header>
          <span class="grow" />
          <el-button @click="historyOpen = true">修改历史</el-button>
          <el-button v-if="auth.isManager" @click="editing = true">编辑试件</el-button>
          <el-button v-if="canReturn" type="primary" @click="giveBack">登记归还</el-button>
          <el-button v-else-if="canBorrow" type="primary" @click="openBorrow">借用</el-button>
        </div>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="状态">
          <div class="actions">
            <StatusTag :status="specimen.status" />
            <el-tag v-if="loan" class="status-tag" :type="overdue(loan) ? 'danger' : 'warning'" disable-transitions>
              {{ loan.borrower.name }} 借用中{{ overdue(loan) ? '，已逾期' : '' }}
            </el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="类别">{{ SPECIMEN_KIND_LABELS[specimen.kind] }}</el-descriptions-item>
        <el-descriptions-item label="材料">{{ specimen.material }}</el-descriptions-item>
        <el-descriptions-item label="尺寸">{{ specimen.dimensions }}</el-descriptions-item>
        <el-descriptions-item label="存放位置">{{ specimen.location }}</el-descriptions-item>
        <el-descriptions-item label="保管人">{{ specimen.custodian?.name }}</el-descriptions-item>
        <el-descriptions-item label="更新时间" :span="2">{{ formatTime(specimen.updated_at) }}</el-descriptions-item>
        <el-descriptions-item label="备注" :span="2"><pre class="pre">{{ specimen.notes }}</pre></el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="card">
      <template #header>
        <div class="actions">
          <span>缺陷参数</span>
          <el-tag v-if="auth.isSupervisor" size="small" :type="specimen.defects_public ? 'success' : 'info'" disable-transitions>
            {{ specimen.defects_public ? '学生可见' : '学生看不到' }}
          </el-tag>
        </div>
      </template>
      <p v-if="specimen.defects === null" class="muted">缺陷参数未公开（用于盲测），管理员公开后才能看到。</p>
      <el-table v-else :data="specimen.defects" empty-text="没有登记缺陷">
        <el-table-column label="类型" min-width="80">
          <template #default="{ row }">{{ DEFECT_KIND_LABELS[row.kind] }}</template>
        </el-table-column>
        <el-table-column prop="size_mm" label="尺寸（mm）" min-width="90" align="right" />
        <el-table-column prop="depth_mm" label="埋深（mm）" min-width="90" align="right" />
        <el-table-column prop="position" label="位置" min-width="140" />
        <el-table-column prop="note" label="备注" min-width="120" />
      </el-table>
    </el-card>

    <el-card class="card" header="借用记录">
      <el-table :data="loans" empty-text="还没有借用记录">
        <el-table-column label="借用人" min-width="80">
          <template #default="{ row }">{{ row.borrower.name }}</template>
        </el-table-column>
        <el-table-column label="借出" min-width="130">
          <template #default="{ row }">{{ formatTime(row.borrowed_at) }}</template>
        </el-table-column>
        <el-table-column label="预计归还" min-width="100">
          <template #default="{ row }">
            <span :class="{ overdue: overdue(row as SpecimenLoan) }">{{ row.due_date }}{{ overdue(row as SpecimenLoan) ? '（已逾期）' : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="归还" min-width="150">
          <template #default="{ row }">
            <span v-if="row.returned_at">{{ formatTime(row.returned_at) }}<span v-if="row.return_note" class="muted"> · {{ row.return_note }}</span></span>
            <span v-else class="muted">未归还</span>
          </template>
        </el-table-column>
        <el-table-column label="项目" min-width="110">
          <template #default="{ row }">{{ row.project?.name }}</template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途" min-width="120" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-dialog v-model="borrowing" :title="`借用 ${specimen.code}`" width="min(460px, 95vw)">
      <el-form label-position="top" @submit.prevent="borrow">
        <el-form-item label="项目" :error="borrowErrors.fe('project_id')">
          <el-select v-model="borrowForm.project_id" aria-label="项目" placeholder="可不选" clearable filterable>
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="用途" :error="borrowErrors.fe('purpose')"><el-input v-model="borrowForm.purpose" /></el-form-item>
        <el-form-item label="预计归还日期" :error="borrowErrors.fe('due_date')">
          <el-date-picker v-model="borrowForm.due_date" type="date" value-format="YYYY-MM-DD" aria-label="预计归还日期" placeholder="可不填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="borrowing = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="borrow">借用</el-button>
      </template>
    </el-dialog>
    <SpecimenFormDialog v-model="editing" :specimen="specimen" @saved="load" />
    <HistoryDrawer v-model="historyOpen" :load="() => specimensApi.history(id)" :labels="HISTORY_LABELS" :values="HISTORY_VALUES" />
  </template>
</template>

<style scoped>
.muted {
  color: var(--el-text-color-secondary);
}
.overdue {
  color: var(--el-color-danger);
}
.grow {
  flex: 1;
}
</style>
