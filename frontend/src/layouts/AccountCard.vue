<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Camera } from '@element-plus/icons-vue'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { ROLE_LABELS } from '@/utils/format'
import { showError } from '@/utils/errors'
import { squareJpeg } from '@/utils/image'

// Who is signed in (DESIGN.md): picture, name with the login name as a tag, then "角色 · 课题组".
// Top of the account menu and of 个人信息; `editable` makes the picture itself the way to change it.
const props = defineProps<{ size: number; editable?: boolean }>()
const auth = useAuthStore()
const name = computed(() => auth.user?.name || auth.user?.username || '')
const roleLine = computed(() =>
  [auth.user?.is_superuser ? '运维' : ROLE_LABELS[auth.user?.role ?? ''], auth.user?.group?.name].filter(Boolean).join(' · '),
)
const textSize = computed(() => ({ '--el-avatar-text-size': `${Math.round(props.size * 0.4)}px` }))
const picker = ref<HTMLInputElement>()
const uploading = ref(false)

async function upload() {
  const file = picker.value?.files?.[0]
  picker.value!.value = '' // picking the same file again still counts
  if (!file) return
  let picture: Blob
  try {
    picture = await squareJpeg(file)
  } catch {
    ElMessage.error('只支持 JPG、PNG、WebP 图片')
    return
  }
  uploading.value = true
  try {
    auth.user = await authApi.uploadAvatar(picture)
    ElMessage.success('头像已更换')
  } catch (e) {
    showError(e)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="account-card">
    <button
      v-if="editable"
      v-loading="uploading"
      type="button"
      class="pick"
      aria-label="更换头像"
      title="更换头像"
      :disabled="uploading"
      @click="picker?.click()"
    >
      <el-avatar :size="size" :src="auth.user?.avatar_url ?? undefined" :style="textSize">{{ name.slice(0, 1) }}</el-avatar>
      <span class="badge" aria-hidden="true"><el-icon><Camera /></el-icon></span>
    </button>
    <!-- outside the button: its click would bubble back to the button and open the picker again -->
    <input v-if="editable" ref="picker" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="upload" />
    <el-avatar v-else :size="size" :src="auth.user?.avatar_url ?? undefined" :style="textSize" aria-hidden="true">
      {{ name.slice(0, 1) }}
    </el-avatar>
    <div class="who">
      <div class="name-row">
        <span class="name">{{ name }}</span>
        <el-tag type="info" size="small" disable-transitions>{{ auth.user?.username }}</el-tag>
      </div>
      <div class="line">{{ roleLine }}</div>
    </div>
  </div>
</template>

<style scoped>
.account-card {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.pick {
  position: relative;
  flex: none;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: none;
  cursor: pointer;
}
.pick:hover .el-avatar {
  filter: brightness(0.92);
}
.pick:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
.pick :deep(.el-loading-mask) {
  border-radius: 50%;
}
/* the corner camera says "tap to change", on touch screens too where there is no hover */
.badge {
  position: absolute;
  right: -2px;
  bottom: -2px;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--lab-bg-card);
  box-shadow: var(--el-box-shadow-light);
  color: var(--lab-text-2);
  font-size: 13px;
}
.el-avatar {
  flex: none;
}
.who {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.name {
  font-size: 16px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.line {
  color: var(--lab-text-3);
  font-size: 13px;
  white-space: nowrap;
}
</style>
