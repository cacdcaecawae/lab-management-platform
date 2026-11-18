<script setup lang="ts">
import { STATUS, type TagType } from '@/utils/format'

// map: for records whose status values mean something else, e.g. a reimbursement's "submitted" (已交财务)
withDefaults(defineProps<{ status: string; map?: Record<string, { label: string; type: TagType }> }>(), { map: () => STATUS })
</script>

<template>
  <el-tag class="status-tag" :type="map[status]?.type ?? 'info'" disable-transitions>{{ map[status]?.label ?? status }}</el-tag>
</template>
