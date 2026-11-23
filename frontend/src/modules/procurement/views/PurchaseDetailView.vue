<script setup lang="ts">
import { replaceSavedEditor } from '@/router/saved-editor'
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Delete, Plus } from '@element-plus/icons-vue'
import { ApiError } from '@/api/client'
import { attachmentsApi, fundsApi, purchasesApi } from '@/modules/procurement/api'
import type { Approval, FundBrief, PurchaseDetail, PurchaseWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { REVIEW_VERDICT_LABELS, STAGE_LABELS, formatMoney, formatTime, itemsTotal, mergeById, purchaseFileDeletable } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import AttachmentList from '@/components/AttachmentList.vue'
import PageHeader from '@/components/PageHeader.vue'
import { closeTab } from '@/layouts/nav'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'
import IconButton from '@/components/IconButton.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const record = ref<PurchaseDetail | null>(null)
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const loading = ref(false)
const busy = ref(false)
const historyOpen = ref(false)
const backTo = route.query.from === 'reviews' ? 'purchase-reviews' : 'purchases'

interface ItemRow {
  name: string
  spec: string
  quantity: number
  unit_price: number | null | undefined // a cleared input-number gives null
  link: string
}
const blankRow = (): ItemRow => ({ name: '', spec: '', quantity: 1, unit_price: undefined, link: '' })
const form = reactive({ fund_id: null as number | null, purpose: '', items: [blankRow()] as ItemRow[] })
const errors = useFieldErrors(['fund_id', 'purpose', 'items'])
// Item errors come back by row index ({"1": {"link": [...]}}) or as one message (["至少需要 1 条明细"]).
const itemsMessage = ref('')
const rowErrors = ref<Record<number, Record<string, string[]>>>({})
const ITEM_FIELDS: Record<string, string> = { name: '品名', spec: '规格型号', quantity: '数量', unit_price: '单价', link: '链接' }

// All funds, so a stopped one still shows on an old request; only active ones can be picked.
const funds = useOptions(() => fundsApi.list({ page_size: 100 }))
const fundOptions = computed(() =>
  mergeById<FundBrief>(funds.value, [record.value?.fund]).filter((f) => f.active || f.id === record.value?.fund?.id),
)

const isNew = !route.params.id // no record yet only means "new" on the -new route
const mine = computed(() => !!record.value && record.value.owner.id === auth.user?.id)
const status = computed(() => record.value?.status)
// After approval the applicant or a manager may correct the items (a changed name, quantity or price restarts the review).
const canCorrect = computed(() => (status.value === 'approved' || status.value === 'purchased') && (mine.value || auth.isManager))
const correcting = ref(false)
const editable = computed(() => (record.value ? (status.value === 'draft' && mine.value) || (canCorrect.value && correcting.value) : isNew))
// Ask before leaving with unsaved changes (fill() takes the snapshot).
const { markSaved } = useUnsavedGuard(form, () => editable.value)
const canReview = computed(() => {
  const role = auth.user?.role
  if (!record.value || mine.value) return false
  return (status.value === 'pending_initial' && role === 'manager') || (status.value === 'pending_final' && role === 'advisor')
})
const lastReturn = computed<Approval | undefined>(() =>
  record.value?.returned ? [...record.value.approvals].reverse().find((a) => a.verdict === 'return') : undefined,
)
const formTotal = computed(() => itemsTotal(form.items))
const waitingFor = computed(() =>
  ({ pending_initial: '等待管理员初审', pending_final: '等待导师终审' } as Record<string, string>)[status.value ?? ''] ?? '',
)
const canMark = computed(() => auth.isManager && (status.value === 'approved' || status.value === 'purchased'))

function fill(r: PurchaseDetail) {
  record.value = r
  form.fund_id = r.fund?.id ?? null
  form.purpose = r.purpose
  form.items = r.items.length
    ? r.items.map((i) => ({ name: i.name, spec: i.spec, quantity: i.quantity, unit_price: Number(i.unit_price), link: i.link }))
    : [blankRow()]
  markSaved()
}

function clearErrors() {
  errors.clear()
  itemsMessage.value = ''
  rowErrors.value = {}
}

function handleErrors(e: unknown) {
  clearErrors()
  const items: unknown = e instanceof ApiError ? e.body.errors?.items : undefined
  if (Array.isArray(items) && items.every((m) => typeof m === 'string')) itemsMessage.value = items.join('；')
  // numbered by the items sent: back to the form's rows, which may include blank ones left out
  else if (items && typeof items === 'object')
    rowErrors.value = Object.fromEntries(Object.entries(items).map(([k, v]) => [sentRows[Number(k)] ?? Number(k), v]))
  errors.handle(e)
}

const rowError = (i: number) =>
  Object.entries(rowErrors.value[i] ?? {})
    .map(([k, msgs]) => `${ITEM_FIELDS[k] ?? k}：${msgs.join('')}`)
    .join('；')

async function load(id: number) {
  loading.value = true
  try {
    fill(await purchasesApi.get(id))
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

// The form row of each item sent (blank rows are not sent).
let sentRows: number[] = []

function removeRow(i: number) {
  form.items.splice(i, 1)
  rowErrors.value = {} // numbered by the rows before
}

function body(): PurchaseWrite {
  sentRows = form.items.flatMap((r, i) => (r.name.trim() || r.spec.trim() || r.link.trim() || r.unit_price != null ? [i] : []))
  const items = sentRows.map((i) => form.items[i]).map((r) => ({
    name: r.name.trim(),
    spec: r.spec.trim(),
    quantity: r.quantity,
    // two decimals as a string: the server stores Decimal; "" gets a field error
    unit_price: r.unit_price == null ? '' : r.unit_price.toFixed(2),
    link: r.link.trim(),
  }))
  const result: PurchaseWrite = { purpose: form.purpose, items }
  // Only a changed fund is sent: a fund stopped after approval must not block correcting the items.
  if ((form.fund_id ?? null) !== (record.value?.fund?.id ?? null)) result.fund_id = form.fund_id ?? null
  return result
}

async function save(): Promise<PurchaseDetail | null> {
  busy.value = true
  try {
    const source = router.currentRoute?.value
    const before = record.value
    const r = before ? await purchasesApi.update(before.id, body()) : await purchasesApi.create(body())
    clearErrors()
    // Replace right away so a second click updates this draft instead of creating another one.
    if (!before && source) void replaceSavedEditor(router, source, { name: 'purchase-detail', params: { id: r.id } })
    fill(r)
    correcting.value = false
    if (before && before.status !== 'draft' && r.status !== before.status) ElMessage.warning('明细已修改，申请重新进入审批')
    return r
  } catch (e) {
    handleErrors(e)
    return null
  } finally {
    busy.value = false
  }
}

async function saveDraft() {
  if (await save()) ElMessage.success('草稿已保存')
}

async function submit() {
  const r = await save()
  if (!r) return
  busy.value = true
  try {
    fill(await purchasesApi.submit(r.id))
    ElMessage.success(record.value?.status === 'pending_final' ? '已提交，等待导师终审' : '已提交，等待管理员初审')
  } catch (e) {
    handleErrors(e)
  } finally {
    busy.value = false
  }
}

async function confirmThen(message: string, title: string, run: () => Promise<PurchaseDetail | void>, done?: string) {
  try {
    await ElMessageBox.confirm(message, title, { type: 'warning' })
  } catch {
    return
  }
  busy.value = true
  try {
    const r = await run()
    if (r) fill(r)
    if (done) ElMessage.success(done)
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

const withdraw = () =>
  confirmThen('撤回后申请回到草稿，修改后需要重新提交。', '撤回申请', () => purchasesApi.withdraw(record.value!.id), '已撤回')
const markPurchased = () =>
  confirmThen('确认已经下单采购？', '标记已采购', () => purchasesApi.markPurchased(record.value!.id), '已标记为已采购')
const markArrived = () =>
  confirmThen('确认货已到？之后可在新建设备、耗材入库时关联这张申请。', '标记已到货', () => purchasesApi.markArrived(record.value!.id), '已标记为已到货')
const remove = () =>
  confirmThen('删除这份草稿？', '删除', async () => {
    await purchasesApi.remove(record.value!.id)
    markSaved() // deleted: nothing left to lose
    closeTab(route.path)
    router.push({ name: 'purchases' })
  })

// ---- review ----
const comment = ref('')
const commentError = ref('')

async function review(verdict: 'approve' | 'return') {
  const r = record.value!
  commentError.value = verdict === 'return' && !comment.value.trim() ? '退回时请写明意见' : ''
  if (commentError.value) return
  busy.value = true
  try {
    // Include the submission: a withdrawal and equal-total resubmission must invalidate the old decision.
    fill(await purchasesApi.review(r.id, {
      verdict, comment: comment.value, status_seen: r.status, total_seen: r.total,
      submitted_seen: r.submitted_at!, // review actions are only shown for submitted requests
    }))
    comment.value = ''
    ElMessage.success(verdict === 'approve' ? '已通过' : '已退回申请人')
  } catch (e) {
    if (e instanceof ApiError && e.body.code === 'stale') {
      ElMessage.warning(e.message)
      await load(r.id)
    } else if (e instanceof ApiError && e.body.errors?.comment) commentError.value = e.body.errors.comment.join('')
    else showError(e)
  } finally {
    busy.value = false
  }
}

const reload = () => record.value && load(record.value.id)

if (route.params.id) load(Number(route.params.id))
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: backTo })">返回采购申请</el-button></template>
  </el-result>
  <div v-else v-loading="loading" class="purchase">
    <el-card class="card">
      <template #header>
        <PageHeader :back="{ name: backTo }">
          <template #title><span :class="{ code: record }">{{ record ? record.code : isNew ? '新建采购申请' : '' }}</span></template>
          <template v-if="record" #tags>
            <StatusTag :status="record.status" />
            <el-tag v-if="record.returned" class="status-tag" type="danger" disable-transitions>被退回</el-tag>
          </template>
          <IconButton v-if="record" :icon="Clock" label="修改历史" @click="historyOpen = true" />
          <template v-if="canReview" />
          <template v-else-if="editable && !correcting">
            <el-button v-if="record && !record.submitted_at" type="danger" plain :disabled="busy" @click="remove">删除草稿</el-button>
            <el-button :loading="busy" @click="saveDraft">保存草稿</el-button>
            <el-button type="primary" :loading="busy" @click="submit">提交审批</el-button>
          </template>
          <template v-else-if="correcting">
            <el-button :disabled="busy" @click="correcting = false; fill(record!)">取消</el-button>
            <el-button type="primary" :loading="busy" @click="save">保存修改</el-button>
          </template>
          <template v-else-if="record">
            <el-button v-if="mine && waitingFor" :loading="busy" @click="withdraw">撤回</el-button>
            <el-button v-if="canCorrect" :disabled="busy" @click="correcting = true">修改明细</el-button>
            <el-button v-if="canMark && status === 'approved'" type="primary" :loading="busy" @click="markPurchased">标记已采购</el-button>
            <el-button v-if="canMark && status === 'purchased'" type="primary" :loading="busy" @click="markArrived">标记已到货</el-button>
          </template>
        </PageHeader>
      </template>

      <el-alert
        v-if="lastReturn"
        type="warning"
        :closable="false"
        class="notice"
        :title="`${lastReturn.reviewer.name}${STAGE_LABELS[lastReturn.stage]}退回：${lastReturn.comment}`"
      />
      <el-alert v-if="correcting" type="info" :closable="false" class="notice" title="修改品名、数量或单价后，申请会重新进入审批" />
      <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" class="notice" />

      <!-- read view: what reviewers see, compact enough for a phone screen -->
      <template v-if="record && !editable">
        <dl class="facts">
          <div><dt>申请人</dt><dd>{{ record.owner.name }}</dd></div>
          <div><dt>经费来源</dt><dd>{{ record.fund ? `${record.fund.code} ${record.fund.name}` : '未选择' }}</dd></div>
          <div v-if="record.submitted_at"><dt>提交时间</dt><dd>{{ formatTime(record.submitted_at) }}</dd></div>
          <div v-if="waitingFor"><dt>进度</dt><dd>{{ waitingFor }}</dd></div>
          <div class="wide"><dt>用途</dt><dd><pre class="pre">{{ record.purpose }}</pre></dd></div>
        </dl>
        <ul class="items">
          <li v-for="i in record.items" :key="i.id">
            <div class="item-main">
              <span class="item-name">{{ i.name }}</span>
              <span v-if="i.spec" class="muted">{{ i.spec }}</span>
              <a v-if="i.link" :href="i.link" target="_blank" rel="noopener noreferrer">链接</a>
            </div>
            <div class="item-num">
              <span class="muted">{{ i.quantity }} × {{ formatMoney(i.unit_price) }}</span>
              <span class="amount">{{ formatMoney(i.subtotal) }}</span>
            </div>
          </li>
        </ul>
        <div class="total"><span>合计</span><span class="amount">¥ {{ formatMoney(record.total) }}</span></div>
      </template>

      <el-form v-else-if="editable" class="form-page" label-position="top" @submit.prevent>
        <div class="form-grid">
          <el-form-item class="span-2" label="经费来源" :error="errors.fe('fund_id')" required>
            <el-select v-model="form.fund_id" filterable placeholder="选择经费来源">
              <el-option v-for="f in fundOptions" :key="f.id" :label="`${f.code} ${f.name}`" :value="f.id" />
            </el-select>
          </el-form-item>
          <el-form-item class="span-2" label="用途" :error="errors.fe('purpose')" required>
            <el-input v-model="form.purpose" type="textarea" :autosize="{ minRows: 1 }" placeholder="买来做什么，用在哪个实验或项目" />
          </el-form-item>
        </div>
        <el-form-item label="明细" :error="itemsMessage" required>
          <div class="rows">
            <div class="row head" aria-hidden="true">
              <span>品名</span><span>规格型号</span><span>数量</span><span>单价（元）</span><span>链接</span><span />
            </div>
            <template v-for="(row, i) in form.items" :key="i">
              <div class="row">
                <el-input v-model="row.name" placeholder="品名" aria-label="品名" />
                <el-input v-model="row.spec" placeholder="规格型号" aria-label="规格型号" />
                <el-input-number v-model="row.quantity" :min="1" :step="1" step-strictly controls-position="right" aria-label="数量" />
                <el-input-number
                  v-model="row.unit_price"
                  :min="0"
                  :precision="2"
                  :step="0.01"
                  :controls="false"
                  placeholder="单价"
                  aria-label="单价（元）"
                  class="price"
                />
                <el-input v-model="row.link" placeholder="购买链接（可不填）" aria-label="链接" />
                <el-button :icon="Delete" text aria-label="删除这一行" :disabled="form.items.length === 1" @click="removeRow(i)" />
              </div>
              <div v-if="rowError(i)" class="row-error">{{ rowError(i) }}</div>
            </template>
            <div class="rows-foot">
              <el-button :icon="Plus" text @click="form.items.push(blankRow())">添加一行</el-button>
              <span class="total-inline">合计 <span class="amount">¥ {{ formatMoney(formTotal) }}</span></span>
            </div>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="record" header="附件" class="card">
      <AttachmentList
        :remove="attachmentsApi.remove"
        :attachments="record.attachments"
        :upload="mine || auth.isManager ? (file, kind) => purchasesApi.upload(record!.id, file, kind) : undefined"
        :can-delete="(a) => purchaseFileDeletable(record!, a) && (a.uploaded_by.id === auth.user?.id || auth.isManager)"
        @changed="reload"
      />
    </el-card>

    <el-card v-if="record?.approvals.length" header="审批记录" class="card">
      <el-timeline>
        <el-timeline-item
          v-for="a in record.approvals"
          :key="a.id"
          :timestamp="formatTime(a.created_at)"
          :type="a.verdict === 'approve' ? 'success' : 'danger'"
          placement="top"
        >
          <div>
            {{ STAGE_LABELS[a.stage] }} · {{ a.reviewer.name }} · <b>{{ REVIEW_VERDICT_LABELS[a.verdict] }}</b>
            <span class="muted">（当时合计 ¥ {{ formatMoney(a.total) }}）</span>
          </div>
          <div v-if="a.comment" class="comment">{{ a.comment }}</div>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <el-card v-if="record && (record.linked_equipment.length || record.linked_stock.length)" header="到货登记" class="card">
      <ul class="linked">
        <li v-for="e in record.linked_equipment" :key="`e${e.id}`">
          设备 <RouterLink :to="{ name: 'equipment-detail', params: { id: e.id } }"><span class="code">{{ e.code }}</span> {{ e.name }}</RouterLink>
        </li>
        <li v-for="t in record.linked_stock" :key="`t${t.id}`">耗材入库 {{ t.consumable }} +{{ t.quantity }} · {{ formatTime(t.created_at) }}</li>
      </ul>
    </el-card>

    <el-card v-if="canReview" header="审批" class="card">
      <el-input
        v-model="comment"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="审批意见（退回时必填）"
        aria-label="审批意见"
        @input="commentError = ''"
      />
      <div v-if="commentError" class="row-error">{{ commentError }}</div>
      <div class="review-actions">
        <el-button :loading="busy" @click="review('return')">退回修改</el-button>
        <el-button type="primary" :loading="busy" @click="review('approve')">通过</el-button>
      </div>
    </el-card>
  </div>
  <HistoryDrawer v-if="record" v-model="historyOpen" :load="() => purchasesApi.history(record!.id)" />
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}
.grow {
  flex: 1;
}
.muted {
  color: var(--el-text-color-secondary);
}
.amount {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px 24px;
  margin: 0 0 16px;
}
.facts .wide {
  grid-column: 1 / -1;
}
.facts dt {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.facts dd {
  margin: 2px 0 0;
}
.items {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--lab-border);
}
.items li {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 16px;
  padding: 10px 0;
  border-bottom: 1px solid var(--lab-border);
}
.item-main {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  min-width: 0;
}
.item-name {
  font-weight: 500;
}
.item-num {
  display: flex;
  align-items: baseline;
  gap: 16px;
  margin-left: auto;
}
.item-num .amount {
  min-width: 90px;
  text-align: right;
}
.total {
  display: flex;
  justify-content: flex-end;
  align-items: baseline;
  gap: 16px;
  padding-top: 12px;
  font-size: 15px;
}
.total .amount {
  font-size: 20px;
  font-weight: 600;
}
.rows {
  width: 100%;
}
.row {
  display: grid;
  grid-template-columns: minmax(120px, 2fr) minmax(100px, 1.4fr) 110px 120px minmax(100px, 1.4fr) 32px;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.row .el-input-number {
  width: 100%;
}
.price :deep(input) {
  text-align: right;
}
.row.head {
  margin-bottom: 4px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--el-text-color-secondary);
}
.row-error {
  margin: -4px 0 8px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--el-color-danger);
}
.rows-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.total-inline {
  font-size: 14px;
}
.total-inline .amount {
  font-size: 16px;
  font-weight: 600;
}
.comment {
  margin-top: 4px;
  white-space: pre-wrap;
  color: var(--el-text-color-regular);
}
.linked {
  margin: 0;
  padding-left: 18px;
  line-height: 1.9;
}
.review-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
.review-actions .el-button + .el-button {
  margin-left: 0;
}
@media (max-width: 768px) {
  /* two short facts per line, so the items, total and review history fit on a phone screen */
  .facts {
    grid-template-columns: 1fr 1fr;
    gap: 8px 16px;
    margin-bottom: 12px;
  }
  .row {
    grid-template-columns: 1fr 1fr;
  }
  .row > :first-child {
    grid-column: 1 / -1;
  }
  .row.head {
    display: none;
  }
}
</style>
