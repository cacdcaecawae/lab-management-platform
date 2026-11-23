import { expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { opsStatusApi, type StorageInfo } from '@/api/opsStatus'
import type { Me, VersionInfo } from '@/api/types'
import { useAuthStore } from './auth'
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

it('forgets the last account once another one is signed in', async () => {
  setActivePinia(createPinia())
  vi.mocked(opsStatusApi.storage).mockClear().mockResolvedValue({ attention: true } as StorageInfo)
  vi.mocked(opsStatusApi.version).mockClear().mockResolvedValue({ current: 'v0.1.7', update_available: true } as VersionInfo)
  const auth = useAuthStore()
  auth.user = { id: 9 } as Me
  const ops = useOpsStore()
  ops.load()
  await flushPromises()
  expect(ops.storage?.attention).toBe(true)
  auth.user = null // 退出登录
  await flushPromises()
  expect([ops.storage, ops.version]).toEqual([null, null])
  auth.user = { id: 9 } as Me // signed in again in the same tab: asked afresh
  ops.load()
  await flushPromises()
  expect(opsStatusApi.storage).toHaveBeenCalledTimes(2)
  expect(ops.version?.update_available).toBe(true)
})
