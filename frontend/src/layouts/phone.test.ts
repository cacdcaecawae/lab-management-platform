import { afterEach, expect, it } from 'vitest'
import { h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import PageToolbar from '@/components/PageToolbar.vue'
import { labelTableCells, pageHeaders, phone, topBarOwner } from './phone'

afterEach(() => {
  phone.value = false
  pageHeaders.value = 0
  topBarOwner.value = null
  document.body.innerHTML = ''
})

it('names every table cell after its column and marks the empty ones', () => {
  document.body.innerHTML = `
    <div class="el-table">
      <div class="el-table__header-wrapper"><table><tr><th class="el-table__cell">编号</th><th class="el-table__cell">保管人</th><th class="el-table__cell">备注</th><th class="el-table__cell">图标</th></tr></table></div>
      <div class="el-table__body-wrapper"><table><tbody>
        <tr class="el-table__row"><td><a>UT-001</a></td><td>学生甲</td><td> </td><td><i class="el-icon"></i></td></tr>
      </tbody></table></div>
    </div>`
  labelTableCells(document)
  const cells = [...document.querySelectorAll('td')]
  expect(cells.map((c) => c.dataset.label)).toEqual(['编号', '保管人', '备注', '图标'])
  expect(cells.map((c) => c.hasAttribute('data-empty'))).toEqual([false, false, true, false])
  cells[2].textContent = '已校准' // the row was re-rendered with a value
  labelTableCells(document)
  expect(cells[2].hasAttribute('data-empty')).toBe(false)
})

it('on a phone the first toolbar of a list page moves its buttons to the top bar', async () => {
  document.body.innerHTML = '<div id="phone-actions"></div><div id="app"></div>'
  phone.value = true
  const toolbar = (label: string) =>
    h(PageToolbar, null, { default: () => h('input'), actions: () => h('button', label) })
  mount({ render: () => [toolbar('新建设备'), toolbar('导出')] }, { attachTo: '#app', global: { plugins: [ElementPlus] } })
  await nextTick()
  expect(document.querySelector('#phone-actions')!.textContent).toBe('新建设备')
  expect(document.querySelector('#app')!.textContent).toContain('导出') // a second toolbar keeps its own

  pageHeaders.value = 1 // a detail page: no top bar, the buttons stay in the card
  await nextTick()
  expect(document.querySelector('#phone-actions')!.textContent).toBe('')
})

it('folds the dropdown filters behind 筛选 on a phone, except single chips and non-foldable toolbars', async () => {
  document.body.innerHTML = '<div id="phone-actions"></div><div id="app"></div>'
  phone.value = true
  const wrapper = mount(PageToolbar, {
    slots: { default: () => [h('input'), h('div', { class: 'el-select' })] },
    global: { plugins: [ElementPlus] },
    attachTo: '#app',
  })
  await nextTick()
  const toggle = wrapper.find('button[aria-label="筛选"]')
  expect(toggle.exists()).toBe(true)
  expect(wrapper.classes()).toContain('filters-foldable')
  await toggle.trigger('click')
  expect(wrapper.classes()).toContain('filters-open')
  wrapper.unmount()

  // nothing but dropdowns: the toggle is the whole row, so it says 筛选 in words
  const only = mount(PageToolbar, { slots: { default: () => h('div', { class: 'el-select' }) }, global: { plugins: [ElementPlus] } })
  await nextTick()
  expect(only.find('.filters-toggle.lonely').text()).toBe('筛选')
  only.unmount()

  // a single checkbox chip (e.g. 仅未读) stays directly visible instead of hiding behind 筛选
  const chip = mount(PageToolbar, { slots: { default: () => h('label', { class: 'el-checkbox' }, '仅未读') }, global: { plugins: [ElementPlus] } })
  await nextTick()
  expect(chip.find('.filters-toggle').exists()).toBe(false)
  expect(chip.classes()).not.toContain('filters-foldable')
  chip.unmount()

  // foldable=false (e.g. 未交名单 week picker) keeps the control visible
  const noFold = mount(PageToolbar, {
    props: { foldable: false },
    slots: { default: () => [h('span', '周一日期'), h('div', { class: 'el-date-editor' })] },
    global: { plugins: [ElementPlus] },
  })
  await nextTick()
  expect(noFold.find('.filters-toggle').exists()).toBe(false)
  noFold.unmount()

  // actions-only toolbar collapses on phone once its buttons moved to the top bar
  const actionsOnly = mount(PageToolbar, {
    slots: { actions: () => h('button', '新建组会') },
    global: { plugins: [ElementPlus] },
    attachTo: '#app',
  })
  await nextTick()
  expect(actionsOnly.classes()).toContain('phone-empty')
  actionsOnly.unmount()
})
