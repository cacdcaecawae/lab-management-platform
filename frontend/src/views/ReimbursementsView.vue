<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { membersApi } from '@/api/members'
import { fundsApi, purchasesApi, reimbursementsApi } from '@/api/procurement'
import type {
  FundBrief,
  PurchaseBrief,
  Reimbursement,
  ReimbursementCategory,
  ReimbursementStats,
  ReimbursementStatus,
  ReimbursementWrite,
  StatsBy,
} from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { CATEGORY_LABELS, REIMBURSEMENT_STATUS, formatMoney, formatTime, mergeById, toDateStr } from '@/utils/format'
import { showActionError, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import AttachmentList from '@/components/AttachmentList.vue'

const auth = useAuthStore()
const tab = ref<'records' | 'stats'>('records')
// Shared by the list, the statistics and the export, so their totals agree.
const filters = reactive({ status: '', category: '', month: '', fund: '' as number | '', owner: '' as number | '' })
const { items, count, page, pageSize, loading, load } = usePagedList(reimbursementsApi.list, filters)

// All funds for filtering (a stopped one still has records); the form offers active ones only.
const funds = useOptions(() => fundsApi.list({ page_size: 100 }))
const members = auth.isSupervisor ? useOptions(() => membersApi.list({ page_size: 100 })) : ref([])
// shortcut: the 100 most recent purchase requests I can see; switch to remote search if that is not enough.
const purchases = useOptions(() => purchasesApi.list({ page_size: 100 }))
const statusLabels = Object.fromEntries(Object.entries(REIMBURSEMENT_STATUS).map(([k, v]) => [k, v.label]))
const historyValues = { status: statusLabels, category: CATEGORY_LABELS }

const writer = (r: Reimbursement) => r.owner.id === auth.user?.id || auth.isManager
const hasInvoice = (r: Reimbursement) => r.attachments.some((a) => a.kind === 'invoice')

// ---- create / edit dialog ----
interface FormState {
  fund_id: number | null
  purchase_id: number | null
  category: ReimbursementCategory
  amount: number | null | undefined
  occurred_on: string
  description: string
}
const blank = (): FormState => ({ fund_id: null, purchase_id: null, category: 'consumable', amount: undefined, occurred_on: toDateStr(new Date()), description: '' })
const form = reactive<FormState>(blank())
let opened: FormState = blank()
const errors = useFieldErrors(Object.keys(blank()))
const current = ref<Reimbursement | null>(null)
const dialogOpen = ref(false)
const saving = ref(false)
const editable = computed(() => !current.value || (current.value.status === 'pending' && writer(current.value)))
const fundOptions = computed(() =>
  mergeById<FundBrief>(funds.value, [current.value?.fund]).filter((f) => f.active || f.id === current.value?.fund.id),
)
// Only the reimbursing person's own purchase requests can be linked (also when a manager edits).
const purchaseOptions = computed(() => {
  const owner = current.value?.owner.id ?? auth.user?.id
  return mergeById<PurchaseBrief>(purchases.value, [current.value?.purchase]).filter((p) => p.owner.id === owner)
})

function openDialog(r: Reimbursement | null) {
  current.value = r
  Object.assign(form, blank(), r && {
    fund_id: r.fund.id, purchase_id: r.purchase?.id ?? null, category: r.category, amount: Number(r.amount),
    occurred_on: r.occurred_on, description: r.description,
  })
  opened = { ...form }
  errors.clear()
  dialogOpen.value = true
}

function body(): Partial<ReimbursementWrite> {
  const all: ReimbursementWrite = {
    fund_id: form.fund_id ?? null,
    purchase_id: form.purchase_id ?? null,
    category: form.category,
    amount: form.amount == null ? '' : form.amount.toFixed(2),
    occurred_on: form.occurred_on ?? '',
    description: form.description,
  }
  if (!current.value) return all
  // An edit sends only what changed: a fund stopped since must not block fixing the description.
  const was: Record<string, unknown> = { ...opened, amount: opened.amount == null ? '' : opened.amount.toFixed(2) }
  return Object.fromEntries(Object.entries(all).filter(([k, v]) => v !== (was[k] ?? null)))
}

async function save() {
  saving.value = true
  try {
    const isNew = !current.value
    const data = body()
    const saved = isNew
      ? await reimbursementsApi.create(data as ReimbursementWrite)
      : Object.keys(data).length
        ? await reimbursementsApi.update(current.value!.id, data)
        : current.value!
    load()
    if (isNew) {
      // Stay open: the invoice is uploaded next, onto the record that now exists.
      openDialog(saved)
      ElMessage.success('已登记，请上传发票')
    } else {
      dialogOpen.value = false
      ElMessage.success('已保存')
    }
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}

async function refreshCurrent() {
  if (!current.value) return
  try {
    current.value = await reimbursementsApi.get(current.value.id)
  } catch (e) {
    showError(e)
  }
  load()
}

// ---- status ----
const NEXT: Record<string, { to: ReimbursementStatus; label: string; confirm: string }> = {
  pending: { to: 'submitted', label: '交财务', confirm: '确认已把发票交给财务？交财务后金额等信息不能再改。' },
  submitted: { to: 'paid', label: '已到账', confirm: '确认报销款已经到账？' },
}

async function advance(r: Reimbursement, to: ReimbursementStatus, message: string) {
  try {
    await ElMessageBox.confirm(message, `报销 ${r.code}`, { type: 'warning' })
  } catch {
    return
  }
  try {
    const saved = await reimbursementsApi.advance(r.id, to)
    if (current.value?.id === r.id) current.value = saved
    ElMessage.success(`已改为“${REIMBURSEMENT_STATUS[saved.status].label}”`)
    load()
  } catch (e) {
    showActionError(e) // e.g. 交财务前请先上传发票
  }
}

async function remove(r: Reimbursement) {
  try {
    await ElMessageBox.confirm(`删除报销 ${r.code}？`, '删除', { type: 'warning' })
    await reimbursementsApi.remove(r.id)
    dialogOpen.value = false
    load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') showError(e)
  }
}

// ---- history ----
const historyOf = ref<Reimbursement | null>(null)
const historyOpen = computed({ get: () => !!historyOf.value, set: (v) => !v && (historyOf.value = null) })

// ---- statistics (managers and advisors) ----
const BY_LABELS: Record<StatsBy, string> = { fund: '经费来源', category: '类别', owner: '人员', month: '月份' }
const by = ref<StatsBy>('category')
const stats = ref<ReimbursementStats | null>(null)
const statsLoading = ref(false)
const statsQuery = computed(() => ({ ...filters, by: by.value }))

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await reimbursementsApi.stats(statsQuery.value)
  } catch (e) {
    showError(e)
  } finally {
    statsLoading.value = false
  }
}

watch([tab, statsQuery], () => tab.value === 'stats' && loadStats())

const summary = () => (stats.value ? [`合计`, String(stats.value.count), formatMoney(stats.value.total)] : [])

async function remindFinance() {
  try {
    const { sent, to } = await reimbursementsApi.remindFinance()
    if (sent) ElMessage.success(`已发送给 ${to}，列出 ${sent} 笔已交财务、尚未到账的报销`)
    else ElMessage.info('没有已交财务、尚未到账的报销，没有发送')
  } catch (e) {
    showError(e)
  }
}

// Managers know who the finance contact is; ops can also set it in 系统管理 → 课题组.
async function editFinanceEmail() {
  try {
    const { finance_email } = await reimbursementsApi.financeEmail()
    const { value } = await ElMessageBox.prompt('每周一收到“已交财务、尚未到账”的报销提醒；留空表示不发。', '财务邮箱', {
      inputValue: finance_email,
      inputPattern: /^\s*$|^\s*[^\s@]+@[^\s@]+\.[^\s@]+\s*$/,
      inputErrorMessage: '请输入有效的邮箱地址',
      confirmButtonText: '保存',
    })
    const saved = (await reimbursementsApi.setFinanceEmail((value ?? '').trim())).finance_email
    ElMessage.success(saved ? `财务邮箱已设为 ${saved}` : '已清空财务邮箱')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') showActionError(e)
  }
}
</script>

<template>
  <el-card class="card">
    <div class="page-toolbar">
      <el-select v-model="filters.status" placeholder="全部状态" clearable aria-label="状态">
        <el-option v-for="(s, k) in REIMBURSEMENT_STATUS" :key="k" :label="s.label" :value="k" />
      </el-select>
      <el-select v-model="filters.category" placeholder="全部类别" clearable aria-label="类别">
        <el-option v-for="(label, k) in CATEGORY_LABELS" :key="k" :label="label" :value="k" />
      </el-select>
      <el-date-picker v-model="filters.month" type="month" value-format="YYYY-MM" placeholder="全部月份" class="month" />
      <el-select v-model="filters.fund" placeholder="全部经费" clearable filterable aria-label="经费来源">
        <el-option v-for="f in funds" :key="f.id" :label="`${f.code} ${f.name}`" :value="f.id" />
      </el-select>
      <el-select v-if="auth.isSupervisor" v-model="filters.owner" placeholder="全部人员" clearable filterable aria-label="人员">
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <span class="grow" />
      <el-button type="primary" @click="openDialog(null)">登记报销</el-button>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="报销记录" name="records">
        <el-table v-loading="loading" :data="items" empty-text="没有报销记录">
          <el-table-column label="编号" min-width="120">
            <template #default="{ row }">
              <el-button link class="code" @click="openDialog(row as Reimbursement)">{{ row.code }}</el-button>
            </template>
          </el-table-column>
          <el-table-column v-if="auth.isSupervisor" label="报销人" min-width="80">
            <template #default="{ row }">{{ row.owner.name }}</template>
          </el-table-column>
          <el-table-column label="类别" min-width="80">
            <template #default="{ row }">{{ CATEGORY_LABELS[row.category] }}</template>
          </el-table-column>
          <el-table-column label="金额（元）" min-width="110" align="right">
            <template #default="{ row }"><span class="amount">{{ formatMoney(row.amount) }}</span></template>
          </el-table-column>
          <el-table-column prop="occurred_on" label="发生日期" min-width="100" />
          <el-table-column label="经费来源" min-width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ row.fund.code }}</template>
          </el-table-column>
          <el-table-column label="状态" min-width="100">
            <template #default="{ row }"><StatusTag :status="row.status" :map="REIMBURSEMENT_STATUS" /></template>
          </el-table-column>
          <el-table-column label="发票" min-width="80">
            <template #default="{ row }">
              <span v-if="hasInvoice(row as Reimbursement)">已上传</span>
              <span v-else class="missing">未上传</span>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="140" show-overflow-tooltip />
          <el-table-column label="操作" min-width="190">
            <template #default="{ row }">
              <template v-if="writer(row as Reimbursement) && NEXT[row.status]">
                <el-button link type="primary" @click="advance(row as Reimbursement, NEXT[row.status].to, NEXT[row.status].confirm)">
                  {{ NEXT[row.status].label }}
                </el-button>
              </template>
              <el-button
                v-if="auth.isManager && row.status === 'submitted'"
                link
                type="primary"
                @click="advance(row as Reimbursement, 'pending', '退回“待提交”后可以修改金额等信息，修改历史里会留下记录。')"
              >
                退回
              </el-button>
              <el-button link type="primary" @click="historyOf = row as Reimbursement">历史</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="page"
          class="pager"
          layout="total, prev, pager, next"
          :total="count"
          :page-size="pageSize"
          hide-on-single-page
        />
      </el-tab-pane>

      <el-tab-pane v-if="auth.isSupervisor" label="统计" name="stats">
        <div class="page-toolbar">
          <el-radio-group v-model="by">
            <el-radio-button v-for="(label, k) in BY_LABELS" :key="k" :value="k">按{{ label }}</el-radio-button>
          </el-radio-group>
          <span class="grow" />
          <el-button tag="a" :href="reimbursementsApi.exportUrl(statsQuery)">导出 Excel</el-button>
          <el-button v-if="auth.isManager" @click="editFinanceEmail">财务邮箱</el-button>
          <el-button v-if="auth.isManager" @click="remindFinance">发送财务提醒</el-button>
        </div>
        <el-table v-loading="statsLoading" :data="stats?.rows ?? []" show-summary :summary-method="summary" empty-text="没有符合条件的报销">
          <el-table-column prop="label" :label="BY_LABELS[by]" min-width="160" />
          <el-table-column prop="count" label="笔数" min-width="80" align="right" />
          <el-table-column label="金额（元）" min-width="120" align="right">
            <template #default="{ row }"><span class="amount">{{ formatMoney(row.total) }}</span></template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </el-card>

  <el-dialog v-model="dialogOpen" :title="current ? `报销 ${current.code}` : '登记报销'" width="min(560px, 95vw)">
    <template v-if="current">
      <div class="state">
        <StatusTag :status="current.status" :map="REIMBURSEMENT_STATUS" />
        <span class="muted">{{ current.owner.name }}</span>
        <span v-if="current.submitted_at" class="muted">交财务 {{ formatTime(current.submitted_at) }}</span>
        <span v-if="current.paid_at" class="muted">到账 {{ formatTime(current.paid_at) }}</span>
      </div>
      <el-alert
        v-if="current.status !== 'pending'"
        type="info"
        :closable="false"
        class="notice"
        title="已交财务的报销不能修改；需要修改请管理员先退回“待提交”。"
      />
    </template>
    <el-form label-position="top" :disabled="!editable" @submit.prevent="save">
      <el-row :gutter="12">
        <el-col :xs="24" :sm="12">
          <el-form-item label="经费来源" :error="errors.fe('fund_id')" required>
            <el-select v-model="form.fund_id" filterable placeholder="选择经费来源">
              <el-option v-for="f in fundOptions" :key="f.id" :label="`${f.code} ${f.name}`" :value="f.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-form-item label="类别" :error="errors.fe('category')" required>
            <el-select v-model="form.category">
              <el-option v-for="(label, k) in CATEGORY_LABELS" :key="k" :label="label" :value="k" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-form-item label="金额（元）" :error="errors.fe('amount')" required>
            <el-input-number v-model="form.amount" :min="0.01" :precision="2" :step="0.01" :controls="false" class="amount-input" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item label="发生日期" :error="errors.fe('occurred_on')" required>
            <el-date-picker v-model="form.occurred_on" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item label="关联采购申请" :error="errors.fe('purchase_id')">
            <el-select v-model="form.purchase_id" filterable clearable placeholder="可不选">
              <el-option v-for="p in purchaseOptions" :key="p.id" :label="`${p.code} ${p.purpose}`" :value="p.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="说明" :error="errors.fe('description')">
        <el-input v-model="form.description" maxlength="200" placeholder="如 耦合剂 3 瓶、会议差旅" />
      </el-form-item>
      <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </el-form>
    <template v-if="current">
      <div class="section-title">发票和附件</div>
      <AttachmentList
        :attachments="current.attachments"
        default-kind="invoice"
        :upload="writer(current) && current.status === 'pending' ? (file, kind) => reimbursementsApi.upload(current!.id, file, kind) : undefined"
        :can-delete="(a) => current!.status === 'pending' && (a.uploaded_by.id === auth.user?.id || auth.isManager)"
        @changed="refreshCurrent"
      />
    </template>
    <template #footer>
      <div class="footer">
        <el-button v-if="current && editable" type="danger" text @click="remove(current)">删除报销</el-button>
        <span class="grow" />
        <el-button @click="dialogOpen = false">{{ editable ? '取消' : '关闭' }}</el-button>
        <el-button v-if="editable" type="primary" :loading="saving" @click="save">保存</el-button>
        <el-button
          v-if="current && writer(current) && current.status === 'pending'"
          type="primary"
          :disabled="!hasInvoice(current)"
          @click="advance(current, 'submitted', NEXT.pending.confirm)"
        >
          交财务
        </el-button>
      </div>
    </template>
  </el-dialog>

  <!-- always mounted: the drawer loads when it opens, and historyOf is set by then -->
  <HistoryDrawer
    v-model="historyOpen"
    :load="() => reimbursementsApi.history(historyOf!.id)"
    :values="historyValues"
  />
</template>

<style scoped>
.amount {
  font-variant-numeric: tabular-nums;
}
.missing {
  color: var(--el-color-danger);
}
.muted {
  color: var(--el-text-color-secondary);
}
.month {
  width: 150px;
}
.state {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-bottom: 12px;
}
.notice {
  margin-bottom: 12px;
}
.amount-input {
  width: 100%;
}
.amount-input :deep(input) {
  text-align: right;
}
.section-title {
  margin: 8px 0 4px;
  font-weight: 600;
}
.footer {
  display: flex;
  align-items: center;
  gap: 8px;
}
.footer .el-button + .el-button {
  margin-left: 0;
}
.grow {
  flex: 1;
}
@media (max-width: 768px) {
  .month {
    width: 100%;
  }
}
</style>
