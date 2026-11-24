<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { ApiError } from '@/api/client'
import type { Attachment, AttachmentKind, MeetingFile } from '@/api/types'
import { ATTACHMENT_KIND_LABELS, formatSize, formatTime } from '@/utils/format'
import { showError } from '@/utils/errors'
import { previewKindOf } from '@/utils/preview'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'
import FilePreviewDialog, { type PreviewTarget } from '@/components/FilePreviewDialog.vue'

// upload: omitted when the viewer may not add files; canDelete: per file (the server checks again).
// Meeting files have no kind: pass withKinds=false; all callers supply their own remover.
type FileItem = Attachment | MeetingFile
const props = withDefaults(
  defineProps<{
    attachments: FileItem[]
    upload?: (file: File, kind: AttachmentKind, onProgress: (percent: number) => void) => Promise<unknown>
    canDelete: (a: FileItem) => boolean
    defaultKind?: AttachmentKind
    withKinds?: boolean
    remove: (id: number) => Promise<unknown>
    accept?: string
    hint?: string
  }>(),
  {
    defaultKind: undefined,
    upload: undefined,
    withKinds: true,
    accept: '.pdf,.jpg,.jpeg,.png',
    hint: 'PDF、JPG、PNG，单个不超过 20 MB',
  },
)
const emit = defineEmits<{ changed: [] }>()

const kind = ref<AttachmentKind>(props.defaultKind ?? 'quote')
const picker = ref<HTMLInputElement>()
const busy = ref(false)
const percent = ref<number | null>(null) // only uploads that report progress (meeting files) show a bar
// Leaving the page while a file is still uploading would lose it: ask first.
useUnsavedGuard({}, () => busy.value, () => busy.value)
const previewOpen = ref(false)
const previewTarget = ref<PreviewTarget | null>(null)

function openPreview(a: FileItem) {
  previewTarget.value = { name: a.name, url: a.url, size: a.size }
  previewOpen.value = true
}

async function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = '' // allow picking the same file again after an error
  if (!files.length || !props.upload) return
  busy.value = true
  try {
    for (const file of files) {
      try {
        percent.value = null
        await props.upload(file, kind.value, (p) => (percent.value = p))
      } catch (err) {
        // A rejected file says why (type, size) in errors.file.
        const reason = err instanceof ApiError ? err.body.errors?.file?.join('；') : undefined
        if (reason) ElMessage.error(`${file.name}：${reason}`)
        else showError(err)
      }
    }
  } finally {
    busy.value = false
    percent.value = null
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
        <el-image
          v-if="previewKindOf(a.name) === 'image'"
          class="thumb"
          :src="a.url"
          :preview-src-list="[a.url]"
          preview-teleported
          fit="cover"
          :alt="a.name"
        />
        <el-button v-if="previewKindOf(a.name)" link type="primary" class="name" @click="openPreview(a)">{{ a.name }}</el-button>
        <a v-else :href="a.url" target="_blank" rel="noopener" class="name">{{ a.name }}</a>
        <span class="meta">{{ formatSize(a.size) }} · {{ a.uploaded_by.name }} · {{ formatTime(a.created_at) }}</span>
        <a v-if="previewKindOf(a.name)" :href="a.url" :download="a.name" class="meta">下载</a>
        <el-button v-if="canDelete(a)" link type="danger" @click="remove(a)">删除</el-button>
      </li>
    </ul>
    <p v-else class="empty">暂无附件</p>
    <div v-if="upload" class="add">
      <el-select v-if="withKinds" v-model="kind" class="kind" aria-label="附件类型">
        <el-option v-for="(label, k) in ATTACHMENT_KIND_LABELS" :key="k" :label="label" :value="k" />
      </el-select>
      <el-button :icon="Upload" :loading="busy" @click="picker?.click()">上传附件</el-button>
      <span class="meta">{{ hint }}</span>
      <input ref="picker" type="file" :accept="accept" multiple hidden @change="onPick" />
      <el-progress v-if="busy && percent !== null" class="progress" :percentage="percent" />
    </div>
    <FilePreviewDialog v-model="previewOpen" :target="previewTarget" />
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
  font-size: 13px;
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
.progress {
  flex-basis: 100%;
}
.kind {
  width: 110px;
}
.thumb {
  width: 34px;
  height: 34px;
  flex: none;
  border-radius: var(--el-border-radius-small);
  border: 1px solid var(--lab-border);
  cursor: zoom-in;
}
</style>
