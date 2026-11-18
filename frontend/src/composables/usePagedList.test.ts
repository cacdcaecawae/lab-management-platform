import { describe, expect, it, vi } from 'vitest'
import { nextTick, reactive } from 'vue'
import { flushPromises } from '@vue/test-utils'
import type { Page } from '@/api/client'
import { usePagedList } from './usePagedList'

describe('usePagedList', () => {
  it('shows the answer to the latest request even when an older one arrives later', async () => {
    const answers: ((page: Page<string>) => void)[] = []
    const fetchPage = vi.fn(() => new Promise<Page<string>>((resolve) => answers.push(resolve)))
    const filters = reactive({ status: 'draft' })
    const list = usePagedList(fetchPage, filters)
    filters.status = 'approved' // the user changes the filter before the first page arrives
    await nextTick()
    expect(fetchPage).toHaveBeenCalledTimes(2)

    answers[1]!({ count: 1, next: null, previous: null, results: ['approved'] })
    await flushPromises()
    answers[0]!({ count: 5, next: null, previous: null, results: ['draft'] })
    await flushPromises()
    expect(list.items.value).toEqual(['approved'])
    expect(list.count.value).toBe(1)
    expect(list.loading.value).toBe(false)
  })
})
