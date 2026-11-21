import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage, ElMessageBox } from 'element-plus'
import MemberSignups from './MemberSignups.vue'
import { membersApi } from '@/modules/members/api'

vi.mock('@/modules/members/api', () => ({
  membersApi: { signup: vi.fn(), setSignup: vi.fn(), pending: vi.fn(), approve: vi.fn(), reject: vi.fn() },
}))
vi.mock('@/utils/errors', () => ({ showError: vi.fn() }))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

const stubs = {
  ElCard: { template: '<div><slot /></div>' },
  ElSwitch: { name: 'ElSwitch', props: ['modelValue'], emits: ['change'], template: '<i />' },
  ElInput: { props: ['modelValue'], template: '<input :value="modelValue" />', methods: { select() {} } },
  ElButton: { template: '<button><slot /></button>' },
  ElTable: { name: 'ElTable', emits: ['selection-change'], template: '<div />' },
  ElTableColumn: true,
}
const a = { id: 4, username: 's_x', name: '甲', email: '', date_joined: '2026-11-20T10:00:00+08:00' }
const b = { ...a, id: 5, username: 's_y', name: '乙' }

async function show(code: string, pending = [a, b]) {
  vi.mocked(membersApi.signup).mockResolvedValue({ code })
  vi.mocked(membersApi.pending).mockResolvedValue(pending)
  const wrapper = mount(MemberSignups, { global: { stubs } })
  await flushPromises()
  return wrapper
}
const button = (wrapper: Awaited<ReturnType<typeof show>>, text: string) =>
  wrapper.findAll('button').find((x) => x.text() === text)!

describe('MemberSignups', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
    vi.mocked(membersApi.approve).mockResolvedValue({ count: 2 })
    vi.mocked(membersApi.reject).mockResolvedValue({ count: 1 })
  })

  it('shows the link while registration is on, and nothing to review when nobody applied', async () => {
    const wrapper = await show('abc123def456', [])
    expect(wrapper.get('input').element.value).toBe(`${location.origin}/register?code=abc123def456`)
    expect(wrapper.text()).not.toContain('待审核')
    vi.mocked(membersApi.setSignup).mockResolvedValue({ code: '' })
    wrapper.findComponent({ name: 'ElSwitch' }).vm.$emit('change', false)
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce() // turning it off breaks links already sent
    expect(membersApi.setSignup).toHaveBeenCalledWith(false)
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('on a plain HTTP page says "copied" only when the fallback copy worked', async () => {
    // jsdom, like a plain HTTP page, has no navigator.clipboard.
    const execCommand = vi.fn(() => false)
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true })
    const wrapper = await show('abc123def456', [])
    await button(wrapper, '复制链接').trigger('click')
    await flushPromises()
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(ElMessage.warning).toHaveBeenCalledWith('浏览器不允许自动复制，链接已选中，请按 Ctrl+C 复制')
    expect(ElMessage.success).not.toHaveBeenCalled()
    execCommand.mockReturnValue(true)
    await button(wrapper, '复制链接').trigger('click')
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('已复制，发到课题组的群里')
  })

  it('approves the selected applications without asking and tells the page', async () => {
    const wrapper = await show('', [a, b])
    expect(wrapper.text()).toContain('待审核（2）')
    expect(button(wrapper, '通过').attributes('disabled')).toBeDefined()
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [b])
    await flushPromises()
    await button(wrapper, '通过').trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(membersApi.approve).toHaveBeenCalledWith([5])
    expect(wrapper.emitted('approved')).toHaveLength(1)
    expect(membersApi.pending).toHaveBeenCalledTimes(2)
  })

  it('asks before approving everyone or rejecting', async () => {
    const wrapper = await show('', [a, b])
    await button(wrapper, '全部通过').trigger('click')
    await flushPromises()
    expect(vi.mocked(ElMessageBox.confirm).mock.calls[0][0]).toContain('通过全部 2 个申请')
    expect(membersApi.approve).toHaveBeenCalledWith([4, 5])

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [a])
    await flushPromises()
    await button(wrapper, '拒绝').trigger('click')
    await flushPromises()
    expect(membersApi.reject).not.toHaveBeenCalled() // cancelled
    await button(wrapper, '拒绝').trigger('click')
    await flushPromises()
    expect(membersApi.reject).toHaveBeenCalledWith([4])
    expect(wrapper.emitted('approved')).toHaveLength(1) // only the approval
  })
})
