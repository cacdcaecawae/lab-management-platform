import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import type { Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { renamedMessage } from '@/utils/format'
import ProfileDialog from './ProfileDialog.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const me: Me = {
  id: 1, username: '2026017', name: '学生甲', role: 'student', is_supervisor: false, is_superuser: false,
  group: { id: 1, name: '超声组' }, email: '', phone: '', research_direction: '', must_change_password: false,
}

it('shows who you are and saves only your own contact details', async () => {
  const calls: { url: string; method?: string; body?: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
    const body = init.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, method: init.method, body })
    return Promise.resolve(new Response(JSON.stringify({ ...me, ...body }), { status: 200 }))
  }))
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.user = { ...me }
  const wrapper = mount(ProfileDialog, { props: { modelValue: true }, global: { plugins: [ElementPlus, pinia] }, attachTo: document.body })
  await flushPromises()
  const text = document.body.textContent!
  for (const shown of ['学生甲', '2026017', '学生', '超声组', '请联系课题组管理员']) expect(text).toContain(shown)

  const email = document.querySelector('.el-dialog input[type="email"]') as HTMLInputElement
  email.value = 'a@example.edu'
  email.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  ;(Array.from(document.querySelectorAll('.el-dialog button')).find((b) => b.textContent?.trim() === '保存') as HTMLButtonElement).click()
  await flushPromises()
  const patch = calls.find((c) => c.method === 'PATCH')!
  expect(patch.url).toBe('/api/auth/me/')
  expect(patch.body).toEqual({ email: 'a@example.edu', phone: '', research_direction: '' }) // nothing else is sent
  expect(auth.user?.email).toBe('a@example.edu') // the sidebar and the next open see the saved values
  wrapper.unmount()
})

it('spells out a changed login name after an account is saved', () => {
  expect(renamedMessage('s_a', 's_a')).toBe('已保存')
  expect(renamedMessage(undefined, 's_a')).toBe('已保存') // a new account
  expect(renamedMessage('s_a', '2026017')).toBe('已保存。学号 / 工号改成了 2026017，下次登录要用新的')
})
