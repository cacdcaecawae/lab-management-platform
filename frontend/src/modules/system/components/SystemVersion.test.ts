import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import type { VersionInfo } from '@/api/types'
import SystemVersion from './SystemVersion.vue'

const base: VersionInfo = {
  current: 'v0.2.0',
  latest: 'v0.3.0',
  url: 'https://github.com/x/y/releases/tag/v0.3.0',
  error: '',
  checked_at: '2026-11-18T09:00:00+08:00',
  update_available: true,
}

it.each([
  [{}, ['有新版本 v0.3.0', 'bash scripts/update.sh v0.3.0', '自动退回 v0.2.0']],
  [{ latest: 'v0.2.0', update_available: false }, ['已是最新版本']],
  [{ current: 'local', update_available: false }, ['从源码构建（local）', '不提示更新']],
  [{ latest: null, update_available: false, error: '连不上 GitHub：timed out' }, ['连不上 GitHub：timed out']],
  [{ latest: null, update_available: false }, ['还没有发布过正式版本']],
])('shows %o', (change, texts) => {
  const text = mount(SystemVersion, { props: { info: { ...base, ...change } }, global: { plugins: [ElementPlus] } }).text()
  for (const t of texts) expect(text).toContain(t)
  if (!('update_available' in change)) return
  expect(text).not.toContain('update.sh') // the command only shows when there is something newer
})
