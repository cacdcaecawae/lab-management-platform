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
      <div class="el-table__header-wrapper"><table><tr><th>编号</th><th>保管人</th><th>备注</th></tr></table></div>
      <div class="el-table__body-wrapper"><table><tbody>
        <tr class="el-table__row"><td><a>UT-001</a></td><td>学生甲</td><td> </td></tr>
      </tbody></table></div>
    </div>`
  labelTableCells(document)
  const cells = [...document.querySelectorAll('td')]
  expect(cells.map((c) => c.dataset.label)).toEqual(['编号', '保管人', '备注'])
  expect(cells.map((c) => c.hasAttribute('data-empty'))).toEqual([false, false, true])
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

it('folds the dropdown filters behind 筛选 on a phone', async () => {
  phone.value = true
  const wrapper = mount(PageToolbar, {
    slots: { default: () => [h('input'), h('div', { class: 'el-select' })] },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await nextTick()
  const toggle = wrapper.find('button[aria-label="筛选"]')
  expect(toggle.exists()).toBe(true)
  await toggle.trigger('click')
  expect(wrapper.classes()).toContain('filters-open')
  wrapper.unmount()

  // nothing but dropdowns: the toggle is the whole row, so it says 筛选 in words
  const only = mount(PageToolbar, { slots: { default: () => h('div', { class: 'el-select' }) }, global: { plugins: [ElementPlus] } })
  await nextTick()
  expect(only.find('.filters-toggle.lonely').text()).toBe('筛选')
  only.unmount()
})
