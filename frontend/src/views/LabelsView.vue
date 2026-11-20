<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import QRCode from 'qrcode'
import { equipmentApi } from '@/modules/equipment/api'
import { specimensApi } from '@/modules/specimens/api'

const perSheet = 24
const maxLabels = perSheet * 4
const route = useRoute()
const router = useRouter()
const origin = window.location.origin
const kind = computed(() => route.query.type === 'equipment' || route.query.type === 'specimen' ? route.query.type : null)
const request = computed(() => {
  const input = route.query.ids
  // Bound both raw input and the number of network requests, even for a hand-edited URL.
  if (!kind.value || typeof input !== 'string' || input.length > maxLabels * 17) return null
  const parts = input.split(',')
  if (parts.length > maxLabels || parts.some((part) => !/^[1-9]\d{0,15}$/.test(part) || !Number.isSafeInteger(Number(part)))) return null
  return { kind: kind.value, ids: [...new Set(parts.map(Number))] }
})

interface Label { id: number; code: string; name: string; url: string; image: string }
const labels = ref<Label[]>([])
const failed = ref<number[]>([])
const loading = ref(false)
const attempts = ref(0)
const ready = computed(() => !loading.value && failed.value.length === 0 && labels.value.length > 0)
const sheets = computed(() => {
  const pages = []
  for (let i = 0; i < labels.value.length; i += perSheet) pages.push(labels.value.slice(i, i + perSheet))
  return pages
})

watch([request, attempts], async ([input], _previous, onCleanup) => {
  let obsolete = false
  onCleanup(() => { obsolete = true })
  labels.value = []
  failed.value = []
  loading.value = !!input
  if (!input) return
  const equipment = input.kind === 'equipment'
  const get = equipment ? equipmentApi.get : specimensApi.get
  const results: Label[] = []
  const errors: number[] = []
  for (let i = 0; i < input.ids.length; i += 6) {
    const batch = input.ids.slice(i, i + 6)
    const responses = await Promise.allSettled(batch.map(async (id): Promise<Label> => {
      const { code, name } = await get(id)
      if (obsolete) throw new Error('Superseded')
      const href = router.resolve({ name: equipment ? 'equipment-detail' : 'specimen-detail', params: { id } }).href
      const url = new URL(href, origin).href
      const image = await QRCode.toDataURL(url, { width: 256, margin: 4, errorCorrectionLevel: 'M' })
      return { id, code, name, url, image }
    }))
    if (obsolete) return
    responses.forEach((response, j) => {
      if (response.status === 'fulfilled') results.push(response.value)
      else errors.push(batch[j]!)
    })
  }
  labels.value = results
  failed.value = errors
  loading.value = false
}, { immediate: true })

function printLabels() {
  if (ready.value) window.print()
}
</script>

<template>
  <main class="label-print">
    <header class="label-toolbar">
      <router-link :to="{ name: kind === 'specimen' ? 'specimens' : 'equipment' }">返回{{ kind === 'specimen' ? '试样与标准件' : '设备台账' }}</router-link>
      <h1>打印二维码标签</h1>
      <p>二维码使用当前站点地址 <strong>{{ origin }}</strong>。请先在正式域名下小批试印，扫码确认后再批量打印；打印请选择 A4、实际大小，并关闭浏览器页眉页脚。建议使用覆膜标签纸。</p>
      <el-alert v-if="!request" title="标签参数无效。请从列表或详情打开，每次最多打印 96 项。" type="warning" :closable="false" />
      <el-alert v-else-if="failed.length" :title="`有 ${failed.length} 项未能生成标签（可能已删除、无权查看或加载失败）。请重试或重新选择。`" type="error" :closable="false" />
      <el-button v-if="failed.length" @click="attempts++">重试</el-button>
      <el-button type="primary" :loading="loading" :disabled="!ready" @click="printLabels">打印标签</el-button>
    </header>
    <div v-if="ready" class="label-pages">
      <section v-for="(sheet, index) in sheets" :key="index" class="label-sheet" :aria-label="`第 ${index + 1} 页`">
        <article v-for="label in sheet" :key="label.id" class="label">
          <img :src="label.image" :alt="`${label.code} 的二维码`" width="96" height="96" />
          <div class="label-text">
            <a :href="label.url">{{ label.code }}</a>
            <span>{{ label.name }}</span>
          </div>
        </article>
      </section>
    </div>
  </main>
</template>

<style scoped>
.label-print { margin: 0 auto; padding: 16px; max-width: 840px; }
.label-toolbar { margin-bottom: 20px; overflow-wrap: anywhere; }
.label-toolbar p { line-height: 1.6; }
.label-toolbar .el-alert { margin-bottom: 8px; }
.label-sheet {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 2mm;
  margin-bottom: 12px;
}
.label {
  display: flex;
  align-items: center;
  border: 1px dashed #888;
  padding: 2mm;
  min-width: 0;
  box-sizing: border-box;
}
.label img { display: block; flex: none; }
.label-text { display: grid; gap: 2px; min-width: 0; font-size: 14px; overflow-wrap: anywhere; }
.label-text a { font-weight: 600; }
@media screen and (max-width: 720px) {
  .label-sheet { grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); }
}
@page label-sheet { size: A4 portrait; margin: 9mm; }
@media print {
  .label-print { page: label-sheet; margin: 0; width: auto; max-width: none; padding: 0; color: #000; }
  .label-toolbar { display: none; }
  .label-sheet { grid-auto-rows: 32mm; margin: 0; }
  .label-sheet + .label-sheet { break-before: page; }
  .label { break-inside: avoid; overflow: hidden; padding: 1mm; gap: 1mm; }
  .label img { width: 27mm; height: 27mm; }
  .label-text { font-size: 9pt; }
  .label-text a { color: #000; text-decoration: none; }
  .label-text span { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
}
</style>
