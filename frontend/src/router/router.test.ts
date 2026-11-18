import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { Me } from '@/api/types'
import { router } from './index'

const me = vi.hoisted(() => vi.fn())
vi.mock('@/api/auth', () => ({ authApi: { me } }))

const ops: Me = {
  id: 1, username: 'ops', name: '', role: 'student', is_supervisor: false, is_superuser: true, group: null,
  email: '', phone: '', research_direction: '', must_change_password: true,
}

// A detail URL typed or pasted must open its page: navigating by name does not check the :id pattern, a full load does.
it('resolves every detail URL by path', () => {
  const details = router.getRoutes().filter((r) => r.path.includes(':id'))
  expect(details.length).toBeGreaterThan(5)
  for (const r of details) {
    const path = r.path.replace(/:id\([^)]*\)/, '7')
    expect(router.resolve(path).name, path).toBe(r.name)
  }
})

describe('route guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia()) // a fresh auth store: the next navigation loads the user from the mock
  })

  it('takes a new ops account (no group, initial password) to the password page', async () => {
    me.mockResolvedValue(ops)
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('password')
  })

  it('takes the ops account to 系统管理 once the password is changed', async () => {
    me.mockResolvedValue({ ...ops, must_change_password: false })
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('system')
  })
})
