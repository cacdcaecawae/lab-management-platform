<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storageApi, type OpsStorage, type GroupStorage } from '@/api/storageUsage'
import { showError } from '@/utils/errors'
import { formatSize } from '@/utils/format'

const props = defineProps<{ ops?: boolean }>()
const opsResult = ref<OpsStorage>()
const groupResult = ref<GroupStorage>()
const loading = ref(false)
const modules: Record<string, string> = {
  raw: '原始数据', knowledge: '知识库', meetings: '组会', procurement: '采购及报销', achievements: '成果全文', equipment: '设备使用照片',
}
const moduleRows = computed(() => opsResult.value?.groups.flatMap(g =>
  Object.entries(g.modules).map(([key, usage]) => ({ group: g.name, source: modules[key] ?? key, ...usage })),
) ?? [])
const monthRows = computed(() => opsResult.value?.groups.flatMap(g =>
  opsResult.value!.month_keys.map(month => ({ group: g.name, month, bytes: g.months[month] ?? 0 })),
) ?? [])
const bytes = formatSize

async function load() {
  loading.value = true
  try {
    if (props.ops) opsResult.value = await storageApi.ops()
    else groupResult.value = await storageApi.group()
  } catch (error) {
    showError(error)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-loading="loading" aria-label="存储用量">
    <template v-if="opsResult">
      <h3>磁盘</h3>
      <p v-if="opsResult.disk.filesystem">
        总量 {{ bytes(opsResult.disk.filesystem.total_bytes) }} · 已用 {{ bytes(opsResult.disk.filesystem.used_bytes) }} ·
        剩余 {{ bytes(opsResult.disk.filesystem.free_bytes) }}
      </p>
      <p v-else-if="opsResult.disk.kind === 'non_local'">文件不在本机磁盘上，没有容量数据</p>
      <p v-else>暂时读不到容量</p>
      <h3>按课题组</h3>
      <el-table empty-text="暂无课题组" :data="opsResult.groups">
        <el-table-column prop="name" label="课题组" />
        <el-table-column label="已知大小"><template #default="{ row }">{{ bytes(row.known_bytes) }}</template></el-table-column>
        <el-table-column prop="unknown_files" label="大小未知的文件数" />
      </el-table>
      <h3>按模块</h3>
      <el-table empty-text="暂无文件" :data="moduleRows">
        <el-table-column prop="group" label="课题组" />
        <el-table-column prop="source" label="模块" />
        <el-table-column label="已知大小"><template #default="{ row }">{{ bytes(row.known_bytes) }}</template></el-table-column>
        <el-table-column prop="unknown_files" label="大小未知的文件数" />
      </el-table>
      <h3>近 12 个月上传、现在还在的文件</h3>
      <el-table empty-text="暂无文件" :data="monthRows">
        <el-table-column prop="group" label="课题组" />
        <el-table-column prop="month" label="月份" />
        <el-table-column label="账面大小"><template #default="{ row }">{{ bytes(row.bytes) }}</template></el-table-column>
      </el-table>
      <p v-if="opsResult.projection">
        按 {{ opsResult.projection.basis_months.join('、') }} 估算，一年约
        {{ bytes(opsResult.projection.annual_retained_known_bytes) }}
      </p>
      <p v-else>不满三个完整月份，暂不估算</p>
    </template>
    <template v-if="groupResult">
      <h3>本组原始数据（按上传成员）</h3>
      <el-table empty-text="暂无文件" :data="groupResult.by_member">
        <el-table-column prop="label" label="成员" />
        <el-table-column label="已知大小"><template #default="{ row }">{{ bytes(row.known_bytes) }}</template></el-table-column>
        <el-table-column prop="unknown_files" label="大小未知的文件数" />
      </el-table>
      <h3>本组原始数据（按项目）</h3>
      <el-table empty-text="暂无文件" :data="groupResult.by_project">
        <el-table-column prop="label" label="项目" />
        <el-table-column label="已知大小"><template #default="{ row }">{{ bytes(row.known_bytes) }}</template></el-table-column>
        <el-table-column prop="unknown_files" label="大小未知的文件数" />
      </el-table>
    </template>
  </section>
</template>
