<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { ApiError } from '@/api/client'
import { attachmentsApi } from '@/api/procurement'
import type { Attachment, AttachmentKind, MeetingFile } from '@/api/types'
import { ATTACHMENT_KIND_LABELS, formatSize, formatTime } from '@/utils/format'
import { showError } from '@/utils/errors'

// upload: omitted when the viewer may not add files; canDelete: per file (the server checks again).
// Meeting files have no kind: pass withKinds=false and their own remove.
type FileItem = Attachment | MeetingFile
const props = withDefaults(
  defineProps<{
    attachments: FileItem[]
    upload?: (file: File, kind: AttachmentKind) => Promise<unknown>
    canDelete: (a: FileItem) => boolean
    defaultKind?: AttachmentKind
    withKinds?: boolean
    remove?: (id: number) => Promise<unknown>
    accept?: string
    hint?: string
  }>(),
  {
    defaultKind: undefined,
    upload: undefined,
    withKinds: true,
    remove: attachmentsApi.remove,
    accept: '.pdf,.jpg,.jpeg,.png',
    hint: 'PDF、JPG、PNG，单个不超过 20 MB',
  },
)
const emit = defineEmits<{ changed: [] }>()

const kind = ref<AttachmentKind>(props.defaultKind ?? 'quote')
const picker = ref<HTMLInputElement>()
const busy = ref(false)

async function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = '' // allow picking the same file again after an error
  if (!files.length || !props.upload) return
  busy.value = true
  try {
    for (const file of files) {
      try {
        await props.upload(file, kind.value)
      } catch (err) {
        // A rejected file says why (type, size) in errors.file.
        const reason = err instanceof ApiError ? err.body.errors?.file?.join('；') : undefined
        if (reason) ElMessage.error(`${file.name}：${reason}`)
        else showError(err)
      }
    }
  } finally {
    busy.value = false
    emit('changed')
  }
}

async function remove(a: FileItem) {
  try {
    await ElMessageBox.confirm(`删除附件“${a.name}”？`, '删除附件', { type: 'warning' })
  } catch {
    return
  }
  try {
    await props.remove(a.id)
    emit('changed')
  } catch (err) {
    showError(err)
  }
}
</script>

<template>
  <div class="attachments">
    <ul v-if="attachments.length" class="files">
      <li v-for="a in attachments" :key="a.id">
        <el-tag v-if="'kind' in a" size="small" disable-transitions>{{ ATTACHMENT_KIND_LABELS[a.kind] }}</el-tag>
        <a :href="a.url" target="_blank" rel="noopener" class="name">{{ a.name }}</a>
        <span class="meta">{{ formatSize(a.size) }} · {{ a.uploaded_by.name }} · {{ formatTime(a.created_at) }}</span>
        <el-button v-if="canDelete(a)" link type="danger" @click="remove(a)">删除</el-button>
      </li>
    </ul>
    <p v-else class="empty">还没有附件</p>
    <div v-if="upload" class="add">
      <el-select v-if="withKinds" v-model="kind" class="kind" aria-label="附件类型">
        <el-option v-for="(label, k) in ATTACHMENT_KIND_LABELS" :key="k" :label="label" :value="k" />
      </el-select>
      <el-button :icon="Upload" :loading="busy" @click="picker?.click()">上传附件</el-button>
      <span class="meta">{{ hint }}</span>
      <input ref="picker" type="file" :accept="accept" multiple hidden @change="onPick" />
    </div>
  </div>
</template>

<style scoped>
.files {
  margin: 0;
  padding: 0;
  list-style: none;
}
.files li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--lab-border);
}
.files li:last-child {
  border-bottom: none;
}
.name {
  min-width: 0;
  overflow-wrap: anywhere;
}
.meta {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.empty {
  margin: 0;
  color: var(--lab-text-3);
}
.add {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.kind {
  width: 110px;
}
</style>
