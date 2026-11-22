import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import type { Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { renamedMessage } from '@/utils/format'
import ProfileDialog from './ProfileDialog.vue'

// jsdom has no canvas: the crop itself is checked in the browser (verify-lab login.md, `avatar`).
vi.mock('@/utils/image', () => ({ squareJpeg: async () => new Blob(['jpeg'], { type: 'image/jpeg' }) }))

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const me: Me = {
  id: 1, username: '2026017', name: '学生甲', role: 'student', is_supervisor: false, is_superuser: false,
  group: { id: 1, name: '超声组' }, email: '', phone: '', wechat: '', research_direction: '', must_change_password: false,
  avatar_url: null,
}

function setup() {
  const calls: { url: string; method?: string; body?: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
    const body = init.body instanceof FormData ? init.body : init.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, method: init.method, body })
    const after = body instanceof FormData ? { ...me, avatar_url: '/api/auth/me/avatar/?v=abc' } : { ...me, ...body }
    return Promise.resolve(new Response(JSON.stringify(after), { status: 200 }))
  }))
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.user = { ...me }
  // mounted where SideNav lives on a phone: inside the menu drawer, which closes as the dialog opens
  const drawer = document.body.appendChild(Object.assign(document.createElement('div'), { className: 'nav-drawer' }))
  const wrapper = mount(ProfileDialog, { props: { modelValue: true }, global: { plugins: [ElementPlus, pinia] }, attachTo: drawer })
  return { calls, auth, wrapper }
}

it('shows who you are and saves only your own contact details', async () => {
  const { calls, auth, wrapper } = setup()
  await flushPromises()
  // the dialog sits under <body>, not in the drawer that hides itself
  expect(document.querySelector('.nav-drawer .el-dialog')).toBeNull()
  expect(document.querySelector('.el-dialog')).not.toBeNull()
  const text = document.body.textContent!
  for (const shown of ['学生甲', '2026017', '学生 · 超声组']) expect(text).toContain(shown)
  expect(text).not.toContain('学号 / 工号') // the login name is a tag, without a label

  const email = document.querySelector('.el-dialog input[type="email"]') as HTMLInputElement
  email.value = 'a@example.edu'
  email.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  ;(Array.from(document.querySelectorAll('.el-dialog button')).find((b) => b.textContent?.trim() === '保存') as HTMLButtonElement).click()
  await flushPromises()
  const patch = calls.find((c) => c.method === 'PATCH')!
  expect(patch.url).toBe('/api/auth/me/')
  expect(patch.body).toEqual({ email: 'a@example.edu', phone: '', wechat: '', research_direction: '' }) // nothing else is sent
  expect(auth.user?.email).toBe('a@example.edu') // the sidebar and the next open see the saved values
  wrapper.unmount()
})

it('changes the picture from the picture itself, without 保存', async () => {
  const { calls, auth, wrapper } = setup()
  await flushPromises()
  const input = document.querySelector('.el-dialog input[type="file"]') as HTMLInputElement
  const opened = vi.spyOn(input, 'click').mockImplementation(() => {})
  ;(document.querySelector('.el-dialog button[aria-label="更换头像"]') as HTMLButtonElement).click()
  expect(opened).toHaveBeenCalledOnce()

  Object.defineProperty(input, 'files', { value: [new File(['png'], 'me.png', { type: 'image/png' })] })
  input.dispatchEvent(new Event('change'))
  await flushPromises()
  const post = calls.find((c) => c.method === 'POST')!
  expect(post.url).toBe('/api/auth/me/avatar/')
  expect((post.body as FormData).get('file')).toBeInstanceOf(Blob)
  expect(auth.user?.avatar_url).toBe('/api/auth/me/avatar/?v=abc') // sidebar, menu and dialog show it right away
  expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
  wrapper.unmount()
})

it('a picture changed while the details are saving stays', async () => {
  // The details' answer was put together before the picture changed and arrives after it.
  const { auth, wrapper } = setup()
  let answerDetails = () => {}
  vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => {
    if (init.body instanceof FormData) return Promise.resolve(new Response(JSON.stringify({ ...me, avatar_url: '/api/auth/me/avatar/?v=new' })))
    const body = JSON.parse(init.body as string)
    return new Promise((resolve) => (answerDetails = () => resolve(new Response(JSON.stringify({ ...me, ...body })))))
  }))
  await flushPromises()
  const phone = document.querySelector('.el-dialog input[autocomplete="tel"], .el-dialog input[type="tel"]') as HTMLInputElement
  phone.value = '13800000000'
  phone.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  ;(Array.from(document.querySelectorAll('.el-dialog button')).find((b) => b.textContent?.trim() === '保存') as HTMLButtonElement).click()
  const input = document.querySelector('.el-dialog input[type="file"]') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [new File(['png'], 'me.png', { type: 'image/png' })] })
  input.dispatchEvent(new Event('change'))
  await flushPromises()
  expect(auth.user?.avatar_url).toBe('/api/auth/me/avatar/?v=new')
  answerDetails()
  await flushPromises()
  expect(auth.user?.phone).toBe('13800000000')
  expect(auth.user?.avatar_url).toBe('/api/auth/me/avatar/?v=new')
  wrapper.unmount()
})

it('spells out a changed login name after an account is saved', () => {
  expect(renamedMessage('s_a', 's_a')).toBe('已保存')
  expect(renamedMessage(undefined, 's_a')).toBe('已保存') // a new account
  expect(renamedMessage('s_a', '2026017')).toBe('已保存。学号 / 工号改成了 2026017，下次登录要用新的')
})
