<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { membersApi } from '@/modules/members/api'
import type { Identity, MemberListItem, MemberStatus } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { suggest } from '@/api/suggestions'
import { useAuthStore } from '@/stores/auth'
import { IDENTITY_LABELS, MEMBER_STATUS, ROLE_LABELS, renamedMessage, roleText } from '@/utils/format'
import { authApi } from '@/api/auth'
import { showError, useFieldErrors } from '@/utils/errors'
import StorageUsage from '@/components/StorageUsage.vue'
import MemberSignups from '@/modules/members/components/MemberSignups.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import FormDialog from '@/components/FormDialog.vue'
import { Download, PieChart } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

// Base role and the 管理员 / 终审人 tags decide what one may do; identity, year, status and 词条 only describe the
// person (the roles-and-identity note). Managers edit students; the 终审人 gives or takes back the 管理员 tag.
const auth = useAuthStore()
const storageOpen = ref(false)
const isManager = computed(() => auth.isManager)

const filters = reactive({ search: '', role: '', identity: '', flag: '', tag: '', year: '' as number | '', status: 'active' })
const keyword = useLiveSearch(filters)
const { items, count, page, pageSize, loading, load, sort } = usePagedList(membersApi.list, filters)
// shortcut: the 词条 and years offered come from the first 100 members; a group has fewer.
const everyone = useOptions(() => membersApi.list({ page_size: 100 }))
const tagOptions = computed(() => [...new Set(everyone.value.flatMap((m) => m.tags))].sort())
const yearOptions = computed(() => [...new Set(everyone.value.map((m) => m.enrollment_year).filter((y) => y))].sort().reverse())
// A plain student: the accounts a manager may edit (with their own); others are managed in 系统管理.
const plain = (m: MemberListItem) => m.role === 'student' && !m.is_manager && !m.is_approver

// ---- create / edit ----
const dialog = ref(false)
const editing = ref<MemberListItem | null>(null)
const blank = {
  username: '', name: '', identity: '' as Identity | '', enrollment_year: null as number | null, member_status: 'active' as MemberStatus,
  tags: [] as string[], email: '', phone: '', wechat: '', research_direction: '', password: '',
}
const form = reactive({ ...blank })
const formErrors = useFieldErrors(Object.keys(blank), 'username')
const saving = ref(false)

function openForm(m: MemberListItem | null) {
  editing.value = m
  const { name, identity, enrollment_year, member_status, tags, research_direction, username = '', email = '', phone = '', wechat = '' } = m ?? blank
  Object.assign(form, blank, { name, identity, enrollment_year, member_status, tags: [...tags], research_direction, username, email, phone, wechat })
  formErrors.clear()
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    const { username, password, member_status, enrollment_year, ...common } = form
    const before = editing.value
    const year = enrollment_year ?? null
    if (before) {
      // one's own status stays 在籍 (the server refuses otherwise)
      await membersApi.update(before.id, { ...common, enrollment_year: year, username, ...(before.id === auth.user?.id ? {} : { member_status }) })
    } else await membersApi.create({ ...common, enrollment_year: year, username, password })
    ElMessage.success(renamedMessage(before?.username, username))
    if (before?.id === auth.user?.id) auth.user = await authApi.me() // own account: the sidebar shows the new name
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
    await membersApi.update(m.id, { member_status: m.is_active ? 'disabled' : 'active' })
    ElMessage.success(m.is_active ? '已停用' : '已启用')
    load()
  } catch (e) {
    showError(e)
  }
}

// ---- the 管理员 tag (终审人) ----
async function toggleManager(m: MemberListItem) {
  const on = !m.is_manager
  try {
    await ElMessageBox.confirm(
      on
        ? `${m.name} 将能维护设备、试件、耗材、经费来源和组会，审核注册、做采购初审。${m.role === 'student' ? '看不到别的同学的实验记录和周报。' : ''}`
        : `${m.name} 将不再是管理员。`,
      on ? '设为管理员' : '取消管理员',
      { confirmButtonText: on ? '设为管理员' : '取消管理员', type: on ? 'info' : 'warning' },
    )
  } catch {
    return
  }
  try {
    await membersApi.setManager(m.id, on)
    ElMessage.success(on ? `${m.name} 已是管理员` : `${m.name} 已不是管理员`)
    if (m.id === auth.user?.id) auth.user = await authApi.me() // the menu follows one's own tag
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

const resetting = ref(false)
async function doReset() {
  resetting.value = true
  try {
    await membersApi.resetPassword(resetTarget.value!.id, newPassword.value)
    ElMessage.success('密码已重置，该成员下次登录时需修改密码')
    resetVisible.value = false
  } catch (e) {
    resetErrors.handle(e)
  } finally {
    resetting.value = false
  }
}
</script>

<template>
  <MemberSignups v-if="isManager" @approved="load" />
  <el-card class="card">
    <PageToolbar>
      <el-input v-model="keyword" :placeholder="auth.isSupervisor ? '搜索姓名、学号、研究方向' : '搜索姓名、研究方向'" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.status" aria-label="状态" placeholder="全部状态" clearable>
        <el-option v-for="(s, value) in MEMBER_STATUS" :key="value" :label="s.label" :value="value" />
      </el-select>
      <el-select v-model="filters.identity" aria-label="身份" placeholder="全部身份" clearable>
        <el-option v-for="(label, value) in IDENTITY_LABELS" :key="value" :label="label" :value="value" />
      </el-select>
      <el-select v-model="filters.role" aria-label="角色" placeholder="全部角色" clearable>
        <el-option v-for="(label, value) in ROLE_LABELS" :key="value" :label="label" :value="value" />
      </el-select>
      <el-select v-model="filters.flag" aria-label="权限" placeholder="全部权限" clearable>
        <el-option label="管理员" value="manager" />
        <el-option label="终审人" value="approver" />
      </el-select>
      <el-select v-model="filters.year" aria-label="年级" placeholder="全部年级" clearable>
        <el-option v-for="y in yearOptions" :key="y!" :label="`${y}级`" :value="y!" />
      </el-select>
      <el-select v-if="tagOptions.length" v-model="filters.tag" aria-label="词条" placeholder="全部词条" clearable filterable>
        <el-option v-for="t in tagOptions" :key="t" :label="t" :value="t" />
      </el-select>
      <template #actions>
        <IconButton v-if="auth.isSupervisor" :icon="Download" label="导出花名册" tag="a" :href="membersApi.exportUrl(filters)" />
        <IconButton v-if="auth.isSupervisor" :icon="PieChart" label="本组存储用量" @click="storageOpen = true" />
        <el-button v-if="isManager" type="primary" @click="openForm(null)">新建成员</el-button>
      </template>
    </PageToolbar>
    <el-table @sort-change="sort" :empty-text="filters.status || filters.identity || filters.role || filters.flag || filters.year || filters.tag || filters.search ? '没有符合条件的成员' : '暂无成员'" v-loading="loading" :data="items">
      <el-table-column prop="name" label="姓名" sortable="custom" min-width="100" />
      <el-table-column v-if="auth.isSupervisor" prop="username" label="学号 / 工号" min-width="120" />
      <el-table-column label="角色" min-width="120">
        <template #default="{ row }">{{ roleText(row as MemberListItem) }}</template>
      </el-table-column>
      <el-table-column label="身份" min-width="80">
        <template #default="{ row }">{{ IDENTITY_LABELS[row.identity] ?? '' }}</template>
      </el-table-column>
      <el-table-column label="年级" prop="enrollment_year" sortable="custom" min-width="90">
        <template #default="{ row }">{{ row.enrollment_year ? `${row.enrollment_year}级` : '' }}</template>
      </el-table-column>
      <el-table-column label="词条" min-width="120">
        <template #default="{ row }">
          <div class="actions"><el-tag v-for="t in row.tags" :key="t" type="info" disable-transitions>{{ t }}</el-tag></div>
        </template>
      </el-table-column>
      <el-table-column prop="research_direction" label="研究方向" min-width="140" />
      <template v-if="auth.isSupervisor">
        <el-table-column prop="email" label="邮箱" min-width="160" />
        <el-table-column prop="phone" label="电话" min-width="140" />
        <el-table-column prop="wechat" label="微信号" min-width="120" />
      </template>
      <el-table-column label="状态" min-width="80">
        <template #default="{ row }">
          <el-tag class="status-tag" :type="MEMBER_STATUS[row.member_status].type" disable-transitions>{{ MEMBER_STATUS[row.member_status].label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="isManager || auth.isApprover" label="操作" min-width="220" fixed="right">
        <template #default="{ row }">
          <template v-if="isManager">
            <!-- Managers handle plain student accounts and their own profile; the rest are managed by ops in 系统管理. -->
            <el-button v-if="plain(row as MemberListItem) || row.id === auth.user?.id" link type="primary" @click="openForm(row as MemberListItem)">编辑</el-button>
            <template v-if="plain(row as MemberListItem)">
              <el-button link type="primary" @click="openReset(row as MemberListItem)">重置密码</el-button>
              <el-button link :type="row.is_active ? 'danger' : 'primary'" @click="toggleActive(row as MemberListItem)">
                {{ row.is_active ? '停用' : '启用' }}
              </el-button>
            </template>
          </template>
          <el-button v-if="auth.isApprover" link type="primary" @click="toggleManager(row as MemberListItem)">
            {{ row.is_manager ? '取消管理员' : '设为管理员' }}
          </el-button>
          <el-text v-else-if="isManager && !plain(row as MemberListItem) && row.id !== auth.user?.id" type="info" size="small">由运维管理</el-text>
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

  <FormDialog v-model="dialog" :title="editing ? '编辑成员' : '新建成员'" :loading="saving" @submit="save">
    <div class="form-grid">
      <el-form-item label="学号 / 工号（登录名）" :error="formErrors.fe('username')" required>
        <el-input v-model="form.username" />
      </el-form-item>
      <el-form-item label="姓名" :error="formErrors.fe('name')" required>
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="角色">
        <span>{{ editing ? roleText(editing) : ROLE_LABELS.student }}</span>
      </el-form-item>
      <el-form-item label="身份" :error="formErrors.fe('identity')">
        <el-select v-model="form.identity" placeholder="未填" clearable>
          <el-option v-for="(label, value) in IDENTITY_LABELS" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item label="入学年份" :error="formErrors.fe('enrollment_year')">
        <el-input-number v-model="form.enrollment_year" :min="1950" :max="2100" :controls="false" placeholder="如 2024" />
      </el-form-item>
      <el-form-item v-if="editing && editing.id !== auth.user?.id" label="状态" :error="formErrors.fe('member_status')">
        <el-select v-model="form.member_status">
          <el-option v-for="(s, value) in MEMBER_STATUS" :key="value" :label="s.label" :value="value" />
        </el-select>
      </el-form-item>
    </div>
    <el-form-item label="词条" :error="formErrors.fe('tags')">
      <el-select v-model="form.tags" multiple filterable allow-create default-first-option :reserve-keyword="false" placeholder="如 博导、安全员，可自己填">
        <el-option v-for="t in tagOptions" :key="t" :label="t" :value="t" />
      </el-select>
    </el-form-item>
    <div class="form-grid">
      <el-form-item class="span-2" label="研究方向" :error="formErrors.fe('research_direction')">
        <el-autocomplete v-model="form.research_direction" :fetch-suggestions="suggest('member.research_direction')" />
      </el-form-item>
      <el-form-item label="邮箱" :error="formErrors.fe('email')">
        <el-input v-model="form.email" />
      </el-form-item>
      <el-form-item label="电话" :error="formErrors.fe('phone')">
        <el-input v-model="form.phone" />
      </el-form-item>
      <el-form-item label="微信号" :error="formErrors.fe('wechat')">
        <el-input v-model="form.wechat" />
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
  <el-dialog v-model="storageOpen" title="本组存储用量" width="min(720px, 95vw)" destroy-on-close>
    <StorageUsage v-if="storageOpen" />
  </el-dialog>
</template>
