import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import LoginView from './LoginView.vue'
import { ApiError } from '@/api/client'

const login = vi.hoisted(() => vi.fn())
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ login }) }))
vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} })
// jsdom has no modal dialogs
Object.assign(HTMLDialogElement.prototype, {
  showModal(this: HTMLDialogElement) { this.setAttribute('open', '') },
  close(this: HTMLDialogElement) { this.removeAttribute('open') },
})

async function show(path: string) {
  const page = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: page },
      { path: '/', name: 'workbench', component: page },
      { path: '/datasets', name: 'datasets', component: page },
    ],
  })
  await router.push(path)
  const wrapper = mount(LoginView, { global: { plugins: [router], stubs: { GlassRing: true } } })
  await flushPromises()
  return { wrapper, router, open: () => wrapper.get('dialog').attributes('open') !== undefined }
}

async function signIn(wrapper: Awaited<ReturnType<typeof show>>['wrapper']) {
  await wrapper.get('#login-user').setValue('s_a')
  await wrapper.get('#login-pass').setValue('Verify-2026!')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('LoginView (the home page)', () => {
  beforeEach(() => login.mockReset())

  it('shows the home page; 登录 opens the sign-in sheet', async () => {
    const { wrapper, open } = await show('/login')
    expect(wrapper.get('h1').text()).toBe('Phase')
    expect(open()).toBe(false)
    await wrapper.get('main button').trigger('click')
    expect(open()).toBe(true)
  })

  it('stays on the home page for someone who only typed the address', async () => {
    const { open } = await show('/login?next=/') // where the guard sends the site's root
    expect(open()).toBe(false)
  })

  it('sent from a page, opens the sheet straight away and goes back there', async () => {
    login.mockResolvedValue(undefined)
    const { wrapper, router, open } = await show('/login?next=/datasets')
    expect(open()).toBe(true)
    await signIn(wrapper)
    expect(login).toHaveBeenCalledWith('s_a', 'Verify-2026!')
    expect(router.currentRoute.value.fullPath).toBe('/datasets')
  })

  it('goes to the workbench, or says why it could not sign in', async () => {
    login.mockRejectedValueOnce(new ApiError(400, { code: 'invalid_credentials', message: '用户名或密码错误' }))
    const { wrapper, router } = await show('/login')
    await wrapper.get('main button').trigger('click')
    await signIn(wrapper)
    expect(wrapper.get('dialog [role=alert]').text()).toBe('用户名或密码错误')
    expect(router.currentRoute.value.name).toBe('login')
    login.mockResolvedValue(undefined)
    await signIn(wrapper)
    expect(router.currentRoute.value.name).toBe('workbench')
  })
})
