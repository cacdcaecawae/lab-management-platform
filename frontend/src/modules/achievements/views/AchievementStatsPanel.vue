<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { achievementStatsApi, type AchievementStatsQuery, type AchievementStats } from '@/modules/achievements/api'
import { ACHIEVEMENT_STATUS_LABELS, ACHIEVEMENT_TYPE_LABELS } from '@/utils/format'
import { showError } from '@/utils/errors'

const groups = { formal: '正式成果（按类型）', all: '全部状态', ...ACHIEVEMENT_STATUS_LABELS }
const filters = reactive<AchievementStatsQuery>({ status: 'formal' })
const applied = ref<AchievementStatsQuery>()
const stats = ref<AchievementStats>()
const loading = ref(false)
const exportUrl = computed(() => applied.value ? achievementStatsApi.exportUrl(applied.value) : '')

async function refresh() {
  if (loading.value) return
  if (filters.year_from && filters.year_to && filters.year_from > filters.year_to) {
    ElMessage.warning('结束年份不能早于开始年份')
    return
  }
  const query = { ...filters }
  loading.value = true
  try {
    stats.value = await achievementStatsApi.list(query)
    applied.value = query
  } catch (error) {
    showError(error)
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <section aria-label="成果统计">
    <el-form inline @submit.prevent="refresh">
      <el-form-item label="起始年份">
        <el-input-number v-model="filters.year_from" :min="1" :max="9999" :precision="0" aria-label="起始年份" :controls="false" />
      </el-form-item>
      <el-form-item label="结束年份">
        <el-input-number v-model="filters.year_to" :min="1" :max="9999" :precision="0" aria-label="结束年份" :controls="false" />
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="filters.status" aria-label="状态" style="width: 190px">
          <el-option v-for="(label, value) in groups" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button :loading="loading" native-type="submit" type="primary">查询</el-button>
        <el-button v-if="exportUrl" tag="a" :href="exportUrl">导出当前统计 Excel</el-button>
      </el-form-item>
    </el-form>
    <p>默认仅统计正式成果：已录用及已发表论文、已授权专利、获奖和已登记软著。</p>
    <template v-if="stats">
      <p>全组去重总计：{{ stats.total.total }} 项。多位本组作者各计 1 项，成员小计不能相加作为组总计。</p>
      <h3>按年份</h3>
      <el-table v-loading="loading" :data="stats.by_year">
        <el-table-column prop="year" label="年份" />
        <el-table-column v-for="(label, key) in ACHIEVEMENT_TYPE_LABELS" :key="key" :prop="key" :label="label" />
        <el-table-column prop="total" label="合计" />
      </el-table>
      <h3>按成员</h3>
      <el-table v-loading="loading" :data="stats.by_member">
        <el-table-column prop="user.name" label="成员" />
        <el-table-column prop="user.id" label="成员 ID" />
        <el-table-column v-for="(label, key) in ACHIEVEMENT_TYPE_LABELS" :key="key" :prop="key" :label="label" />
        <el-table-column prop="total" label="合计" />
      </el-table>
    </template>
  </section>
</template>
