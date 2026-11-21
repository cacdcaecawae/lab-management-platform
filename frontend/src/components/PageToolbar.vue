<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, onUpdated, ref, useSlots, useTemplateRef } from 'vue'
import { Filter } from '@element-plus/icons-vue'
import { pageHeaders, phone, topBarOwner } from '@/layouts/phone'
import IconButton from './IconButton.vue'

// Top of a list page (DESIGN.md): filters wrap on the left, #actions stay together at the top right. Styles in theme.css.
// Phone ("手机"): the dropdown filters fold behind 筛选, and the page's first toolbar puts its #actions in the top bar.
const slots = useSlots()
const root = useTemplateRef<HTMLElement>('root')
const filters = useTemplateRef<HTMLElement>('filters')
const open = ref(false)
const foldable = ref(false)
const lonely = ref(false) // nothing but folded filters: the 筛选 button is the whole row, so it gets its word
const me = Symbol('PageToolbar')
const toTopBar = computed(() => phone.value && topBarOwner.value === me && pageHeaders.value === 0)

const FOLDED = '.el-select, .el-checkbox, .el-date-editor'
function check() {
  foldable.value = !!filters.value?.querySelector(`:scope > :is(${FOLDED})`)
  lonely.value = foldable.value && !filters.value?.querySelector(`:scope > :not(${FOLDED})`)
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
  <div ref="root" class="page-toolbar" :class="{ 'filters-open': open }">
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
      v-else-if="phone && foldable"
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
