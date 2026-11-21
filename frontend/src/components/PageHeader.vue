<script setup lang="ts">
import { useRouter, type RouteLocationRaw } from 'vue-router'

// Card header of a detail / edit page (DESIGN.md): back, title and #tags on the left, the page's buttons on the right.
const props = defineProps<{ back: RouteLocationRaw; title?: string }>()
const router = useRouter()
</script>

<template>
  <div class="page-head">
    <el-page-header @back="router.push(props.back)">
      <template #content><slot name="title">{{ title }}</slot></template>
    </el-page-header>
    <slot name="tags" />
    <div v-if="$slots.default" class="page-head-actions"><slot /></div>
  </div>
</template>
