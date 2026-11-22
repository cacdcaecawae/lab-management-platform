<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, onUpdated, ref, useSlots, useTemplateRef } from 'vue'
import { Filter } from '@element-plus/icons-vue'
import { pageHeaders, phone, topBarOwner } from '@/layouts/phone'
import IconButton from './IconButton.vue'

// Top of a list page (DESIGN.md): filters wrap on the left, #actions stay together at the top right. Styles in theme.css.
// Phone ("手机"): the dropdown filters fold behind 筛选, and the page's first toolbar puts its #actions in the top bar.
const props = withDefaults(defineProps<{ foldable?: boolean }>(), { foldable: true })
const slots = useSlots()
const root = useTemplateRef<HTMLElement>('root')
const filters = useTemplateRef<HTMLElement>('filters')
const open = ref(false)
const hasFoldable = ref(false)
const lonely = ref(false) // nothing but folded filters: the 筛选 button is the whole row, so it gets its word
const empty = ref(false)
const me = Symbol('PageToolbar')
const toTopBar = computed(() => phone.value && topBarOwner.value === me && pageHeaders.value === 0)

const FOLDED = '.el-select, .el-checkbox, .el-date-editor'
function check() {
  const el = filters.value
  empty.value = !el?.children.length
  if (!props.foldable || !el) {
    hasFoldable.value = false
    lonely.value = false
    return
  }
  const folded = Array.from(el.querySelectorAll(`:scope > :is(${FOLDED})`))
  const hasOther = !!el.querySelector(`:scope > :not(${FOLDED})`)
  // A single chip by itself (e.g. 仅未读, 只看我的) takes the same room as 筛选, so keep it one tap away.
  const singleChip = !hasOther && folded.length === 1 && folded[0]!.classList.contains('el-checkbox')
  hasFoldable.value = folded.length > 0 && !singleChip
  lonely.value = hasFoldable.value && !hasOther
}
onMounted(() => {
  check()
  // not a toolbar inside a dialog or drawer, nor a second one further down the page
  if (slots.actions && !topBarOwner.value && !root.value?.closest('.el-dialog, .el-drawer')) topBarOwner.value = me
})
onUpdated(check)
onBeforeUnmount(() => {
  if (topBarOwner.value === me) topBarOwner.value = null
})
</script>

<template>
  <div ref="root" class="page-toolbar" :class="{ 'filters-open': open, 'filters-foldable': hasFoldable, 'phone-empty': toTopBar && empty }">
    <div ref="filters" class="page-toolbar-filters"><slot /></div>
    <el-button
      v-if="phone && lonely"
      class="filters-toggle lonely"
      :icon="Filter"
      text
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ open ? '收起筛选' : '筛选' }}
    </el-button>
    <IconButton
      v-else-if="phone && hasFoldable"
      class="filters-toggle"
      :icon="Filter"
      :label="open ? '收起筛选' : '筛选'"
      :aria-expanded="open"
      @click="open = !open"
    />
    <Teleport v-if="$slots.actions" to="#phone-actions" :disabled="!toTopBar" defer>
      <div class="page-toolbar-actions"><slot name="actions" /></div>
    </Teleport>
  </div>
</template>
