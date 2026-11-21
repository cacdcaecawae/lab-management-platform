<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { usageStatsApi, type UsageStatsQuery, type UsageStatsRow } from '../api'

const month = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit' })
  .formatToParts(new Date())
const year = Number(month.find((part) => part.type === 'year')?.value)
const monthNumber = Number(month.find((part) => part.type === 'month')?.value)
const dateKey = (y: number, m: number) => `${y}-${String(m).padStart(2, '0')}-01`
const filters = reactive<UsageStatsQuery>({
  from: dateKey(year, monthNumber),
  to: dateKey(monthNumber === 12 ? year + 1 : year, monthNumber === 12 ? 1 : monthNumber + 1),
  by: 'equipment',
})
const rows = ref<UsageStatsRow[]>([])
const applied = ref<UsageStatsQuery>()
const loading = ref(false)
const exportUrl = computed(() => applied.value ? usageStatsApi.exportUrl(applied.value) : '')
const groups = { equipment: '设备', user: '人员', project: '项目', month: '月份' }

async function refresh() {
  if (loading.value) return
  if (!filters.from || !filters.to || filters.from >= filters.to) {
    ElMessage.warning('请选择有效日期范围，结束日期须晚于开始日期')
    return
  }
  const query = { ...filters }
  loading.value = true
  try {
    rows.value = await usageStatsApi.list(query)
    applied.value = query
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '无法加载设备使用统计')
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <el-card>
    <el-form inline @submit.prevent="refresh">
      <el-form-item label="开始日期">
        <el-date-picker v-model="filters.from" type="date" value-format="YYYY-MM-DD" aria-label="开始日期" />
      </el-form-item>
      <el-form-item label="结束日期（不含）">
        <el-date-picker v-model="filters.to" type="date" value-format="YYYY-MM-DD" aria-label="结束日期（不含）" />
      </el-form-item>
      <el-form-item label="分组">
        <el-select v-model="filters.by" aria-label="分组" style="width: 120px">
          <el-option v-for="(label, value) in groups" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button native-type="submit" type="primary" :loading="loading">查询</el-button>
        <el-button v-if="exportUrl" tag="a" :href="exportUrl">导出当前结果 Excel</el-button>
      </el-form-item>
    </el-form>
    <p v-if="applied">{{ applied.from }} 至 {{ applied.to }}（不含），按{{ groups[applied.by] }}统计</p>
    <p>按北京时间统计。预约小时不是实际使用时长；已登记预约小时仅统计提交过使用登记的预约。按月时，时长跨月分摊，次数只计入窗口内第一个相交月。</p>
    <el-table empty-text="暂无使用记录" v-loading="loading" :data="rows">
      <el-table-column prop="key.label" label="分组" min-width="140" />
      <el-table-column label="预约小时" min-width="100">
        <template #default="{ row }">{{ row.booked_hours.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="已登记预约小时" min-width="145">
        <template #default="{ row }">{{ row.reported_hours.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="bookings" label="预约数" min-width="90" />
      <el-table-column prop="abnormal" label="异常数" min-width="90" />
    </el-table>
  </el-card>
</template>
