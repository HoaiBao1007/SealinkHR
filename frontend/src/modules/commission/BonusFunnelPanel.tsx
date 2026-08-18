import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useConfirmDialog } from '../../shared/ui/ConfirmDialog'
import { credentialedFetch } from '../../shared/api/credentialedFetch'
import { formatVnd, formatVietnameseNumber, parseVndInput } from '../../shared/utils/currency'

type WalletJob = { job_id: number | null; job_no: string; period_id?: number; period_label?: string; earned: number; manual_credit?: number; manual_decrease?: number; held: number; payment_held?: number; manual_held?: number; scheduled: number; transferred?: number; available: number; paid: number }
type WalletPeriodSummary = { period_id: number; period_label: string; payout_periods?: string[]; total_profit_loss: number; total_bonus_quarter: number; monthly_bonus: number }
type Wallet = { sales_rep: string; period_id: number; period_labels?: string[]; period_summaries?: WalletPeriodSummary[]; total_bonus_quarter?: number; total_earned: number; manual_credit_amount: number; manual_decrease_amount: number; held_amount: number; scheduled_amount: number; transferred_amount: number; available_amount: number; paid_amount: number; recoverable_amount: number; jobs: WalletJob[] }
type Schedule = { id: number; sales_rep: string; payout_period: string; status: string; total_amount: number; note?: string | null; source_period_ids?: number[]; is_period_scoped?: boolean }
type Ledger = { id: number; job_id?: number | null; job_no?: string | null; job_customer?: string | null; job_display_name?: string | null; current_held_amount?: number; current_payment_held_amount?: number; current_manual_held_amount?: number; entry_type: string; amount: number; payout_period?: string | null; reason_code?: string | null; note?: string | null; created_at?: string | null }
type BonusLock = { locked: boolean; period_id: number; sales_rep: string; reason?: string | null; locked_by?: string | null; locked_at?: string | null }
type WalletJobDetail = {
  id: number; periodId: number; periodLabel: string; jobNo: string; jobDate?: string | null; hbl?: string | null; mbl?: string | null
  customer?: string | null; vendor?: string | null; salesRep?: string | null; shipper?: string | null; consignee?: string | null
  subType?: string | null; containerString?: string | null; wt?: number | null; vol?: number | null; carrierBookingNo?: string | null
  por?: string | null; finalDestination?: string | null; realizedRevenue: number; unrealizedRevenue: number; realizedCost: number
  unrealizedCost: number; profitLoss: number; containerPicked?: string | null; paymentReceived?: string | null
  periodProfitLoss?: number; periodTotalBonusQuarter?: number; periodMonthlyBonus?: number; nextReleasePayoutPeriods?: string[]; heldReleaseMode?: 'NEXT_QUARTER_LUMP' | 'NEXT_QUARTER_SPLIT'; heldReleasePayoutPeriod?: string | null
  earned: number; manualCredit: number; manualDecrease: number; paymentHeld: number; manualHeld: number; held: number; scheduled: number; transferred: number; available: number; paid: number; hasWalletEntry: boolean; remark?: string | null
  paymentVerificationId?: number | null; paymentVerificationStatus?: 'PENDING' | 'VERIFIED' | 'REJECTED' | 'COMMAND_CREATED' | null; paymentReportNote?: string | null; paymentVerificationNote?: string | null; paymentCommandNote?: string | null; paymentReportedAt?: string | null
}
type JobEdit = { paymentReceived: 'YES' | 'NO'; manualHeld: string; remark: string; commandNote: string; releasePayoutPeriod: string }
type WalletFocus = {
  periodId: number
  periodLabel: string
  salesRep: string
  jobId?: number
  requestKey?: number
  target?: 'accounting-queue' | 'job-detail'
} | null

type JobColumn = { key: keyof WalletJobDetail; label: string; numeric?: boolean; width: number }
const JOB_COLUMNS: JobColumn[] = [
  { key: 'jobNo', label: 'JOB #', width: 120 }, { key: 'jobDate', label: 'JOB DATE', width: 100 },
  { key: 'hbl', label: 'HBL/HAWB', width: 140 }, { key: 'mbl', label: 'MBL', width: 140 },
  { key: 'customer', label: 'CUSTOMER', width: 180 }, { key: 'vendor', label: 'VENDOR', width: 160 },
  { key: 'salesRep', label: 'SALES REP', width: 130 }, { key: 'shipper', label: 'SHIPPER', width: 160 },
  { key: 'consignee', label: 'CONSIGNEE', width: 160 }, { key: 'subType', label: 'SUBTYPE', width: 100 },
  { key: 'containerString', label: 'CONTAINER', width: 130 }, { key: 'wt', label: 'WT', numeric: true, width: 90 },
  { key: 'vol', label: 'VOL', numeric: true, width: 90 }, { key: 'carrierBookingNo', label: 'BOOKING #', width: 140 },
  { key: 'por', label: 'POR', width: 120 }, { key: 'finalDestination', label: 'FINAL DEST.', width: 140 },
  { key: 'realizedRevenue', label: 'REALIZED REV', numeric: true, width: 140 }, { key: 'unrealizedRevenue', label: 'UNREALIZED REV', numeric: true, width: 150 },
  { key: 'realizedCost', label: 'REALIZED COST', numeric: true, width: 130 }, { key: 'unrealizedCost', label: 'UNREALIZED COST', numeric: true, width: 140 },
  { key: 'profitLoss', label: 'PROFIT/LOSS', numeric: true, width: 130 }, { key: 'containerPicked', label: 'CONTAINER PICKED', width: 140 },
  { key: 'paymentReceived', label: 'PAYMENT RECEIVED', width: 150 },
]

const money = (value: number) => formatVnd(value || 0)
const decimal = (value: number) => formatVietnameseNumber(value || 0, { maximumFractionDigits: 3 })
const currentMonth = () => new Date().toISOString().slice(0, 7)
const parseMoneyInput = (value: string) => parseVndInput(value)
const formatMoneyInput = (value: string) => {
  const numeric = value.replace(/\D/g, '')
  return numeric ? money(Number(numeric)) : ''
}
const normalizedPayment = (value?: string | null): 'YES' | 'NO' => String(value || 'NO').toUpperCase() === 'YES' ? 'YES' : 'NO'
export function BonusFunnelPanel({ apiBase, token, focus, jobEditorOpen = false, onJobEditorClose }: { apiBase: string; token: string | null; focus?: WalletFocus; jobEditorOpen?: boolean; onJobEditorClose?: () => void }) {
  const confirm = useConfirmDialog()
  const headers = useMemo((): Record<string, string> => token ? { Authorization: `Bearer ${token}` } : {}, [token])
  const [wallets, setWallets] = useState<Wallet[]>([])
  const [walletJobs, setWalletJobs] = useState<WalletJobDetail[]>([])
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [ledger, setLedger] = useState<Ledger[]>([])
  const [bonusLock, setBonusLock] = useState<BonusLock | null>(null)
  const [selectedRep, setSelectedRep] = useState('')
  const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null)
  const [selectedPeriodLabel, setSelectedPeriodLabel] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [notificationHighlightJobId, setNotificationHighlightJobId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [jobEdits, setJobEdits] = useState<Record<number, JobEdit>>({})
  const [loadedJobContext, setLoadedJobContext] = useState<{ salesRep: string; periodId: number | null } | null>(null)
  const [jobSearch, setJobSearch] = useState('')
  const [lockedOnly, setLockedOnly] = useState(false)
  const [ledgerOpen, setLedgerOpen] = useState(false)
  const ledgerCloseButtonRef = useRef<HTMLButtonElement>(null)
  const jobEditorCloseButtonRef = useRef<HTMLButtonElement>(null)
  const loadRequestId = useRef(0)
  const selectedWallet = wallets.find(item => item.sales_rep === selectedRep && item.period_id === selectedPeriodId) || wallets.find(item => item.sales_rep === selectedRep)
  const isBonusLocked = selectedPeriodId != null && bonusLock?.locked === true

  async function load(rep = selectedRep, periodId = selectedPeriodId) {
    const requestId = ++loadRequestId.current
    setLoadedJobContext(null)
    const params = new URLSearchParams()
    if (rep) params.set('sales_rep', rep)
    if (periodId != null) params.set('period_id', String(periodId))
    const query = params.toString() ? `?${params.toString()}` : ''
    const lockRequest = rep && periodId != null
      ? credentialedFetch(`${apiBase}/api/commission/wallet/lock?sales_rep=${encodeURIComponent(rep)}&period_id=${periodId}`, { headers })
      : Promise.resolve(null)
    const [walletRes, scheduleRes, ledgerRes, jobsRes, lockRes] = await Promise.all([
      credentialedFetch(`${apiBase}/api/commission/wallet${query}`, { headers }),
      credentialedFetch(`${apiBase}/api/commission/wallet/schedules${query}`, { headers }),
      credentialedFetch(`${apiBase}/api/commission/wallet/ledger${query}`, { headers }),
      credentialedFetch(`${apiBase}/api/commission/wallet/jobs${query}`, { headers }),
      lockRequest,
    ])
    // A notification can change the selected period while the initial unfiltered
    // request is still running. Ignore that stale response so it cannot replace
    // the exact employee/period/JOB selected by the notification.
    if (requestId !== loadRequestId.current) return
    if (walletRes.ok) {
      const data: Wallet[] = await walletRes.json()
      setWallets(data)
      if (!rep && data[0]) {
        setSelectedRep(data[0].sales_rep)
        setSelectedPeriodId(data[0].period_id)
        setSelectedPeriodLabel(data[0].period_labels?.[0] || '')
      }
    }
    if (scheduleRes.ok) setSchedules(await scheduleRes.json())
    if (ledgerRes.ok) setLedger(await ledgerRes.json())
    if (jobsRes.ok) {
      setWalletJobs(await jobsRes.json())
      setLoadedJobContext({ salesRep: rep, periodId })
    }
    setBonusLock(lockRes && lockRes.ok ? await lockRes.json() : null)
  }

  useEffect(() => { void load() }, [])
  useEffect(() => { if (selectedRep) void load(selectedRep, selectedPeriodId) }, [selectedRep, selectedPeriodId])
  useEffect(() => {
    if (!focus) {
      if (selectedPeriodId != null) {
        setSelectedPeriodId(null)
        setSelectedPeriodLabel('')
        if (selectedRep) void load(selectedRep, null)
      }
      return
    }
    setSelectedRep(focus.salesRep)
    setSelectedPeriodId(focus.periodId)
    setSelectedPeriodLabel(focus.periodLabel)
    setSelectedJobId(focus.jobId ?? null)
    setNotificationHighlightJobId(focus.jobId ?? null)
    setJobSearch('')
    setLockedOnly(false)
    void load(focus.salesRep, focus.periodId)
  }, [focus?.requestKey, focus?.periodId, focus?.periodLabel, focus?.salesRep, focus?.jobId])
  useEffect(() => {
    if (walletJobs.length && !walletJobs.some(item => item.id === selectedJobId)) {
      setSelectedJobId(walletJobs.find(item => item.hasWalletEntry)?.id ?? walletJobs[0].id)
    }
  }, [selectedJobId, walletJobs])
  useEffect(() => {
    if (!focus?.jobId || !walletJobs.some(item => item.id === focus.jobId)) return
    setSelectedJobId(focus.jobId)
    setNotificationHighlightJobId(focus.jobId)
    const scrollTimer = window.setTimeout(() => {
      const targetId = focus.target === 'accounting-queue'
        ? `commission-accounting-job-${focus.jobId}`
        : `commission-job-${focus.jobId}`
      document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' })
    }, 180)
    const highlightTimer = window.setTimeout(() => setNotificationHighlightJobId(current => current === focus.jobId ? null : current), 6000)
    return () => {
      window.clearTimeout(scrollTimer)
      window.clearTimeout(highlightTimer)
    }
  }, [focus?.requestKey, focus?.jobId, focus?.target, walletJobs])
  useEffect(() => {
    setJobEdits(Object.fromEntries(walletJobs.map(job => [job.id, {
      paymentReceived: String(job.paymentReceived || 'NO').toUpperCase() === 'YES' ? 'YES' : 'NO',
      manualHeld: money(job.manualHeld),
      remark: job.remark || '',
      commandNote: job.paymentCommandNote || '',
      releasePayoutPeriod: job.heldReleasePayoutPeriod || job.nextReleasePayoutPeriods?.[0] || currentMonth(),
    }])))
  }, [walletJobs])
  useEffect(() => {
    if (!ledgerOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ledgerCloseButtonRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setLedgerOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [ledgerOpen])
  useEffect(() => {
    if (jobEditorOpen) jobEditorCloseButtonRef.current?.focus()
  }, [jobEditorOpen])

  const filteredJobs = useMemo(() => {
    const keyword = jobSearch.trim().toLocaleLowerCase('vi-VN')
    return walletJobs.filter(job => {
      const matchesSearch = !keyword || [job.jobNo, job.customer, job.hbl, job.mbl, job.shipper, job.consignee, job.periodLabel].some(value => String(value || '').toLocaleLowerCase('vi-VN').includes(keyword))
      return matchesSearch && (!lockedOnly || job.manualHeld > 0)
    })
  }, [jobSearch, lockedOnly, walletJobs])
  const lockedJobs = walletJobs.filter(job => job.manualHeld > 0)
  const jobEditorContextReady = !focus || (
    loadedJobContext?.salesRep === focus.salesRep
    && loadedJobContext.periodId === focus.periodId
  )
  const heldJobs = walletJobs.filter(job => job.held > 0)
  // Use the same saved period summary as the import history. The detailed JOB
  // table remains available for auditing, but it must not create a second P&L total.
  const periodTotals = useMemo(() => Array.from(new Map(walletJobs.map(job => [job.periodId, {
    profitLoss: Number(job.periodProfitLoss || 0),
    totalBonusQuarter: Number(job.periodTotalBonusQuarter || 0),
  }])).values()), [walletJobs])
  const totalPnL = periodTotals.reduce((sum, period) => sum + period.profitLoss, 0)

  async function call(path: string, body?: object, method = 'POST') {
    setBusy(true); setMessage('')
    try {
      const res = await credentialedFetch(`${apiBase}${path}`, { method, headers: { 'Content-Type': 'application/json', ...headers }, body: body ? JSON.stringify(body) : undefined })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể thực hiện thao tác.')
      setMessage(data.message || 'Đã cập nhật phễu thưởng.')
      await load(selectedRep, selectedPeriodId)
      return true
    } catch (error) { setMessage((error as Error).message); return false } finally { setBusy(false) }
  }

  async function undoLastWalletOperation() {
    if (isBonusLocked) return setMessage('Bảng bonus đã khóa; không thể hoàn tác.')
    if (!selectedRep) return setMessage('Chọn nhân viên trước khi hoàn tác.')
    if (!await confirm({
      title: 'Hoàn tác thao tác ví thưởng',
      message: `Hoàn tác thao tác ví gần nhất của ${selectedRep}? Hệ thống sẽ tạo bút toán đảo chiều để vẫn giữ lịch sử đối soát. Đợt đã chi trả không thể hoàn tác tại đây.`,
      confirmLabel: 'Hoàn tác',
      tone: 'danger',
    })) return
    await call('/api/commission/wallet/undo-last', { sales_rep: selectedRep, source_period_id: selectedPeriodId })
  }

  function updateJobEdit(jobId: number, patch: Partial<JobEdit>) {
    setJobEdits(previous => ({ ...previous, [jobId]: { ...previous[jobId], ...patch } }))
  }

  async function saveHeldReleasePlan(job: WalletJobDetail) {
    const edit = jobEdits[job.id]
    if (!edit || !selectedRep) return
    if (isBonusLocked) return setMessage('Bảng bonus đã khóa; không thể đổi hình thức chi trả.')
    if (!edit.releasePayoutPeriod) return setMessage('Chọn tháng trả một lần.')
    await call(`/api/commission/periods/${job.periodId}/jobs/${job.id}/release-plan`, {
      release_mode: 'NEXT_QUARTER_LUMP',
      release_payout_period: edit.releasePayoutPeriod,
    }, 'PUT')
  }

  async function reportPayment(job: WalletJobDetail) {
    if (isBonusLocked) return setMessage('Bảng bonus đã khóa; không thể gửi báo cáo thanh toán.')
    if (!await confirm({ title: `Báo kế toán cho JOB ${job.jobNo}`, message: 'Xác nhận Sales đã báo khách hàng thanh toán? Tiền vẫn được giữ nguyên cho đến khi kế toán xác minh và lập lệnh chi trả.', confirmLabel: 'Gửi báo cáo' })) return
    const edit = jobEdits[job.id]
    await call(`/api/commission/periods/${job.periodId}/jobs/${job.id}/payment-report`, { note: edit?.remark || null })
  }

  async function reviewPayment(job: WalletJobDetail, action: 'VERIFY' | 'REJECT') {
    if (!job.paymentVerificationId) return
    const accepted = action === 'VERIFY'
    if (!await confirm({ title: accepted ? `Xác minh JOB ${job.jobNo}` : `Từ chối JOB ${job.jobNo}`, message: accepted ? 'Kế toán xác minh khách đã thanh toán. Ví vẫn chưa thay đổi cho đến khi lập lệnh chi trả.' : 'Yêu cầu sẽ bị từ chối và JOB tiếp tục ở trạng thái đang giữ.', confirmLabel: accepted ? 'Xác minh' : 'Từ chối', tone: accepted ? undefined : 'danger' })) return
    await call(`/api/commission/payment-verifications/${job.paymentVerificationId}/review`, { action, note: jobEdits[job.id]?.remark || null })
  }

  async function createPaymentCommand(job: WalletJobDetail) {
    const edit = jobEdits[job.id]
    if (!job.paymentVerificationId || !edit) return
    if (!edit.releasePayoutPeriod) return setMessage('Chọn tháng trả trước khi lập lệnh chi trả.')
    if (!await confirm({ title: `Lập lệnh chi trả ${job.jobNo}`, message: `Xác nhận trả một lần vào tháng ${edit.releasePayoutPeriod}. Số tiền giữ của JOB sẽ được chuyển vào lịch chi trả, lịch sử sổ cái không bị sửa.`, confirmLabel: 'Lập lệnh chi trả' })) return
    await call(`/api/commission/payment-verifications/${job.paymentVerificationId}/payout-command`, { release_mode: 'NEXT_QUARTER_LUMP', release_payout_period: edit.releasePayoutPeriod, note: edit.commandNote || null })
  }

  async function lockBonusTable() {
    if (!selectedRep || selectedPeriodId == null || isBonusLocked) return
    if (!await confirm({
      title: 'Khóa bảng bonus',
      message: `Sau khi khóa, tất cả chỉnh sửa JOB, giữ/mở giữ, chuyển kỳ, lập lịch, chi trả và hoàn tác của ${selectedRep} trong ${selectedPeriodLabel || `kỳ #${selectedPeriodId}`} sẽ bị chặn. Thao tác này dùng để chốt dữ liệu kế toán.`,
      confirmLabel: 'Khóa bảng bonus',
      tone: 'danger',
    })) return
    await call('/api/commission/wallet/lock', { period_id: selectedPeriodId, sales_rep: selectedRep })
  }

  function getJobPreview(job: WalletJobDetail, edit: JobEdit) {
    const currentPayment = normalizedPayment(job.paymentReceived)
    let paymentHeld = job.paymentHeld
    let available = job.available
    if (edit.paymentReceived !== currentPayment) {
      if (edit.paymentReceived === 'YES') { available += paymentHeld; paymentHeld = 0 } else { paymentHeld += available; available = 0 }
    }
    const manualDelta = parseMoneyInput(edit.manualHeld) - job.manualHeld
    return { paymentHeld: Math.max(0, paymentHeld), available: available - manualDelta, changed: edit.paymentReceived !== currentPayment || Math.abs(manualDelta) >= 0.01 }
  }

  async function saveJobEdit(job: WalletJobDetail) {
    const edit = jobEdits[job.id]
    if (!edit || !selectedRep) return
    if (isBonusLocked) return setMessage('Bảng bonus đã khóa; không thể chỉnh sửa JOB.')
    const paymentChanged = edit.paymentReceived !== normalizedPayment(job.paymentReceived)
    const remarkChanged = edit.remark.trim() !== (job.remark || '').trim()
    const targetManualHeld = parseMoneyInput(edit.manualHeld)
    const manualHoldChanged = Math.abs(targetManualHeld - job.manualHeld) >= 0.01
    const isReleasingHeldBonus = normalizedPayment(job.paymentReceived) === 'NO' && edit.paymentReceived === 'YES' && job.paymentHeld > 0
    const releaseDescription = `trả một lần phần đang giữ vào tháng ${edit.releasePayoutPeriod}`
    if (!paymentChanged && !remarkChanged && !manualHoldChanged) return setMessage(`JOB ${job.jobNo} chưa có thay đổi.`)
    if (!await confirm({ title: `Lưu chỉnh sửa JOB ${job.jobNo}`, message: isReleasingHeldBonus ? `JOB chuyển sang YES: hệ thống sẽ ${releaseDescription}.` : 'Payment Received sẽ đồng bộ lại ví; Giữ thủ công chỉ tạo bút toán chênh lệch và không thay đổi công thức commission.', confirmLabel: 'Lưu chỉnh sửa' })) return
    setBusy(true); setMessage('')
    try {
      if (paymentChanged || remarkChanged) {
        const paymentRes = await credentialedFetch(`${apiBase}/api/commission/periods/${job.periodId}/jobs/${job.id}/payment`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify({ payment_received: edit.paymentReceived, remark: edit.remark || null, release_mode: 'NEXT_QUARTER_LUMP', release_payout_period: edit.releasePayoutPeriod }) })
        const paymentData = await paymentRes.json()
        if (!paymentRes.ok) throw new Error(paymentData.detail || 'Không thể lưu Payment Received.')
      }
      if (manualHoldChanged) {
        const holdRes = await credentialedFetch(`${apiBase}/api/commission/wallet/jobs/${job.id}/manual-hold`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify({ sales_rep: selectedRep, manual_held_amount: targetManualHeld, remark: edit.remark || null }) })
        const holdData = await holdRes.json()
        if (!holdRes.ok) throw new Error(holdData.detail || 'Không thể cập nhật giữ thủ công.')
      }
      setMessage(`Đã lưu chỉnh sửa JOB ${job.jobNo}.`)
      await load(selectedRep, selectedPeriodId)
    } catch (error) { setMessage((error as Error).message) } finally { setBusy(false) }
  }

  const cellStyle = (width: number, numeric = false) => ({ padding: '7px 12px', textAlign: numeric ? 'right' as const : 'left' as const, fontFamily: numeric ? 'monospace' : 'inherit', borderRight: '1px solid #cbd5e1', minWidth: width, maxWidth: width, overflow: 'hidden', textOverflow: 'ellipsis' as const })

  return <>
  <section className="ui-card" style={{ marginTop: 16, display: 'flex', flexDirection: 'column' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center', order: 40 }}>
      <div><h3 style={{ margin: 0 }}>Phễu bonus linh động</h3><p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 12 }}>Theo dõi ví thưởng và lịch chi trả, không thay đổi công thức commission nguồn.</p></div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {selectedPeriodId != null && <button className="ui-button ui-button-secondary" disabled={busy || !selectedRep || isBonusLocked} onClick={() => void lockBonusTable()}>🔒 {isBonusLocked ? 'Đã khóa bảng bonus' : 'Khóa bảng bonus'}</button>}
        <button className="ui-button ui-button-secondary" disabled={busy || !selectedRep || isBonusLocked} onClick={() => void undoLastWalletOperation()}>↶ Hoàn tác bước gần nhất</button>
        <button className="ui-button ui-button-secondary" disabled={busy} onClick={() => load(selectedRep, selectedPeriodId)}>Làm mới</button>
      </div>
    </div>
    {selectedWallet && <div style={{ marginTop: 12, padding: '9px 12px', borderRadius: 8, background: '#eff6ff', color: '#1e3a5f', fontWeight: 600, order: 41 }}>
      {selectedPeriodId != null ? `Đang xem ví theo kỳ đã chọn: ${selectedPeriodLabel || selectedWallet.period_labels?.join(' · ') || 'Chưa xác định'} · ${selectedWallet.sales_rep}` : `Kỳ nguồn của ${selectedWallet.sales_rep}: ${selectedWallet.period_labels?.join(' · ') || 'Chưa xác định'}`} · Chi trả theo tháng: {selectedWallet.period_summaries?.flatMap(item => item.payout_periods || []).map(value => value.replace('-', '/')).join(' · ') || 'Chưa xác định'} · Đã chuyển kỳ sau: {money(selectedWallet.transferred_amount)}
    </div>}
    {isBonusLocked && <div className="ui-state ui-state-error" style={{ marginTop: 12, padding: 10, order: 42 }}>
      🔒 Bảng bonus đã chốt. API đã chặn mọi thao tác làm thay đổi JOB, số dư, lịch chi trả và hoàn tác của kỳ này.
      {bonusLock?.locked_at && <small style={{ display: 'block', marginTop: 4 }}>Khóa lúc: {new Date(bonusLock.locked_at).toLocaleString('vi-VN')}{bonusLock.locked_by ? ` · bởi ${bonusLock.locked_by}` : ''}</small>}
    </div>}
    {message && <p className={message.includes('Không') || message.includes('Nhập') ? 'ui-state ui-state-error' : 'ui-state'} style={{ marginTop: 12, padding: 10, order: 43 }}>{message}</p>}
    <div className="ui-table-wrap" style={{ marginTop: 14, order: 44 }}><table className="ui-table"><thead><tr><th>Nhân viên Sales</th><th>Kỳ nguồn → ba tháng chi trả</th><th>Tổng thưởng quý</th><th>Thưởng chuẩn / tháng</th><th>Giữ (cả quý)</th><th>Đã lập lịch</th><th>Đã chuyển kỳ sau</th><th>Khả dụng</th><th>Đã trả</th><th>Thu hồi</th></tr></thead><tbody>{wallets.map(item => <tr key={`${item.sales_rep}-${item.period_id}`} onClick={() => { setSelectedRep(item.sales_rep); setSelectedPeriodId(item.period_id); setSelectedPeriodLabel(item.period_summaries?.[0]?.period_label || item.period_labels?.[0] || '') }} style={{ cursor: 'pointer', background: selectedRep === item.sales_rep && selectedPeriodId === item.period_id ? '#eff6ff' : undefined }}><td>{item.sales_rep}</td><td>{item.period_summaries?.map(period => <div key={period.period_id} style={{ lineHeight: 1.4 }}><b>{period.period_label}</b><br /><small>Trả: {(period.payout_periods || []).map(value => value.replace('-', '/')).join(' · ')}</small></div>)}</td><td style={{ color: '#1d4ed8', fontWeight: 700 }}>{money(item.total_bonus_quarter ?? 0)}</td><td>{item.period_summaries?.length ? item.period_summaries.map(period => <div key={period.period_id}>{money(period.monthly_bonus)}</div>) : money(item.total_earned)}</td><td style={{ color: '#b45309', fontWeight: 700 }}>{money(item.held_amount)}</td><td>{money(item.scheduled_amount)}</td><td style={{ color: '#2563eb', fontWeight: 700 }}>{money(item.transferred_amount)}</td><td style={{ color: item.available_amount < 0 ? '#b91c1c' : '#047857' }}>{money(item.available_amount)}</td><td>{money(item.paid_amount)}</td><td style={{ color: '#b91c1c' }}>{money(item.recoverable_amount)}</td></tr>)}</tbody></table></div>
    {selectedRep && <>
      <div className="ui-card" style={{ display: 'none' }} aria-hidden="true">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
          <div><h4 style={{ margin: 0 }}>JOB đang giữ bonus</h4><small style={{ color: '#92400e' }}>Số dư lấy trực tiếp từ sổ cái. Chọn phương án trước; khi Payment Received chuyển sang YES, hệ thống sẽ áp dụng đúng phương án đã lưu.</small></div>
          <b style={{ color: '#b45309' }}>Tổng đang giữ: {money(heldJobs.reduce((sum, job) => sum + job.held, 0))}</b>
        </div>
        {heldJobs.length === 0 ? <p className="ui-state" style={{ marginTop: 12 }}>Không có JOB nào đang bị giữ bonus trong phạm vi ví này.</p> : <div className="ui-table-wrap" style={{ maxHeight: 270, marginTop: 12 }}><table className="ui-table"><thead><tr><th>JOB</th><th>Khách hàng</th><th>Payment</th><th>Giữ tự động</th><th>Giữ thủ công</th><th>Tổng đang giữ</th><th>Hình thức chi trả khi mở khóa</th><th /></tr></thead><tbody>{heldJobs.map(job => {
          const edit = jobEdits[job.id]
          if (!edit) return null
          const months = job.nextReleasePayoutPeriods || []
          return <tr key={job.id}><td><b>{job.jobNo}</b><small style={{ display: 'block', color: '#64748b' }}>{job.periodLabel}</small></td><td>{job.customer || '—'}</td><td style={{ color: normalizedPayment(job.paymentReceived) === 'YES' ? '#047857' : '#b45309', fontWeight: 700 }}>{normalizedPayment(job.paymentReceived)}</td><td style={{ color: '#b45309' }}>{money(job.paymentHeld)}</td><td style={{ color: '#b91c1c' }}>{money(job.manualHeld)}</td><td style={{ color: '#b45309', fontWeight: 800 }}>{money(job.held)}</td><td><b>Trả một lần</b><select className="ui-input" disabled={busy || isBonusLocked} style={{ minWidth: 135, marginTop: 6 }} value={edit.releasePayoutPeriod} onChange={event => updateJobEdit(job.id, { releasePayoutPeriod: event.target.value })}>{months.map(month => <option key={month} value={month}>{month}</option>)}</select><small style={{ display: 'block', marginTop: 4, color: '#64748b' }}>{months.join(' · ')}</small></td><td><button className="ui-button ui-button-secondary" disabled={busy || isBonusLocked} onClick={() => void saveHeldReleasePlan(job)}>Lưu tháng trả</button></td></tr>
        })}</tbody></table></div>}
      </div>

      <div className="ui-card" style={{ marginTop: 16, borderColor: '#fcd34d', order: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}><h4 style={{ margin: 0 }}>JOB đang giữ bonus & hàng đợi kế toán</h4><b style={{ color: '#b45309' }}>Tổng đang giữ: {money(heldJobs.reduce((sum, job) => sum + job.held, 0))}</b></div>
        <small style={{ color: '#92400e' }}>Bảng duy nhất theo từng JOB: số giữ tự động/thủ công, trạng thái xác minh và lệnh chi trả. JOB chỉ giữ thủ công không cần báo kế toán.</small>
        <div className="ui-table-wrap" style={{ maxHeight: 330, marginTop: 10 }}><table className="ui-table"><thead><tr><th>JOB / kỳ nguồn</th><th>Giữ tự động</th><th>Giữ thủ công</th><th>Tổng giữ</th><th>Trạng thái</th><th>Phương án</th><th>Ghi chú kế toán</th><th>Thao tác kế toán</th></tr></thead><tbody>{heldJobs.filter(job => job.held > 0).map(job => {
          const edit = jobEdits[job.id]
          const state = job.paymentVerificationStatus || 'NONE'
          const months = job.nextReleasePayoutPeriods || []
          if (!edit) return null
          const isNotificationTarget = job.id === notificationHighlightJobId
          return <tr
            id={`commission-accounting-job-${job.id}`}
            data-job-id={job.id}
            key={`payment-workflow-${job.id}`}
            style={{
              scrollMarginTop: 120,
              background: isNotificationTarget ? '#fef3c7' : undefined,
              outline: isNotificationTarget ? '3px solid #f59e0b' : undefined,
              outlineOffset: isNotificationTarget ? -3 : undefined,
              transition: 'background-color 240ms ease, outline-color 240ms ease',
            }}
          ><td><b>{job.jobNo}</b><small style={{ display: 'block' }}>{job.periodLabel} · {job.customer || '—'}</small></td><td style={{ color: '#b45309', fontWeight: 700 }}>{money(job.paymentHeld)}</td><td style={{ color: '#b91c1c', fontWeight: 700 }}>{money(job.manualHeld)}</td><td style={{ color: '#b45309', fontWeight: 800 }}>{money(job.held)}</td><td><b>{job.paymentHeld <= 0 ? 'Giữ thủ công' : state === 'NONE' ? 'Chưa báo' : state === 'PENDING' ? 'Chờ kế toán xác minh' : state === 'VERIFIED' ? 'Đã xác minh' : state === 'COMMAND_CREATED' ? 'Đã lập lệnh' : 'Đã từ chối'}</b><small style={{ display: 'block' }}>{job.paymentVerificationNote || job.paymentReportNote || ''}</small></td><td>{state === 'COMMAND_CREATED' && job.heldReleaseMode === 'NEXT_QUARTER_SPLIT' ? <small>Lịch cũ: chia đều 3 tháng</small> : <><b>Trả một lần</b><select className="ui-input" disabled={busy || isBonusLocked || state !== 'VERIFIED' || job.paymentHeld <= 0} value={edit.releasePayoutPeriod} onChange={event => updateJobEdit(job.id, { releasePayoutPeriod: event.target.value })}>{months.map(month => <option key={month} value={month}>{month}</option>)}</select></>}</td><td>{state === 'COMMAND_CREATED' ? <small>{job.paymentCommandNote || 'Kế toán đã lập lệnh chi trả theo JOB.'}</small> : <input className="ui-input" disabled={busy || isBonusLocked || state !== 'VERIFIED' || job.paymentHeld <= 0} value={edit.commandNote} onChange={event => updateJobEdit(job.id, { commandNote: event.target.value })} placeholder="Nguồn tiền / lý do chi trả" style={{ minWidth: 230 }} />}</td><td>{job.paymentHeld <= 0 ? <span>Không cần báo</span> : state === 'NONE' || state === 'REJECTED' ? <button className="ui-button ui-button-secondary" disabled={busy || isBonusLocked} onClick={() => void reportPayment(job)}>Báo kế toán</button> : state === 'PENDING' ? <><button className="ui-button ui-button-primary" disabled={busy || isBonusLocked} onClick={() => void reviewPayment(job, 'VERIFY')}>Xác minh</button> <button className="ui-button ui-button-secondary" disabled={busy || isBonusLocked} onClick={() => void reviewPayment(job, 'REJECT')}>Từ chối</button></> : state === 'VERIFIED' ? <button className="ui-button ui-button-primary" disabled={busy || isBonusLocked} onClick={() => void createPaymentCommand(job)}>Lập lệnh chi trả</button> : 'Đã tạo lịch'}</td></tr>
        })}</tbody></table></div>
      </div>

      {jobEditorOpen && createPortal(
        <div className="ui-modal-backdrop" role="presentation" onMouseDown={onJobEditorClose} style={{ zIndex: 3200, padding: 16 }}>
          <section role="dialog" aria-modal="true" aria-labelledby="commission-manual-job-editor-title" onMouseDown={event => event.stopPropagation()} style={{ width: 'min(96vw, 1780px)', height: 'min(92vh, 940px)', background: '#fff', borderRadius: 18, boxShadow: '0 28px 80px rgba(15,23,42,.38)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, padding: '12px 18px', borderBottom: '1px solid #dbe3ef', background: '#f8fafc' }}>
              <div>
                <h3 id="commission-manual-job-editor-title" style={{ margin: 0, color: '#0f172a' }}>Sửa thủ công JOB &amp; giữ bonus</h3>
                <small style={{ color: '#64748b' }}>{selectedRep} · {selectedPeriodLabel || 'Chưa xác định kỳ commission'}</small>
              </div>
              <button ref={jobEditorCloseButtonRef} type="button" className="ui-button ui-button-secondary app-close-button" aria-label="Đóng sửa thủ công JOB" onClick={onJobEditorClose} style={{ width: 38, minWidth: 38, height: 38, padding: 0, borderRadius: 10, fontSize: 22, lineHeight: 1 }}>×</button>
            </header>
            <div style={{ flex: 1, overflow: 'auto', padding: 16, overscrollBehavior: 'contain' }}>
      {!jobEditorContextReady ? (
        <div className="ui-state ui-state-loading" role="status" style={{ minHeight: 240 }}>
          Đang tải đúng dữ liệu JOB của nhân viên và kỳ commission đã chọn…
        </div>
      ) : <div className="ui-card" style={{ margin: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', background: 'linear-gradient(135deg,#eff6ff,#dbeafe)', border: '1px solid #93c5fd', borderRadius: 14, padding: '14px 18px' }}>
          <span style={{ fontSize: 24 }}>🔒</span>
          <div style={{ flex: 1, minWidth: 240 }}><div style={{ fontWeight: 800, fontSize: 16, color: '#1e3a8a' }}>Chi tiết JOB để giữ bonus: {selectedRep}</div><div style={{ fontSize: 13, color: '#3b82f6', marginTop: 4 }}>Hiển thị đầy đủ dữ liệu Job PnL · <b>{walletJobs.length} JOBs</b> · <b>{lockedJobs.length} JOB đang giữ thủ công</b></div></div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}><div style={{ background: 'linear-gradient(135deg,#065f46,#059669)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}><div style={{ fontSize: 9, fontWeight: 700, opacity: .8 }}>TỔNG P&L KỲ/QUÝ</div><div style={{ fontSize: 15, fontWeight: 800 }}>{money(totalPnL)}</div></div><div style={{ background: 'linear-gradient(135deg,#1e3a8a,#2563eb)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}><div style={{ fontSize: 9, fontWeight: 700, opacity: .8 }}>TỔNG THƯỞNG QUÝ</div><div style={{ fontSize: 15, fontWeight: 800 }}>{money(selectedWallet?.total_bonus_quarter ?? periodTotals.reduce((sum, period) => sum + period.totalBonusQuarter, 0))}</div></div><div style={{ background: 'linear-gradient(135deg,#9a3412,#ea580c)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}><div style={{ fontSize: 9, fontWeight: 700, opacity: .8 }}>GIỮ THỦ CÔNG</div><div style={{ fontSize: 15, fontWeight: 800 }}>{money(lockedJobs.reduce((sum, job) => sum + job.manualHeld, 0))}</div></div></div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '14px 0' }}><input className="ui-input" style={{ flex: '1 1 300px' }} placeholder="Tìm JOB, khách hàng, HBL/MBL, shipper, consignee..." value={jobSearch} onChange={event => setJobSearch(event.target.value)} /><label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600 }}><input type="checkbox" checked={lockedOnly} onChange={event => setLockedOnly(event.target.checked)} /> Chỉ JOB đang giữ thủ công</label></div>
        {(() => {
          const job = walletJobs.find(item => item.id === selectedJobId)
          const edit = job ? jobEdits[job.id] : undefined
          if (!job || !edit || normalizedPayment(job.paymentReceived) !== 'NO' || job.paymentHeld <= 0) return null
          const targetMonths = job.nextReleasePayoutPeriods || []
          return <div className="ui-card" style={{ margin: '0 0 14px', padding: 12, background: '#fffbeb', borderColor: '#fcd34d' }}>
            <strong>Tháng dự kiến trả một lần</strong>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
              <span style={{ color: '#92400e', fontWeight: 700 }}>Đang giữ: {money(job.paymentHeld)}</span>
              <select className="ui-input" disabled={busy || isBonusLocked} style={{ width: 150 }} value={edit.releasePayoutPeriod} onChange={event => updateJobEdit(job.id, { releasePayoutPeriod: event.target.value })}>{targetMonths.map(month => <option key={month} value={month}>{month}</option>)}</select>
              <button className="ui-button ui-button-secondary" disabled={busy || isBonusLocked} onClick={() => void saveHeldReleasePlan(job)}>Lưu tháng trả</button>
            </div>
            <small style={{ display: 'block', marginTop: 7, color: '#78350f' }}>Ba tháng kỳ kế tiếp: {targetMonths.join(' · ') || 'Chưa xác định'}. Sales báo thanh toán, kế toán xác minh, sau đó lập lệnh ở hàng đợi phía trên.</small>
          </div>
        })()}
        <div style={{ border: '1px solid #cbd5e1', borderRadius: 14, overflow: 'auto', maxHeight: 540 }}>
          <table style={{ borderCollapse: 'collapse', fontSize: 12, whiteSpace: 'nowrap' }}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}><tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}><th style={cellStyle(42)}>#</th><th style={cellStyle(170)}>KỲ/QUÝ</th>{JOB_COLUMNS.map(col => <th key={col.key} style={cellStyle(col.width, col.numeric)}>{col.label}</th>)}<th style={cellStyle(130, true)}>BONUS RÒNG</th><th style={cellStyle(130, true)}>GIỮ TỰ ĐỘNG</th><th style={cellStyle(145, true)}>GIỮ THỦ CÔNG</th><th style={cellStyle(120, true)}>ĐÃ LẬP LỊCH</th><th style={cellStyle(120, true)}>KHẢ DỤNG</th><th style={cellStyle(120, true)}>ĐÃ TRẢ</th><th style={cellStyle(220)}>REMARK</th><th style={cellStyle(110)}>LƯU</th></tr></thead>
            <tbody>{filteredJobs.map((job, index) => {
              const isSelected = job.id === selectedJobId
              const edit = jobEdits[job.id] || { paymentReceived: normalizedPayment(job.paymentReceived), manualHeld: money(job.manualHeld), remark: job.remark || '', commandNote: '', releasePayoutPeriod: job.nextReleasePayoutPeriods?.[0] || currentMonth() }
              const preview = getJobPreview(job, edit)
              const isNotificationTarget = job.id === notificationHighlightJobId
              return <tr id={`commission-job-${job.id}`} data-job-id={job.id} key={job.id} onClick={() => setSelectedJobId(job.id)} style={{ cursor: 'pointer', scrollMarginTop: 120, background: isNotificationTarget ? '#fef3c7' : isSelected ? '#dbeafe' : index % 2 === 0 ? '#fff' : '#f8fafc', borderBottom: '1px solid #cbd5e1', outline: isNotificationTarget ? '3px solid #f59e0b' : undefined, outlineOffset: isNotificationTarget ? -3 : undefined, transition: 'background-color 240ms ease, outline-color 240ms ease' }}>
                <td style={cellStyle(42)}>{index + 1}</td><td style={{ ...cellStyle(170), color: '#1d4ed8', fontWeight: 700 }}>{job.periodLabel}</td>
                {JOB_COLUMNS.map(col => { const value = job[col.key]; const isPnl = col.key === 'profitLoss'; const isPayment = col.key === 'paymentReceived'; return <td key={col.key} title={String(value ?? '')} style={{ ...cellStyle(col.width, col.numeric), fontWeight: isPnl || col.key === 'jobNo' ? 700 : col.key === 'salesRep' ? 600 : 400, color: isPnl ? Number(value) >= 0 ? '#15803d' : '#b91c1c' : '#000' }}>{isPayment ? <><b style={{ color: normalizedPayment(job.paymentReceived) === 'YES' ? '#047857' : '#b45309' }}>{normalizedPayment(job.paymentReceived)}</b><small style={{ display: 'block', color: '#64748b' }}>{job.paymentVerificationStatus === 'PENDING' ? 'Chờ kế toán' : job.paymentVerificationStatus === 'VERIFIED' ? 'Đã xác minh' : job.paymentVerificationStatus === 'COMMAND_CREATED' ? 'Đã lập lệnh' : ''}</small></> : col.numeric ? (col.key === 'wt' || col.key === 'vol' ? decimal(Number(value)) : money(Number(value))) : (value === null || value === undefined || value === '' ? '—' : String(value))}</td> })}
                <td style={{ ...cellStyle(130, true), color: '#1d4ed8', fontWeight: 700 }}>{money(job.earned)}</td><td style={{ ...cellStyle(130, true), color: '#b45309', background: preview.changed ? '#fff7ed' : undefined, fontWeight: preview.changed ? 800 : 400 }}>{money(preview.paymentHeld)}{preview.changed && <small style={{ display: 'block', fontSize: 9 }}>Dự kiến</small>}</td>
                <td style={cellStyle(145, true)}><input aria-label={`Giữ thủ công ${job.jobNo}`} value={edit.manualHeld} disabled={busy || isBonusLocked || !job.hasWalletEntry} inputMode="numeric" onClick={event => event.stopPropagation()} onChange={event => updateJobEdit(job.id, { manualHeld: formatMoneyInput(event.target.value) })} style={{ width: 120, textAlign: 'right', border: '1px solid #93c5fd', borderRadius: 6, padding: '4px 6px', color: parseMoneyInput(edit.manualHeld) > 0 ? '#b91c1c' : '#475569', fontWeight: 800, background: '#fff' }} /></td>
                <td style={cellStyle(120, true)}>{money(job.scheduled)}</td><td style={{ ...cellStyle(120, true), color: preview.available < 0 ? '#b91c1c' : '#047857', background: preview.changed ? '#ecfdf5' : undefined, fontWeight: 700 }}>{money(preview.available)}{preview.changed && <small style={{ display: 'block', fontSize: 9 }}>Dự kiến</small>}</td><td style={cellStyle(120, true)}>{money(job.paid)}</td>
                <td style={cellStyle(220)}><input aria-label={`Remark ${job.jobNo}`} value={edit.remark} disabled={busy || isBonusLocked} onClick={event => event.stopPropagation()} onChange={event => updateJobEdit(job.id, { remark: event.target.value })} placeholder="Lý do chỉnh sửa" style={{ width: 195, border: '1px solid #93c5fd', borderRadius: 6, padding: '4px 6px', background: '#fff' }} /></td>
                <td style={cellStyle(110)}><button className="ui-button ui-button-primary" style={{ minHeight: 30, padding: '4px 10px', fontSize: 11 }} disabled={busy || isBonusLocked} onClick={event => { event.stopPropagation(); void saveJobEdit(job) }}>Lưu</button></td>
              </tr>
            })}</tbody>
            <tfoot><tr style={{ background: '#e2e8f0', fontWeight: 800, position: 'sticky', bottom: 0, borderTop: '2px solid #cbd5e1' }}><td style={cellStyle(42)}>Σ</td><td style={cellStyle(170)}>{filteredJobs.length} JOBs</td>{JOB_COLUMNS.map(col => <td key={col.key} style={cellStyle(col.width, col.numeric)}>{col.key === 'profitLoss' ? money(filteredJobs.reduce((sum, job) => sum + job.profitLoss, 0)) : ''}</td>)}<td style={cellStyle(130, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.earned, 0))}</td><td style={cellStyle(130, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.paymentHeld, 0))}</td><td style={cellStyle(145, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.manualHeld, 0))}</td><td style={cellStyle(120, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.scheduled, 0))}</td><td style={cellStyle(120, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.available, 0))}</td><td style={cellStyle(120, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.paid, 0))}</td><td style={cellStyle(220)} /><td style={cellStyle(110)} /></tr></tfoot>
          </table>
        </div>
      </div>}
            </div>
            <footer style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '10px 18px', borderTop: '1px solid #dbe3ef', background: '#f8fafc' }}>
              <small style={{ color: isBonusLocked ? '#b91c1c' : '#64748b', fontWeight: isBonusLocked ? 700 : 500 }}>{isBonusLocked ? 'Bảng bonus đã khóa — không thể chỉnh sửa.' : 'Các thay đổi chỉ được ghi nhận sau khi nhấn Lưu tại đúng dòng JOB.'}</small>
              <button type="button" className="ui-button ui-button-secondary" onClick={onJobEditorClose}>Đóng sửa thủ công</button>
            </footer>
          </section>
        </div>,
        document.body,
      )}
      <h4 style={{ margin: '20px 0 8px', order: 46 }}>Lịch chi trả</h4><div className="ui-table-wrap" style={{ order: 47 }}><table className="ui-table"><thead><tr><th>Tháng trả</th><th>Số tiền</th><th>Trạng thái</th><th /></tr></thead><tbody>{schedules.map(item => <tr key={item.id}><td>{item.payout_period}</td><td>{money(item.total_amount)}</td><td>{item.status}{item.is_period_scoped === false && <small style={{ display: 'block', color: '#b45309' }}>Lịch chung nhiều kỳ</small>}</td><td>{item.status === 'SCHEDULED' && <>{item.is_period_scoped === false ? <small style={{ color: '#64748b' }}>Mở tất cả ví để xử lý lịch chung</small> : <><button className="ui-button ui-button-primary" disabled={busy || isBonusLocked} onClick={() => call(`/api/commission/wallet/schedules/${item.id}/pay`, {})}>Chi trả</button> <button className="ui-button ui-button-secondary" disabled={busy || isBonusLocked} onClick={() => call(`/api/commission/wallet/schedules/${item.id}/cancel`, {})}>Hủy lịch</button></>}</>}</td></tr>)}</tbody></table></div>
      <div className="ui-card" style={{ marginTop: 16, order: 50, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div><h4 style={{ margin: 0 }}>Lịch sử sổ cái</h4><small style={{ color: '#64748b' }}>Đang ẩn chi tiết để giao diện gọn hơn · {ledger.length} giao dịch</small></div>
        <button className="ui-button ui-button-secondary" onClick={() => setLedgerOpen(true)}>Xem lịch sử sổ cái</button>
      </div>
    </>}
  </section>
  {ledgerOpen && createPortal(
    <div className="ui-modal-backdrop" role="presentation" onMouseDown={() => setLedgerOpen(false)} style={{ zIndex: 3000 }}>
      <section role="dialog" aria-modal="true" aria-labelledby="commission-ledger-title" onMouseDown={event => event.stopPropagation()} style={{ width: 'min(96vw, 1500px)', maxHeight: '88vh', background: '#fff', borderRadius: 16, boxShadow: '0 24px 80px rgba(15,23,42,.3)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '16px 20px', borderBottom: '1px solid #dbe3ef' }}>
          <div><h3 id="commission-ledger-title" style={{ margin: 0 }}>Lịch sử sổ cái</h3><small style={{ color: '#64748b' }}>{selectedRep} · {selectedPeriodLabel || 'Tất cả kỳ'} · {ledger.length} giao dịch</small></div>
          <button ref={ledgerCloseButtonRef} className="ui-button ui-button-secondary" aria-label="Đóng lịch sử sổ cái" onClick={() => setLedgerOpen(false)}>Đóng</button>
        </header>
        <div className="ui-table-wrap" style={{ overflow: 'auto', margin: 16, border: '1px solid #dbe3ef', borderRadius: 10 }}><table className="ui-table"><thead><tr><th style={{ position: 'sticky', top: 0, zIndex: 1 }}>Thời điểm</th><th style={{ position: 'sticky', top: 0, zIndex: 1 }}>JOB đang tác động</th><th style={{ position: 'sticky', top: 0, zIndex: 1 }}>Khách hàng</th><th style={{ position: 'sticky', top: 0, zIndex: 1 }}>Đang giữ của JOB</th><th style={{ position: 'sticky', top: 0, zIndex: 1 }}>Giao dịch</th><th style={{ position: 'sticky', top: 0, zIndex: 1 }}>Số tiền</th><th style={{ position: 'sticky', top: 0, zIndex: 1 }}>Tháng đích</th><th style={{ position: 'sticky', top: 0, zIndex: 1 }}>Lý do</th></tr></thead><tbody>{ledger.map(item => <tr key={item.id}><td>{item.created_at ? new Date(item.created_at).toLocaleString('vi-VN') : ''}</td><td><b>{item.job_no || 'Điều chỉnh kỳ'}</b></td><td>{item.job_customer || '—'}</td><td style={{ color: Number(item.current_held_amount || 0) > 0 ? '#b45309' : '#64748b', fontWeight: 700 }}>{item.job_id ? money(Number(item.current_held_amount || 0)) : '—'}</td><td>{item.entry_type}</td><td style={{ color: item.amount < 0 ? '#b91c1c' : '#047857' }}>{money(item.amount)}</td><td>{item.payout_period || '—'}</td><td>{item.note || item.reason_code || '—'}</td></tr>)}</tbody></table></div>
      </section>
    </div>,
    document.body,
  )}
  </>
}
