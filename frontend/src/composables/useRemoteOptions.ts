import { ref, type Ref } from 'vue'
import type { Page } from '@/api/client'
import { mergeById } from '@/utils/format'
import { showError } from '@/utils/errors'

// Options for a <el-select filterable remote :remote-method="search">: the latest 20 at first, then the server's
// matches for what is typed (the select waits 300 ms itself). The select can reach every record, not only the first page.
// `immediate: false` waits for the first search() (a dialog that loads when it opens).
export function useRemoteOptions<T extends { id: number }>(fetchPage: (search: string) => Promise<Page<T>>, immediate = true) {
  const found = ref([]) as Ref<T[]>
  const loading = ref(false)
  const seen = new Map<number, T>() // what was picked from an earlier search keeps its label
  let latest = 0

  async function search(text = '') {
    const mine = ++latest
    loading.value = true
    try {
      const page = await fetchPage(text)
      if (mine !== latest) return
      for (const item of page.results) seen.set(item.id, item)
      found.value = page.results
    } catch (e) {
      if (mine === latest) showError(e)
    } finally {
      if (mine === latest) loading.value = false
    }
  }
  if (immediate) search()

  // The matches, plus the chosen ones they leave out: ids picked earlier, or the objects a record came with.
  const options = (chosen: (number | T | null | undefined)[]) =>
    mergeById(found.value, chosen.map((c) => (typeof c === 'number' ? seen.get(c) : c)))
  return { options, search, loading }
}
