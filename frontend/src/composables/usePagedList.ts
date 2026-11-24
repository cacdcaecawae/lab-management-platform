import { ref, watch, type Ref } from 'vue'
import type { Page } from '@/api/client'
import type { ListQuery } from '@/api/types'
import { showError } from '@/utils/errors'

// Paginated table state. `filters` is a reactive object; changing it goes back to page 1.
export function usePagedList<T>(fetchPage: (q: ListQuery) => Promise<Page<T>>, filters: ListQuery, pageSize = 20) {
  const items = ref([]) as Ref<T[]>
  const count = ref(0)
  const page = ref(1)
  const loading = ref(false)
  let latest = 0 // only the newest request may fill the table: answers can arrive out of order

  async function load() {
    const mine = ++latest
    loading.value = true
    try {
      const res = await fetchPage({ ...filters, page: page.value, page_size: pageSize })
      if (mine !== latest) return
      items.value = res.results
      count.value = res.count
    } catch (e) {
      if (mine === latest) showError(e)
    } finally {
      if (mine === latest) loading.value = false
    }
  }

  watch(
    () => ({ ...filters }),
    () => (page.value === 1 ? load() : (page.value = 1)),
  )
  watch(page, load)
  load()
  // <el-table @sort-change="sort">: a column's `prop` is the server's ordering name; sorted on the server, so pages agree.
  const sort = ({ prop, order }: { prop: string | null; order: 'ascending' | 'descending' | null }) => {
    filters.ordering = prop && order ? `${order === 'descending' ? '-' : ''}${prop}` : undefined
  }
  return { items, count, page, pageSize, loading, load, sort }
}
