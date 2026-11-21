<script setup lang="ts">
import { reactive, ref } from 'vue'
import { systemApi } from '@/modules/system/api'
import type { SystemGroup, SystemGroupWrite } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { formatTime } from '@/utils/format'
import { useFieldErrors } from '@/utils/errors'
import PageToolbar from '@/components/PageToolbar.vue'
import FormDialog from '@/components/FormDialog.vue'

const { items, count, page, pageSize, loading, load } = usePagedList(systemApi.groups, {})

const blank: SystemGroupWrite = { name: '', finance_email: '' }
const form = reactive({ ...blank })
const errors = useFieldErrors(Object.keys(blank))
const editing = ref<SystemGroup | null>(null)
const open = ref(false)
const saving = ref(false)

function openDialog(g: SystemGroup | null) {
  editing.value = g
  Object.assign(form, blank, g && { name: g.name, finance_email: g.finance_email })
  errors.clear()
  open.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) await systemApi.updateGroup(editing.value.id, form)
    else await systemApi.createGroup(form)
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
  <PageToolbar>
    <template #actions>
      <el-button type="primary" @click="openDialog(null)">新建课题组</el-button>
    </template>
  </PageToolbar>
  <el-table v-loading="loading" :data="items" empty-text="暂无课题组">
    <el-table-column prop="name" label="名称" min-width="160" />
    <el-table-column prop="finance_email" label="财务邮箱" min-width="180" />
    <el-table-column prop="member_count" label="在籍成员" min-width="90" align="right" />
    <el-table-column label="创建时间" min-width="150">
      <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="操作" min-width="70">
      <template #default="{ row }"><el-button link type="primary" @click="openDialog(row as SystemGroup)">编辑</el-button></template>
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

  <FormDialog v-model="open" :title="editing ? '编辑课题组' : '新建课题组'" size="sm" :loading="saving" @submit="save">
    <el-form-item label="名称" :error="errors.fe('name')" required><el-input v-model="form.name" /></el-form-item>
    <el-form-item label="财务邮箱" :error="errors.fe('finance_email')">
      <el-input v-model="form.finance_email" placeholder="每周一收到“已交财务、尚未到账”的报销提醒；可不填" />
    </el-form-item>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>
</template>
