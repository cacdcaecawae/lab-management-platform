// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, it, vi } from 'vitest'
import AchievementStatsPanel from './AchievementStatsPanel.vue'

const stats = vi.hoisted(() => ({ list: vi.fn(), exportUrl: vi.fn().mockReturnValue('/filtered-export') }))
vi.mock('@/api/achievements', () => ({ achievementStatsApi: stats }))

it('loads formal outcomes and exports the query that produced the displayed totals', async () => {
  stats.list.mockResolvedValue({
    by_year: [{ year: 2026, paper: 2, patent: 1, award: 1, software: 1, total: 5 }],
    by_member: [{ user: { id: 1, name: '测试成员' }, paper: 2, patent: 0, award: 0, software: 0, total: 2 }],
    total: { paper: 2, patent: 1, award: 1, software: 1, total: 5 },
    status: 'formal',
  })
  const page = mount(AchievementStatsPanel, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  expect(stats.list).toHaveBeenCalledWith({ status: 'formal' })
  expect(page.text()).toContain('全组去重总计：5 项')
  expect(page.text()).toContain('测试成员')
  expect(page.get('a').attributes('href')).toBe('/filtered-export')
  expect(stats.exportUrl).toHaveBeenCalledWith({ status: 'formal' })
  page.unmount()
})
