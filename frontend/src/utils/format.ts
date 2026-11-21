// Display labels and formatting shared by the pages.

export const ROLE_LABELS: Record<string, string> = { student: '学生', manager: '管理员', advisor: '导师' }

// After editing an account (成员, 系统管理): a changed login name is spelled out, since the person signs in with it.
export function renamedMessage(before: string | undefined, after: string): string {
  return before !== undefined && before !== after ? `已保存。学号 / 工号改成了 ${after}，下次登录要用新的` : '已保存'
}
export const KIND_LABELS: Record<string, string> = { raw: '原始数据', script: '脚本', result: '处理结果', other: '其他' }
export type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'
export const STATUS: Record<string, { label: string; type: TagType }> = {
  draft: { label: '草稿', type: 'info' },
  submitted: { label: '已提交', type: 'primary' },
  needs_revision: { label: '需补充', type: 'danger' },
  reviewed: { label: '已阅', type: 'success' },
  active: { label: '进行中', type: 'success' },
  closed: { label: '已结束', type: 'info' },
  available: { label: '可用', type: 'success' },
  needs_check: { label: '待检查', type: 'warning' },
  repair: { label: '维修', type: 'danger' },
  retired: { label: '停用', type: 'info' },
  damaged: { label: '损坏', type: 'danger' },
  pending_initial: { label: '待初审', type: 'warning' },
  pending_final: { label: '待终审', type: 'warning' },
  approved: { label: '已批准', type: 'success' },
  purchased: { label: '已采购', type: 'primary' },
  arrived: { label: '已到货', type: 'info' },
}
// Separate map: a reimbursement's "submitted" means handed to finance, not 已提交.
export const REIMBURSEMENT_STATUS: Record<string, { label: string; type: TagType }> = {
  pending: { label: '待提交', type: 'info' },
  submitted: { label: '已交财务', type: 'warning' },
  paid: { label: '已到账', type: 'success' },
}

export const PURCHASE_STATUSES = ['draft', 'pending_initial', 'pending_final', 'approved', 'purchased', 'arrived']
export const CATEGORY_LABELS: Record<string, string> = { equipment: '设备', consumable: '耗材', travel: '差旅', ai_tool: 'AI 工具', other: '其他' }
export const ATTACHMENT_KIND_LABELS: Record<string, string> = { quote: '报价单', invoice: '发票', other: '其他' }
export const STAGE_LABELS: Record<string, string> = { initial: '初审', final: '终审' }
export const REVIEW_VERDICT_LABELS: Record<string, string> = { approve: '通过', return: '退回修改' }

// Display only: the server's amounts are authoritative. "2536.5" -> "2,536.50".
export function formatMoney(value: string | number | null | undefined): string {
  return Number(value ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// A form's running total, summed in cents so 3 × 0.10 is 0.30, not 0.30000000000000004.
export function itemsTotal(items: { quantity: number | null | undefined; unit_price: number | null | undefined }[]): number {
  return items.reduce((cents, i) => cents + Math.round((i.unit_price ?? 0) * 100) * (i.quantity ?? 0), 0) / 100
}

// Mirrors the server (AttachmentViewSet.destroy): a draft's files go freely, none while under review, and after a
// review only the files no reviewer has seen, i.e. uploaded after the latest review.
export function purchaseFileDeletable(
  purchase: { status: string; approvals: { created_at: string }[] },
  file: { created_at: string },
): boolean {
  if (purchase.status === 'draft') return true
  if (purchase.status === 'pending_initial' || purchase.status === 'pending_final') return false
  const last = purchase.approvals.at(-1)
  return !last || new Date(file.created_at) > new Date(last.created_at)
}

export const DOC_CATEGORY_LABELS: Record<string, string> = {
  sdk: '设备 SDK', manual: '使用手册', experience: '调试经验', procedure: '操作规范', template: '代码模板',
}
export const ACHIEVEMENT_TYPE_LABELS: Record<string, string> = { paper: '论文', patent: '专利', award: '获奖', software: '软著' }
export const ACHIEVEMENT_STATUS_LABELS: Record<string, string> = {
  submitted: '投稿中', accepted: '已录用', published: '已发表', filed: '申请中', granted: '已授权', awarded: '已获奖', registered: '已登记',
}
// Same as the server (achievements.models.STATUSES): the first one is the default for a new record.
export const ACHIEVEMENT_STATUSES: Record<string, string[]> = {
  paper: ['submitted', 'accepted', 'published'], patent: ['filed', 'granted'], award: ['awarded'], software: ['registered'],
}
export const VENUE_LABELS: Record<string, string> = {
  paper: '期刊 / 会议', patent: '专利号 / 授权号', award: '奖项与等级', software: '登记号',
}

export const EQUIPMENT_STATUSES = ['available', 'needs_check', 'repair', 'retired']
export const SPECIMEN_STATUSES = ['available', 'damaged', 'retired']
export const SPECIMEN_KIND_LABELS: Record<string, string> = { standard: '标准试块', reference: '对比试块', sample: '试样', other: '其他' }
export const DEFECT_KIND_LABELS: Record<string, string> = {
  fbh: '平底孔', sdh: '横通孔', notch: '刻槽', crack: '裂纹', delamination: '分层', other: '其他',
}
export const BOOKING_KIND_LABELS: Record<string, string> = { use: '使用', maintenance: '维护' }
export const CONDITION_LABELS: Record<string, string> = { normal: '正常', abnormal: '异常' }
export const TXN_KIND_LABELS: Record<string, string> = { in: '入库', out: '领用', return: '退回', adjust: '盘点调整', allocation: '批次期初分配', batch_mode: '批次管理变更' }

// Field names that appear in HistoryEntry.changes.
export const FIELD_LABELS: Record<string, string> = {
  status: '状态', title: '名称', date: '日期', project: '项目', equipment: '设备说明', equipment_item: '台账设备', specimen: '试件',
  code: '设备编号', name: '名称', model: '型号', category: '类别', location: '存放位置', custodian: '保管人',
  purchase_date: '购置日期', calibration_due: '下次校准日期', notes: '备注',
  params: '参数', steps: '步骤与现场记录', anomalies: '异常情况', script_repo: 'git 仓库', script_commit: 'commit',
  script_path: '入口脚本', method_version: '方法版本', environment: '运行环境', conclusion: '结论',
  goals: '本周目标', done: '完成工作', findings: '主要发现与证据', next_plan: '下周计划', week_start: '周一日期',
  submitted_at: '提交时间', data_versions: '引用的数据版本',
  purpose: '用途', fund: '经费来源', purchase: '采购申请', amount: '金额', occurred_on: '发生日期', description: '说明',
  paid_at: '到账时间',
  tags: '标签', minutes: '纪要', authors: '作者', venue: '出处 / 编号', link: 'DOI / 链接', fulltext_name: '全文',
  mail_enabled: '启用邮件', mail_host: 'SMTP 服务器', mail_port: '端口', mail_security: '加密方式', mail_username: '账号',
  mail_from: '发件人地址',
}

const pad = (n: number) => String(n).padStart(2, '0')

// Local calendar date; toISOString() would give the previous day before 08:00 in UTC+8.
export function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function mondayOf(d: Date = new Date()): string {
  return toDateStr(new Date(d.getFullYear(), d.getMonth(), d.getDate() - ((d.getDay() + 6) % 7)))
}

// For <el-date-picker :disabled-date>: weekly reports start on a Monday.
export const notMonday = (d: Date) => d.getDay() !== 1

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${toDateStr(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// "2026-11-18 09:00 – 11:00", with the end date only when it differs.
export function formatPeriod(start: string, end: string): string {
  const s = formatTime(start)
  const e = formatTime(end)
  return `${s} – ${e.slice(0, 10) === s.slice(0, 10) ? e.slice(11) : e}`
}

export function formatSize(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let n = bytes
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return i === 0 ? `${n} B` : `${n.toFixed(1)} ${units[i]}`
}

// Select options plus the objects already embedded in a record, so linked items outside the loaded page still show a label.
export function mergeById<T extends { id: number }>(list: T[], extra: (T | null | undefined)[]): T[] {
  const ids = new Set(list.map((x) => x.id))
  return [...list, ...extra.filter((x): x is T => !!x && !ids.has(x.id))]
}
