<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { equipmentApi } from '../api'
import { docsApi } from '@/modules/knowledge/api'
import type { Doc, EquipmentDetail } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { CONDITION_LABELS, DOC_CATEGORY_LABELS, formatPeriod, formatTime } from '@/utils/format'
import { errorMessage } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import EquipmentFormDialog from '../components/EquipmentFormDialog.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const equipment = ref<EquipmentDetail | null>(null)
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const editing = ref(false)
const historyOpen = ref(false)

const docs = ref<Doc[]>([])

async function load() {
  try {
    equipment.value = await equipmentApi.get(id)
    // the device's SDKs, manuals, procedures... from the knowledge base (shortcut: the latest 20)
    docs.value = (await docsApi.list({ equipment: id })).results
  } catch (e) {
    loadError.value = errorMessage(e)
  }
}

load()
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'equipment' })">返回设备台账</el-button></template>
  </el-result>
  <template v-else-if="equipment">
    <el-card class="card">
      <template #header>
        <div class="actions">
          <el-page-header @back="router.push({ name: 'equipment' })">
            <template #content><span class="code">{{ equipment.code }}</span> {{ equipment.name }}</template>
          </el-page-header>
          <span style="flex: 1" />
          <el-button @click="historyOpen = true">修改历史</el-button>
          <el-button v-if="auth.isManager" @click="editing = true">编辑设备</el-button>
          <el-button type="primary" @click="router.push({ name: 'bookings', query: { equipment: equipment.id } })">预约</el-button>
        </div>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="状态">
          <div class="actions">
            <StatusTag :status="equipment.status" />
            <el-tag v-if="equipment.in_use" class="status-tag" type="primary" disable-transitions>使用中</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="型号">{{ equipment.model }}</el-descriptions-item>
        <el-descriptions-item label="类别">{{ equipment.category }}</el-descriptions-item>
        <el-descriptions-item label="存放位置">{{ equipment.location }}</el-descriptions-item>
        <el-descriptions-item label="保管人">{{ equipment.custodian?.name }}</el-descriptions-item>
        <el-descriptions-item label="购置日期">{{ equipment.purchase_date }}</el-descriptions-item>
        <el-descriptions-item label="下次校准日期">{{ equipment.calibration_due }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatTime(equipment.updated_at) }}</el-descriptions-item>
        <el-descriptions-item label="采购申请" :span="2">
          <!-- the request is private to its applicant and supervisors: others see the code only -->
          <RouterLink v-if="equipment.purchase && auth.isSupervisor" class="code" :to="{ name: 'purchase-detail', params: { id: equipment.purchase.id } }">
            {{ equipment.purchase.code }}
          </RouterLink>
          <span v-else class="code">{{ equipment.purchase?.code }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="备注" :span="2"><pre class="pre">{{ equipment.notes }}</pre></el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="card">
      <template #header>
        <div class="actions">
          <span>资料</span>
          <span class="grow" />
          <el-button link type="primary" @click="router.push({ name: 'knowledge', query: { equipment: id } })">在知识库中查看</el-button>
        </div>
      </template>
      <ul v-if="docs.length" class="docs">
        <li v-for="d in docs" :key="d.id">
          <el-tag size="small" disable-transitions>{{ DOC_CATEGORY_LABELS[d.category] }}</el-tag>
          <RouterLink :to="{ name: 'knowledge', query: { equipment: id, doc: d.id } }">{{ d.title }}</RouterLink>
          <a v-if="d.latest" :href="d.latest.url" target="_blank" rel="noopener" class="muted">{{ d.latest.name }}（第 {{ d.latest.number }} 版）</a>
        </li>
      </ul>
      <p v-else class="muted">知识库里还没有这台设备的资料</p>
    </el-card>

    <el-card class="card" header="最近使用记录">
      <el-table :data="equipment.recent_usage" empty-text="还没有使用记录">
        <el-table-column label="时间" min-width="170">
          <template #default="{ row }">{{ formatPeriod(row.start_at, row.end_at) }}</template>
        </el-table-column>
        <el-table-column label="使用人" min-width="80">
          <template #default="{ row }">{{ row.user.name }}</template>
        </el-table-column>
        <el-table-column label="项目" min-width="110">
          <template #default="{ row }">{{ row.project?.name }}</template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途" min-width="120" show-overflow-tooltip />
        <el-table-column label="使用后状况" min-width="220">
          <template #default="{ row }">
            <span v-if="!row.report" class="muted">未登记</span>
            <div v-else class="report">
              <el-tag class="status-tag" :type="row.report.condition === 'abnormal' ? 'danger' : 'success'" disable-transitions>
                {{ CONDITION_LABELS[row.report.condition] }}
              </el-tag>
              <span v-if="row.report.description">{{ row.report.description }}</span>
              <a v-if="row.report.photo_url" :href="row.report.photo_url" target="_blank" rel="noopener">照片</a>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <EquipmentFormDialog v-model="editing" :equipment="equipment" @saved="load" @stale="load" />
    <HistoryDrawer v-model="historyOpen" :load="() => equipmentApi.history(id)" />
  </template>
</template>

<style scoped>
.report {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.muted {
  color: var(--el-text-color-secondary);
}
.grow {
  flex: 1;
}
.docs {
  margin: 0;
  padding: 0;
  list-style: none;
}
.docs li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  padding: 6px 0;
}
</style>
