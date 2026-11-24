<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { systemApi } from '@/modules/system/api'
import type { Account, Identity, Role, SystemGroup } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { IDENTITY_LABELS, MEMBER_STATUS, ROLE_LABELS, formatTime, renamedMessage, roleText } from '@/utils/format'
import { showError, useFieldErrors } from '@/utils/errors'
import PageToolbar from '@/components/PageToolbar.vue'
import FormDialog from '@/components/FormDialog.vue'

const filters = reactive({ search: '', group: '' as number | '', role: '', flag: '' })
const keyword = useLiveSearch(filters)
const { items, count, page, pageSize, loading, load } = usePagedList(systemApi.accounts, filters)

const groups = ref<SystemGroup[]>([])
async function loadGroups() {
  try {
    groups.value = (await systemApi.groups({ page_size: 100 })).results
  } catch (e) {
    showError(e)
  }
}
loadGroups()

// ---- create / edit ----
const dialog = ref(false)
const editing = ref<Account | null>(null)
const blank = {
  username: '',
  name: '',
  role: 'student' as Role,
  is_manager: false,
  is_approver: false,
  identity: '' as Identity | '',
  enrollment_year: null as number | null,
  tags: [] as string[],
  group_id: null as number | null,
  email: '',
  phone: '',
  wechat: '',
  research_direction: '',
  password: '',
}
const form = reactive({ ...blank })
const formErrors = useFieldErrors(Object.keys(blank), 'username')
const saving = ref(false)

function openForm(a: Account | null) {
  editing.value = a
  const { username, name, role, is_manager, is_approver, identity, enrollment_year, tags, email, phone, wechat, research_direction } = a ?? blank
  Object.assign(form, blank, {
    username, name, role, is_manager, is_approver, identity, enrollment_year, tags: [...tags], email, phone, wechat, research_direction,
    group_id: a?.group?.id ?? null,
  })
  formErrors.clear()
  dialog.value = true
  loadGroups() // a group may have been created on the other tab meanwhile
}

async function save() {
  saving.value = true
  try {
    const { username, password, group_id, enrollment_year, ...common } = form
    const year = enrollment_year ?? null
    if (editing.value) await systemApi.updateAccount(editing.value.id, { ...common, enrollment_year: year, username })
    else await systemApi.createAccount({ ...common, enrollment_year: year, username, password, group_id: group_id! })
    ElMessage.success(editing.value ? renamedMessage(editing.value.username, username) : '已新建，对方首次登录时需修改密码')
    dialog.value = false
    load()
  } catch (e) {
    formErrors.handle(e)
  } finally {
    saving.value = false
  }
}

async function toggleActive(a: Account) {
  if (a.is_active) {
    try {
      await ElMessageBox.confirm(`停用后 ${a.name} 将不能登录，确定停用？`, '停用账号', { type: 'warning' })
    } catch {
      return
    }
  }
  try {
    await systemApi.updateAccount(a.id, { is_active: !a.is_active })
    ElMessage.success(a.is_active ? '已停用' : '已启用')
    load()
  } catch (e) {
    showError(e)
  }
}

// ---- reset password ----
const resetVisible = ref(false)
const resetTarget = ref<Account | null>(null)
const newPassword = ref('')
const resetErrors = useFieldErrors(['password'])

function openReset(a: Account) {
  resetTarget.value = a
  newPassword.value = ''
  resetErrors.clear()
  resetVisible.value = true
}

const resetting = ref(false)
async function doReset() {
  resetting.value = true
  try {
    await systemApi.resetPassword(resetTarget.value!.id, newPassword.value)
    ElMessage.success('密码已重置，对方下次登录时需修改密码')
    resetVisible.value = false
  } catch (e) {
    resetErrors.handle(e)
  } finally {
    resetting.value = false
  }
}
</script>

<template>
  <PageToolbar>
    <el-input v-model="keyword" placeholder="搜索姓名、学号、邮箱" clearable @change="filters.search = keyword" />
    <el-select v-model="filters.group" placeholder="全部课题组" aria-label="课题组" clearable>
      <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
    </el-select>
    <el-select v-model="filters.role" placeholder="全部角色" aria-label="角色" clearable>
      <el-option v-for="(label, value) in ROLE_LABELS" :key="value" :label="label" :value="value" />
    </el-select>
    <el-select v-model="filters.flag" placeholder="全部权限" aria-label="权限" clearable>
      <el-option label="管理员" value="manager" />
      <el-option label="终审人" value="approver" />
    </el-select>
    <template #actions>
      <el-button type="primary" @click="openForm(null)">新建账号</el-button>
    </template>
  </PageToolbar>
  <el-table empty-text="暂无账号" v-loading="loading" :data="items">
    <el-table-column prop="name" label="姓名" min-width="100" />
    <el-table-column prop="username" label="学号 / 工号" min-width="110" />
    <el-table-column label="课题组" min-width="140">
      <template #default="{ row }">{{ row.group?.name ?? '（未分配）' }}</template>
    </el-table-column>
    <el-table-column label="角色" min-width="130">
      <template #default="{ row }">{{ roleText(row as Account) }}</template>
    </el-table-column>
    <el-table-column prop="email" label="邮箱" min-width="170" />
    <el-table-column label="状态" min-width="160">
      <template #default="{ row }">
        <!-- one tag: 未改初始密码 is an account in use that has not signed in for real yet -->
        <el-tag v-if="row.pending" class="status-tag" type="warning" disable-transitions>待审核</el-tag>
        <el-tag v-else-if="row.is_active && row.must_change_password" class="status-tag" type="warning" disable-transitions>未改初始密码</el-tag>
        <el-tag v-else class="status-tag" :type="MEMBER_STATUS[row.member_status].type" disable-transitions>{{ MEMBER_STATUS[row.member_status].label }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="最近登录" min-width="150">
      <template #default="{ row }">{{ row.last_login ? formatTime(row.last_login) : '从未登录' }}</template>
    </el-table-column>
    <el-table-column label="操作" min-width="190" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" @click="openForm(row as Account)">编辑</el-button>
        <el-button link type="primary" @click="openReset(row as Account)">重置密码</el-button>
        <el-button link :type="row.is_active ? 'danger' : 'primary'" @click="toggleActive(row as Account)">
          {{ row.is_active ? '停用' : '启用' }}
        </el-button>
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

  <FormDialog v-model="dialog" :title="editing ? '编辑账号' : '新建账号'" :loading="saving" @submit="save">
    <div class="form-grid">
      <el-form-item label="学号 / 工号（登录名）" :error="formErrors.fe('username')" required>
        <el-input v-model="form.username" />
      </el-form-item>
      <el-form-item label="姓名" :error="formErrors.fe('name')" required><el-input v-model="form.name" /></el-form-item>
      <!-- fixed once created: moving someone changes who can see their records (done in /admin/ if ever needed) -->
      <el-form-item label="课题组" :error="formErrors.fe('group_id')" required>
        <span v-if="editing">{{ editing.group?.name ?? '（未分配）' }}</span>
        <el-select v-else v-model="form.group_id" placeholder="选择课题组">
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="基础角色" :error="formErrors.fe('role')" required>
        <el-select v-model="form.role">
          <el-option v-for="(label, value) in ROLE_LABELS" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item label="权限" :error="formErrors.fe('is_manager') || formErrors.fe('is_approver')">
        <el-checkbox v-model="form.is_manager">管理员</el-checkbox>
        <el-checkbox v-model="form.is_approver">终审人</el-checkbox>
      </el-form-item>
      <el-form-item label="身份" :error="formErrors.fe('identity')">
        <el-select v-model="form.identity" placeholder="未填" clearable>
          <el-option v-for="(label, value) in IDENTITY_LABELS" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item label="入学年份" :error="formErrors.fe('enrollment_year')">
        <el-input-number v-model="form.enrollment_year" :min="1950" :max="2100" :controls="false" placeholder="如 2024" />
      </el-form-item>
      <el-form-item class="span-2" label="词条" :error="formErrors.fe('tags')">
        <el-select v-model="form.tags" multiple filterable allow-create default-first-option :reserve-keyword="false" placeholder="如 教授、博导">
          <el-option v-for="t in form.tags" :key="t" :label="t" :value="t" />
        </el-select>
      </el-form-item>
      <el-form-item label="邮箱" :error="formErrors.fe('email')"><el-input v-model="form.email" /></el-form-item>
      <el-form-item label="电话" :error="formErrors.fe('phone')"><el-input v-model="form.phone" /></el-form-item>
      <el-form-item label="微信号" :error="formErrors.fe('wechat')"><el-input v-model="form.wechat" /></el-form-item>
      <el-form-item label="研究方向" :error="formErrors.fe('research_direction')">
        <el-input v-model="form.research_direction" />
      </el-form-item>
    </div>
    <el-form-item v-if="!editing" label="初始密码" :error="formErrors.fe('password')" required>
      <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
    </el-form-item>
    <el-alert v-for="msg in formErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>

  <FormDialog v-model="resetVisible" title="重置密码" size="sm" confirm-text="重置" :loading="resetting" @submit="doReset">
    <template #before>
      <p>为 {{ resetTarget?.name }} 设置新的初始密码，对方下次登录时需修改。</p>
    </template>
    <el-form-item label="新密码" :error="resetErrors.fe('password')">
      <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" />
    </el-form-item>
    <el-alert v-for="msg in resetErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>
</template>
