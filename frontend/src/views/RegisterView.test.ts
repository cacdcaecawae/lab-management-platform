import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ElementPlus from 'element-plus'
import RegisterView from './RegisterView.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'

const query: { code?: string } = {}
vi.mock('vue-router', () => ({ useRoute: () => ({ query }) }))
vi.mock('@/api/auth', () => ({ authApi: { csrf: vi.fn(), register: vi.fn() } }))

function show(code?: string) {
  query.code = code
  return mount(RegisterView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
}

async function fill(wrapper: ReturnType<typeof show>, password = 'Signup-2026!', confirm = password) {
  const inputs = wrapper.findAll('input')
  for (const [i, value] of ['2026001', '新同学', 'new@example.edu', password, confirm].entries()) await inputs[i].setValue(value)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('RegisterView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('without a link explains where registration starts', () => {
    const wrapper = show()
    expect(wrapper.text()).toContain('注册要用课题组管理员发的注册链接打开')
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('sends the form with the code from the link and says it waits for approval', async () => {
    vi.mocked(authApi.register).mockResolvedValue(undefined)
    const wrapper = show('abc123def456')
    await fill(wrapper)
    expect(authApi.csrf).toHaveBeenCalled()
    expect(authApi.register).toHaveBeenCalledWith({
      code: 'abc123def456', username: '2026001', name: '新同学', email: 'new@example.edu', password: 'Signup-2026!',
    })
    expect(wrapper.text()).toContain('已提交，等待课题组管理员审核')
  })

  it('checks the repeated password and shows what the server rejected', async () => {
    const wrapper = show('abc123def456')
    await fill(wrapper, 'Signup-2026!', 'other')
    expect(wrapper.text()).toContain('两次输入的密码不一致')
    expect(authApi.register).not.toHaveBeenCalled()
    vi.mocked(authApi.register).mockRejectedValue(
      new ApiError(400, { code: 'validation_error', message: '提交的数据有误', errors: { code: ['注册链接已失效，请向课题组管理员要新的链接'] } }),
    )
    await fill(wrapper)
    expect(wrapper.text()).toContain('注册链接已失效')
    expect(wrapper.text()).not.toContain('已提交')
  })
})
