// Opened for another record, the drawer shows that record's history: not the previous one's while it loads, and not
// an answer for the previous one that arrives late.
import { expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import type { HistoryEntry } from '@/api/types'
import HistoryDrawer from './HistoryDrawer.vue'

const entry = (id: number, reason: string): HistoryEntry => ({
  id, date: '2026-11-20T10:00:00+08:00', type: 'changed', user: { id: 1, name: '管理员甲' }, reason, changes: [],
})

it('shows the record it was opened for, not an answer that came late', async () => {
  let answerA!: (list: HistoryEntry[]) => void
  const wrapper = mount(HistoryDrawer, {
    props: { modelValue: false, load: () => new Promise<HistoryEntry[]>((resolve) => (answerA = resolve)) },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await wrapper.setProps({ modelValue: true }) // record A, slow
  await wrapper.setProps({ modelValue: false })
  await wrapper.setProps({ load: () => Promise.resolve([entry(2, 'B 改了')]), modelValue: true }) // record B
  await flushPromises()
  answerA([entry(1, 'A 改了')])
  await flushPromises()
  expect(document.body.textContent).toContain('B 改了')
  expect(document.body.textContent).not.toContain('A 改了')
  wrapper.unmount()
})
