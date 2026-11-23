<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import SystemAccounts from '@/modules/system/components/SystemAccounts.vue'
import SystemGroups from '@/modules/system/components/SystemGroups.vue'
import SystemMail from '@/modules/system/components/SystemMail.vue'
import SystemStorage from '@/modules/system/components/SystemStorage.vue'
import SystemVersion from '@/modules/system/components/SystemVersion.vue'
import SystemLoginEvents from '@/components/SystemLoginEvents.vue'
import { useOpsStore } from '@/stores/ops'

// Every 系统管理 page (modules/system/index.ts), one per sidebar item. The status and the version are the ones the
// sidebar marks, so these pages read and refresh them in the shared store.
const route = useRoute()
const page = computed(() => route.name)
const ops = useOpsStore()
// On every page: this view stays mounted while moving between them (RoutePage), and a check that failed is asked again.
watch(page, () => ops.load(), { immediate: true })
</script>

<template>
  <el-card class="card">
    <SystemStorage v-if="page === 'system-storage'" v-model:info="ops.storage" />
    <SystemAccounts v-else-if="page === 'system-accounts'" />
    <SystemGroups v-else-if="page === 'system-groups'" />
    <SystemMail v-else-if="page === 'system-mail'" />
    <SystemVersion v-else-if="page === 'system-version'" v-model:info="ops.version" />
    <SystemLoginEvents v-else-if="page === 'system-logins'" />
  </el-card>
</template>
