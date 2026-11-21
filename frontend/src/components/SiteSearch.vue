<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { searchSite, type SearchGroup } from '@/api/search'

const route = useRoute()
const root = ref<HTMLElement>()
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
  if (open.value && event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.defaultPrevented || event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || event.isComposing
    || (event.target instanceof HTMLElement && event.target.closest('input,textarea,select,[contenteditable]'))) return
  // The sidebar and the phone drawer each have a search box: only the one on screen answers.
  if (!root.value?.offsetParent) return
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
  <div ref="root" class="site-search" @keydown.esc.stop="close">
    <button type="button" class="search-trigger" aria-label="全站搜索" :aria-expanded="open" @click="open ? close() : launch()">
      <el-icon><Search /></el-icon>
      <span>搜索</span>
      <kbd>/</kbd>
    </button>
    <!-- Teleported to body so the sidebar's sticky stacking context (z-index: 20) never traps the mask under page overlays. -->
    <Teleport to="body">
      <div v-if="open" class="search-mask" @click.self="close" @keydown.esc.stop="close">
        <section class="search-panel" role="dialog" aria-label="全站搜索">
          <form role="search" class="search-box" @submit.prevent="search">
            <el-icon><Search /></el-icon>
            <input ref="input" v-model="query" type="search" aria-label="搜索关键词" placeholder="输入关键词，至少 2 个字" />
          </form>
          <div v-if="status || groups.length" class="search-results">
            <p v-if="status" role="status" class="search-status">{{ status }}</p>
            <div v-for="group in groups" :key="group.module">
              <h3>{{ group.label }}</h3>
              <ul>
                <li v-for="item in group.items" :key="item.id">
                  <RouterLink :to="item.link" @click="close">{{ item.title }} <small v-if="item.subtitle">{{ item.subtitle }}</small></RouterLink>
                </li>
              </ul>
            </div>
          </div>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.search-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 32px;
  padding: 0 6px 0 12px;
  border: 1px solid var(--lab-border);
  border-radius: 999px;
  background: var(--lab-bg-card);
  color: var(--lab-text-3);
  font: inherit;
  cursor: pointer;
}
.search-trigger:hover,
.search-trigger:focus-visible {
  border-color: var(--el-border-color);
  outline: none;
}
kbd {
  margin-left: auto;
  padding: 0 6px;
  border: 1px solid var(--lab-border);
  border-radius: 999px;
  font-family: var(--lab-mono);
  font-size: 13px;
  line-height: 18px;
}
.search-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 12vh 16px 0;
  background: rgba(0, 0, 0, 0.25);
}
.search-panel {
  display: flex;
  flex-direction: column;
  width: min(600px, 100%);
  max-height: 70vh;
  overflow: hidden;
  border-radius: 14px;
  background: var(--lab-bg-card);
  box-shadow: var(--el-box-shadow);
}
.search-box {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 52px;
  padding: 0 16px;
  color: var(--lab-text-3);
  font-size: 18px;
}
.search-box input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--lab-text);
  font: inherit;
  font-size: 16px;
}
.search-results {
  overflow: auto;
  padding: 4px 8px 12px;
  border-top: 1px solid var(--lab-border);
}
.search-status {
  margin: 12px 8px;
  color: var(--lab-text-3);
}
h3 {
  margin: 12px 8px 4px;
  color: var(--lab-text-3);
  font-size: 13px;
  font-weight: 600;
}
ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
a {
  display: block;
  padding: 8px;
  border-radius: var(--lab-radius);
  color: var(--lab-text);
  overflow-wrap: anywhere;
}
a:hover,
a:focus-visible {
  background: var(--lab-bg);
  text-decoration: none;
}
small {
  margin-left: 8px;
  color: var(--lab-text-3);
  font-size: 13px;
}
</style>
