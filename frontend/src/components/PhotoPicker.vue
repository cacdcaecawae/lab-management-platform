<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Camera } from '@element-plus/icons-vue'
import { preparePhoto } from '@/utils/image'
import { formatSize } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    modelValue: File | null
    hint?: string
    disabled?: boolean
  }>(),
  {
    hint: '可选，拍一张放回位置方便下一个人找（自动压缩）',
    disabled: false,
  },
)
const emit = defineEmits<{ 'update:modelValue': [file: File | null] }>()

const input = ref<HTMLInputElement>()
const previewUrl = ref<string | null>(null)
const busy = ref(false)

function revokePreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
}

watch(
  () => props.modelValue,
  (file) => {
    revokePreview()
    if (file && typeof URL.createObjectURL === 'function') {
      previewUrl.value = URL.createObjectURL(file)
    }
    if (!file && input.value) {
      input.value.value = ''
    }
  },
  { immediate: true },
)

onBeforeUnmount(revokePreview)

async function acceptFile(raw: File) {
  busy.value = true
  try {
    const ready = await preparePhoto(raw)
    emit('update:modelValue', ready)
  } catch {
    ElMessage.error('无法读取这张图片，请使用 JPG、PNG 或 WebP 格式')
  } finally {
    busy.value = false
  }
}

async function onChange(e: Event) {
  const el = e.target as HTMLInputElement
  const raw = el.files?.[0]
  el.value = ''
  if (!raw) return
  await acceptFile(raw)
}

async function onPaste(e: ClipboardEvent) {
  if (props.disabled) return
  const item = Array.from(e.clipboardData?.items ?? []).find((it) => it.type.startsWith('image/'))
  const file = item?.getAsFile()
  if (!file) return
  e.preventDefault()
  await acceptFile(file)
}

function clear() {
  emit('update:modelValue', null)
}
</script>

<template>
  <div class="photo-picker" tabindex="0" @paste="onPaste">
    <div v-if="modelValue" class="picked">
      <img v-if="previewUrl" :src="previewUrl" :alt="modelValue.name" class="thumb" />
      <div class="info">
        <div class="name">{{ modelValue.name }}</div>
        <div class="muted">{{ formatSize(modelValue.size) }}</div>
        <div class="ops">
          <el-button link type="primary" :disabled="disabled || busy" @click="input?.click()">重新选择</el-button>
          <el-button link type="danger" :disabled="disabled || busy" @click="clear">移除</el-button>
        </div>
      </div>
    </div>
    <div v-else class="empty-row">
      <el-button :icon="Camera" :loading="busy" :disabled="disabled" @click="input?.click()">拍照 / 选图</el-button>
      <span class="muted">{{ hint }}</span>
    </div>
    <input ref="input" type="file" accept="image/jpeg,image/png,image/webp,image/*" hidden @change="onChange" />
  </div>
</template>

<style scoped>
.photo-picker {
  width: 100%;
  outline: none;
}
.empty-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}
.picked {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid var(--lab-border);
  border-radius: var(--lab-radius);
  background: var(--lab-bg-subtle);
}
.thumb {
  width: 72px;
  height: 72px;
  flex: none;
  border-radius: var(--el-border-radius-small);
  object-fit: cover;
  border: 1px solid var(--lab-border);
}
.info {
  min-width: 0;
  flex: 1;
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--lab-text);
}
.ops {
  display: flex;
  gap: 12px;
  margin-top: 2px;
}
.muted {
  color: var(--lab-text-3);
  font-size: var(--el-font-size-small);
}
</style>
