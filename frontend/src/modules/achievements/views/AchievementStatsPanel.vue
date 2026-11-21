<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { achievementStatsApi, type AchievementStatsQuery, type AchievementStats } from '@/modules/achievements/api'
import { ACHIEVEMENT_STATUS_LABELS, ACHIEVEMENT_TYPE_LABELS } from '@/utils/format'
import { showError } from '@/utils/errors'
import { Download } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'
import PageToolbar from '@/components/PageToolbar.vue'

const groups = { formal: '正式成果（按类型）', all: '全部状态', ...ACHIEVEMENT_STATUS_LABELS }
const filters = reactive<AchievementStatsQuery>({ status: 'formal' })
const applied = ref<AchievementStatsQuery>()
const stats = ref<AchievementStats>()
const loading = ref(false)
const exportUrl = computed(() => applied.value ? achievementStatsApi.exportUrl(applied.value) : '')
let latest = 0

// Every filter applies on change (DESIGN.md list toolbar); a slower earlier answer never replaces a newer one.
async function refresh() {
  if (filters.year_from && filters.year_to && filters.year_from > filters.year_to) {
    ElMessage.warning('结束年份不能早于开始年份')
    return
  }
  const query = { ...filters }
  const id = ++latest
  loading.value = true
  try {
    const result = await achievementStatsApi.list(query)
    if (id !== latest) return
    stats.value = result
    applied.value = query
  } catch (error) {
    if (id === latest) showError(error)
  } finally {
    if (id === latest) loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <section aria-label="成果统计">
    <PageToolbar>
      <el-input-number v-model="filters.year_from" :min="1" :max="9999" :precision="0" placeholder="起始年份" aria-label="起始年份" :controls="false" @change="refresh" />
      <el-input-number v-model="filters.year_to" :min="1" :max="9999" :precision="0" placeholder="结束年份" aria-label="结束年份" :controls="false" @change="refresh" />
      <el-select v-model="filters.status" aria-label="状态" @change="refresh">
        <el-option v-for="(label, value) in groups" :key="value" :label="label" :value="value" />
      </el-select>
      <template #actions>
        <IconButton v-if="exportUrl" :icon="Download" label="导出当前统计 Excel" tag="a" :href="exportUrl" />
      </template>
    </PageToolbar>
    <template v-if="stats">
      <p>全组去重总计：{{ stats.total.total }} 项</p>
      <h3>按年份</h3>
      <el-table empty-text="暂无成果" v-loading="loading" :data="stats.by_year">
        <el-table-column prop="year" label="年份" />
        <el-table-column v-for="(label, key) in ACHIEVEMENT_TYPE_LABELS" :key="key" :prop="key" :label="label" />
        <el-table-column prop="total" label="合计" />
      </el-table>
      <h3>按成员</h3>
      <el-table empty-text="暂无成果" v-loading="loading" :data="stats.by_member">
        <el-table-column prop="user.name" label="成员" />
        <el-table-column prop="user.id" label="成员 ID" />
        <el-table-column v-for="(label, key) in ACHIEVEMENT_TYPE_LABELS" :key="key" :prop="key" :label="label" />
        <el-table-column prop="total" label="合计" />
      </el-table>
    </template>
  </section>
</template>
