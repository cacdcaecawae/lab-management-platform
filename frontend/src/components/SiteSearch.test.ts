import { expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import SiteSearch from './SiteSearch.vue'
import type { SearchGroup } from '@/api/search'

const lookup = vi.hoisted(() => vi.fn())
vi.mock('@/api/search', () => ({ searchSite: lookup }))
const push = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRoute: () => ({ fullPath: '/' }), useRouter: () => ({ push }) }))

it('debounces and drops earlier results as soon as the query changes', async () => {
  vi.useFakeTimers()
  let old!: (value: SearchGroup[]) => void
  lookup.mockImplementationOnce(() => new Promise(resolve => { old = resolve }))
  lookup.mockResolvedValueOnce([{ module: 'new', label: '新结果', items: [{ id: 7, title: '新试件', subtitle: '', link: '/specimens/7' }] }])
  const wrapper = mount(SiteSearch, { global: { plugins: [ElementPlus], stubs: { RouterLink: true, teleport: true } } })
  try {
    await wrapper.get('button').trigger('click')
    await wrapper.get('input').setValue('旧查询')
    await vi.advanceTimersByTimeAsync(299)
    expect(lookup).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(lookup).toHaveBeenCalledWith('旧查询')
    await wrapper.get('input').setValue('新查询')
    old([{ module: 'old', label: '旧结果', items: [] }])
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧结果')
    await vi.advanceTimersByTimeAsync(300)
    expect(wrapper.text()).toContain('新结果')
    expect(wrapper.get('router-link-stub').attributes('to')).toBe('/specimens/7')
  } finally {
    wrapper.unmount()
    vi.useRealTimers()
  }
})

it('teleports the search overlay to body and closes on Escape', async () => {
  const wrapper = mount(SiteSearch, { global: { plugins: [ElementPlus], stubs: { RouterLink: true } }, attachTo: document.body })
  try {
    await wrapper.get('button').trigger('click')
    expect(document.body.querySelector(':scope > .search-mask')).not.toBeNull()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(document.body.querySelector(':scope > .search-mask')).toBeNull()
  } finally {
    wrapper.unmount()
  }
})

it('moves through the results with the arrow keys and opens one with Enter', async () => {
  vi.useFakeTimers()
  lookup.mockResolvedValueOnce([
    { module: 'reports', label: '周报', items: [{ id: 1, title: '2026-11-16', subtitle: '学生甲', link: '/reports/1' }] },
    { module: 'actions', label: '行动项', items: [{ id: 2, title: '补实验', subtitle: '学生甲', link: '/meetings/5' }] },
  ])
  const wrapper = mount(SiteSearch, { global: { plugins: [ElementPlus], stubs: { RouterLink: true, teleport: true } } })
  try {
    await wrapper.get('button').trigger('click')
    const input = () => wrapper.get('input') // the teleport stub renders the panel anew
    await input().setValue('学生甲')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    await input().trigger('keydown', { key: 'ArrowDown' })
    await input().trigger('keydown', { key: 'ArrowDown' })
    expect(input().attributes('aria-activedescendant')).toBe('search-actions-2')
    expect(wrapper.get('#search-actions-2').attributes('aria-selected')).toBe('true')
    await wrapper.get('form').trigger('submit')
    expect(push).toHaveBeenCalledWith('/meetings/5')
  } finally {
    wrapper.unmount()
    vi.useRealTimers()
  }
})
