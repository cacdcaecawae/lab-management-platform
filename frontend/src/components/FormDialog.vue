<script setup lang="ts">
import { ref } from 'vue'
import type { DialogInstance } from 'element-plus'
import { phone } from '@/layouts/phone'

// Every dialog with a form (DESIGN.md): three widths, labels on top, 取消 + the main button at the bottom right.
// #before / #after sit outside the form, so a read-only form does not grey them out; #extra goes bottom left.
const open = defineModel<boolean>({ required: true })
const props = withDefaults(
  defineProps<{
    title: string
    size?: 'sm' | 'md' | 'lg'
    confirmText?: string
    cancelText?: string
    loading?: boolean
    disabled?: boolean
    readonly?: boolean
  }>(),
  { size: 'md', confirmText: '保存', cancelText: undefined },
)
const emit = defineEmits<{ submit: [] }>()
const WIDTHS = { sm: 'min(460px, 95vw)', md: 'min(620px, 95vw)', lg: 'min(800px, 95vw)' }
const dialog = ref<DialogInstance>()

function submit() {
  if (!props.readonly && !props.disabled && !props.loading) emit('submit')
}
</script>

<template>
  <!-- phone: the whole screen, 取消 / 保存 stay at the bottom while the form scrolls (theme.css) -->
  <el-dialog ref="dialog" v-model="open" :title="title" :width="WIDTHS[size]" :fullscreen="phone">
    <slot name="before" />
    <el-form label-position="top" :disabled="readonly" @submit.prevent="submit">
      <slot />
    </el-form>
    <slot name="after" />
    <template #footer>
      <div class="form-dialog-footer">
        <slot name="extra" />
        <span class="grow" />
        <!-- handleClose goes through the dialog's before-close, like × and Esc -->
        <el-button @click="dialog?.handleClose()">{{ cancelText ?? (readonly ? '关闭' : '取消') }}</el-button>
        <el-button v-if="!readonly" type="primary" :loading="loading" :disabled="disabled" @click="submit">{{ confirmText }}</el-button>
        <slot name="actions" />
      </div>
    </template>
  </el-dialog>
</template>

<style>
.form-dialog-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.form-dialog-footer .el-button + .el-button {
  margin-left: 0;
}
</style>
