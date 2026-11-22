<script setup lang="ts">
import type { Component } from 'vue'

// A tool action (DESIGN.md): copy, regenerate, history, print, export, statistics, edit, re-check. Only an icon;
// its name shows in a tooltip and is read out by screen readers. Decisions (保存、提交、通过、删除、新建、发送)
// keep their words. Other attributes (v-if, @click, :loading, :disabled, tag / href) go to the button.
defineOptions({ inheritAttrs: false })
defineProps<{ icon: Component; label: string }>()
</script>

<template>
  <el-tooltip :content="label" placement="bottom" :show-after="300">
    <!-- the span takes the hover, so a disabled button still says what it does -->
    <span class="icon-button"><el-button v-bind="$attrs" class="icon-only" :icon="icon" :aria-label="label" text circle /></span>
  </el-tooltip>
</template>

<style scoped>
.icon-button {
  display: inline-flex;
}
</style>
