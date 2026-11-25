import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { Me } from '@/api/types'
import { router } from './index'
import { postAuthTarget } from './post-auth'
import { ApiError, authRequired } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const me = vi.hoisted(() => vi.fn())
vi.mock('@/api/auth', () => ({ authApi: { me } }))

const ops: Me = {
  id: 1, username: 'ops', name: '', role: 'student', is_manager: false,
  is_approver: false,
  is_supervisor: false, is_superuser: true, group: null,
  email: '', phone: '', wechat: '', research_direction: '', must_change_password: true, avatar_url: null,
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

  it('takes the ops account to 存储与备份 once the password is changed', async () => {
    me.mockResolvedValue({ ...ops, must_change_password: false })
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('system-storage')
  })

  const student: Me = {
    ...ops, id: 2, username: 'student', is_superuser: false, group: { id: 1, name: '测试课题组' },
    must_change_password: false,
  }

  it.each(['/equipment/11', '/specimens/12'])('opens %s with a ready session', async (path) => {
    me.mockResolvedValue({ ...student })
    await router.push(path)
    expect(router.currentRoute.value.fullPath).toBe(path)
  })

  it('takes the old 原始数据 list to 实验与原始数据, filters kept', async () => {
    me.mockResolvedValue({ ...student })
    await router.push('/datasets?project=3')
    expect(router.currentRoute.value.fullPath).toBe('/experiments?project=3')
  })

  it('retains the original route through sign-in and the initial password guard', async () => {
    const target = '/specimens/42?tab=history#anchor'
    me.mockRejectedValue(new ApiError(403, { code: 'not_authenticated', message: '请登录' }))
    await router.push(target)
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe(target)
    const auth = useAuthStore()
    auth.user = { ...student, must_change_password: true }
    await router.replace(postAuthTarget(router, router.currentRoute.value.query.next)!)
    expect(router.currentRoute.value.name).toBe('password')
    expect(router.currentRoute.value.query.next).toBe(target)
    auth.user.must_change_password = false
    await router.replace(postAuthTarget(router, router.currentRoute.value.query.next)!)
    expect(router.currentRoute.value.fullPath).toBe(target)
  })

  it('retains the open equipment route when the API requests a password change', async () => {
    me.mockResolvedValue({ ...student })
    await router.push('/equipment/21')
    authRequired.handler?.('password_change_required')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('password'))
    expect(router.currentRoute.value.query.next).toBe('/equipment/21')
  })

  it('shows a signed-in user the home page, unless there is a page to go back to', async () => {
    me.mockResolvedValue({ ...student })
    await router.push('/login')
    expect(router.currentRoute.value.fullPath).toBe('/login')
    await router.push('/login?next=/equipment/3')
    expect(router.currentRoute.value.fullPath).toBe('/equipment/3')
  })

  it('admits only managers to the label preview, including after login', async () => {
    me.mockResolvedValue({ ...student })
    await router.push('/labels?type=equipment&ids=1')
    expect(router.currentRoute.value.name).toBe('workbench')
    const auth = useAuthStore()
    auth.user = { ...student, is_manager: true, is_supervisor: true }
    await router.push('/labels?type=equipment&ids=1')
    expect(router.currentRoute.value.name).toBe('labels')
  })

})


// '/': the workbench, where signing in goes anyway; the site's address opens the home page, not the sign-in sheet
it.each(['https://other.example/', '//other.example/', '/\\other.example/', '/login?next=/equipment/1', '/password', '/unknown', ['/equipment/1'], '/'])(
  'does not accept a non-app or auth route as return target: %s',
  (candidate) => expect(postAuthTarget(router, candidate)).toBeUndefined(),
)
