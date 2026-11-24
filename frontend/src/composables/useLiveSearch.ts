import { onScopeDispose, ref, watch } from 'vue'

// A list's search box: the keyword applies 300 ms after typing stops; Enter (@change) applies it at once.
// Element Plus's input leaves the model alone while an input method is composing, so half-typed pinyin is not searched.
export function useLiveSearch(filters: { search?: string }) {
  const keyword = ref(filters.search ?? '')
  let timer: ReturnType<typeof setTimeout> | undefined
  watch(keyword, (text) => {
    clearTimeout(timer)
    timer = setTimeout(() => (filters.search = text), 300)
  })
  onScopeDispose(() => clearTimeout(timer))
  return keyword
}
