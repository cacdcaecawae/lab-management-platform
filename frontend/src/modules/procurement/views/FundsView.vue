<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { membersApi } from '@/modules/members/api'
import { fundsApi } from '@/modules/procurement/api'
import type { Fund, FundWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { mergeById } from '@/utils/format'
import { useFieldErrors } from '@/utils/errors'
import PageToolbar from '@/components/PageToolbar.vue'
import FormDialog from '@/components/FormDialog.vue'

const filters = reactive({ search: '', active: '' as 1 | '', owner: '' as number | '' })
const keyword = useLiveSearch(filters)
const { items, count, page, pageSize, loading, load } = usePagedList(fundsApi.list, filters)
const members = useOptions(() => membersApi.list({ is_active: true, page_size: 100 }))

const blank: FundWrite = { code: '', name: '', owner_id: null, active: true, notes: '' }
const form = reactive<FundWrite>({ ...blank })
const errors = useFieldErrors(Object.keys(blank))
const editing = ref<Fund | null>(null)
const open = ref(false)
const saving = ref(false)
const ownerOptions = computed(() => mergeById(members.value, [editing.value?.owner]))

function openDialog(f: Fund | null) {
  editing.value = f
  Object.assign(form, blank, f && { code: f.code, name: f.name, owner_id: f.owner?.id ?? null, active: f.active, notes: f.notes })
  errors.clear()
  open.value = true
}

async function save() {
  saving.value = true
  try {
    const body = { ...form, owner_id: form.owner_id ?? null }
    if (editing.value) await fundsApi.update(editing.value.id, body)
    else await fundsApi.create(body)
    open.value = false
    load()
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
      <el-input v-model="keyword" placeholder="搜索经费号、名称" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.owner" placeholder="全部负责人" clearable filterable aria-label="负责人">
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-checkbox v-model="filters.active" :true-value="1" false-value="">只看可用</el-checkbox>
      <template #actions>
        <el-button type="primary" @click="openDialog(null)">新建经费来源</el-button>
      </template>
    </PageToolbar>
    <el-table v-loading="loading" :data="items" empty-text="暂无经费来源">
      <el-table-column label="经费号" min-width="120">
        <template #default="{ row }"><span class="code">{{ row.code }}</span></template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column label="负责人" min-width="90">
        <template #default="{ row }">{{ row.owner?.name }}</template>
      </el-table-column>
      <el-table-column label="状态" min-width="80">
        <template #default="{ row }">
          <el-tag class="status-tag" :type="row.active ? 'success' : 'info'" disable-transitions>{{ row.active ? '可用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="notes" label="备注" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" min-width="70" fixed="right">
        <template #default="{ row }"><el-button link type="primary" @click="openDialog(row as Fund)">编辑</el-button></template>
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

  <FormDialog v-model="open" :title="editing ? '编辑经费来源' : '新建经费来源'" :loading="saving" @submit="save">
    <div class="form-grid">
      <el-form-item label="经费号" :error="errors.fe('code')" required><el-input v-model="form.code" /></el-form-item>
      <el-form-item class="span-2" label="名称" :error="errors.fe('name')" required>
        <el-input v-model="form.name" placeholder="如 国自然面上项目" />
      </el-form-item>
      <el-form-item class="span-2" label="负责人" :error="errors.fe('owner_id')">
        <el-select v-model="form.owner_id" filterable clearable placeholder="可不选">
          <el-option v-for="m in ownerOptions" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态" :error="errors.fe('active')">
        <el-switch v-model="form.active" active-text="可用" inactive-text="停用" />
      </el-form-item>
    </div>
    <el-form-item label="备注" :error="errors.fe('notes')">
      <el-input v-model="form.notes" type="textarea" :autosize="{ minRows: 2 }" />
    </el-form-item>
    <el-alert v-if="editing && !form.active" type="info" :closable="false" title="停用后不能再在新的采购和报销里选择，已有记录照常显示。" />
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>
</template>
