import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useConfirmDialog } from '../../shared/ui/ConfirmDialog'
import { credentialedFetch } from '../../shared/api/credentialedFetch'
import { formatVnd, formatVietnameseNumber, parseVndInput } from '../../shared/utils/currency'
import { AppIcon } from '../../shared/ui/AppIcon'
import { MonthYearSelect } from '../../shared/ui/MonthYearSelect'
import { VndInput } from '../../shared/ui/VndInput'
import { BrandedDateInput } from '../../shared/ui/BrandedDateInput'

type WalletJob = { job_id: number | null; job_no: string; period_id?: number; period_label?: string; earned: number; manual_credit?: number; manual_decrease?: number; held: number; payment_held?: number; manual_held?: number; scheduled: number; transferred?: number; available: number; paid: number }
type WalletPeriodSummary = { period_id: number; period_label: string; payout_periods?: string[]; total_profit_loss: number; total_bonus_quarter: number; monthly_bonus: number }
type Wallet = { sales_rep: string; period_id: number; period_labels?: string[]; period_summaries?: WalletPeriodSummary[]; total_bonus_quarter?: number; total_earned: number; manual_credit_amount: number; manual_decrease_amount: number; held_amount: number; scheduled_amount: number; transferred_amount: number; available_amount: number; paid_amount: number; recoverable_amount: number; jobs: WalletJob[] }
type ScheduleJob = { job_id: number; job_no: string; period_id: number; period_label: string; amount: number }
type Schedule = { id: number; sales_rep: string; payout_period: string; status: string; total_amount: number; jobs?: ScheduleJob[]; note?: string | null; source_period_ids?: number[]; is_period_scoped?: boolean }
type Ledger = { id: number; job_id?: number | null; job_no?: string | null; job_customer?: string | null; job_display_name?: string | null; current_held_amount?: number; current_payment_held_amount?: number; current_manual_held_amount?: number; entry_type: string; amount: number; payout_period?: string | null; reason_code?: string | null; note?: string | null; created_at?: string | null }
type BonusLock = { locked: boolean; period_id: number; sales_rep: string; reason?: string | null; locked_by?: string | null; locked_at?: string | null }
type WalletJobDetail = {
  id: number; periodId: number; periodLabel: string; jobNo: string; jobDate?: string | null; hbl?: string | null; mbl?: string | null
  customer?: string | null; vendor?: string | null; salesRep?: string | null; shipper?: string | null; consignee?: string | null
  subType?: string | null; containerString?: string | null; wt?: number | null; vol?: number | null; carrierBookingNo?: string | null
  por?: string | null; finalDestination?: string | null; realizedRevenue: number; unrealizedRevenue: number; realizedCost: number
  unrealizedCost: number; profitLoss: number; containerPicked?: string | null; paymentReceived?: string | null; receivableAmount?: number | null; balanceAmount?: number | null; paymentReceivedAmount?: number | null; holdBonusPercent?: number | null; holdBonusAmount?: number | null
  periodProfitLoss?: number; periodTarget?: number; periodCoefficient?: number; periodTotalBonusQuarter?: number; periodMonthlyBonus?: number; customerPaymentPeriods?: string[]; nextReleasePayoutPeriods?: string[]; heldReleaseMode?: 'NEXT_QUARTER_LUMP' | 'NEXT_QUARTER_SPLIT'; heldReleasePayoutPeriod?: string | null
  earned: number; calculationEarned?: number; manualCredit: number; manualDecrease: number; paymentHeld: number; manualHeld: number; held: number; scheduled: number; transferred: number; available: number; paid: number; hasWalletEntry: boolean; remark?: string | null
  paymentVerificationId?: number | null; paymentVerificationStatus?: 'PENDING' | 'VERIFIED' | 'REJECTED' | 'COMMAND_CREATED' | null; paymentReportNote?: string | null; paymentVerificationNote?: string | null; paymentCommandNote?: string | null; paymentReportedAt?: string | null
}
type JobEdit = { paymentReceived: 'YES' | 'NO'; paymentReceivedAmount: number; manualHeld: string; remark: string; commandNote: string; releasePayoutPeriod: string }
type WalletFocus = {
  periodId: number
  periodLabel: string
  salesRep: string
  jobId?: number
  requestKey?: number
  target?: 'accounting-queue' | 'job-detail'
} | null
type ScopeTab = 'all' | 'user'
type NetBonusTooltipState = {
  kind: 'header' | 'job'
  anchor: { top: number; right: number; bottom: number; left: number; width: number }
  job?: WalletJobDetail
}
type PaymentMonthPrompt = { jobId: number; paymentDate: string; payoutMonths: string[] }
type LoadOptions = { preserveJobContext?: boolean }

type JobColumn = { key: keyof WalletJobDetail; label: string; numeric?: boolean; width: number }
const JOB_COLUMNS: JobColumn[] = [
  { key: 'jobNo', label: 'JOB #', width: 92 }, { key: 'jobDate', label: 'JOB DATE', width: 82 },
  { key: 'hbl', label: 'HBL/HAWB', width: 112 }, { key: 'mbl', label: 'MBL', width: 112 },
  { key: 'customer', label: 'CUSTOMER', width: 142 }, { key: 'vendor', label: 'VENDOR', width: 122 },
  { key: 'salesRep', label: 'SALES REP', width: 108 }, { key: 'shipper', label: 'SHIPPER', width: 126 },
  { key: 'consignee', label: 'CONSIGNEE', width: 126 }, { key: 'subType', label: 'SUBTYPE', width: 82 },
  { key: 'containerString', label: 'CONTAINER', width: 104 }, { key: 'wt', label: 'WT', numeric: true, width: 68 },
  { key: 'vol', label: 'VOL', numeric: true, width: 68 }, { key: 'carrierBookingNo', label: 'BOOKING #', width: 108 },
  { key: 'por', label: 'POR', width: 82 }, { key: 'finalDestination', label: 'FINAL DEST.', width: 106 },
  { key: 'realizedRevenue', label: 'REALIZED REV', numeric: true, width: 110 }, { key: 'unrealizedRevenue', label: 'UNREALIZED REV', numeric: true, width: 116 },
  { key: 'realizedCost', label: 'REALIZED COST', numeric: true, width: 108 }, { key: 'unrealizedCost', label: 'UNREALIZED COST', numeric: true, width: 114 },
  { key: 'profitLoss', label: 'PROFIT/LOSS', numeric: true, width: 106 }, { key: 'containerPicked', label: 'CONTAINER PICKED', width: 102 },
  { key: 'paymentReceived', label: 'PAYMENT RECEIVED', width: 224 },
]

const MANUAL_JOB_WIDTHS = {
  index: 38,
  period: 132,
  holdPercent: 128,
  bonus: 110,
  automaticHeld: 110,
  manualHeld: 124,
  scheduled: 100,
  available: 104,
  paid: 100,
  remark: 168,
  save: 76,
} as const

const money = (value: number) => formatVnd(value || 0)
const decimal = (value: number) => formatVietnameseNumber(value || 0, { maximumFractionDigits: 3 })
const currentMonth = () => new Date().toISOString().slice(0, 7)
const parseMoneyInput = (value: string) => parseVndInput(value)
const formatMoneyInput = (value: string) => {
  const numeric = value.replace(/\D/g, '')
  return numeric ? money(Number(numeric)) : ''
}
const normalizedPayment = (value?: string | null): 'YES' | 'NO' => String(value || 'NO').toUpperCase() === 'YES' ? 'YES' : 'NO'
const paymentMonthLabel = (value: string) => {
  const [year, month] = value.split('-')
  return month && year ? `Tháng ${month}/${year}` : value
}
const eligiblePayoutMonths = (commissionMonths: string[], payoutMonths: string[], paymentMonth: string, paymentDate: string) => {
  const paymentIndex = commissionMonths.indexOf(paymentMonth)
  const paymentDay = Number(paymentDate.slice(8, 10))
  if (paymentIndex < 0 || paymentDate.slice(0, 7) !== paymentMonth || !paymentDay) return []
  const payoutStartIndex = paymentDay <= 25 ? Math.max(0, paymentIndex - 1) : paymentIndex
  return payoutMonths.slice(payoutStartIndex)
}
const fixedHoldBonusAmount = (job: WalletJobDetail) => Number(
  job.holdBonusAmount ?? Math.round(Math.max(0, Number(job.profitLoss || 0)) * 30) / 100,
)

function NetBonusFormulaContent({ job, jobs }: { job: WalletJobDetail; jobs: WalletJobDetail[] }) {
  const periodProfitLoss = Number(job.periodProfitLoss || 0)
  const periodProfitSale = periodProfitLoss * 0.95
  const target = Number(job.periodTarget || 0)
  const difference = Math.max(0, periodProfitSale - target)
  const referenceLevel = Number(job.periodCoefficient || 0)
  const quarterBonus = difference > 0 ? Number(job.periodTotalBonusQuarter || 0) : 0
  const effectiveRate = difference > 0 ? quarterBonus / difference : 0
  const monthlyBonus = difference > 0 ? Number(job.periodMonthlyBonus || quarterBonus / 3) : 0
  const positivePeriodProfit = jobs
    .filter(item => item.periodId === job.periodId && item.salesRep === job.salesRep)
    .reduce((sum, item) => sum + Math.max(0, Number(item.profitLoss || 0)), 0)
  const positiveJobProfit = Math.max(0, Number(job.profitLoss || 0))
  const allocationRate = positivePeriodProfit > 0 ? positiveJobProfit / positivePeriodProfit : 0
  const calculatedJobBonus = Number(
    job.calculationEarned ?? Math.round(monthlyBonus * allocationRate * 100) / 100,
  )
  const manualCredit = Number(job.manualCredit || 0)
  const manualDecrease = Number(job.manualDecrease || 0)

  return (
    <div>
      <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>
        Công thức Bonus ròng · {job.jobNo}
      </strong>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, color: '#cbd5e1', fontSize: 11 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Profit/Loss gốc</span><b style={{ fontFamily: 'monospace' }}>{money(periodProfitLoss)}</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Profit Sale (95%)</span><b style={{ fontFamily: 'monospace' }}>{money(periodProfitSale)}</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Target</span><b style={{ fontFamily: 'monospace' }}>{money(target)}</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Chênh lệch</span><b style={{ fontFamily: 'monospace' }}>{money(difference)}</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: '#a78bfa' }}><span>Level tham chiếu</span><b>{referenceLevel > 8 ? '> 8' : referenceLevel.toFixed(2)}</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: '#34d399' }}><span>Tỷ lệ thưởng hiệu dụng</span><b>{decimal(effectiveRate * 100)}%</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Tổng thưởng quý</span><b style={{ fontFamily: 'monospace' }}>{money(quarterBonus)}</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Thưởng tháng</span><b style={{ fontFamily: 'monospace' }}>{money(monthlyBonus)}</b></div>
        <div style={{ borderTop: '1px solid #334155', paddingTop: 6, display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Tỷ trọng JOB</span><b>{money(positiveJobProfit)} / {money(positivePeriodProfit)} = {decimal(allocationRate * 100)}%</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Bonus theo công thức JOB</span><b style={{ fontFamily: 'monospace' }}>{money(calculatedJobBonus)}</b></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Điều chỉnh tăng / giảm</span><b style={{ fontFamily: 'monospace' }}>+{money(manualCredit)} / −{money(manualDecrease)}</b></div>
        <div style={{ borderTop: '1px solid #334155', paddingTop: 6, display: 'flex', justifyContent: 'space-between', gap: 12, color: '#38bdf8' }}><span style={{ fontWeight: 800 }}>Bonus ròng</span><b style={{ fontFamily: 'monospace' }}>{money(job.earned)}</b></div>
        <div style={{ color: '#94a3b8', fontSize: 11, fontStyle: 'italic', lineHeight: 1.4 }}>
          Hệ số được áp dụng ở cấp kỳ trước khi thưởng tháng được phân bổ cho từng JOB theo tỷ trọng Profit/Loss dương.
        </div>
      </div>
    </div>
  )
}

function NetBonusFloatingTooltip({ tooltip, jobs }: { tooltip: NetBonusTooltipState | null; jobs: WalletJobDetail[] }) {
  if (!tooltip || typeof document === 'undefined') return null

  const width = tooltip.kind === 'job' ? 340 : 310
  const estimatedHeight = tooltip.kind === 'job' ? 330 : 205
  const viewportMargin = 10
  const left = Math.max(
    viewportMargin,
    Math.min(window.innerWidth - width - viewportMargin, tooltip.anchor.left + tooltip.anchor.width / 2 - width / 2),
  )
  const roomAbove = tooltip.anchor.top - viewportMargin
  const top = roomAbove >= estimatedHeight + 8
    ? tooltip.anchor.top - estimatedHeight - 8
    : Math.min(window.innerHeight - estimatedHeight - viewportMargin, tooltip.anchor.bottom + 8)

  return createPortal(
    <div
      role="tooltip"
      style={{
        position: 'fixed',
        left,
        top: Math.max(viewportMargin, top),
        width,
        zIndex: 10000,
        padding: '12px 14px',
        boxSizing: 'border-box',
        borderRadius: 8,
        background: '#1e293b',
        color: '#f8fafc',
        boxShadow: '0 12px 30px rgba(15, 23, 42, .35)',
        textAlign: 'left',
        whiteSpace: 'normal',
        pointerEvents: 'none',
      }}
    >
      {tooltip.kind === 'job' && tooltip.job ? (
        <NetBonusFormulaContent job={tooltip.job} jobs={jobs} />
      ) : (
        <>
          <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>Công thức tính Bonus ròng</strong>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7, color: '#cbd5e1', fontSize: 11 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Profit Sale</span><b>Profit/Loss × 95%</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Chênh lệch</span><b>max(0, Profit Sale − Target)</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Tổng thưởng quý</span><b>Chênh lệch × Hệ số</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Thưởng tháng</span><b>Tổng thưởng quý / 3</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Bonus JOB</span><b style={{ textAlign: 'right' }}>Thưởng tháng × tỷ trọng P/L dương của JOB</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, borderTop: '1px solid #334155', paddingTop: 6, color: '#38bdf8' }}><span style={{ fontWeight: 800 }}>Bonus ròng</span><b>Bonus JOB + tăng − giảm thủ công</b></div>
            <div style={{ color: '#94a3b8', fontSize: 11, fontStyle: 'italic' }}>* Có áp dụng hệ số bonus; hệ số được tính ở cấp kỳ trước khi phân bổ xuống JOB.</div>
          </div>
        </>
      )}
    </div>,
    document.body,
  )
}

export function BonusFunnelPanel({ apiBase, token, focus, refreshVersion = 0, onDataChanged, jobEditorOpen = false, onJobEditorClose }: { apiBase: string; token: string | null; focus?: WalletFocus; refreshVersion?: number; onDataChanged?: () => void | Promise<void>; jobEditorOpen?: boolean; onJobEditorClose?: () => void }) {
  const confirm = useConfirmDialog()
  const headers = useMemo((): Record<string, string> => token ? { Authorization: `Bearer ${token}` } : {}, [token])
  const [wallets, setWallets] = useState<Wallet[]>([])
  const [walletJobs, setWalletJobs] = useState<WalletJobDetail[]>([])
  const [allWalletJobs, setAllWalletJobs] = useState<WalletJobDetail[]>([])
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
  const [scheduleToCancel, setScheduleToCancel] = useState<Schedule | null>(null)
  const [scheduleCancelReason, setScheduleCancelReason] = useState('')
  const [paymentMonthPrompt, setPaymentMonthPrompt] = useState<PaymentMonthPrompt | null>(null)
  const [heldScope, setHeldScope] = useState<ScopeTab>('all')
  const [scheduleScope, setScheduleScope] = useState<ScopeTab>('all')
  const [netBonusTooltip, setNetBonusTooltip] = useState<NetBonusTooltipState | null>(null)
  const ledgerCloseButtonRef = useRef<HTMLButtonElement>(null)
  const jobEditorCloseButtonRef = useRef<HTMLButtonElement>(null)
  const loadRequestId = useRef(0)
  const selectedWallet = wallets.find(item => item.sales_rep === selectedRep && item.period_id === selectedPeriodId) || wallets.find(item => item.sales_rep === selectedRep)
  const isBonusLocked = selectedPeriodId != null && bonusLock?.locked === true

  function showNetBonusTooltip(kind: NetBonusTooltipState['kind'], anchor: HTMLElement, job?: WalletJobDetail) {
    const rect = anchor.getBoundingClientRect()
    setNetBonusTooltip({
      kind,
      job,
      anchor: { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, width: rect.width },
    })
  }

  async function load(rep = selectedRep, periodId = selectedPeriodId, options: LoadOptions = {}) {
    const requestId = ++loadRequestId.current
    if (!options.preserveJobContext) setLoadedJobContext(null)
    const params = new URLSearchParams()
    if (rep) params.set('sales_rep', rep)
    if (periodId != null) params.set('period_id', String(periodId))
    const query = params.toString() ? `?${params.toString()}` : ''
    const lockRequest = rep && periodId != null
      ? credentialedFetch(`${apiBase}/api/commission/wallet/lock?sales_rep=${encodeURIComponent(rep)}&period_id=${periodId}`, { headers })
      : Promise.resolve(null)
    const allJobsRequest = rep
      ? credentialedFetch(`${apiBase}/api/commission/wallet/jobs`, { headers })
      : Promise.resolve(null)
    const [walletRes, scheduleRes, ledgerRes, jobsRes, allJobsRes, lockRes] = await Promise.all([
      credentialedFetch(`${apiBase}/api/commission/wallet${query}`, { headers }),
      credentialedFetch(`${apiBase}/api/commission/wallet/schedules`, { headers }),
      credentialedFetch(`${apiBase}/api/commission/wallet/ledger${query}`, { headers }),
      credentialedFetch(`${apiBase}/api/commission/wallet/jobs${query}`, { headers }),
      allJobsRequest,
      lockRequest,
    ])
    // A notification can change the selected period while the initial unfiltered
    // request is still running. Ignore that stale response so it cannot replace
    // the exact employee/period/JOB selected by the notification.
    if (requestId !== loadRequestId.current) return
    if (walletRes.ok) {
      const data: Wallet[] = await walletRes.json()
      setWallets(data)
    }
    if (scheduleRes.ok) setSchedules(await scheduleRes.json())
    if (ledgerRes.ok) setLedger(await ledgerRes.json())
    if (jobsRes.ok) {
      const data: WalletJobDetail[] = await jobsRes.json()
      setWalletJobs(data)
      if (!rep) setAllWalletJobs(data)
      setLoadedJobContext({ salesRep: rep, periodId })
    }
    if (allJobsRes?.ok) setAllWalletJobs(await allJobsRes.json())
    setBonusLock(lockRes && lockRes.ok ? await lockRes.json() : null)
  }

  useEffect(() => { void load() }, [])
  useEffect(() => { if (selectedRep) void load(selectedRep, selectedPeriodId) }, [selectedRep, selectedPeriodId])
  useEffect(() => {
    if (refreshVersion > 0) void load(selectedRep, selectedPeriodId)
  }, [refreshVersion])
  useEffect(() => {
    if (!selectedRep) {
      setHeldScope('all')
      setScheduleScope('all')
    }
  }, [selectedRep])
  useEffect(() => {
    if (!focus) {
      if (selectedRep || selectedPeriodId != null) {
        setSelectedRep('')
        setSelectedPeriodId(null)
        setSelectedPeriodLabel('')
        setSelectedJobId(null)
        setHeldScope('all')
        setScheduleScope('all')
        void load('', null)
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
    setHeldScope('user')
    setScheduleScope('user')
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
    const editableJobs = allWalletJobs.length ? allWalletJobs : walletJobs
    setJobEdits(Object.fromEntries(editableJobs.map(job => [job.id, {
      paymentReceived: String(job.paymentReceived || 'NO').toUpperCase() === 'YES' ? 'YES' : 'NO',
      paymentReceivedAmount: Number(job.paymentReceivedAmount || 0),
      manualHeld: money(job.manualHeld),
      remark: job.remark || '',
      commandNote: job.paymentCommandNote || '',
      releasePayoutPeriod: job.heldReleasePayoutPeriod || job.nextReleasePayoutPeriods?.[0] || currentMonth(),
    }])))
  }, [allWalletJobs, walletJobs])
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
  const actualHeldAmount = (job: WalletJobDetail) => Math.max(0, fixedHoldBonusAmount(job)) + Math.max(0, Number(job.manualHeld || 0))
  const heldJobs = walletJobs.filter(job => actualHeldAmount(job) > 0)
  const allHeldJobs = allWalletJobs.filter(job => actualHeldAmount(job) > 0)
  const visibleHeldJobs = heldScope === 'all' ? allHeldJobs : heldJobs
  const visibleSchedules = scheduleScope === 'all'
    ? schedules
    : schedules.filter(item => item.sales_rep === selectedRep)
  const heldActionsDisabled = busy || (heldScope === 'user' && isBonusLocked)
  const scheduleActionsDisabled = busy || (scheduleScope === 'user' && isBonusLocked)

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
      const res = await credentialedFetch(`${apiBase}${path}`, { method, headers: { 'Content-Type': 'application/json', ...headers }, body: body ? JSON.stringify(body) : undefined, suppressDataChanged: true })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể thực hiện thao tác.')
      setMessage(data.message || 'Đã cập nhật phễu thưởng.')
      await Promise.all([
        load(selectedRep, selectedPeriodId, { preserveJobContext: true }),
        onDataChanged?.(),
      ])
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

  async function createDirectPaymentCommand(job: WalletJobDetail) {
    const edit = jobEdits[job.id]
    if (!edit) return
    if (!edit.releasePayoutPeriod) return setMessage('Chọn tháng trả trước khi chi trả.')
    if (!await confirm({
      title: `Chi trả JOB ${job.jobNo}`,
      message: `Kế toán sẽ chủ động xác minh và lập lịch trả một lần vào tháng ${edit.releasePayoutPeriod}, kể cả khi nhân viên chưa gửi yêu cầu. Tiếp tục?`,
      confirmLabel: 'Chi trả',
    })) return
    await call(`/api/commission/periods/${job.periodId}/jobs/${job.id}/direct-payout-command`, {
      release_mode: 'NEXT_QUARTER_LUMP',
      release_payout_period: edit.releasePayoutPeriod,
      note: edit.commandNote || null,
    })
  }

  async function cancelSchedule() {
    if (!scheduleToCancel) return
    const reason = scheduleCancelReason.trim()
    if (!reason) return setMessage('Vui lòng nhập lý do hủy lịch chi trả.')
    const cancelled = await call(`/api/commission/wallet/schedules/${scheduleToCancel.id}/cancel`, { reason })
    if (cancelled) {
      setScheduleToCancel(null)
      setScheduleCancelReason('')
    }
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
    const currentAmount = Number(job.paymentReceivedAmount || 0)
    const paymentEvidenceChanged = edit.paymentReceived !== currentPayment || Math.abs(edit.paymentReceivedAmount - currentAmount) >= 0.01
    if (paymentEvidenceChanged) {
      const fullyPaid = edit.paymentReceived === 'YES' && edit.paymentReceivedAmount >= Math.max(0, Number(job.profitLoss || 0)) - 0.005
      if (fullyPaid) {
        paymentHeld = 0
        available = 0
      } else if (paymentHeld <= 0 && job.earned > 0) {
        paymentHeld = job.earned
        available = Math.max(0, job.earned - job.manualHeld - job.scheduled - job.paid)
      }
    }
    const manualDelta = parseMoneyInput(edit.manualHeld) - job.manualHeld
    return { paymentHeld: Math.max(0, paymentHeld), available: Math.max(0, available - manualDelta), changed: paymentEvidenceChanged || Math.abs(manualDelta) >= 0.01 }
  }

  async function saveJobEdit(job: WalletJobDetail, paymentMonth?: string, paymentDate?: string, paymentMonthConfirmed = false, payoutMonths?: string[]) {
    const edit = jobEdits[job.id]
    if (!edit || !selectedRep) return
    if (isBonusLocked) return setMessage('Bảng bonus đã khóa; không thể chỉnh sửa JOB.')
    const paymentChanged = edit.paymentReceived !== normalizedPayment(job.paymentReceived)
    const paymentAmountChanged = Math.abs(edit.paymentReceivedAmount - Number(job.paymentReceivedAmount || 0)) >= 0.01
    const remarkChanged = edit.remark.trim() !== (job.remark || '').trim()
    const targetManualHeld = parseMoneyInput(edit.manualHeld)
    const manualHoldChanged = Math.abs(targetManualHeld - job.manualHeld) >= 0.01
    const paymentEvidenceChanged = paymentChanged || (edit.paymentReceived === 'YES' && paymentAmountChanged)
    if (paymentEvidenceChanged && edit.paymentReceived === 'YES' && edit.paymentReceivedAmount <= 0) return setMessage(`Nhập số tiền đã trả của JOB ${job.jobNo} trước khi lưu.`)
    if (!paymentEvidenceChanged && !remarkChanged && !manualHoldChanged) return setMessage(`JOB ${job.jobNo} chưa có thay đổi.`)
    const willRemainHeld = edit.paymentReceived === 'NO' || edit.paymentReceivedAmount < Math.max(0, Number(job.profitLoss || 0)) - 0.005
    const currentFullyPaid = normalizedPayment(job.paymentReceived) === 'YES' && Number(job.paymentReceivedAmount || 0) >= Math.max(0, Number(job.profitLoss || 0)) - 0.005
    const needsPaymentMonth = paymentEvidenceChanged && edit.paymentReceived === 'YES' && (normalizedPayment(job.paymentReceived) === 'NO' || (!willRemainHeld && !currentFullyPaid))
    if (needsPaymentMonth && !paymentMonthConfirmed) {
      const months = job.customerPaymentPeriods || []
      if (months.length !== 3) return setMessage(`Không xác định được ba tháng thuộc kỳ Commission của JOB ${job.jobNo}.`)
      setPaymentMonthPrompt({ jobId: job.id, paymentDate: '', payoutMonths: [] })
      return
    }
    if (!paymentMonthConfirmed && !await confirm({ title: `Lưu chỉnh sửa JOB ${job.jobNo}`, message: `Payment Received: ${edit.paymentReceived}${edit.paymentReceived === 'YES' ? ` · Đã trả ${money(edit.paymentReceivedAmount)}` : ''}. ${willRemainHeld ? 'JOB chưa thanh toán đủ nên vẫn áp dụng Hold 30%.' : 'JOB đã thanh toán đủ nên Hold 30% sẽ được gỡ.'} Các cột tổng hợp và ví thưởng sẽ được đồng bộ ngay.`, confirmLabel: 'Lưu chỉnh sửa' })) return
    setBusy(true); setMessage('')
    try {
      if (paymentEvidenceChanged) {
        const paymentRes = await credentialedFetch(`${apiBase}/api/commission/periods/${job.periodId}/jobs/${job.id}/manual-payment`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify({ payment_received: edit.paymentReceived, payment_received_amount: edit.paymentReceived === 'YES' ? edit.paymentReceivedAmount : 0, payment_month: needsPaymentMonth ? paymentMonth : null, payment_date: needsPaymentMonth ? paymentDate : null, payout_months: needsPaymentMonth && !willRemainHeld ? payoutMonths : null, remark: edit.remark || null }), suppressDataChanged: true })
        const paymentData = await paymentRes.json()
        if (!paymentRes.ok) throw new Error(paymentData.detail || 'Không thể lưu Payment Received.')
      } else if (remarkChanged) {
        const remarkRes = await credentialedFetch(`${apiBase}/api/commission/periods/${job.periodId}/jobs/${job.id}/payment`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify({ payment_received: normalizedPayment(job.paymentReceived), remark: edit.remark || null }), suppressDataChanged: true })
        const remarkData = await remarkRes.json()
        if (!remarkRes.ok) throw new Error(remarkData.detail || 'Không thể lưu ghi chú JOB.')
      }
      if (manualHoldChanged) {
        const holdRes = await credentialedFetch(`${apiBase}/api/commission/wallet/jobs/${job.id}/manual-hold`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify({ sales_rep: selectedRep, manual_held_amount: targetManualHeld, remark: edit.remark || null }), suppressDataChanged: true })
        const holdData = await holdRes.json()
        if (!holdRes.ok) throw new Error(holdData.detail || 'Không thể cập nhật giữ thủ công.')
      }
      setMessage(`Đã lưu chỉnh sửa JOB ${job.jobNo}.`)
      await Promise.all([
        load(selectedRep, selectedPeriodId, { preserveJobContext: true }),
        onDataChanged?.(),
      ])
    } catch (error) { setMessage((error as Error).message) } finally { setBusy(false) }
  }

  const cellStyle = (width: number, numeric = false) => ({ padding: '6px 7px', boxSizing: 'border-box' as const, width, textAlign: numeric ? 'right' as const : 'left' as const, fontFamily: numeric ? 'monospace' : 'inherit', borderRight: '1px solid #cbd5e1', minWidth: width, maxWidth: width, overflow: 'hidden', textOverflow: 'ellipsis' as const })

  const confirmPaymentMonthSave = () => {
    if (!paymentMonthPrompt) return
    const job = walletJobs.find(item => item.id === paymentMonthPrompt.jobId)
    if (!job) return
    const selectedMonth = job.customerPaymentPeriods?.[1]
    if (!selectedMonth) return setMessage(`Không xác định được tháng giữa của kỳ Commission cho JOB ${job.jobNo}.`)
    if (!paymentMonthPrompt.paymentDate || paymentMonthPrompt.paymentDate.slice(0, 7) !== selectedMonth) return setMessage(`Chọn ngày khách hàng thanh toán trong ${paymentMonthLabel(selectedMonth)}.`)
    setPaymentMonthPrompt(null)
    void saveJobEdit(job, selectedMonth, paymentMonthPrompt.paymentDate, true, paymentMonthPrompt.payoutMonths)
  }

  return <>
  <section className="commission-funnel-panel" style={{ marginTop: 16, display: 'flex', flexDirection: 'column' }}>
    {selectedWallet && <div style={{ marginTop: 12, padding: '9px 12px', borderRadius: 8, background: '#eff6ff', color: '#1e3a5f', fontWeight: 600, order: 41 }}>
      {selectedPeriodId != null ? `Đang xem ví theo kỳ đã chọn: ${selectedPeriodLabel || selectedWallet.period_labels?.join(' · ') || 'Chưa xác định'} · ${selectedWallet.sales_rep}` : `Kỳ nguồn của ${selectedWallet.sales_rep}: ${selectedWallet.period_labels?.join(' · ') || 'Chưa xác định'}`} · Chi trả theo tháng: {selectedWallet.period_summaries?.flatMap(item => item.payout_periods || []).map(value => value.replace('-', '/')).join(' · ') || 'Chưa xác định'} · Đã chuyển kỳ sau: {money(selectedWallet.transferred_amount)}
    </div>}
    {isBonusLocked && <div className="ui-state ui-state-error" style={{ marginTop: 12, padding: 10, order: 42 }}>
      <AppIcon name="lock" size={16} /> Bảng bonus đã chốt. API đã chặn mọi thao tác làm thay đổi JOB, số dư, lịch chi trả và hoàn tác của kỳ này.
      {bonusLock?.locked_at && <small style={{ display: 'block', marginTop: 4 }}>Khóa lúc: {new Date(bonusLock.locked_at).toLocaleString('vi-VN')}{bonusLock.locked_by ? ` · bởi ${bonusLock.locked_by}` : ''}</small>}
    </div>}
    {message && <p className={message.includes('Không') || message.includes('Nhập') ? 'ui-state ui-state-error' : 'ui-state'} style={{ marginTop: 12, padding: 10, order: 43 }}>{message}</p>}
    <>
      <div className="commission-held-jobs-toolbar" style={{ marginTop: 16, order: 9 }}>
        <div className="commission-held-jobs-heading">
          <div className="commission-held-jobs-summary-row"><h4 style={{ margin: 0 }}>JOB đang giữ bonus &amp; hàng đợi kế toán</h4><b style={{ color: '#b45309' }}>Tổng đang giữ: {money(visibleHeldJobs.reduce((sum, job) => sum + actualHeldAmount(job), 0))}</b></div>
          <small style={{ color: '#92400e' }}>Mỗi JOB hiển thị theo thẻ riêng; Hold Bonus cố định bằng 30% Bonus ròng, cộng thêm phần giữ thủ công.</small>
        </div>
        <div className="commission-funnel-actions">
          {selectedPeriodId != null && <button className="ui-button ui-button-secondary" disabled={busy || !selectedRep || isBonusLocked} onClick={() => void lockBonusTable()}><AppIcon name="lock" size={16} /> {isBonusLocked ? 'Đã khóa bảng bonus' : 'Khóa bảng bonus'}</button>}
          <button className="ui-button ui-button-secondary" disabled={busy || !selectedRep || isBonusLocked} onClick={() => void undoLastWalletOperation()}><AppIcon name="undo" size={16} /> Hoàn tác bước gần nhất</button>
          <button className="ui-button ui-button-secondary" disabled={busy} onClick={() => load(selectedRep, selectedPeriodId)}><AppIcon name="refresh" size={16} /> Làm mới</button>
        </div>
      </div>
      <div className="commission-held-jobs-section" style={{ order: 10 }}>
        <div className="app-segmented-tabs commission-tablist commission-tablist--two" role="tablist" aria-label="Phạm vi JOB đang giữ">
          <button type="button" className="app-segmented-tab" role="tab" aria-selected={heldScope === 'all'} onClick={() => setHeldScope('all')}>Tổng <span>{allHeldJobs.length}</span></button>
          <button type="button" className="app-segmented-tab" role="tab" aria-selected={heldScope === 'user'} disabled={!selectedRep} title={selectedRep ? `Chỉ hiển thị JOB của ${selectedRep}` : 'Chọn một ví bonus để xem theo nhân viên'} onClick={() => setHeldScope('user')}>{selectedRep || 'Nhân viên'} <span>{heldJobs.length}</span></button>
        </div>
        <div className="commission-held-job-list" role="list" aria-label="Danh sách JOB đang giữ bonus">{visibleHeldJobs.map(job => {
          const edit = jobEdits[job.id]
          const state = job.paymentVerificationStatus || 'NONE'
          const months = job.nextReleasePayoutPeriods || []
          if (!edit) return null
          const isNotificationTarget = job.id === notificationHighlightJobId
          return <article
            role="listitem"
            className="commission-held-job-card"
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
          >
            <header className="commission-held-job-card__identity">
              <div><b>{job.jobNo}</b><small>{job.periodLabel} · {job.customer || '—'}</small></div>
              <span>{job.salesRep || '—'}</span>
            </header>
            <div className="commission-held-job-card__metrics">
              <div><small>Đã trả</small><b className="is-paid">{money(Number(job.paymentReceivedAmount || 0))}</b></div>
              <div><small>Hold 30%</small><b>{money(fixedHoldBonusAmount(job))}</b></div>
              <div><small>Giữ thủ công</small><b className="is-manual">{money(job.manualHeld)}</b></div>
              <div><small>Tổng đang giữ</small><b>{money(actualHeldAmount(job))}</b></div>
            </div>
            <div className="commission-held-job-card__workflow">
              <div className="commission-held-status-cell"><small>Trạng thái</small><b>{job.paymentHeld <= 0 ? 'Giữ thủ công' : state === 'NONE' ? 'Chưa yêu cầu' : state === 'PENDING' ? 'Chờ kế toán xác minh' : state === 'VERIFIED' ? 'Đã xác minh' : state === 'COMMAND_CREATED' ? 'Đã lập lệnh' : 'Đã từ chối'}</b><small>{job.paymentVerificationNote || job.paymentReportNote || ''}</small></div>
              <div className="commission-held-method-cell">{state === 'COMMAND_CREATED' && job.heldReleaseMode === 'NEXT_QUARTER_SPLIT' ? <small>Lịch cũ: chia đều 3 tháng</small> : <div className="commission-held-control-stack"><b>Trả một lần</b><MonthYearSelect id={`held-job-payout-${job.id}`} className="commission-held-month-year" compact showLabels={false} availablePeriods={months} disabled={heldActionsDisabled || !['NONE', 'REJECTED', 'VERIFIED'].includes(state) || job.paymentHeld <= 0} value={edit.releasePayoutPeriod} onChange={releasePayoutPeriod => updateJobEdit(job.id, { releasePayoutPeriod })} yearLabel={`Năm chi trả cho JOB ${job.jobNo}`} monthLabel={`Tháng chi trả cho JOB ${job.jobNo}`} /></div>}</div>
              <div className="commission-held-note-cell">{state === 'COMMAND_CREATED' ? <small>{job.paymentCommandNote || 'Kế toán đã lập lệnh chi trả theo JOB.'}</small> : <input className="ui-input" disabled={heldActionsDisabled || !['NONE', 'REJECTED', 'VERIFIED'].includes(state) || job.paymentHeld <= 0} value={edit.commandNote} onChange={event => updateJobEdit(job.id, { commandNote: event.target.value })} placeholder="Nguồn tiền / lý do chi trả" />}</div>
              <div className="commission-held-actions-cell"><div className="commission-held-row-actions">{job.paymentHeld <= 0 ? <span>Không cần xử lý</span> : state === 'NONE' || state === 'REJECTED' ? <button className="ui-button ui-button-primary" disabled={heldActionsDisabled} onClick={() => void createDirectPaymentCommand(job)}>Chi trả</button> : state === 'PENDING' ? <><button className="ui-button ui-button-primary" disabled={heldActionsDisabled} onClick={() => void reviewPayment(job, 'VERIFY')}>Xác minh</button><button className="ui-button ui-button-secondary" disabled={heldActionsDisabled} onClick={() => void reviewPayment(job, 'REJECT')}>Từ chối</button></> : state === 'VERIFIED' ? <button className="ui-button ui-button-primary" disabled={heldActionsDisabled} onClick={() => void createPaymentCommand(job)}>Lập lệnh chi trả</button> : <span>Đã tạo lịch</span>}</div></div>
            </div>
          </article>
        })}{visibleHeldJobs.length === 0 && <div className="commission-held-job-list__empty">Không có JOB đang giữ trong phạm vi này.</div>}</div>
      </div>

      {jobEditorOpen && createPortal(
        <div className="ui-modal-backdrop" role="presentation" onMouseDown={onJobEditorClose} style={{ zIndex: 3200, padding: 16 }}>
          <section role="dialog" aria-modal="true" aria-labelledby="commission-manual-job-editor-title" onMouseDown={event => event.stopPropagation()} style={{ width: 'min(96vw, 1780px)', height: 'min(92vh, 940px)', background: '#fff', borderRadius: 18, boxShadow: '0 28px 80px rgba(15,23,42,.38)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, padding: '12px 18px', borderBottom: '1px solid #dbe3ef', background: '#f8fafc' }}>
              <div>
                <h3 id="commission-manual-job-editor-title" style={{ margin: 0, color: '#0f172a' }}>Sửa thủ công JOB &amp; giữ bonus</h3>
                <small style={{ color: '#64748b' }}>{selectedRep} · {selectedPeriodLabel || 'Chưa xác định kỳ commission'}</small>
              </div>
              <button ref={jobEditorCloseButtonRef} type="button" className="ui-button ui-button-secondary app-close-button" aria-label="Đóng sửa thủ công JOB" onClick={onJobEditorClose} style={{ width: 38, minWidth: 38, height: 38, padding: 0, borderRadius: 10, lineHeight: 1 }}><AppIcon name="close" size={18} /></button>
            </header>
            <div style={{ flex: 1, overflow: 'auto', padding: 16, overscrollBehavior: 'contain' }}>
      {!jobEditorContextReady ? (
        <div className="ui-state ui-state-loading" role="status" style={{ minHeight: 240 }}>
          Đang tải đúng dữ liệu JOB của nhân viên và kỳ commission đã chọn…
        </div>
      ) : <div className="ui-card" style={{ margin: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', background: 'linear-gradient(135deg,#eff6ff,#dbeafe)', border: '1px solid #93c5fd', borderRadius: 14, padding: '14px 18px' }}>
          <AppIcon name="lock" size={24} />
          <div style={{ flex: 1, minWidth: 240 }}><div style={{ fontWeight: 800, fontSize: 16, color: '#1e3a8a' }}>Chi tiết JOB để giữ bonus: {selectedRep}</div><div style={{ fontSize: 13, color: '#3b82f6', marginTop: 4 }}>Hiển thị đầy đủ dữ liệu Job PnL · <b>{walletJobs.length} JOBs</b> · <b>{lockedJobs.length} JOB đang giữ thủ công</b></div></div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}><div style={{ background: 'linear-gradient(135deg,#065f46,#059669)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}><div style={{ fontSize: 11, fontWeight: 700, opacity: .8 }}>TỔNG P&L KỲ/QUÝ</div><div style={{ fontSize: 15, fontWeight: 800 }}>{money(totalPnL)}</div></div><div style={{ background: 'linear-gradient(135deg,#1e3a8a,#2563eb)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}><div style={{ fontSize: 11, fontWeight: 700, opacity: .8 }}>TỔNG THƯỞNG QUÝ</div><div style={{ fontSize: 15, fontWeight: 800 }}>{money(selectedWallet?.total_bonus_quarter ?? periodTotals.reduce((sum, period) => sum + period.totalBonusQuarter, 0))}</div></div><div style={{ background: 'linear-gradient(135deg,#9a3412,#ea580c)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}><div style={{ fontSize: 11, fontWeight: 700, opacity: .8 }}>GIỮ THỦ CÔNG</div><div style={{ fontSize: 15, fontWeight: 800 }}>{money(lockedJobs.reduce((sum, job) => sum + job.manualHeld, 0))}</div></div></div>
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
              <MonthYearSelect id={`job-editor-payout-${job.id}`} compact showLabels={false} availablePeriods={targetMonths} disabled={busy || isBonusLocked} value={edit.releasePayoutPeriod} onChange={releasePayoutPeriod => updateJobEdit(job.id, { releasePayoutPeriod })} yearLabel={`Năm trả JOB ${job.jobNo}`} monthLabel={`Tháng trả JOB ${job.jobNo}`} />
              <button className="ui-button ui-button-secondary" disabled={busy || isBonusLocked} onClick={() => void saveHeldReleasePlan(job)}>Lưu tháng trả</button>
            </div>
            <small style={{ display: 'block', marginTop: 7, color: '#78350f' }}>Ba tháng kỳ kế tiếp: {targetMonths.join(' · ') || 'Chưa xác định'}. Sales báo thanh toán, kế toán xác minh, sau đó lập lệnh ở hàng đợi phía trên.</small>
          </div>
        })()}
        <div style={{ border: '1px solid #cbd5e1', borderRadius: 14, overflow: 'auto', maxHeight: 540 }}>
          <table style={{ borderCollapse: 'collapse', fontSize: 11, whiteSpace: 'nowrap', tableLayout: 'fixed' }}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}><tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}><th style={cellStyle(MANUAL_JOB_WIDTHS.index)}>#</th><th style={cellStyle(MANUAL_JOB_WIDTHS.period)}>KỲ/QUÝ</th>{JOB_COLUMNS.map(col => <th key={col.key} style={cellStyle(col.width, col.numeric)}>{col.label}</th>)}<th style={cellStyle(MANUAL_JOB_WIDTHS.holdPercent, true)} title="Hold = 30% Profit/Loss dương của từng JOB">HOLD BONUS 30%</th><th style={cellStyle(MANUAL_JOB_WIDTHS.bonus, true)}>
              <span
                tabIndex={0}
                aria-label="Xem công thức Bonus ròng"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 3, cursor: 'help' }}
                onMouseEnter={event => showNetBonusTooltip('header', event.currentTarget)}
                onMouseLeave={() => setNetBonusTooltip(null)}
                onFocus={event => showNetBonusTooltip('header', event.currentTarget)}
                onBlur={() => setNetBonusTooltip(null)}
              >
                <span>BONUS RÒNG</span> <span className="commission-tooltip-icon">?</span>
              </span>
            </th><th style={cellStyle(MANUAL_JOB_WIDTHS.automaticHeld, true)}>GIỮ TỰ ĐỘNG</th><th style={cellStyle(MANUAL_JOB_WIDTHS.manualHeld, true)}>GIỮ THỦ CÔNG</th><th style={cellStyle(MANUAL_JOB_WIDTHS.scheduled, true)}>ĐÃ LẬP LỊCH</th><th style={cellStyle(MANUAL_JOB_WIDTHS.available, true)}>KHẢ DỤNG</th><th style={cellStyle(MANUAL_JOB_WIDTHS.paid, true)}>ĐÃ TRẢ</th><th style={cellStyle(MANUAL_JOB_WIDTHS.remark)}>REMARK</th><th style={cellStyle(MANUAL_JOB_WIDTHS.save)}>LƯU</th></tr></thead>
            <tbody>{filteredJobs.map((job, index) => {
              const isSelected = job.id === selectedJobId
              const edit = jobEdits[job.id] || { paymentReceived: normalizedPayment(job.paymentReceived), paymentReceivedAmount: Number(job.paymentReceivedAmount || 0), manualHeld: money(job.manualHeld), remark: job.remark || '', commandNote: '', releasePayoutPeriod: job.nextReleasePayoutPeriods?.[0] || currentMonth() }
              const preview = getJobPreview(job, edit)
              const isNotificationTarget = job.id === notificationHighlightJobId
              return <tr id={`commission-job-${job.id}`} data-job-id={job.id} key={job.id} onClick={() => setSelectedJobId(job.id)} style={{ cursor: 'pointer', scrollMarginTop: 120, background: isNotificationTarget ? '#fef3c7' : isSelected ? '#dbeafe' : index % 2 === 0 ? '#fff' : '#f8fafc', borderBottom: '1px solid #cbd5e1', outline: isNotificationTarget ? '3px solid #f59e0b' : undefined, outlineOffset: isNotificationTarget ? -3 : undefined, transition: 'background-color 240ms ease, outline-color 240ms ease' }}>
                <td style={cellStyle(MANUAL_JOB_WIDTHS.index)}>{index + 1}</td><td style={{ ...cellStyle(MANUAL_JOB_WIDTHS.period), color: '#1d4ed8', fontWeight: 700 }}>{job.periodLabel}</td>
                {JOB_COLUMNS.map(col => {
                  const value = job[col.key]
                  const isPnl = col.key === 'profitLoss'
                  const isPayment = col.key === 'paymentReceived'
                  return <td key={col.key} title={isPayment ? 'Có thể đổi NO/YES, nhập số tiền đã trả hoặc chọn Trả hết' : String(value ?? '')} style={{ ...cellStyle(col.width, col.numeric), overflow: isPayment ? 'visible' : 'hidden', fontWeight: isPnl || col.key === 'jobNo' ? 700 : col.key === 'salesRep' ? 600 : 400, color: isPnl ? Number(value) >= 0 ? '#15803d' : '#b91c1c' : '#000' }}>
                    {isPayment ? <div onClick={event => event.stopPropagation()} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <select aria-label={`Payment Received ${job.jobNo}`} value={edit.paymentReceived} disabled={busy || isBonusLocked} onChange={event => updateJobEdit(job.id, { paymentReceived: event.target.value as 'YES' | 'NO', paymentReceivedAmount: event.target.value === 'YES' ? edit.paymentReceivedAmount : 0 })} style={{ width: '100%', minWidth: 0, border: '1px solid #93c5fd', borderRadius: 6, padding: '4px 6px', background: '#fff', color: edit.paymentReceived === 'YES' ? '#047857' : '#b45309', fontWeight: 800 }}><option value="NO">NO</option><option value="YES">YES</option></select>
                      {edit.paymentReceived === 'YES' && <div style={{ display: 'flex', alignItems: 'stretch', gap: 4 }}>
                        <VndInput aria-label={`Số tiền đã trả ${job.jobNo}`} value={edit.paymentReceivedAmount} disabled={busy || isBonusLocked} onValueChange={paymentReceivedAmount => updateJobEdit(job.id, { paymentReceivedAmount })} onEmpty={() => updateJobEdit(job.id, { paymentReceivedAmount: 0 })} placeholder="Số tiền đã trả" style={{ flex: '1 1 auto', width: 0, minWidth: 0, boxSizing: 'border-box', textAlign: 'right', border: '1px solid #93c5fd', borderRadius: 6, padding: '4px 6px', color: '#047857', fontWeight: 700, background: '#fff' }} />
                        <button type="button" aria-label={`Trả hết JOB ${job.jobNo}`} title={`Điền toàn bộ Profit/Loss: ${money(Math.max(0, Number(job.profitLoss || 0)))}`} disabled={busy || isBonusLocked || Number(job.profitLoss || 0) <= 0} onClick={() => updateJobEdit(job.id, { paymentReceivedAmount: Math.max(0, Number(job.profitLoss || 0)) })} style={{ flex: '0 0 auto', border: '1px solid #0284c7', borderRadius: 6, padding: '4px 7px', background: '#e0f2fe', color: '#0369a1', fontSize: 11, fontWeight: 800, cursor: busy || isBonusLocked ? 'not-allowed' : 'pointer', whiteSpace: 'nowrap' }}>Trả hết</button>
                      </div>}
                    </div> : col.numeric ? (col.key === 'wt' || col.key === 'vol' ? decimal(Number(value)) : money(Number(value))) : (value === null || value === undefined || value === '' ? '—' : String(value))}
                  </td>
                })}
                <td style={{ ...cellStyle(MANUAL_JOB_WIDTHS.holdPercent, true), background: '#fffbeb', color: '#92400e', fontWeight: 800 }} title={`Profit/Loss ${money(job.profitLoss)} × 30% = ${money(fixedHoldBonusAmount(job))}`}>{money(fixedHoldBonusAmount(job))}</td>
                <td style={{ ...cellStyle(MANUAL_JOB_WIDTHS.bonus, true), color: '#1d4ed8', fontWeight: 700 }}>
                  <span
                    tabIndex={0}
                    aria-label={`Xem công thức Bonus ròng của JOB ${job.jobNo}`}
                    style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'flex-end', gap: 3, cursor: 'help' }}
                    onMouseEnter={event => showNetBonusTooltip('job', event.currentTarget, job)}
                    onMouseLeave={() => setNetBonusTooltip(null)}
                    onFocus={event => showNetBonusTooltip('job', event.currentTarget, job)}
                    onBlur={() => setNetBonusTooltip(null)}
                  >
                    <span>{money(job.earned)}</span>
                    <span className="commission-tooltip-icon">?</span>
                  </span>
                </td><td style={{ ...cellStyle(MANUAL_JOB_WIDTHS.automaticHeld, true), color: '#b45309', background: preview.changed ? '#fff7ed' : undefined, fontWeight: preview.changed ? 800 : 400 }}>{money(preview.paymentHeld)}{preview.changed && <small style={{ display: 'block', fontSize: 11 }}>Dự kiến</small>}</td>
                <td style={cellStyle(MANUAL_JOB_WIDTHS.manualHeld, true)}><input aria-label={`Giữ thủ công ${job.jobNo}`} value={edit.manualHeld} disabled={busy || isBonusLocked || !job.hasWalletEntry} inputMode="numeric" onClick={event => event.stopPropagation()} onChange={event => updateJobEdit(job.id, { manualHeld: formatMoneyInput(event.target.value) })} style={{ width: '100%', minWidth: 0, boxSizing: 'border-box', textAlign: 'right', border: '1px solid #93c5fd', borderRadius: 6, padding: '4px 6px', color: parseMoneyInput(edit.manualHeld) > 0 ? '#b91c1c' : '#475569', fontWeight: 800, background: '#fff' }} /></td>
                <td style={cellStyle(MANUAL_JOB_WIDTHS.scheduled, true)}>{money(job.scheduled)}</td><td style={{ ...cellStyle(MANUAL_JOB_WIDTHS.available, true), color: preview.available < 0 ? '#b91c1c' : '#047857', background: preview.changed ? '#ecfdf5' : undefined, fontWeight: 700 }}>{money(preview.available)}{preview.changed && <small style={{ display: 'block', fontSize: 11 }}>Dự kiến</small>}</td><td style={cellStyle(MANUAL_JOB_WIDTHS.paid, true)}>{money(job.paid)}</td>
                <td style={cellStyle(MANUAL_JOB_WIDTHS.remark)}><input aria-label={`Remark ${job.jobNo}`} value={edit.remark} disabled={busy || isBonusLocked} onClick={event => event.stopPropagation()} onChange={event => updateJobEdit(job.id, { remark: event.target.value })} placeholder="Lý do chỉnh sửa" style={{ width: '100%', minWidth: 0, boxSizing: 'border-box', border: '1px solid #93c5fd', borderRadius: 6, padding: '4px 6px', background: '#fff' }} /></td>
                <td style={cellStyle(MANUAL_JOB_WIDTHS.save)}><button className="ui-button ui-button-primary" style={{ minHeight: 30, padding: '4px 10px', fontSize: 11 }} disabled={busy || isBonusLocked} onClick={event => { event.stopPropagation(); void saveJobEdit(job) }}>Lưu</button></td>
              </tr>
            })}</tbody>
            <tfoot><tr style={{ background: '#e2e8f0', fontWeight: 800, position: 'sticky', bottom: 0, borderTop: '2px solid #cbd5e1' }}><td style={cellStyle(MANUAL_JOB_WIDTHS.index)}>Σ</td><td style={cellStyle(MANUAL_JOB_WIDTHS.period)}>{filteredJobs.length} JOBs</td>{JOB_COLUMNS.map(col => <td key={col.key} style={cellStyle(col.width, col.numeric)}>{col.key === 'profitLoss' ? money(filteredJobs.reduce((sum, job) => sum + job.profitLoss, 0)) : ''}</td>)}<td style={cellStyle(MANUAL_JOB_WIDTHS.holdPercent, true)} title="Tổng tiền Hold 30%">{money(filteredJobs.reduce((sum, job) => sum + fixedHoldBonusAmount(job), 0))}</td><td style={cellStyle(MANUAL_JOB_WIDTHS.bonus, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.earned, 0))}</td><td style={cellStyle(MANUAL_JOB_WIDTHS.automaticHeld, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.paymentHeld, 0))}</td><td style={cellStyle(MANUAL_JOB_WIDTHS.manualHeld, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.manualHeld, 0))}</td><td style={cellStyle(MANUAL_JOB_WIDTHS.scheduled, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.scheduled, 0))}</td><td style={cellStyle(MANUAL_JOB_WIDTHS.available, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.available, 0))}</td><td style={cellStyle(MANUAL_JOB_WIDTHS.paid, true)}>{money(filteredJobs.reduce((sum, job) => sum + job.paid, 0))}</td><td style={cellStyle(MANUAL_JOB_WIDTHS.remark)} /><td style={cellStyle(MANUAL_JOB_WIDTHS.save)} /></tr></tfoot>
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
      <div className="commission-schedule-heading" style={{ order: 46 }}>
        <h4 style={{ margin: 0 }}>Lịch chi trả</h4>
        <div className="app-segmented-tabs commission-tablist commission-tablist--two" role="tablist" aria-label="Phạm vi lịch chi trả">
          <button type="button" className="app-segmented-tab" role="tab" aria-selected={scheduleScope === 'all'} onClick={() => setScheduleScope('all')}>Tổng <span>{schedules.length}</span></button>
          <button type="button" className="app-segmented-tab" role="tab" aria-selected={scheduleScope === 'user'} disabled={!selectedRep} title={selectedRep ? `Chỉ hiển thị lịch của ${selectedRep}` : 'Chọn một ví bonus để xem theo nhân viên'} onClick={() => setScheduleScope('user')}>{selectedRep || 'Nhân viên'} <span>{schedules.filter(item => item.sales_rep === selectedRep).length}</span></button>
        </div>
      </div>
      <div className="ui-table-wrap commission-schedule-table-wrap" style={{ order: 47 }}><table className="ui-table commission-schedule-table"><thead><tr><th>Nhân viên</th><th>JOB / kỳ nguồn</th><th>Tháng trả</th><th>Số tiền</th><th>Trạng thái</th><th /></tr></thead><tbody>{visibleSchedules.map(item => <tr key={item.id}><td><b>{item.sales_rep}</b></td><td className="commission-schedule-job-cell">{item.jobs?.length ? item.jobs.map(job => <div key={job.job_id}><b>{job.job_no}</b><small>{job.period_label}</small></div>) : <span>—</span>}</td><td>{item.payout_period}</td><td>{money(item.total_amount)}</td><td>{item.status}</td><td>{item.status === 'SCHEDULED' && <div className="commission-schedule-row-actions"><button className="ui-button ui-button-primary" disabled={scheduleActionsDisabled} onClick={() => call(`/api/commission/wallet/schedules/${item.id}/pay`, {})}>Chi trả</button><button className="ui-button ui-button-secondary" disabled={scheduleActionsDisabled} onClick={() => { setScheduleToCancel(item); setScheduleCancelReason('') }}>Hủy lịch</button></div>}</td></tr>)}{visibleSchedules.length === 0 && <tr><td colSpan={6} style={{ padding: 24, textAlign: 'center', color: '#64748b' }}>Không có lịch chi trả trong phạm vi này.</td></tr>}</tbody></table></div>
      <div className="ui-card" style={{ marginTop: 16, order: 50, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div><h4 style={{ margin: 0 }}>Lịch sử sổ cái</h4><small style={{ color: '#64748b' }}>Đang ẩn chi tiết để giao diện gọn hơn · {ledger.length} giao dịch</small></div>
        <button className="ui-button ui-button-secondary" onClick={() => setLedgerOpen(true)}>Xem lịch sử sổ cái</button>
      </div>
    </>
  </section>
  {scheduleToCancel && createPortal(
    <div className="ui-modal-backdrop" role="presentation" onMouseDown={() => !busy && setScheduleToCancel(null)} style={{ zIndex: 3300 }}>
      <section role="dialog" aria-modal="true" aria-labelledby="cancel-commission-schedule-title" onMouseDown={event => event.stopPropagation()} style={{ width: 'min(92vw, 560px)', background: '#fff', borderRadius: 16, boxShadow: '0 24px 80px rgba(15,23,42,.35)', padding: 20 }}>
        <h3 id="cancel-commission-schedule-title" style={{ margin: 0, color: '#0f172a' }}>Hủy lịch chi trả tháng {scheduleToCancel.payout_period}</h3>
        <p style={{ color: '#64748b', fontSize: 13, lineHeight: 1.6 }}>JOB sẽ trở về bảng đang giữ, nhân viên được đưa về trạng thái chưa yêu cầu và nhận thông báo kèm lý do này.</p>
        <label style={{ display: 'block', color: '#334155', fontSize: 13, fontWeight: 700 }}>
          Lý do hủy <span style={{ color: '#dc2626' }}>*</span>
          <textarea autoFocus className="ui-input" rows={4} value={scheduleCancelReason} onChange={event => setScheduleCancelReason(event.target.value)} placeholder="Nhập lý do để thông báo cho nhân viên..." style={{ width: '100%', marginTop: 8, resize: 'vertical' }} />
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
          <button type="button" className="ui-button ui-button-secondary" disabled={busy} onClick={() => setScheduleToCancel(null)}>Không hủy</button>
          <button type="button" className="ui-button ui-button-primary" disabled={busy || !scheduleCancelReason.trim()} onClick={() => void cancelSchedule()}>Xác nhận hủy lịch</button>
        </div>
      </section>
    </div>,
    document.body,
  )}
  {paymentMonthPrompt && (() => {
    const job = walletJobs.find(item => item.id === paymentMonthPrompt.jobId)
    const edit = job ? jobEdits[job.id] : undefined
    if (!job || !edit) return null
    const commissionMonths = job.customerPaymentPeriods || []
    const normalPayoutMonths = job.nextReleasePayoutPeriods || []
    const customerPaymentMonth = commissionMonths[1] || ''
    const paymentDate = paymentMonthPrompt.paymentDate || ''
    const paymentDateValid = paymentDate.slice(0, 7) === customerPaymentMonth
    const fullyPaid = edit.paymentReceivedAmount >= Math.max(0, Number(job.profitLoss || 0)) - 0.005
    const payoutCandidates = eligiblePayoutMonths(commissionMonths, normalPayoutMonths, customerPaymentMonth, paymentDate)
    const selectedPayoutMonths = payoutCandidates.filter(month => paymentMonthPrompt.payoutMonths.includes(month))
    const changedFromNo = normalizedPayment(job.paymentReceived) === 'NO'
    return createPortal(
      <div className="ui-modal-backdrop" role="presentation" onMouseDown={() => !busy && setPaymentMonthPrompt(null)} style={{ zIndex: 3600 }}>
        <section role="alertdialog" aria-modal="true" aria-labelledby="commission-payment-month-title" onMouseDown={event => event.stopPropagation()} style={{ width: 'min(94vw, 760px)', maxHeight: '88vh', background: '#fff', borderRadius: 16, boxShadow: '0 24px 80px rgba(15,23,42,.4)', overflow: 'auto' }}>
          <header style={{ padding: '18px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a' }}>
            <h3 id="commission-payment-month-title" style={{ margin: 0, color: '#92400e' }}>⚠ Xác nhận tháng khách hàng thanh toán</h3>
            <p style={{ margin: '7px 0 0', color: '#78350f', fontSize: 13, lineHeight: 1.55 }}>JOB <b>{job.jobNo}</b> {changedFromNo ? 'đang chuyển từ NO sang YES' : 'vừa được cập nhật thành đã thanh toán đủ'}. Tháng khách thanh toán được cố định là tháng giữa của kỳ Commission. Nếu thanh toán chậm nhất ngày 25, có thể chọn thêm tháng chi đầu tiên; sau ngày 25, tháng đó sẽ bị khóa.</p>
          </header>
          <div style={{ padding: 20 }}>
            <div style={{ marginBottom: 8, color: '#0f172a', fontSize: 13, fontWeight: 800 }}>1. Tháng khách hàng thanh toán trong kỳ Commission</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 10 }}>
              <div style={{ border: '2px solid #0284c7', borderRadius: 10, padding: '11px 8px', background: '#e0f2fe', color: '#075985', textAlign: 'center' }}>
                <b style={{ display: 'block', fontSize: 13 }}>{paymentMonthLabel(customerPaymentMonth)}</b>
                <small style={{ display: 'block', marginTop: 5 }}>Tháng giữa kỳ · mốc khóa tháng chi đầu tiên là ngày 25</small>
              </div>
              <label style={{ display: 'grid', gap: 6, color: '#334155', fontSize: 12, fontWeight: 700 }}>
                Ngày khách hàng thanh toán thực tế
                <BrandedDateInput
                  value={paymentDate}
                  min={`${customerPaymentMonth}-01`}
                  max={`${customerPaymentMonth}-${new Date(Date.UTC(Number(customerPaymentMonth.slice(0, 4)), Number(customerPaymentMonth.slice(5, 7)), 0)).getUTCDate()}`}
                  onChange={event => {
                    const paymentDate = event.target.value
                    const nextCandidates = eligiblePayoutMonths(commissionMonths, normalPayoutMonths, customerPaymentMonth, paymentDate)
                    setPaymentMonthPrompt({
                      jobId: job.id,
                      paymentDate,
                      payoutMonths: paymentMonthPrompt.payoutMonths.filter(month => nextCandidates.includes(month)),
                    })
                  }}
                  placeholder="Chọn ngày thanh toán"
                  aria-label="Ngày khách hàng thanh toán thực tế"
                  style={{ minHeight: 40, width: '100%' }}
                />
              </label>
            </div>
            <div style={{ margin: '18px 0 8px', color: '#0f172a', fontSize: 13, fontWeight: 800 }}>2. Chọn một hoặc nhiều tháng chi bonus đang giữ</div>
            {fullyPaid ? <div role="group" aria-label="Các tháng chi bonus đang giữ" style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(1, normalPayoutMonths.length)}, minmax(0, 1fr))`, gap: 9 }}>
              {normalPayoutMonths.map((month, index) => {
                const active = selectedPayoutMonths.includes(month)
                const eligible = payoutCandidates.includes(month)
                const firstPayoutMonth = index === 0
                return <button
                  key={month}
                  type="button"
                  role="checkbox"
                  aria-checked={active}
                  aria-disabled={!eligible}
                  disabled={!eligible}
                  onClick={() => setPaymentMonthPrompt({
                    jobId: job.id,
                    paymentDate,
                    payoutMonths: active
                      ? selectedPayoutMonths.filter(value => value !== month)
                      : payoutCandidates.filter(value => selectedPayoutMonths.includes(value) || value === month),
                  })}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, width: '100%', border: active ? '2px solid #0284c7' : '1px solid #cbd5e1', borderRadius: 10, padding: '11px 12px', background: active ? '#f0f9ff' : eligible ? '#fff' : '#f1f5f9', color: eligible ? '#1e293b' : '#94a3b8', cursor: eligible ? 'pointer' : 'not-allowed', textAlign: 'left', opacity: eligible ? 1 : 0.82 }}
                >
                  <span>
                    <b style={{ display: 'block', color: active ? '#075985' : eligible ? '#1e293b' : '#64748b', fontSize: 13 }}>{paymentMonthLabel(month)}</b>
                    <small style={{ display: 'block', marginTop: 4, color: eligible ? '#64748b' : '#b45309', lineHeight: 1.45 }}>
                      {!paymentDateValid ? 'Chọn ngày thanh toán trước' : firstPayoutMonth && !eligible ? 'Bị khóa: thanh toán sau ngày 25' : firstPayoutMonth ? 'Khả dụng: thanh toán chậm nhất ngày 25' : 'Thuộc kỳ chi trả hiện tại'}
                    </small>
                  </span>
                  <span aria-hidden="true" style={{ display: 'grid', placeItems: 'center', flexShrink: 0, width: 20, height: 20, borderRadius: 5, border: active ? '2px solid #0284c7' : '2px solid #94a3b8', background: active ? '#0284c7' : '#fff', color: '#fff', boxSizing: 'border-box', fontWeight: 900 }}>{active ? '✓' : ''}</span>
                </button>
              })}
            </div> : <div style={{ padding: 12, borderRadius: 10, border: '1px solid #fed7aa', background: '#fff7ed', color: '#9a3412', fontSize: 12, lineHeight: 1.55 }}>JOB chưa thanh toán đủ nên hệ thống chỉ ghi nhận tháng khách thanh toán, vẫn giữ 30% và chưa chọn tháng chi bonus.</div>}
            <div style={{ marginTop: 16, padding: 12, borderRadius: 10, background: fullyPaid ? '#ecfdf5' : '#fff7ed', color: fullyPaid ? '#065f46' : '#9a3412', fontSize: 12, lineHeight: 1.6 }}>
              <div><b>Profit/Loss:</b> {money(job.profitLoss)} · <b>Đã trả:</b> {money(edit.paymentReceivedAmount)}</div>
              {fullyPaid
                ? selectedPayoutMonths.length > 0
                  ? <div><b>Đã thanh toán đủ.</b> Bonus đang giữ <b>{money(job.paymentHeld)}</b> sẽ chia đều vào <b>{selectedPayoutMonths.length} tháng đã chọn</b> ({selectedPayoutMonths.map(paymentMonthLabel).join(', ')}), khoảng <b>{money(job.paymentHeld / selectedPayoutMonths.length)}/tháng</b>. Thưởng gốc của cả ba tháng và các tháng không chọn vẫn giữ nguyên.</div>
                  : <div><b>Đã thanh toán đủ.</b> Hãy chọn ít nhất một tháng để chi bonus đang giữ {money(job.paymentHeld)}.</div>
                : <div><b>Chưa thanh toán đủ.</b> Hệ thống ghi nhận tháng đối chiếu nhưng vẫn giữ 30% và chưa lập lịch chi bonus.</div>}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
              <button type="button" className="ui-button ui-button-secondary" disabled={busy} onClick={() => setPaymentMonthPrompt(null)}>Quay lại</button>
              <button type="button" className="ui-button ui-button-primary" disabled={busy || commissionMonths.length !== 3 || !paymentDateValid || (fullyPaid && selectedPayoutMonths.length === 0)} onClick={() => void confirmPaymentMonthSave()}>Xác nhận và lưu</button>
            </div>
          </div>
        </section>
      </div>,
      document.body,
    )
  })()}
  <NetBonusFloatingTooltip tooltip={netBonusTooltip} jobs={walletJobs} />
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
