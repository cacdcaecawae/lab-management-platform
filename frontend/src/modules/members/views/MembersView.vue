<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { membersApi } from '@/modules/members/api'
import type { MemberListItem, Role } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { ROLE_LABELS } from '@/utils/format'
import { showError, useFieldErrors } from '@/utils/errors'

const auth = useAuthStore()
const isManager = computed(() => auth.user?.role === 'manager')

const filters = reactive({ search: '', role: '' })
const keyword = ref('')
const { items, count, page, pageSize, loading, load } = usePagedList(membersApi.list, filters)

// ---- create / edit ----
const dialog = ref(false)
const editing = ref<MemberListItem | null>(null)
const blank = { username: '', name: '', role: 'student' as Role, email: '', phone: '', research_direction: '', password: '' }
const form = reactive({ ...blank })
const formErrors = useFieldErrors(Object.keys(blank))
const saving = ref(false)

function openForm(m: MemberListItem | null) {
  editing.value = m
  const { name, role, research_direction, username = '', email = '', phone = '' } = m ?? blank
  Object.assign(form, blank, { name, role, research_direction, username, email, phone })
  formErrors.clear()
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    const { username, password, ...common } = form
    if (editing.value) await membersApi.update(editing.value.id, common)
    else await membersApi.create({ ...common, username, password })
    ElMessage.success('已保存')
    dialog.value = false
    load()
  } catch (e) {
    formErrors.handle(e)
  } finally {
    saving.value = false
  }
}

async function toggleActive(m: MemberListItem) {
  if (m.is_active) {
    try {
      await ElMessageBox.confirm(`停用后 ${m.name} 将不能登录，确定停用？`, '停用成员', { type: 'warning' })
    } catch {
      return
    }
  }
  try {
    await membersApi.update(m.id, { is_active: !m.is_active })
    ElMessage.success(m.is_active ? '已停用' : '已启用')
    load()
  } catch (e) {
    showError(e)
  }
}

// ---- reset password ----
const resetVisible = ref(false)
const resetTarget = ref<MemberListItem | null>(null)
const newPassword = ref('')
const resetErrors = useFieldErrors(['password'])

function openReset(m: MemberListItem) {
  resetTarget.value = m
  newPassword.value = ''
  resetErrors.clear()
  resetVisible.value = true
}

async function doReset() {
  try {
    await membersApi.resetPassword(resetTarget.value!.id, newPassword.value)
    ElMessage.success('密码已重置，该成员下次登录时需修改密码')
    resetVisible.value = false
  } catch (e) {
    resetErrors.handle(e)
  }
}
</script>

<template>
  <el-card class="card">
    <div class="page-toolbar">
      <el-input v-model="keyword" :placeholder="auth.isSupervisor ? '搜索姓名、学号、研究方向' : '搜索姓名、研究方向'" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.role" aria-label="角色" placeholder="全部角色" clearable>
        <el-option v-for="(label, value) in ROLE_LABELS" :key="value" :label="label" :value="value" />
      </el-select>
      <span class="grow" />
      <el-button v-if="isManager" type="primary" @click="openForm(null)">新建成员</el-button>
    </div>
    <el-table v-loading="loading" :data="items">
      <el-table-column prop="name" label="姓名" min-width="100" />
      <el-table-column v-if="auth.isSupervisor" prop="username" label="学号 / 工号" min-width="120" />
      <el-table-column label="角色" min-width="80">
        <template #default="{ row }">{{ ROLE_LABELS[row.role] }}</template>
      </el-table-column>
      <el-table-column prop="research_direction" label="研究方向" min-width="160" />
      <template v-if="auth.isSupervisor">
        <el-table-column prop="email" label="邮箱" min-width="160" />
        <el-table-column prop="phone" label="电话" min-width="120" />
      </template>
      <el-table-column label="状态" min-width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" disable-transitions>{{ row.is_active ? '在籍' : '已停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="isManager" label="操作" min-width="200" fixed="right">
        <template #default="{ row }">
          <!-- Managers handle student accounts and their own profile; advisor / manager accounts are managed by ops in 系统管理. -->
          <el-button v-if="row.role === 'student' || row.id === auth.user?.id" link type="primary" @click="openForm(row as MemberListItem)">编辑</el-button>
          <template v-if="row.role === 'student'">
            <el-button link type="primary" @click="openReset(row as MemberListItem)">重置密码</el-button>
            <el-button link :type="row.is_active ? 'danger' : 'primary'" @click="toggleActive(row as MemberListItem)">
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
          </template>
          <el-text v-else-if="row.id !== auth.user?.id" type="info" size="small">由运维管理</el-text>
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

  <el-dialog v-model="dialog" :title="editing ? '编辑成员' : '新建成员'" width="min(520px, 95vw)">
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item label="学号 / 工号（登录名）" :error="formErrors.fe('username')" required>
        <el-input v-model="form.username" :disabled="!!editing" />
      </el-form-item>
      <el-form-item label="姓名" :error="formErrors.fe('name')" required>
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="角色" :error="formErrors.fe('role')">
        <span>{{ ROLE_LABELS[form.role] }}</span>
      </el-form-item>
      <el-form-item label="研究方向" :error="formErrors.fe('research_direction')">
        <el-input v-model="form.research_direction" />
      </el-form-item>
      <el-form-item label="邮箱" :error="formErrors.fe('email')">
        <el-input v-model="form.email" />
      </el-form-item>
      <el-form-item label="电话" :error="formErrors.fe('phone')">
        <el-input v-model="form.phone" />
      </el-form-item>
      <el-form-item v-if="!editing" label="初始密码" :error="formErrors.fe('password')" required>
        <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-alert v-for="msg in formErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="resetVisible" title="重置密码" width="min(420px, 95vw)">
    <p>为 {{ resetTarget?.name }} 设置新的初始密码，对方下次登录时需修改。</p>
    <el-form label-position="top" @submit.prevent="doReset">
      <el-form-item label="新密码" :error="resetErrors.fe('password')">
        <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-alert v-for="msg in resetErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </el-form>
    <template #footer>
      <el-button @click="resetVisible = false">取消</el-button>
      <el-button type="primary" @click="doReset">重置</el-button>
    </template>
  </el-dialog>
</template>
