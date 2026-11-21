<script setup lang="ts">
import { onMounted, onUpdated, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { setTabTitle } from '@/layouts/nav'

// Card header of a detail / edit page (DESIGN.md): back, title and #tags on the left, the page's buttons on the right.
const props = defineProps<{ back: RouteLocationRaw; title?: string }>()
const router = useRouter()
const route = useRoute()

// The shown title also names this record's tab in the top bar (after loading, and after a new record is saved).
const head = useTemplateRef<HTMLElement>('head')
const publish = () => setTabTitle(route.path, head.value?.querySelector('.el-page-header__content')?.textContent?.trim() ?? '')
onMounted(publish)
onUpdated(publish)
watch(() => route.path, publish, { flush: 'post' })
</script>

<template>
  <div ref="head" class="page-head">
    <el-page-header @back="router.push(props.back)">
      <template #content><slot name="title">{{ title }}</slot></template>
    </el-page-header>
    <slot name="tags" />
    <div v-if="$slots.default" class="page-head-actions"><slot /></div>
  </div>
</template>
