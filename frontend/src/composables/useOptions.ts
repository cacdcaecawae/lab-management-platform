import { ref, type Ref } from 'vue'
import type { Page } from '@/api/client'
import { showError } from '@/utils/errors'

// Options for a <el-select>, loaded once.
// shortcut: callers ask for page_size=100, so only the first 100 items are offered; switch to remote search if lists grow past that.
export function useOptions<T>(fetchPage: () => Promise<Page<T>>): Ref<T[]> {
  const list = ref([]) as Ref<T[]>
  fetchPage().then((r) => (list.value = r.results), showError)
  return list
}
