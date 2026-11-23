<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download, TopRight } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'
import { formatSize } from '@/utils/format'
import {
  MAX_PDF_PREVIEW_BYTES,
  isDelimitedFile,
  parseDelimitedRows,
  previewKindOf,
  type PreviewKind,
} from '@/utils/preview'

export interface PreviewTarget {
  name: string
  url: string
  previewUrl?: string
  size?: number
}

const props = withDefaults(
  defineProps<{
    target: PreviewTarget | null
    maxPdfBytes?: number
  }>(),
  {
    maxPdfBytes: MAX_PDF_PREVIEW_BYTES,
  },
)
const open = defineModel<boolean>({ required: true })

const loading = ref(false)
const error = ref('')
const pdfTooLarge = ref(false)
const pdfTooLargeSize = ref<number | null>(null)
const blobUrl = ref<string | null>(null)
const textContent = ref('')
const truncated = ref(false)
const textView = ref<'table' | 'raw'>('table')
let seq = 0
let activeController: AbortController | null = null
let activeReader: ReadableStreamDefaultReader<Uint8Array> | null = null

const kind = computed<PreviewKind | null>(() => (props.target ? previewKindOf(props.target.name) : null))
const delimiter = computed(() => (props.target ? isDelimitedFile(props.target.name) : null))
const rawUrl = computed(() => {
  if (!props.target) return ''
  return props.target.previewUrl ? `${props.target.previewUrl}?raw=1` : props.target.url
})

const parsedTable = computed(() => {
  if (!delimiter.value || !textContent.value) return null
  const rows = parseDelimitedRows(textContent.value, delimiter.value)
  if (!rows.length) return null
  const maxCols = Math.min(20, Math.max(...rows.map((r) => r.length)))
  const headers = rows[0].slice(0, maxCols).map((h, i) => h.trim() || `列 ${i + 1}`)
  const data = rows.slice(1).map((r) => {
    const obj: Record<string, string> = {}
    for (let i = 0; i < maxCols; i++) obj[`c${i}`] = r[i] ?? ''
    return obj
  })
  return { headers, data }
})

function revokeBlob() {
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = null
  }
}

function cancelActive() {
  if (activeReader) {
    const r = activeReader
    activeReader = null
    void r.cancel().catch(() => {})
  }
  if (activeController) {
    activeController.abort()
    activeController = null
  }
}

function isAbortError(e: unknown, signal: AbortSignal): boolean {
  return signal.aborted || (e instanceof DOMException && e.name === 'AbortError')
}

async function readCappedStream(response: Response, signal: AbortSignal, maxBytes = 256 * 1024, maxLines = 200) {
  const reader = response.body?.getReader()
  if (!reader) {
    const full = await response.text()
    const lines = full.split(/\r?\n/)
    return { content: lines.slice(0, maxLines).join('\n'), truncated: lines.length > maxLines }
  }
  activeReader = reader
  const chunks: Uint8Array[] = []
  let total = 0
  let byteTruncated = false
  try {
    while (true) {
      if (signal.aborted) {
        await reader.cancel()
        return { content: '', truncated: false }
      }
      const { value, done } = await reader.read()
      if (done) break
      if (value) {
        if (total + value.byteLength > maxBytes) {
          chunks.push(value.subarray(0, maxBytes - total))
          byteTruncated = true
          await reader.cancel()
          break
        }
        chunks.push(value)
        total += value.byteLength
      }
    }
  } finally {
    if (activeReader === reader) activeReader = null
    reader.releaseLock()
  }
  const buf = new Uint8Array(chunks.reduce((s, c) => s + c.byteLength, 0))
  let offset = 0
  for (const c of chunks) {
    buf.set(c, offset)
    offset += c.byteLength
  }
  const text = new TextDecoder('utf-8', { fatal: false }).decode(buf)
  const lines = text.split(/\r?\n/)
  const clipped = byteTruncated && lines.length > 1 ? lines.slice(0, -1) : lines
  const lineTruncated = clipped.length > maxLines
  return { content: clipped.slice(0, maxLines).join('\n'), truncated: byteTruncated || lineTruncated }
}

async function readCappedPdf(response: Response, controller: AbortController, maxBytes: number): Promise<Blob | null> {
  const headerLen = Number(response.headers.get('content-length') ?? '')
  if (Number.isFinite(headerLen) && headerLen > maxBytes) {
    pdfTooLarge.value = true
    pdfTooLargeSize.value = headerLen
    void response.body?.cancel().catch(() => {})
    controller.abort()
    return null
  }
  const reader = response.body?.getReader()
  if (!reader) {
    const buf = await response.arrayBuffer()
    if (buf.byteLength > maxBytes) {
      pdfTooLarge.value = true
      pdfTooLargeSize.value = buf.byteLength
      return null
    }
    return new Blob([buf], { type: 'application/pdf' })
  }
  activeReader = reader
  const chunks: BlobPart[] = []
  let total = 0
  try {
    while (true) {
      if (controller.signal.aborted) {
        await reader.cancel()
        return null
      }
      const { value, done } = await reader.read()
      if (done) break
      if (value) {
        total += value.byteLength
        if (total > maxBytes) {
          pdfTooLarge.value = true
          pdfTooLargeSize.value = total
          chunks.length = 0
          await reader.cancel()
          controller.abort()
          return null
        }
        chunks.push(value)
      }
    }
  } finally {
    if (activeReader === reader) activeReader = null
    reader.releaseLock()
  }
  if (controller.signal.aborted) return null
  return new Blob(chunks, { type: 'application/pdf' })
}

async function loadPreview() {
  const mySeq = ++seq
  cancelActive()
  revokeBlob()
  error.value = ''
  pdfTooLarge.value = false
  pdfTooLargeSize.value = null
  textContent.value = ''
  truncated.value = false
  textView.value = delimiter.value ? 'table' : 'raw'
  const target = props.target
  if (!open.value || !target || !kind.value) {
    loading.value = false
    return
  }

  if (kind.value === 'image') {
    loading.value = false
    return // <el-image> loads directly with session cookies
  }

  if (kind.value === 'pdf' && target.size != null && target.size > props.maxPdfBytes) {
    pdfTooLarge.value = true
    pdfTooLargeSize.value = target.size
    loading.value = false
    return
  }

  const controller = new AbortController()
  activeController = controller
  loading.value = true
  try {
    if (kind.value === 'pdf') {
      const res = await fetch(rawUrl.value, { credentials: 'same-origin', signal: controller.signal })
      if (!res.ok) throw new Error(`加载失败（${res.status}）`)
      const blob = await readCappedPdf(res, controller, props.maxPdfBytes)
      if (mySeq !== seq) return
      if (!blob) {
        if (pdfTooLargeSize.value != null) pdfTooLarge.value = true
        return
      }
      blobUrl.value = URL.createObjectURL(blob)
      return
    }
    if (target.previewUrl) {
      const res = await fetch(target.previewUrl, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`加载失败（${res.status}）`)
      const data = (await res.json()) as { content?: string; truncated?: boolean }
      if (mySeq !== seq || controller.signal.aborted) return
      textContent.value = data.content ?? ''
      truncated.value = !!data.truncated
    } else {
      const res = await fetch(target.url, { credentials: 'same-origin', signal: controller.signal })
      if (!res.ok) throw new Error(`加载失败（${res.status}）`)
      const data = await readCappedStream(res, controller.signal)
      if (mySeq !== seq || controller.signal.aborted) return
      textContent.value = data.content
      truncated.value = data.truncated
    }
  } catch (e) {
    if (mySeq !== seq || isAbortError(e, controller.signal)) return
    error.value = e instanceof Error ? e.message : '预览加载失败'
  } finally {
    if (activeController === controller) activeController = null
    if (mySeq === seq) loading.value = false
  }
}

watch(
  [open, () => props.target],
  () => {
    if (open.value) {
      void loadPreview()
    } else {
      seq++
      cancelActive()
      revokeBlob()
      loading.value = false
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  seq++
  cancelActive()
  revokeBlob()
})
</script>

<template>
  <el-dialog v-model="open" width="min(920px, 95vw)" destroy-on-close class="preview-dialog">
    <template #header>
      <div class="head" v-if="target">
        <div class="title-wrap">
          <span class="title">{{ target.name }}</span>
          <span v-if="target.size != null" class="muted">{{ formatSize(target.size) }}</span>
        </div>
        <div class="head-actions">
          <el-radio-group v-if="kind === 'text' && parsedTable" v-model="textView" size="small" aria-label="文本视图">
            <el-radio-button value="table">表格</el-radio-button>
            <el-radio-button value="raw">原文</el-radio-button>
          </el-radio-group>
          <IconButton v-if="kind === 'image' || kind === 'pdf'" :icon="TopRight" label="新窗口打开" tag="a" :href="rawUrl" target="_blank" rel="noopener" />
          <IconButton :icon="Download" label="下载文件" tag="a" :href="target.url" :download="target.name" />
        </div>
      </div>
    </template>

    <div v-loading="loading" class="body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <template v-else-if="!target || !kind">
        <el-empty description="该文件类型暂不支持在线预览，请下载查看" />
      </template>
      <div v-else-if="kind === 'image'" class="image-wrap">
        <el-image :src="rawUrl" :preview-src-list="[rawUrl]" preview-teleported fit="contain" class="preview-img" :alt="target.name" />
      </div>
      <div v-else-if="kind === 'pdf' && pdfTooLarge" class="large-pdf">
        <el-empty
          :description="`PDF 超过弹窗预览上限（${formatSize(maxPdfBytes)}）${pdfTooLargeSize ? `，当前约 ${formatSize(pdfTooLargeSize)}` : ''}，请新窗口打开或下载查看`"
        >
          <div class="actions">
            <el-button tag="a" :href="rawUrl" target="_blank" rel="noopener">新窗口打开</el-button>
            <el-button type="primary" tag="a" :href="target.url" :download="target.name">下载文件</el-button>
          </div>
        </el-empty>
      </div>
      <div v-else-if="kind === 'pdf'" class="pdf-wrap">
        <iframe v-if="blobUrl" :src="blobUrl" :title="target.name" class="pdf-frame" />
      </div>
      <div v-else-if="kind === 'text'" class="text-wrap">
        <el-alert
          v-if="truncated"
          type="info"
          :closable="false"
          show-icon
          class="trunc-alert"
          title="文件较大，仅展示前 200 行（最多 256 KB），完整内容请点击右上角下载。"
        />
        <el-table v-if="textView === 'table' && parsedTable" :data="parsedTable.data" max-height="62vh" border size="small" empty-text="暂无内容">
          <el-table-column v-for="(h, idx) in parsedTable.headers" :key="idx" :label="h" min-width="120">
            <template #default="{ row }"><span class="csv-cell">{{ row[`c${idx}`] }}</span></template>
          </el-table-column>
        </el-table>
        <pre v-else class="code-box mono">{{ textContent }}</pre>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  padding-right: 28px;
}
.title-wrap {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.title {
  font-size: var(--el-font-size-medium);
  font-weight: 600;
  color: var(--lab-text);
  overflow-wrap: anywhere;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.body {
  min-height: 200px;
}
.image-wrap {
  display: flex;
  justify-content: center;
  background: var(--lab-bg-subtle);
  border-radius: var(--lab-radius);
  padding: 12px;
}
.preview-img {
  max-height: 70vh;
  max-width: 100%;
  cursor: zoom-in;
}
.pdf-wrap {
  height: 72vh;
}
.pdf-frame {
  width: 100%;
  height: 100%;
  border: 1px solid var(--lab-border);
  border-radius: var(--lab-radius);
  background: var(--lab-bg-subtle);
}
.large-pdf {
  padding: 24px 12px;
}
.trunc-alert {
  margin-bottom: 12px;
}
.csv-cell {
  white-space: pre-wrap;
  word-break: break-word;
}
.code-box {
  margin: 0;
  padding: 12px 14px;
  max-height: 62vh;
  overflow: auto;
  border: 1px solid var(--lab-border);
  border-radius: var(--lab-radius);
  background: var(--lab-bg-subtle);
  color: var(--lab-text);
  white-space: pre;
  line-height: 1.55;
}
.muted {
  color: var(--lab-text-3);
  font-size: var(--el-font-size-small);
}
</style>
