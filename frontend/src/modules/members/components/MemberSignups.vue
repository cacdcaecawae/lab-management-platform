<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, type InputInstance } from 'element-plus'
import { membersApi } from '@/modules/members/api'
import type { PendingMember } from '@/api/types'
import { showError } from '@/utils/errors'
import { formatTime } from '@/utils/format'
import PageToolbar from '@/components/PageToolbar.vue'
import { CopyDocument, RefreshRight } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

// For managers: the group's registration link and the applications waiting for approval.
const emit = defineEmits<{ approved: [] }>()
const code = ref('')
const pending = ref<PendingMember[]>([])
const selected = ref<PendingMember[]>([])
const linkInput = ref<InputInstance>()
const link = computed(() => `${location.origin}/register?code=${code.value}`)

async function loadPending() {
  pending.value = await membersApi.pending()
}

onMounted(async () => {
  try {
    code.value = (await membersApi.signup()).code
    await loadPending()
  } catch (e) {
    showError(e)
  }
})

async function setOpen(open: boolean, ask = '') {
  if (ask) {
    try {
      await ElMessageBox.confirm(ask, '学生注册', { type: 'warning' })
    } catch {
      return
    }
  }
  try {
    code.value = (await membersApi.setSignup(open)).code
    ElMessage.success(open ? '已生成新的注册链接' : '已关闭学生注册，旧链接失效')
  } catch (e) {
    showError(e)
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(link.value)
  } catch {
    // Plain HTTP pages have no clipboard API: select the text and fall back to the old copy command.
    linkInput.value?.select()
    if (!document.execCommand('copy')) {
      ElMessage.warning('浏览器不允许自动复制，链接已选中，请按 Ctrl+C 复制')
      return
    }
  }
  ElMessage.success('已复制，发到课题组的群里')
}

async function decide(approve: boolean, rows: PendingMember[], ask = '') {
  if (ask) {
    try {
      await ElMessageBox.confirm(ask, approve ? '通过申请' : '拒绝申请', { type: 'warning' })
    } catch {
      return
    }
  }
  try {
    const { count } = await (approve ? membersApi.approve : membersApi.reject)(rows.map((r) => r.id))
    ElMessage.success(approve ? `已通过 ${count} 人，现在可以登录了` : `已拒绝 ${count} 人`)
    if (approve) emit('approved')
    await loadPending()
  } catch (e) {
    showError(e)
  }
}
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-switch
        :model-value="!!code"
        active-text="允许学生用链接注册"
        aria-label="允许学生用链接注册"
        @change="(on) => setOpen(!!on, on ? '' : '关闭后，已经发出去的链接都会失效。确定关闭？')"
      />
      <template v-if="code">
        <el-input ref="linkInput" :model-value="link" readonly aria-label="注册链接" class="grow" @focus="linkInput?.select()" />
        <IconButton :icon="CopyDocument" label="复制链接" @click="copy" />
        <IconButton :icon="RefreshRight" label="换一个链接" @click="setOpen(true, '换一个链接后，旧链接失效。确定更换？')" />
      </template>
    </PageToolbar>
    <template v-if="pending.length">
      <h3>待审核（{{ pending.length }}）</h3>
      <el-table empty-text="暂无待审核的申请" :data="pending" @selection-change="(rows: PendingMember[]) => (selected = rows)">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="name" label="姓名" min-width="100" />
        <el-table-column prop="username" label="学号" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="160" />
        <el-table-column label="申请时间" min-width="140">
          <template #default="{ row }">{{ formatTime(row.date_joined) }}</template>
        </el-table-column>
      </el-table>
      <PageToolbar>
        <el-button type="primary" :disabled="!selected.length" @click="decide(true, selected)">通过</el-button>
        <el-button
          type="danger"
          :disabled="!selected.length"
          @click="decide(false, selected, `拒绝后这 ${selected.length} 个申请会被删除，对方可以重新申请。确定拒绝？`)"
        >
          拒绝
        </el-button>
        <el-button @click="decide(true, pending, `通过全部 ${pending.length} 个申请？请先核对学号和姓名。`)">全部通过</el-button>
      </PageToolbar>
    </template>
  </el-card>
</template>
