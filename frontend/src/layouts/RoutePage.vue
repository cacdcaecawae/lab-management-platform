<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { consumeSavedEditorReplacement } from '@/router/saved-editor'

const router = useRouter()
const instance = ref(0)
watch(router.currentRoute, (to, from) => {
  // Reselecting another record must reload setup data. Only the initiating
  // save can retain its editor instance across a create -> saved replacement.
  if (to.params.id !== from.params.id && !consumeSavedEditorReplacement(router, from, to)) instance.value++
}, { flush: 'sync' })
</script>

<template>
  <RouterView v-slot="{ Component }">
    <component :is="Component" :key="instance" />
  </RouterView>
</template>
