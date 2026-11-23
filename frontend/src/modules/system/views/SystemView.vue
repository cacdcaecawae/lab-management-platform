<script setup lang="ts">
import { computed } from 'vue'
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
ops.load()
</script>

<template>
  <el-card class="card">
    <SystemStorage v-if="page === 'system-storage'" v-model:info="ops.storage" />
    <SystemAccounts v-else-if="page === 'system-accounts'" />
    <SystemGroups v-else-if="page === 'system-groups'" />
    <SystemMail v-else-if="page === 'system-mail'" />
    <template v-else-if="page === 'system-version'">
      <SystemVersion v-if="ops.version" v-model:info="ops.version" />
    </template>
    <SystemLoginEvents v-else-if="page === 'system-logins'" />
  </el-card>
</template>
