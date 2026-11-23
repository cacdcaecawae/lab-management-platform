import { expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { opsStatusApi, type StorageInfo } from '@/api/opsStatus'
import type { VersionInfo } from '@/api/types'
import { useOpsStore } from './ops'

vi.mock('@/api/opsStatus', () => ({ opsStatusApi: { storage: vi.fn(), version: vi.fn() } }))
vi.mock('@/utils/errors', () => ({ showError: vi.fn() }))

it('asks once at a time, and again after a failure', async () => {
  setActivePinia(createPinia())
  const version = { current: 'v0.1.6', update_available: false } as VersionInfo
  vi.mocked(opsStatusApi.storage).mockResolvedValue({ attention: false } as StorageInfo)
  vi.mocked(opsStatusApi.version).mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValue(version)
  const ops = useOpsStore()
  ops.load() // the sidebar at sign-in
  ops.load() // and the 系统管理 page, before either answered
  await flushPromises()
  expect(opsStatusApi.version).toHaveBeenCalledTimes(1)
  expect(ops.version).toBeNull()
  ops.load() // another 系统管理 page opened
  await flushPromises()
  expect(opsStatusApi.version).toHaveBeenCalledTimes(2)
  expect(ops.version).toEqual(version)
})
