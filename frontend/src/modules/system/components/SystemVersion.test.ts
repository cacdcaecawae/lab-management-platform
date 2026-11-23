import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import type { VersionInfo } from '@/api/types'
import { systemApi } from '@/modules/system/api'
import SystemVersion from './SystemVersion.vue'

const base: VersionInfo = {
  current: 'v0.2.0',
  latest: 'v0.3.0',
  url: 'https://github.com/x/y/releases/tag/v0.3.0',
  error: '',
  checked_at: '2026-11-18T09:00:00+08:00',
  update_available: true,
  agent: false,
}

const show = (change: Partial<VersionInfo>) =>
  mount(SystemVersion, { props: { info: { ...base, ...change } }, global: { plugins: [ElementPlus] } })

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

it.each([
  // A failed update rolls back only when the migrations did not change; otherwise the site stays stopped.
  [{}, ['有新版本 v0.3.0', 'bash scripts/update.sh v0.3.0', '没改数据库结构的，自动退回 v0.2.0', '网站保持停止', 'update-agent.sh --install']],
  [{ agent: true }, ['有新版本 v0.3.0', '立即更新']],
  [{ latest: 'v0.2.0', update_available: false }, ['已是最新版本']],
  [{ current: 'local', update_available: false }, ['从源码构建（local）']],
  [{ latest: null, update_available: false, error: '连不上 GitHub：timed out' }, ['连不上 GitHub：timed out']],
  [{ latest: null, update_available: false }, ['还没有发布过正式版本']],
])('shows %o', (change, texts) => {
  const text = show(change).text()
  for (const t of texts) expect(text).toContain(t)
  if ('agent' in change) expect(text).not.toContain('update.sh') // the agent runs it
  if (!('update_available' in change)) return
  expect(text).not.toContain('update.sh') // the command only shows when there is something newer
})

it('offers 重新检查 before the first answer, or when it failed', async () => {
  vi.spyOn(systemApi, 'version').mockResolvedValue(base)
  const wrapper = mount(SystemVersion, { props: { info: null }, global: { plugins: [ElementPlus] } })
  expect(wrapper.text()).toContain('当前版本')
  await wrapper.get('button[aria-label="重新检查"]').trigger('click')
  await flushPromises()
  expect(systemApi.version).toHaveBeenCalledWith(true)
  expect(wrapper.emitted('update:info')).toEqual([[base]])
})

it('follows the update from the server, ignoring the status an earlier update left', async () => {
  vi.useFakeTimers()
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
  vi.spyOn(systemApi, 'update').mockResolvedValue({ target: 'v0.3.0', requested_at: 1000 })
  const statuses = [
    { state: 'failed', step: 0, target: 'v0.3.0', started: 400 }, // an earlier try at the same release
    { state: 'running', step: 2, target: 'v0.3.0', started: 1001 },
  ]
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(statuses.shift()))))
  const wrapper = show({ agent: true })
  await wrapper.get('button.update').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('等待服务器开始更新')
  expect(wrapper.text()).not.toContain('没有更新')
  await vi.advanceTimersByTimeAsync(2000)
  expect(wrapper.text()).toContain('第 2 步，共 3 步：停止网站并备份')
  expect(systemApi.update).toHaveBeenCalledWith('v0.3.0')
  vi.unstubAllGlobals()
})
