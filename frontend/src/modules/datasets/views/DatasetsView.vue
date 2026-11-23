<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { datasetsApi } from '@/modules/datasets/api'
import { projectsApi } from '@/modules/projects/api'
import { membersApi } from '@/modules/members/api'
import type { DatasetKind } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { KIND_LABELS, formatSize, formatTime } from '@/utils/format'
import { useFieldErrors } from '@/utils/errors'
import PageToolbar from '@/components/PageToolbar.vue'
import FormDialog from '@/components/FormDialog.vue'

const auth = useAuthStore()
const router = useRouter()
const projects = useOptions(() => projectsApi.list({ page_size: 100 }))
const members = auth.isSupervisor ? useOptions(() => membersApi.list({ page_size: 100 })) : ref([])
const filters = reactive({ project: '' as number | '', owner: '' as number | '', kind: '', search: '' })
const keyword = ref('')
const { items, count, page, pageSize, loading } = usePagedList(datasetsApi.list, filters)

const dialog = ref(false)
const blank = { project_id: null as number | null, name: '', kind: 'raw' as DatasetKind, description: '' }
const form = reactive({ ...blank })
const errors = useFieldErrors(Object.keys(blank))
const saving = ref(false)

function openCreate() {
  Object.assign(form, blank)
  errors.clear()
  dialog.value = true
}

async function create() {
  saving.value = true
  try {
    const d = await datasetsApi.create({ ...form, project_id: form.project_id as number })
    dialog.value = false
    router.push({ name: 'dataset-detail', params: { id: d.id } })
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索名称" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.project" aria-label="项目" placeholder="全部项目" clearable filterable>
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-if="auth.isSupervisor" v-model="filters.owner" aria-label="创建人" placeholder="全部成员" clearable filterable>
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-select v-model="filters.kind" aria-label="类型" placeholder="全部类型" clearable>
        <el-option v-for="(label, value) in KIND_LABELS" :key="value" :label="label" :value="value" />
      </el-select>
      <template #actions>
        <el-button type="primary" @click="openCreate">新建数据集</el-button>
      </template>
    </PageToolbar>
    <el-table empty-text="暂无数据集" v-loading="loading" :data="items">
      <el-table-column label="编号" min-width="130">
        <template #default="{ row }">
          <RouterLink class="code" :to="{ name: 'dataset-detail', params: { id: row.id } }">{{ row.code }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column label="类型" min-width="90">
        <template #default="{ row }">{{ KIND_LABELS[row.kind] }}</template>
      </el-table-column>
      <el-table-column label="项目" min-width="140">
        <template #default="{ row }">{{ row.project.name }}</template>
      </el-table-column>
      <el-table-column label="创建人" min-width="90">
        <template #default="{ row }">{{ row.owner.name }}</template>
      </el-table-column>
      <el-table-column prop="file_count" label="文件数" min-width="70" />
      <el-table-column label="总大小" min-width="90">
        <template #default="{ row }">{{ formatSize(row.total_size) }}</template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="140">
        <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
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

  <FormDialog v-model="dialog" title="新建数据集" :loading="saving" @submit="create">
    <el-form-item label="项目" :error="errors.fe('project_id')" required>
      <el-select v-model="form.project_id" filterable placeholder="选择项目">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="名称" :error="errors.fe('name')" required>
      <el-input v-model="form.name" />
    </el-form-item>
    <el-form-item label="类型" :error="errors.fe('kind')" required>
      <el-radio-group v-model="form.kind">
        <el-radio v-for="(label, value) in KIND_LABELS" :key="value" :value="value">{{ label }}</el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item label="说明" :error="errors.fe('description')">
      <el-input v-model="form.description" type="textarea" :autosize="{ minRows: 3 }" />
    </el-form-item>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>
</template>
