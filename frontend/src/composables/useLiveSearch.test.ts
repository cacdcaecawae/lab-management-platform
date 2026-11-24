import { afterEach, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import { flushPromises } from '@vue/test-utils'
import type { Page } from '@/api/client'
import { useLiveSearch } from './useLiveSearch'
import { useRemoteOptions } from './useRemoteOptions'

afterEach(() => vi.useRealTimers())

it('applies the keyword once typing has stopped for 300 ms', async () => {
  vi.useFakeTimers()
  const filters = reactive({ search: '' })
  const scope = effectScope()
  const keyword = scope.run(() => useLiveSearch(filters))!
  keyword.value = '探'
  await nextTick()
  vi.advanceTimersByTime(200)
  keyword.value = '探头'
  await nextTick()
  vi.advanceTimersByTime(299)
  expect(filters.search).toBe('')
  vi.advanceTimersByTime(1)
  expect(filters.search).toBe('探头')
  keyword.value = ''
  await nextTick()
  scope.stop() // leaving the page drops the pending search
  vi.advanceTimersByTime(300)
  expect(filters.search).toBe('探头')
})

it('keeps the label of an option picked from an earlier search', async () => {
  const pages: Record<string, { id: number; name: string }[]> = { '': [{ id: 1, name: '近的' }], 老: [{ id: 99, name: '老的' }] }
  const fetch = vi.fn(async (search: string): Promise<Page<{ id: number; name: string }>> =>
    ({ count: 1, next: null, previous: null, results: pages[search] ?? [] }))
  const remote = useRemoteOptions(fetch)
  await flushPromises()
  await remote.search('老')
  await remote.search('')
  // 99 was picked while searching 老; 7 came with the record
  expect(remote.options([99, { id: 7, name: '记录里的' }]).map((o) => o.name)).toEqual(['近的', '老的', '记录里的'])
})
