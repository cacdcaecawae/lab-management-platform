// Types mirror docs/api-contract.md. Keep them in sync with the contract, not with guesses.

export type Role = 'student' | 'manager' | 'advisor'

export interface UserBrief {
  id: number
  name: string
}

export interface Me {
  id: number
  username: string
  name: string
  role: Role
  is_supervisor: boolean
  is_superuser: boolean // the ops account: 系统管理 only, usually without a group
  group: { id: number; name: string } | null
  email: string
  phone: string
  wechat: string
  research_direction: string
  must_change_password: boolean
  avatar_url: string | null // the person's own picture (changes with every upload); null: the name's first character
}

// 个人信息: what a person changes about themselves; name, login name and role are set by managers / ops.
export type MeUpdate = Partial<Pick<Me, 'email' | 'phone' | 'wechat' | 'research_direction'>>

// Same shape as the (unexported) Query in client.ts.
export type { Query as ListQuery } from './client'

// ---- members ----

export interface Member {
  id: number
  name: string
  role: Role
  research_direction: string
  is_active: boolean
}

export interface MemberDetail extends Member {
  username: string
  email: string
  phone: string
  wechat: string
  must_change_password: boolean
}

// Students get Member, supervisors (and the user themself) get MemberDetail.
export type MemberListItem = Member & Partial<Omit<MemberDetail, keyof Member>>

export interface MemberCreate {
  username: string
  name: string
  role: Role
  email?: string
  phone?: string
  wechat?: string
  research_direction?: string
  password: string
}

// username: managers can correct a member's login name (e.g. a student number mistyped at signup)
export type MemberUpdate = Partial<Pick<MemberDetail, 'username' | 'name' | 'role' | 'email' | 'phone' | 'wechat' | 'research_direction' | 'is_active'>>

// A student who registered through the group's link and waits for a manager.
export interface PendingMember {
  id: number
  username: string
  name: string
  email: string
  date_joined: string
}

export interface Registration {
  code: string
  username: string
  name: string
  email: string
  password: string
}

// ---- projects ----

export interface ProjectBrief {
  id: number
  name: string
}

export type ProjectStatus = 'active' | 'closed'

export interface ProjectLog {
  id: number
  date: string
  content: string
  author: UserBrief
  created_at: string
}

export interface Project {
  id: number
  name: string
  leader: UserBrief
  members: UserBrief[]
  stage: string
  status: ProjectStatus
  description: string
  latest_log: ProjectLog | null
  created_at: string
  updated_at: string
}

export interface ProjectWrite {
  name: string
  leader_id: number
  member_ids: number[]
  stage: string
  status: ProjectStatus
  description: string
}

// ---- datasets & files ----

export type DatasetKind = 'raw' | 'script' | 'result' | 'other'

export interface Dataset {
  id: number
  code: string
  project: ProjectBrief
  owner: UserBrief
  name: string
  kind: DatasetKind
  description: string
  file_count: number
  total_size: number
  // current version code: SHA256 of the file list, shown as its first 12 characters
  version: string
  created_at: string
  updated_at: string
}

export interface DatasetBrief {
  id: number
  code: string
  name: string
  kind: DatasetKind
  // Only on datasets embedded in experiments / runs / reports: the version pinned when the record was
  // submitted (null for drafts and older records), and whether files were added since.
  version?: string | null
  changed?: boolean
}

export interface DatasetWrite {
  project_id: number
  name: string
  kind: DatasetKind
  description: string
}

export interface DataFile {
  id: number
  dataset_id: number
  name: string
  size: number
  sha256: string
  uploaded_by: UserBrief
  uploaded_at: string
  download_url: string
}

// ---- experiments & processing runs ----

export type RecordStatus = 'draft' | 'submitted'

export interface Experiment {
  id: number
  code: string
  project: ProjectBrief
  owner: UserBrief
  title: string
  date: string
  equipment_item: EquipmentBrief | null
  equipment: string
  specimen: string
  specimen_items: SpecimenBrief[]
  params: Record<string, unknown>
  steps: string
  anomalies: string
  datasets: DatasetBrief[]
  status: RecordStatus
  submitted_at: string | null
  created_at: string
  updated_at: string
}

export interface ExperimentWrite {
  project_id: number | null
  title: string
  date: string | null
  equipment_item_id: number | null
  equipment: string
  specimen: string
  specimen_item_ids: number[]
  params: Record<string, unknown>
  steps: string
  anomalies: string
  dataset_ids: number[]
}

export interface ExperimentBrief {
  id: number
  code: string
  title: string
  status: RecordStatus
}

export interface ProcessingRun {
  id: number
  code: string
  project: ProjectBrief
  owner: UserBrief
  title: string
  inputs: DatasetBrief[]
  script_dataset: DatasetBrief | null
  script_repo: string
  script_commit: string
  script_path: string
  method_version: string
  params: Record<string, unknown>
  environment: string
  output_dataset: DatasetBrief | null
  conclusion: string
  status: RecordStatus
  submitted_at: string | null
  created_at: string
  updated_at: string
}

export interface RunWrite {
  project_id: number | null
  title: string
  input_ids: number[]
  script_dataset_id: number | null
  script_repo: string
  script_commit: string
  script_path: string
  method_version: string
  params: Record<string, unknown>
  environment: string
  output_dataset_id: number | null
  conclusion: string
}

export type RunBrief = ExperimentBrief

// ---- weekly reports ----

export type ReportStatus = 'draft' | 'submitted' | 'needs_revision' | 'reviewed'
export type Verdict = 'reviewed' | 'needs_revision'

export interface Feedback {
  id: number
  author: UserBrief
  verdict: Verdict
  content: string
  created_at: string
}

export interface WeeklyReportBrief {
  id: number
  owner: UserBrief
  week_start: string
  status: ReportStatus
  submitted_at: string | null
}

export interface WeeklyReport extends WeeklyReportBrief {
  goals: string
  done: string
  findings: string
  next_plan: string
  experiments: ExperimentBrief[]
  datasets: DatasetBrief[]
  runs: RunBrief[]
  feedback: Feedback[]
  created_at: string
  updated_at: string
}

export interface ReportWrite {
  week_start: string
  goals: string
  done: string
  findings: string
  next_plan: string
  experiment_ids: number[]
  dataset_ids: number[]
  run_ids: number[]
}

export interface FeedbackWrite {
  verdict: Verdict
  content: string
}

// ---- history & dashboard ----

export interface HistoryEntry {
  id: number
  date: string
  type: 'created' | 'changed' | 'deleted'
  user: UserBrief | null
  reason: string
  changes: { field: string; old: unknown; new: unknown }[]
}

export interface BorrowedSpecimenReminder {
  loan_id: number
  specimen: SpecimenBrief
  borrowed_at: string
  due_date: string | null
  overdue: boolean
}

export interface Dashboard {
  my: {
    borrowed_specimens: BorrowedSpecimenReminder[]
    borrowed_specimens_count: number
    action_items: MyActionItem[]
    tasks: WorkbenchTask[]
    reports_needing_revision: WeeklyReportBrief[]
    draft_experiments: ExperimentBrief[]
    current_week_report: WeeklyReportBrief | null
    upcoming_bookings: Booking[]
    unreported_bookings: Booking[]
    // my drafts whose last submission was sent back with a comment
    returned_purchases: Purchase[]
  }
  supervisor: {
    week_start: string
    missing_reports: UserBrief[]
    pending_reviews: WeeklyReportBrief[]
    // managers: waiting for the initial review; advisors: for the final review
    purchases_to_review: Purchase[]
  } | null
  // managers only (they maintain equipment and consumables)
  manager: {
    overdue_loans: (BorrowedSpecimenReminder & { borrower: UserBrief })[]
    overdue_loans_count: number
    calibration_due: (EquipmentBrief & { calibration_due: string })[]
    calibration_due_count: number
    equipment_to_check: EquipmentBrief[]
    low_stock: Consumable[]
    expiring_batches?: { id: number; batch_no: string; expires_on: string; stock: number; consumable__name: string }[]
  } | null
}

// ---- equipment & bookings ----

// 试样与标准件. defects is null when hidden: a blind test's answer, for students until a manager makes it public.
export type SpecimenKind = 'standard' | 'reference' | 'sample' | 'other'
export type SpecimenStatus = 'available' | 'damaged' | 'retired'
export type DefectKind = 'fbh' | 'sdh' | 'notch' | 'crack' | 'delamination' | 'other'

export interface Defect {
  kind: DefectKind
  size_mm: string | number | null // the server returns "2.00"
  depth_mm: string | number | null
  position: string
  note: string
}

export interface SpecimenLoan {
  id: number
  borrower: UserBrief
  project: ProjectBrief | null
  purpose: string
  due_date: string | null
  borrowed_at: string
  returned_at: string | null
  returned_by: UserBrief | null
  return_note: string
}

export interface LoanWrite {
  project_id?: number | null
  purpose?: string
  due_date?: string | null
}

export interface SpecimenBrief {
  id: number
  code: string
  name: string
  status: SpecimenStatus
}

export interface Specimen extends SpecimenBrief {
  kind: SpecimenKind
  material: string
  dimensions: string
  location: string
  custodian: UserBrief | null
  defects_public: boolean
  defects: (Defect & { id: number })[] | null
  current_loan: SpecimenLoan | null
  notes: string
  created_at: string
  updated_at: string
}

export interface SpecimenWrite {
  code: string
  name: string
  kind: SpecimenKind
  material: string
  dimensions: string
  location: string
  custodian_id: number | null
  status: SpecimenStatus
  defects_public: boolean
  notes: string
  defects: Defect[]
}

export type EquipmentStatus = 'available' | 'needs_check' | 'repair' | 'retired'

export interface EquipmentBrief {
  id: number
  code: string
  name: string
  status: EquipmentStatus
}

export interface Equipment extends EquipmentBrief {
  model: string
  category: string
  location: string
  custodian: UserBrief | null
  // derived: a booking is running right now ("使用中" is not a stored status)
  in_use: boolean
  purchase_date: string | null
  calibration_due: string | null
  notes: string
  // the arrived purchase request it came from (code only: the request itself is private)
  purchase: PurchaseRef | null
  created_at: string
  updated_at: string
}

// GET /api/equipment/{id}/ only: the latest started use bookings, newest first
export interface EquipmentDetail extends Equipment {
  recent_usage: Booking[]
}

export interface EquipmentWrite {
  code: string
  name: string
  model: string
  category: string
  location: string
  custodian_id: number | null
  status: EquipmentStatus
  purchase_date: string | null
  calibration_due: string | null
  notes: string
  purchase_id: number | null
}

export type BookingKind = 'use' | 'maintenance'
export type Condition = 'normal' | 'abnormal'

export interface UsageReport {
  condition: Condition
  description: string
  photo_url: string | null
  reported_at: string
}

export interface Booking {
  id: number
  equipment: EquipmentBrief
  user: UserBrief
  project: ProjectBrief | null
  kind: BookingKind
  start_at: string
  end_at: string
  purpose: string
  cancelled_at: string | null
  report: UsageReport | null
  created_at: string
}

export interface BookingWrite {
  equipment_id: number
  project_id: number | null
  kind: BookingKind
  start_at: string
  end_at: string
  purpose: string
}

// ---- consumables ----

export interface ConsumableBatch {
  id: number
  batch_no: string
  expires_on: string | null
  stock: number
  can_issue: boolean
}

export interface BatchModeWrite {
  tracks_batches: boolean
  stock_version_seen: number
  opening_batch?: { batch_no: string; expires_on?: string }
}

export interface Consumable {
  id: number
  name: string
  spec: string
  unit: string
  location: string
  safety_stock: number
  // sum of all transactions
  stock: number
  // Latest append-only ledger entry id; 0 before the first entry.
  stock_version: number
  low: boolean
  tracks_batches?: boolean
  batches?: ConsumableBatch[]
  nearest_expiry?: string | null
  notes: string
  created_at: string
  updated_at: string
}

export type ConsumableWrite = Pick<Consumable, 'name' | 'spec' | 'unit' | 'location' | 'safety_stock' | 'notes'>

export type TxnKind = 'in' | 'out' | 'return' | 'adjust'

export interface StockTxn {
  id: number
  kind: TxnKind | "allocation" | "batch_mode"
  batch?: { batch_no: string; expires_on: string | null } | null
  // signed: out is negative
  quantity: number
  handler: UserBrief
  project: ProjectBrief | null
  purchase: PurchaseRef | null
  note: string
  created_at: string
}

// quantity: positive for in / out / return; the signed difference for adjust
export interface StockTxnWrite {
  // Required for adjust: version shown with the stock used to calculate the difference.
  stock_version_seen?: number
  batch_id?: number
  batch_no?: string
  expires_on?: string
  kind: TxnKind
  quantity: number
  project_id: number | null
  // stock-in only: the arrived purchase request it came from
  purchase_id?: number | null
  note: string
}

// ---- procurement: funds, purchase requests, reimbursements ----
// Amounts are strings with two decimals ("1200.00"), as the API sends them; the server's totals are authoritative.

export interface FundBrief {
  id: number
  code: string
  name: string
  active: boolean
}

export interface Fund extends FundBrief {
  owner: UserBrief | null
  notes: string
  created_at: string
  updated_at: string
}

export interface FundWrite {
  code: string
  name: string
  owner_id: number | null
  active: boolean
  notes: string
}

export type AttachmentKind = 'quote' | 'invoice' | 'other'

export interface Attachment {
  id: number
  kind: AttachmentKind
  name: string
  size: number
  uploaded_by: UserBrief
  // permission-checked download, opens inline
  url: string
  created_at: string
}

export type PurchaseStatus = 'draft' | 'pending_initial' | 'pending_final' | 'approved' | 'purchased' | 'arrived'

export interface PurchaseItem {
  id: number
  name: string
  spec: string
  quantity: number
  unit_price: string
  subtotal: string
  link: string
}

export type PurchaseItemWrite = Pick<PurchaseItem, 'name' | 'spec' | 'quantity' | 'unit_price' | 'link'>

export interface Approval {
  id: number
  stage: 'initial' | 'final'
  reviewer: UserBrief
  verdict: 'approve' | 'return'
  comment: string
  // the total the reviewer saw
  total: string
  created_at: string
}

export interface PurchaseRef {
  id: number
  code: string
}

export interface PurchaseBrief extends PurchaseRef {
  owner: UserBrief
  purpose: string
  status: PurchaseStatus
}

export interface Purchase extends PurchaseBrief {
  fund: FundBrief | null
  items: PurchaseItem[]
  total: string
  // a draft whose last submission was sent back (a withdrawal is not a return)
  returned: boolean
  submitted_at: string | null
  created_at: string
  updated_at: string
}

export interface PurchaseDetail extends Purchase {
  approvals: Approval[]
  attachments: Attachment[]
  linked_equipment: { id: number; code: string; name: string }[]
  linked_stock: { id: number; consumable: string; quantity: number; created_at: string }[]
}

export interface PurchaseWrite {
  fund_id?: number | null
  purpose: string
  // replaces all items
  items: PurchaseItemWrite[]
}

// The submission, status and total on screen; 409 `stale` if any changed since
export interface ReviewWrite {
  verdict: 'approve' | 'return'
  comment: string
  status_seen: PurchaseStatus
  total_seen: string
  submitted_seen: string
}

export type ReimbursementCategory = 'equipment' | 'consumable' | 'travel' | 'ai_tool' | 'other'
export type ReimbursementStatus = 'pending' | 'submitted' | 'paid'

export interface Reimbursement {
  id: number
  code: string
  owner: UserBrief
  fund: FundBrief
  purchase: PurchaseBrief | null
  category: ReimbursementCategory
  amount: string
  occurred_on: string
  description: string
  status: ReimbursementStatus
  submitted_at: string | null
  paid_at: string | null
  attachments: Attachment[]
  created_at: string
  updated_at: string
}

export interface ReimbursementWrite {
  fund_id: number | null
  purchase_id: number | null
  category: ReimbursementCategory
  amount: string
  occurred_on: string
  description: string
}

export type StatsBy = 'fund' | 'category' | 'owner' | 'month'

export interface ReimbursementStats {
  by: StatsBy
  rows: { key: string | number; label: string; count: number; total: string }[]
  count: number
  total: string
}

// ---- system (系统管理, ops account only) ----

export type MailSecurity = 'ssl' | 'starttls' | 'none'

export interface MailSettingsWrite {
  mail_enabled: boolean
  mail_host: string
  mail_port: number
  mail_security: MailSecurity
  mail_username: string
  mail_from: string
  mail_password?: string // write-only; leave out (or blank) to keep the stored one
}

// GET /api/system/version/ — current: APP_VERSION of the running images ("local" for a build from source)
export interface VersionInfo {
  current: string
  latest: string | null // null: nothing released yet, or GitHub unreachable (error)
  url: string
  error: string
  checked_at: string
  update_available: boolean
}

export interface MailSettings extends Omit<MailSettingsWrite, 'mail_password'> {
  password_set: boolean
  last_mail_error: string
  last_mail_error_at: string | null
}

export interface SystemGroup {
  id: number
  name: string
  finance_email: string
  member_count: number // active members
  created_at: string
}

export type SystemGroupWrite = Pick<SystemGroup, 'name' | 'finance_email'>

export interface Account {
  id: number
  username: string
  name: string
  role: Role
  group: { id: number; name: string } | null
  email: string
  phone: string
  wechat: string
  research_direction: string
  is_active: boolean
  must_change_password: boolean
  pending: boolean
  last_login: string | null
}

export type AccountUpdate = Partial<Pick<Account, 'username' | 'name' | 'role' | 'email' | 'phone' | 'wechat' | 'research_direction' | 'is_active'>>

export interface AccountCreate extends Required<Omit<AccountUpdate, 'is_active'>> {
  username: string
  group_id: number
  password: string
}

// ---- knowledge base (phase 4) ----

export type DocCategory = 'sdk' | 'manual' | 'experience' | 'procedure' | 'template'

export interface DocVersion {
  id: number
  number: number
  name: string
  size: number
  sha256: string
  note: string
  uploaded_by: UserBrief
  url: string // permission-checked; PDF and images open inline, anything else downloads
  created_at: string
}

export interface Doc {
  id: number
  title: string
  category: DocCategory
  equipment: EquipmentBrief | null
  tags: string[]
  description: string
  author: UserBrief
  latest: DocVersion | null
  created_at: string
  updated_at: string
}

export interface DocDetail extends Doc {
  versions: DocVersion[] // newest first
}

export interface DocWrite {
  title: string
  category: DocCategory
  equipment_id: number | null
  tags: string[]
  description: string
}

// ---- group meetings (phase 4) ----

export interface AgendaItem {
  id: number
  presenter: UserBrief
  topic: string
}

export interface ActionItem {
  id: number
  owner: UserBrief
  content: string
  due_date: string | null
  done_at: string | null
}

export interface MyActionItem extends ActionItem {
  meeting: { id: number; date: string; title: string }
}

export interface MeetingFile {
  id: number
  name: string
  size: number
  uploaded_by: UserBrief
  url: string
  created_at: string
}

export interface Meeting {
  id: number
  date: string
  title: string
  minutes: string
  agenda: AgendaItem[]
  actions: ActionItem[]
  files: MeetingFile[]
  created_by: UserBrief
  created_at: string
  updated_at: string
}

export interface MeetingWrite {
  date: string
  title: string
  minutes: string
  agenda: { presenter_id: number; topic: string }[]
  // an item with id is kept (and keeps its done state); items left out are removed
  actions: { id?: number; owner_id: number; content: string; due_date: string | null }[]
}

// ---- achievements (phase 4) ----

export type AchievementType = 'paper' | 'patent' | 'award' | 'software'
export type AchievementStatus = 'submitted' | 'accepted' | 'published' | 'filed' | 'granted' | 'awarded' | 'registered'

export interface Achievement {
  id: number
  type: AchievementType
  title: string
  authors: string // as printed, outside authors too
  members: UserBrief[]
  venue: string
  date: string
  status: AchievementStatus
  link: string
  fulltext_name: string
  fulltext_url: string | null
  notes: string
  created_by: UserBrief
  created_at: string
  updated_at: string
}

export interface AchievementWrite {
  type: AchievementType
  title: string
  authors: string
  member_ids: number[]
  venue: string
  date: string
  status: AchievementStatus
  link: string
  notes: string
}

export type TaskStatus = 'todo' | 'doing' | 'done'
export interface WorkbenchTask {
  id: number
  title: string
  due_date: string | null
  status: TaskStatus
  project: { id: number; name: string }
}

export interface ProjectTask extends Omit<WorkbenchTask, 'project'> {
  description: string
  assignee: (UserBrief & { current: boolean }) | null
  milestone: { id: number; title: string } | null
  created_by: number
  history: { actor: string; changes: Record<string, { before: unknown; after: unknown }>; created_at: string }[]
}

export interface TaskWrite {
  title: string
  description: string
  assignee_id: number | null
  milestone_id: number | null
  due_date: string | null
  status: TaskStatus
}
export interface ProjectMilestone {
  id: number
  title: string
  due_date: string | null
  done_at: string | null
  task_total: number
  task_done: number
}
export type MilestoneWrite = Pick<ProjectMilestone, 'title' | 'due_date'> & { done: boolean }
