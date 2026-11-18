<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { consumablesApi } from '@/api/equipment'
import { purchasesApi } from '@/api/procurement'
import { projectsApi } from '@/api/projects'
import type { Consumable, ConsumableWrite, StockTxn, TxnKind } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { TXN_KIND_LABELS, formatTime } from '@/utils/format'
import { showError, useFieldErrors } from '@/utils/errors'

const auth = useAuthStore()
const filters = reactive({ search: '', low: '' as 1 | '' })
const keyword = ref('')
const { items, count, page, pageSize, loading, load } = usePagedList(consumablesApi.list, filters)
const projects = useOptions(() => projectsApi.list({ status: 'active', page_size: 100 }))
// Stock-in (managers only) may name the arrived purchase request it came from.
const arrived = auth.isManager ? useOptions(() => purchasesApi.list({ status: 'arrived', page_size: 100 })) : ref([])

// ---- item create / edit (managers) ----
const blankItem: ConsumableWrite = { name: '', spec: '', unit: '个', location: '', safety_stock: 0, notes: '' }
const itemForm = reactive<ConsumableWrite>({ ...blankItem })
const itemErrors = useFieldErrors(Object.keys(blankItem))
const editing = ref<Consumable | null>(null)
const itemOpen = ref(false)
const saving = ref(false)

function openItem(c: Consumable | null) {
  editing.value = c
  Object.assign(itemForm, blankItem, c && { name: c.name, spec: c.spec, unit: c.unit, location: c.location, safety_stock: c.safety_stock, notes: c.notes })
  itemErrors.clear()
  itemOpen.value = true
}

async function saveItem() {
  saving.value = true
  try {
    if (editing.value) await consumablesApi.update(editing.value.id, itemForm)
    else await consumablesApi.create(itemForm)
    itemOpen.value = false
    load()
  } catch (e) {
    itemErrors.handle(e)
  } finally {
    saving.value = false
  }
}

// ---- stock transactions ----
const txnTarget = ref<Consumable | null>(null)
const txnOpen = ref(false)
const txnForm = reactive({
  kind: 'out' as TxnKind, quantity: 1, counted: 0, project_id: null as number | null, purchase_id: null as number | null, note: '',
})
const txnErrors = useFieldErrors(['kind', 'quantity', 'project_id', 'purchase_id', 'note'])
// Stocktaking: enter what is on the shelf; the API takes the difference from the book stock.
const diff = computed(() => txnForm.counted - (txnTarget.value?.stock ?? 0))

function openTxn(c: Consumable, kind: TxnKind) {
  txnTarget.value = c
  Object.assign(txnForm, { kind, quantity: 1, counted: c.stock, project_id: null, purchase_id: null, note: '' })
  txnErrors.clear()
  txnOpen.value = true
}

async function saveTxn() {
  const c = txnTarget.value
  if (!c) return
  saving.value = true
  try {
    const quantity = txnForm.kind === 'adjust' ? diff.value : txnForm.quantity
    const purchase_id = txnForm.kind === 'in' ? (txnForm.purchase_id ?? null) : null
    await consumablesApi.addTxn(c.id, { kind: txnForm.kind, quantity, project_id: txnForm.project_id, purchase_id, note: txnForm.note })
    ElMessage.success(`已登记${TXN_KIND_LABELS[txnForm.kind]}`)
    txnOpen.value = false
    load()
  } catch (e) {
    txnErrors.handle(e)
  } finally {
    saving.value = false
  }
}

// ---- transaction history ----
const historyOf = ref<Consumable | null>(null)
const historyOpen = computed({ get: () => !!historyOf.value, set: (v) => !v && (historyOf.value = null) })
const txns = ref<StockTxn[]>([])
const txnPage = ref(1)
const hasMore = ref(false)

async function loadTxns(c: Consumable, reset: boolean) {
  txnPage.value = reset ? 1 : txnPage.value + 1
  try {
    const res = await consumablesApi.txns(c.id, { page: txnPage.value })
    txns.value = reset ? res.results : [...txns.value, ...res.results]
    hasMore.value = !!res.next
  } catch (e) {
    showError(e)
  }
}

function openHistory(c: Consumable) {
  historyOf.value = c
  txns.value = []
  loadTxns(c, true)
}

const signed = (n: number) => (n > 0 ? `+${n}` : String(n))
</script>

<template>
  <el-card class="card">
    <div class="page-toolbar">
      <el-input v-model="keyword" placeholder="搜索名称、规格、位置" clearable @change="filters.search = keyword" />
      <el-checkbox v-model="filters.low" :true-value="1" false-value="">只看低于安全库存</el-checkbox>
      <span class="grow" />
      <el-button v-if="auth.isManager" type="primary" @click="openItem(null)">新增耗材</el-button>
    </div>
    <el-table v-loading="loading" :data="items">
      <el-table-column prop="name" label="名称" min-width="130" />
      <el-table-column prop="spec" label="规格" min-width="100" />
      <el-table-column label="库存" min-width="130">
        <template #default="{ row }">
          <span class="stock" :class="{ low: row.low }">{{ row.stock }} {{ row.unit }}</span>
          <el-tag v-if="row.low" class="status-tag low-tag" type="danger" disable-transitions>不足</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="安全库存" min-width="80">
        <template #default="{ row }">{{ row.safety_stock }}</template>
      </el-table-column>
      <el-table-column prop="location" label="存放位置" min-width="110" />
      <el-table-column label="操作" min-width="260">
        <template #default="{ row }">
          <el-button link type="primary" @click="openTxn(row as Consumable, 'out')">领用</el-button>
          <el-button link type="primary" @click="openTxn(row as Consumable, 'return')">退回</el-button>
          <template v-if="auth.isManager">
            <el-button link type="primary" @click="openTxn(row as Consumable, 'in')">入库</el-button>
            <el-button link type="primary" @click="openTxn(row as Consumable, 'adjust')">盘点</el-button>
            <el-button link type="primary" @click="openItem(row as Consumable)">编辑</el-button>
          </template>
          <el-button link type="primary" @click="openHistory(row as Consumable)">流水</el-button>
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
  </el-card>

  <el-dialog v-model="itemOpen" :title="editing ? '编辑耗材' : '新增耗材'" width="min(520px, 95vw)">
    <el-form label-position="top" @submit.prevent="saveItem">
      <el-row :gutter="12">
        <el-col :xs="24" :sm="14">
          <el-form-item label="名称" :error="itemErrors.fe('name')" required><el-input v-model="itemForm.name" /></el-form-item>
        </el-col>
        <el-col :xs="24" :sm="10">
          <el-form-item label="规格" :error="itemErrors.fe('spec')"><el-input v-model="itemForm.spec" placeholder="如 1 m、250 mL" /></el-form-item>
        </el-col>
        <el-col :xs="12" :sm="8">
          <el-form-item label="单位" :error="itemErrors.fe('unit')" required><el-input v-model="itemForm.unit" /></el-form-item>
        </el-col>
        <el-col :xs="12" :sm="8">
          <el-form-item label="安全库存" :error="itemErrors.fe('safety_stock')">
            <el-input-number v-model="itemForm.safety_stock" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-form-item label="存放位置" :error="itemErrors.fe('location')"><el-input v-model="itemForm.location" /></el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="备注" :error="itemErrors.fe('notes')">
        <el-input v-model="itemForm.notes" type="textarea" :autosize="{ minRows: 2 }" />
      </el-form-item>
      <el-alert v-for="msg in itemErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </el-form>
    <template #footer>
      <el-button @click="itemOpen = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="saveItem">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="txnOpen" :title="`${TXN_KIND_LABELS[txnForm.kind]}：${txnTarget?.name} ${txnTarget?.spec}`" width="min(460px, 95vw)">
    <el-form v-if="txnTarget" label-position="top" @submit.prevent="saveTxn">
      <p class="book">账面库存 {{ txnTarget.stock }} {{ txnTarget.unit }}</p>
      <el-form-item v-if="txnForm.kind === 'adjust'" label="盘点实际数量" :error="txnErrors.fe('quantity')" required>
        <el-input-number v-model="txnForm.counted" :min="0" controls-position="right" />
        <span class="diff">差额 {{ signed(diff) }}</span>
      </el-form-item>
      <el-form-item v-else :label="`数量（${txnTarget.unit}）`" :error="txnErrors.fe('quantity')" required>
        <el-input-number v-model="txnForm.quantity" :min="1" controls-position="right" />
      </el-form-item>
      <el-form-item v-if="txnForm.kind === 'out' || txnForm.kind === 'return'" label="项目" :error="txnErrors.fe('project_id')">
        <el-select v-model="txnForm.project_id" filterable clearable placeholder="可不选">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="txnForm.kind === 'in'" label="采购申请（已到货）" :error="txnErrors.fe('purchase_id')">
        <el-select v-model="txnForm.purchase_id" filterable clearable placeholder="可不选">
          <el-option v-for="p in arrived" :key="p.id" :label="`${p.code} ${p.purpose}`" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注" :error="txnErrors.fe('note')">
        <el-input v-model="txnForm.note" maxlength="200" />
      </el-form-item>
      <el-alert v-for="msg in txnErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </el-form>
    <template #footer>
      <el-button @click="txnOpen = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="txnForm.kind === 'adjust' && diff === 0" @click="saveTxn">登记</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="historyOpen" :title="`出入库流水：${historyOf?.name} ${historyOf?.spec}`" size="min(640px, 100vw)">
    <el-table :data="txns" empty-text="没有流水">
      <el-table-column label="时间" min-width="130">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="类型" min-width="80">
        <template #default="{ row }">{{ TXN_KIND_LABELS[row.kind] }}</template>
      </el-table-column>
      <el-table-column label="数量" min-width="70" align="right">
        <template #default="{ row }"><span class="mono">{{ signed(row.quantity) }}</span></template>
      </el-table-column>
      <el-table-column label="经手人" min-width="80">
        <template #default="{ row }">{{ row.handler.name }}</template>
      </el-table-column>
      <el-table-column label="项目" min-width="100">
        <template #default="{ row }">{{ row.project?.name }}</template>
      </el-table-column>
      <el-table-column label="采购申请" min-width="110">
        <template #default="{ row }"><span class="code">{{ row.purchase?.code }}</span></template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
    </el-table>
    <el-button v-if="hasMore && historyOf" link type="primary" class="more" @click="loadTxns(historyOf, false)">加载更多</el-button>
  </el-drawer>
</template>

<style scoped>
.stock {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
.stock.low {
  color: var(--el-color-danger);
}
.low-tag {
  margin-left: 8px;
}
.book {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
}
.diff {
  margin-left: 12px;
  font-variant-numeric: tabular-nums;
}
.more {
  margin-top: 12px;
}
</style>
