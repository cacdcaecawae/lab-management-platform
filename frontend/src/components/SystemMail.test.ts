// The authorization code is write-only: the form never shows it, and a blank field must not overwrite the stored one.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import type { MailSettings } from '@/api/types'
import SystemMail from './SystemMail.vue'

const stored: MailSettings = {
  mail_enabled: true,
  mail_host: 'smtp.example.edu',
  mail_port: 465,
  mail_security: 'ssl',
  mail_username: 'lab@example.edu',
  mail_from: '',
  password_set: true,
  last_mail_error: '',
  last_mail_error_at: null,
}
const api = vi.hoisted(() => ({ mail: vi.fn(), saveMail: vi.fn(), testMail: vi.fn(), mailHistory: vi.fn() }))
vi.mock('@/api/system', () => ({ systemApi: api }))

async function mountForm() {
  api.mail.mockResolvedValue(stored)
  api.saveMail.mockImplementation(async () => stored)
  const wrapper = mount(SystemMail, { global: { plugins: [ElementPlus, createPinia()] } })
  await flushPromises()
  const save = async () => {
    await wrapper.find('form').trigger('submit')
    await flushPromises()
  }
  return { wrapper, save }
}

describe('SystemMail', () => {
  it('keeps the stored code when the field is left blank', async () => {
    const { wrapper, save } = await mountForm()
    expect((wrapper.find('input[type="password"]').element as HTMLInputElement).placeholder).toBe('已设置，留空不修改')
    await save()
    expect(api.saveMail).toHaveBeenLastCalledWith(expect.not.objectContaining({ mail_password: expect.anything() }))
  })

  it('sends a newly typed code', async () => {
    const { wrapper, save } = await mountForm()
    await wrapper.find('input[type="password"]').setValue('new-code')
    await save()
    expect(api.saveMail).toHaveBeenLastCalledWith(expect.objectContaining({ mail_password: 'new-code', mail_host: 'smtp.example.edu' }))
  })

  it('asks to save before sending a test mail with unsaved changes', async () => {
    const { wrapper } = await mountForm()
    await wrapper.find('input[placeholder="如 smtp.example.edu.cn"]').setValue('smtp2.example.edu')
    await wrapper.findAll('form')[1].trigger('submit')
    await flushPromises()
    expect(api.testMail).not.toHaveBeenCalled()
  })
})
