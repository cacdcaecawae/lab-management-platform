<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { specimensApi } from '../api'
import { projectsApi } from '@/modules/projects/api'
import type { Specimen, SpecimenLoan } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { DEFECT_KIND_LABELS, SPECIMEN_KIND_LABELS, formatTime, toDateStr } from '@/utils/format'
import { ApiError } from '@/api/client'
import { errorMessage, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import SpecimenFormDialog from '../components/SpecimenFormDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import FormDialog from '@/components/FormDialog.vue'
import PhotoPicker from '@/components/PhotoPicker.vue'
import { Clock, Edit, Printer } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

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

const returning = ref(false)
const returnLoanId = ref<number | null>(null)
const returnForm = reactive({ return_location: '', note: '', photo: null as File | null })
const returnErrors = useFieldErrors(['return_location', 'note', 'photo', 'loan_id_seen'])

function openReturn() {
  if (!loan.value) return
  returnLoanId.value = loan.value.id
  Object.assign(returnForm, { return_location: '', note: '', photo: null })
  returnErrors.clear()
  returning.value = true
}

async function submitReturn() {
  const loanIdSeen = returnLoanId.value
  if (!loanIdSeen) return
  saving.value = true
  try {
    await specimensApi.giveBack(id, loanIdSeen, {
      note: returnForm.note.trim(),
      return_location: returnForm.return_location.trim(),
      photo: returnForm.photo,
    })
    returning.value = false
    ElMessage.success('已登记归还')
    load()
  } catch (e) {
    if (e instanceof ApiError && (e.body.code === 'stale_loan' || e.body.code === 'not_on_loan')) {
      returning.value = false
      ElMessage.warning(e.message)
      load()
    } else {
      returnErrors.handle(e)
    }
  } finally {
    saving.value = false
  }
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
        <PageHeader :back="{ name: 'specimens' }">
          <template #title><span class="code">{{ specimen.code }}</span> {{ specimen.name }}</template>
          <IconButton :icon="Clock" label="修改历史" @click="historyOpen = true" />
          <IconButton v-if="auth.isManager" :icon="Printer" label="打印标签" @click="router.push({ name: 'labels', query: { type: 'specimen', ids: String(specimen.id) } })" />
          <IconButton v-if="auth.isManager" :icon="Edit" label="编辑试件" @click="editing = true" />
          <el-button v-if="canReturn" type="primary" @click="openReturn">登记归还</el-button>
          <el-button v-else-if="canBorrow" type="primary" @click="openBorrow">借用</el-button>
        </PageHeader>
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
        <el-descriptions-item v-if="specimen.latest_return_photo" label="最近放回实拍" :span="2">
          <div class="photo-clue">
            <el-image
              class="clue-thumb"
              :src="specimen.latest_return_photo.url"
              :preview-src-list="[specimen.latest_return_photo.url]"
              preview-teleported
              fit="cover"
              alt="最近放回实拍"
            />
            <div class="clue-meta">
              <div v-if="specimen.latest_return_photo.location">{{ specimen.latest_return_photo.location }}</div>
              <div class="muted">
                {{ specimen.latest_return_photo.returned_by?.name || '成员' }} · {{ formatTime(specimen.latest_return_photo.returned_at) }}
                <span v-if="specimen.latest_return_photo.note"> · {{ specimen.latest_return_photo.note }}</span>
              </div>
            </div>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="更新时间" :span="2">{{ formatTime(specimen.updated_at) }}</el-descriptions-item>
        <el-descriptions-item label="备注" :span="2"><pre class="pre">{{ specimen.notes }}</pre></el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="card">
      <template #header>
        <div class="actions">
          <span>缺陷参数</span>
          <el-tag v-if="auth.isSupervisor" class="status-tag" :type="specimen.defects_public ? 'success' : 'info'" disable-transitions>
            {{ specimen.defects_public ? '学生可见' : '学生看不到' }}
          </el-tag>
        </div>
      </template>
      <p v-if="specimen.defects === null" class="muted">缺陷参数未公开（用于盲测），管理员公开后才能看到。</p>
      <el-table v-else :data="specimen.defects" empty-text="暂无缺陷">
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
      <el-table :data="loans" empty-text="暂无借用记录">
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
        <el-table-column label="归还" min-width="200">
          <template #default="{ row }">
            <div v-if="row.returned_at" class="return-cell">
              <el-image
                v-if="row.return_photo_url"
                class="row-thumb"
                :src="row.return_photo_url"
                :preview-src-list="[row.return_photo_url]"
                preview-teleported
                fit="cover"
                alt="归还照片"
              />
              <div>
                <span>{{ formatTime(row.returned_at) }}</span>
                <span v-if="row.return_location" class="muted"> · {{ row.return_location }}</span>
                <span v-if="row.return_note" class="muted"> · {{ row.return_note }}</span>
              </div>
            </div>
            <span v-else class="muted">未归还</span>
          </template>
        </el-table-column>
        <el-table-column label="项目" min-width="110">
          <template #default="{ row }">{{ row.project?.name }}</template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途" min-width="120" show-overflow-tooltip />
      </el-table>
    </el-card>

    <FormDialog v-model="borrowing" :title="`借用 ${specimen.code}`" size="sm" confirm-text="借用" :loading="saving" @submit="borrow">
      <el-form-item label="项目" :error="borrowErrors.fe('project_id')">
        <el-select v-model="borrowForm.project_id" aria-label="项目" placeholder="可不选" clearable filterable>
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="用途" :error="borrowErrors.fe('purpose')"><el-input v-model="borrowForm.purpose" /></el-form-item>
      <el-form-item label="预计归还日期" :error="borrowErrors.fe('due_date')">
        <el-date-picker v-model="borrowForm.due_date" type="date" value-format="YYYY-MM-DD" aria-label="预计归还日期" placeholder="可不填" />
      </el-form-item>
      <el-alert v-for="msg in borrowErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </FormDialog>
    <FormDialog v-model="returning" :title="`归还 ${specimen.code}`" size="sm" confirm-text="登记归还" :loading="saving" @submit="submitReturn">
      <el-form-item label="放回位置（可选）" :error="returnErrors.fe('return_location')">
        <el-input v-model="returnForm.return_location" :placeholder="specimen.location ? `当前：${specimen.location}，换了位置再填` : '例如 A302 试块柜 2 层'" />
      </el-form-item>
      <el-form-item label="归还说明（可选）" :error="returnErrors.fe('note')">
        <el-input v-model="returnForm.note" placeholder="例如 完好、表面有划痕" />
      </el-form-item>
      <el-form-item label="放回位置照片（可选）" :error="returnErrors.fe('photo')">
        <PhotoPicker v-model="returnForm.photo" />
      </el-form-item>
      <el-alert v-for="msg in returnErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </FormDialog>
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
.photo-clue {
  display: flex;
  align-items: center;
  gap: 12px;
}
.clue-thumb {
  width: 72px;
  height: 72px;
  flex: none;
  border-radius: var(--lab-radius);
  border: 1px solid var(--lab-border);
  cursor: zoom-in;
}
.clue-meta {
  min-width: 0;
}
.return-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.row-thumb {
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: var(--el-border-radius-small);
  border: 1px solid var(--lab-border);
  cursor: zoom-in;
}
</style>
