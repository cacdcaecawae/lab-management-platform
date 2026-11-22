<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '@/modules/system/api'
import type { MailSecurity, MailSettings, MailSettingsWrite } from '@/api/types'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/format'
import { useFieldErrors } from '@/utils/errors'
import { Clock } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

const SECURITY: Record<MailSecurity, { label: string; port: number }> = {
  ssl: { label: 'SSL', port: 465 },
  starttls: { label: 'STARTTLS', port: 587 },
  none: { label: '不加密', port: 25 },
}
const HISTORY_VALUES = { mail_security: Object.fromEntries(Object.entries(SECURITY).map(([k, v]) => [k, v.label])) }

const blank: Required<MailSettingsWrite> = {
  mail_enabled: false,
  mail_host: '',
  mail_port: 465,
  mail_security: 'ssl',
  mail_username: '',
  mail_from: '',
  mail_password: '',
}
const keys = Object.keys(blank) as (keyof MailSettingsWrite)[]
const form = reactive({ ...blank })
const saved = ref<MailSettings | null>(null)
const errors = useFieldErrors(keys)
const saving = ref(false)
const historyOpen = ref(false)

const testTo = ref(useAuthStore().user?.email ?? '')
const testErrors = useFieldErrors(['to'])
const testing = ref(false)

const dirty = computed(() => !!saved.value && keys.some((k) => form[k] !== (k === 'mail_password' ? '' : saved.value![k])))

function fill(s: MailSettings) {
  saved.value = s
  Object.assign(form, Object.fromEntries(keys.map((k) => [k, k === 'mail_password' ? '' : s[k]])))
}

onMounted(async () => {
  try {
    fill(await systemApi.mail())
  } catch (e) {
    errors.handle(e)
  }
})

// Follow the usual port of the chosen security unless a custom port was typed in.
function securityChanged(to: MailSecurity) {
  if (Object.values(SECURITY).some((s) => s.port === form.mail_port)) form.mail_port = SECURITY[to].port
}

async function save() {
  saving.value = true
  try {
    const { mail_password, ...rest } = form
    fill(await systemApi.saveMail(mail_password ? { ...rest, mail_password } : rest)) // no password: keep the stored one
    errors.clear()
    ElMessage.success('已保存，立即生效')
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}

async function sendTest() {
  if (dirty.value) {
    ElMessage.warning('测试邮件用的是已保存的设置，请先保存')
    return
  }
  testing.value = true
  testErrors.clear()
  try {
    const { to } = await systemApi.testMail(testTo.value)
    ElMessage.success(`测试邮件已发到 ${to}，请查收`)
  } catch (e) {
    testErrors.handle(e) // e.g. 发送失败：535 Error: authentication failed
  } finally {
    testing.value = false
    saved.value = await systemApi.mail().catch(() => saved.value) // refresh the last failure
  }
}
</script>

<template>
  <el-form class="mail-form" label-position="top" @submit.prevent="save">
    <el-form-item :error="errors.fe('mail_enabled')">
      <el-switch v-model="form.mail_enabled" active-text="启用邮件" aria-label="启用邮件" />
    </el-form-item>
    <div class="form-grid">
      <el-form-item class="span-2" label="SMTP 服务器" :error="errors.fe('mail_host')">
        <el-input v-model="form.mail_host" placeholder="如 smtp.example.edu.cn" />
      </el-form-item>
      <el-form-item label="端口" :error="errors.fe('mail_port')">
        <el-input-number v-model="form.mail_port" :min="1" :max="65535" :controls="false" />
      </el-form-item>
    </div>
    <el-form-item label="加密方式" :error="errors.fe('mail_security')">
      <el-radio-group v-model="form.mail_security" @change="(v) => securityChanged(v as MailSecurity)">
        <el-radio-button v-for="(s, k) in SECURITY" :key="k" :value="k">{{ s.label }}</el-radio-button>
      </el-radio-group>
    </el-form-item>
    <div class="form-grid">
      <el-form-item class="span-all" label="账号" :error="errors.fe('mail_username')">
        <el-input v-model="form.mail_username" placeholder="通常是完整的邮箱地址" autocomplete="off" />
      </el-form-item>
      <el-form-item class="span-all" label="授权码" :error="errors.fe('mail_password')">
        <el-input
          v-model="form.mail_password"
          type="password"
          show-password
          autocomplete="new-password"
          :placeholder="saved?.password_set ? '已设置，留空不修改' : '邮箱网页版设置里生成的客户端授权码'"
        />
      </el-form-item>
    </div>
    <el-form-item label="发件人地址" :error="errors.fe('mail_from')">
      <el-input v-model="form.mail_from" placeholder="留空时用账号" />
    </el-form-item>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    <div class="actions">
      <el-button type="primary" native-type="submit" :loading="saving">保存</el-button>
      <IconButton :icon="Clock" label="修改历史" @click="historyOpen = true" />
    </div>
  </el-form>

  <el-divider />

  <el-form class="mail-form" label-position="top" @submit.prevent="sendTest">
    <el-form-item label="收件地址" :error="testErrors.fe('to')">
      <div class="test-row">
        <el-input v-model="testTo" />
        <el-button native-type="submit" :loading="testing">发送测试邮件</el-button>
      </div>
    </el-form-item>
  </el-form>
  <el-alert
    v-if="saved?.last_mail_error"
    class="mail-form"
    type="error"
    :closable="false"
    :title="`最近一次发送失败（${formatTime(saved.last_mail_error_at!)}）`"
    :description="saved.last_mail_error"
  />

  <HistoryDrawer v-model="historyOpen" :load="systemApi.mailHistory" :values="HISTORY_VALUES" />
</template>

<style scoped>
.mail-form {
  max-width: 640px;
}
.test-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
</style>
