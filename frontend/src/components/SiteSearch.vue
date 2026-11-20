<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { searchSite, type SearchGroup } from '@/api/search'

const route = useRoute()
const open = ref(false)
const input = ref<HTMLInputElement>()
const query = ref('')
const groups = ref<SearchGroup[]>([])
const status = ref('')
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined

function reset() {
  clearTimeout(timer)
  ++generation
  groups.value = []
  status.value = ''
}

function close() {
  open.value = false
  reset()
  query.value = ''
}

async function launch() {
  open.value = true
  await nextTick()
  input.value?.focus()
}

async function search() {
  reset()
  const current = generation
  const q = query.value.trim()
  const length = Array.from(q).length
  if (length < 2 || length > 100) return
  status.value = '搜索中…'
  try {
    const result = await searchSite(q)
    if (current === generation) {
      groups.value = result
      status.value = result.length ? '' : '没有找到结果'
    }
  } catch {
    if (current === generation) status.value = '搜索失败，请重试'
  }
}

watch(query, () => {
  reset()
  if (open.value) timer = setTimeout(search, 300)
}, { flush: 'sync' })
watch(() => route.fullPath, close)

function shortcut(event: KeyboardEvent) {
  if (event.defaultPrevented || event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || event.isComposing
    || (event.target instanceof HTMLElement && event.target.closest('input,textarea,select,[contenteditable]'))) return
  event.preventDefault()
  void launch()
}
onMounted(() => window.addEventListener('keydown', shortcut))
onBeforeUnmount(() => {
  reset()
  window.removeEventListener('keydown', shortcut)
})
</script>

<template>
  <div class="site-search" @keydown.esc.stop="close">
    <el-button :icon="Search" text aria-label="全站搜索" :aria-expanded="open" @click="open ? close() : launch()" />
    <section v-if="open" class="search-panel" aria-label="全站搜索">
      <form role="search" @submit.prevent="search">
        <input ref="input" v-model="query" type="search" aria-label="搜索关键词" placeholder="输入 2 至 100 个字" />
      </form>
      <p v-if="status" role="status">{{ status }}</p>
      <div v-for="group in groups" :key="group.module">
        <h3>{{ group.label }}</h3>
        <ul>
          <li v-for="item in group.items" :key="item.id">
            <RouterLink :to="item.link" @click="close">{{ item.title }} <small v-if="item.subtitle">{{ item.subtitle }}</small></RouterLink>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
.site-search { margin-left: auto; position: relative; }
.search-panel {
  position: absolute; top: 100%; right: 0; width: min(380px, 90vw); max-height: 70vh; overflow: auto;
  box-sizing: border-box; padding: 12px; border: 1px solid var(--lab-border); border-radius: 8px;
  background: var(--el-bg-color); box-shadow: var(--el-box-shadow-light);
}
input { box-sizing: border-box; width: 100%; padding: 8px; }
h3 { font-size: 14px; margin: 12px 0 4px; }
ul { list-style: none; margin: 0; padding: 0; }
a { display: block; padding: 5px; overflow-wrap: anywhere; }
@media (max-width: 768px) {
  .search-panel { position: fixed; top: 52px; left: 0; right: 0; width: 100%; }
}
</style>
