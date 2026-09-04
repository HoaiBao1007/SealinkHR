import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import * as XLSX from 'xlsx'
import { useConfirmDialog } from '../../shared/ui/ConfirmDialog'
import { credentialedFetch } from '../../shared/api/credentialedFetch'
import { BonusFunnelPanel } from './BonusFunnelPanel'
import { VndInput } from '../../shared/ui/VndInput'
import { formatVietnameseNumber, parseVndInput } from '../../shared/utils/currency'
import { AppIcon } from '../../shared/ui/AppIcon'

function parseDateStringToDate(s: string): Date | null {
  if (!s) return null;
  s = s.trim().replace(/\u00a0/g, ' ');
  const monthNames: Record<string, number> = {
    jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
    jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
  };

  // Climax uses this format in the report header: 01-Apr-2026.
  const alphaMonth = s.match(/^(\d{1,2})[-\s]([a-z]{3,9})[-\s,](\d{4})$/i);
  if (alphaMonth) {
    const month = monthNames[alphaMonth[2].slice(0, 3).toLowerCase()];
    if (month !== undefined) {
      const parsed = new Date(Number(alphaMonth[3]), month, Number(alphaMonth[1]));
      if (parsed.getFullYear() === Number(alphaMonth[3]) && parsed.getMonth() === month && parsed.getDate() === Number(alphaMonth[1])) return parsed;
      return null;
    }
  }
  // Try YYYY-MM-DD
  let match = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  if (match) {
    const parsed = new Date(parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3]));
    return parsed.getFullYear() === parseInt(match[1]) && parsed.getMonth() === parseInt(match[2]) - 1 && parsed.getDate() === parseInt(match[3]) ? parsed : null;
  }
  // Try DD-MM-YYYY or DD/MM/YYYY
  match = s.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
  if (match) {
    const parsed = new Date(parseInt(match[3]), parseInt(match[2]) - 1, parseInt(match[1]));
    return parsed.getFullYear() === parseInt(match[3]) && parsed.getMonth() === parseInt(match[2]) - 1 && parsed.getDate() === parseInt(match[1]) ? parsed : null;
  }
  
  // Try parsing directly
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d;
  return null;
}

function toIsoDate(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}

function toClimaxDate(value: Date): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${String(value.getDate()).padStart(2, '0')}-${months[value.getMonth()]}-${value.getFullYear()}`;
}

function getMonthsInRange(start: Date, end: Date): string[] {
  const months: string[] = [];
  let curr = new Date(start.getFullYear(), start.getMonth(), 1);
  const last = new Date(end.getFullYear(), end.getMonth(), 1);
  while (curr <= last) {
    const y = curr.getFullYear();
    const m = String(curr.getMonth() + 1).padStart(2, '0');
    months.push(`${y}-${m}`);
    curr.setMonth(curr.getMonth() + 1);
  }
  return months;
}

function doMonthsOverlap(startA: Date, endA: Date, startB: Date, endB: Date): boolean {
  const monthsA = getMonthsInRange(startA, endA);
  const monthsB = getMonthsInRange(startB, endB);
  return monthsA.some(m => monthsB.includes(m));
}

// ══════════════════════════════════════════════════════════
// Constants: 23 cột đúng theo file Climax
// ══════════════════════════════════════════════════════════
const CLIMAX_COLUMNS = [
  { key: 'jobNo',             label: 'Job #',              idx: 0,  num: false, width: 120 },
  { key: 'jobDate',           label: 'Job Date',           idx: 1,  num: false, width: 100 },
  { key: 'hbl',               label: 'HBL/HAWB',           idx: 2,  num: false, width: 140 },
  { key: 'mbl',               label: 'MBL',                idx: 3,  num: false, width: 140 },
  { key: 'customer',          label: 'Customer',           idx: 4,  num: false, width: 180 },
  { key: 'vendor',            label: 'Vendor',             idx: 5,  num: false, width: 160 },
  { key: 'salesRep',          label: 'Sales Rep',          idx: 6,  num: false, width: 130 },
  { key: 'shipper',           label: 'Shipper',            idx: 7,  num: false, width: 160 },
  { key: 'consignee',         label: 'Consignee',          idx: 8,  num: false, width: 160 },
  { key: 'subType',           label: 'SubType',            idx: 9,  num: false, width: 90  },
  { key: 'containerString',   label: 'Container String',   idx: 10, num: false, width: 130 },
  { key: 'wt',                label: 'WT',                 idx: 11, num: true,  width: 80  },
  { key: 'vol',               label: 'VOL',                idx: 12, num: true,  width: 80  },
  { key: 'carrierBookingNo',  label: 'CarrierBookingNo',   idx: 13, num: false, width: 140 },
  { key: 'por',               label: 'POR',                idx: 14, num: false, width: 90  },
  { key: 'finalDestination',  label: 'Final Destination',  idx: 15, num: false, width: 140 },
  { key: 'realizedRevenue',   label: 'Realized Revenue',   idx: 16, num: true,  width: 140 },
  { key: 'unrealizedRevenue', label: 'Unrealized Revenue', idx: 17, num: true,  width: 150 },
  { key: 'realizedCost',      label: 'Realized Cost',      idx: 18, num: true,  width: 120 },
  { key: 'unrealizedCost',    label: 'Unrealized Cost',    idx: 19, num: true,  width: 130 },
  { key: 'profitLoss',        label: 'Profit/Loss',        idx: 20, num: true,  width: 130 },
  { key: 'containerPicked',   label: 'Container Picked',   idx: 21, num: false, width: 130 },
  { key: 'paymentReceived',   label: 'Payment Received',   idx: 22, num: false, width: 140 },
]

// ══════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════
type JobPnLRow = Record<string, string | number>
type DetailJobTab = 'source' | 'payable' | 'held'

type CommissionReceivableAttachment = {
  id: number
  period_id: number
  job_id: number
  job_no: string
  sales_rep?: string | null
  original_filename: string
  content_type?: string | null
  size_bytes: number
  note?: string | null
  uploaded_by?: string | null
  created_at: string
}

type CommissionReceivableReconciliation = {
  original_filename: string
  positive_rows: number
  ignored_non_positive_rows: number
  invalid_positive_rows: number
  matched_jobs: number
  unmatched_positive_jobs: number
  unmatched_job_nos: string[]
  attachment: CommissionReceivableAttachment
  updates: Array<{
    job_id: number
    job_no: string
    source_rows: number
    receivable_amount: number
    payment_received_amount: number
    balance_amount: number
    paid_percent: number
    hold_bonus_percent: number
    hold_bonus_amount: number
    net_bonus: number
  }>
}

interface SalesRepSummaryIn {
  sales_rep: string
  job_count: number
  total_profit_loss: number
  sales_bonus?: number
  target?: number
  bonus_rate?: number
  total_bonus_quarter?: number
  payment_received_total?: number
  hold_bonus_total?: number
  employee_salary?: number
  coefficient?: number
  is_pnl_overridden?: boolean
  is_target_overridden?: boolean
  is_rate_overridden?: boolean
  is_total_bonus_overridden?: boolean
  is_monthly_bonus_overridden?: boolean
  remark?: string
  bonus_rules?: any[]
  uses_progressive_bonus?: boolean
  monthly_payouts?: Array<{
    payout_period: string
    amount: number
    base_amount?: number
    released_amount?: number
  }>
}

interface SavedPeriod {
  id: number
  period_label: string
  job_count: number
  total_profit_loss: number
  created_at: string
  sales_rep_summary: SalesRepSummaryIn[]
  source_filename?: string | null
  from_date?: string | null
  till_date?: string | null
  payout_periods?: string[]
}

interface PendingCommissionImport {
  fileName: string
  rows: JobPnLRow[]
  periodLabel: string
  fromDate: string
  tillDate: string
  periodParseError: string | null
}

interface CommissionMergeManualJob {
  jobId: number
  jobNo: string
  salesRep: string | null
  reasons: string[]
  sourceFilename: string
  periodId: number
  periodLabel: string
}

interface CommissionMergePreviewSummary {
  newJobs: number
  automaticUpdates: number
  manualJobs: CommissionMergeManualJob[]
}

interface CommissionWalletSummary {
  sales_rep: string
  period_labels?: string[]
  period_summaries?: Array<{
    period_id: number
    period_label: string
    payout_periods?: string[]
    total_bonus_quarter: number
    formula_total_bonus_quarter?: number
    formula_effective_coefficient?: number
    formula_monthly_bonus?: number
    payment_received_total?: number
    gross_total_bonus_quarter?: number
    hold_adjusted_total_bonus?: number
    cash_basis_coefficient?: number
    cash_basis_monthly_bonus?: number
    monthly_bonus: number
    policy_hold_amount?: number
    quarter_hold_amount?: number
    holds_entire_profit?: boolean
    monthly_payout?: number
    temporary_bonus_opening?: number
    temporary_bonus_available?: number
    monthly_available_amounts?: Array<{
      payout_period: string
      amount: number
      base_amount?: number
      released_amount?: number
    }>
  }>
  total_bonus_quarter?: number
  total_earned: number
  manual_credit_amount: number
  manual_decrease_amount: number
  held_amount: number
  scheduled_amount: number
  transferred_amount: number
  available_amount: number
  paid_amount: number
  recoverable_amount: number
  policy: { payout_mode: string; minimum_amount: number; is_active: boolean }
}

export type CommissionNotificationFocus = {
  periodId: number
  periodLabel: string
  salesRep: string
  jobId?: number
  requestKey?: number
  target?: 'accounting-queue' | 'job-detail'
}

interface Props {
  apiBase: string
  token: string | null
  notificationFocus?: CommissionNotificationFocus | null
  externalRefreshVersion?: number
}

// ══════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════
function fmtNum(v: number, decimals = 0) {
  return formatVietnameseNumber(v, { maximumFractionDigits: decimals })
}

function fmtBonusCoefficient(value: number, decimals = 2) {
  return `${fmtNum(Math.max(0, Number(value || 0)) * 100, decimals)}%`
}

function getBonusReferenceLevel(profitLoss: number, employeeSalary: number) {
  const salary = Number(employeeSalary || 0)
  const profitSale = Math.max(0, Number(profitLoss || 0)) * 0.95
  return salary > 0 ? profitSale / salary : 0
}

function fmtBonusReferenceLevel(value: number) {
  const level = Math.max(0, Number(value || 0))
  return level > 8 ? '> 8' : level.toFixed(2)
}

const HOLD_30_HELP = [
  'Công thức Hold 30%:',
  'Số tiền giữ = max(0, Profit/Loss JOB) × 30%',
  'Áp dụng cho mọi JOB có hoặc chưa có dữ liệu công nợ.',
  'Tỷ lệ cố định và không được chỉnh sửa thủ công.',
].join('\n')

function hold30CellHelp(row: JobPnLRow): string {
  const jobNo = String(row.jobNo || '—')
  const profitLoss = Math.max(0, Number(row.profitLoss || 0))
  const amount = Number(row.holdBonusAmount ?? Math.round(profitLoss * 30) / 100)
  return [
    `JOB ${jobNo}`,
    `Profit/Loss dương: ${fmtNum(profitLoss, 2)}`,
    'Tỷ lệ Hold: 30%',
    `Phép tính: ${fmtNum(profitLoss, 2)} × 30% = ${fmtNum(amount, 2)}`,
    'Áp dụng kể cả khi JOB chưa có dữ liệu công nợ.',
    'Không được phép chỉnh sửa thủ công.',
  ].join('\n')
}

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleDateString('vi-VN') } catch { return iso }
}

function commissionQuarterLabel(fromDate?: string | null, tillDate?: string | null) {
  const source = tillDate || fromDate
  if (!source) return 'Chưa xác định kỳ'
  const match = source.match(/^(\d{4})-(\d{2})/)
  if (!match) return 'Chưa xác định kỳ'
  const year = Number(match[1])
  const month = Number(match[2])
  if (!year || month < 1 || month > 12) return 'Chưa xác định kỳ'
  return `Kỳ ${Math.ceil(month / 3)}/${year}`
}

function payoutPeriodLabel(value: string) {
  const match = String(value || '').match(/^(\d{4})-(\d{2})$/)
  return match ? `Tháng ${match[2]}/${match[1]}` : value || 'Chưa xác định tháng'
}

function fmtFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function findHeaderRowIndex(rows: any[][]): number {
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i] || []
    if (row.some((v: any) => {
      if (typeof v !== 'string') return false
      const s = v.toLowerCase().trim().replace(/[^a-z0-9#]/g, '')
      return s.includes('job#') || s.includes('jobnumber') || s.includes('jobno') || s.includes('hbl') || s.includes('salesrep')
    })) {
      return i
    }
  }
  return 5
}

function findHeaderColIndex(headerRow: any[], key: string, label: string): number {
  const normalizedHeaders = headerRow.map(h => String(h ?? '').toLowerCase().trim().replace(/[^a-z0-9]/g, ''))
  
  // Define matching criteria for each column key
  const matchers: Record<string, string[]> = {
    jobNo: ['job', 'jobno', 'jobnumber', 'job#'],
    jobDate: ['jobdate', 'jobdatef', 'date'],
    hbl: ['hbl', 'hawb', 'hblhawb', 'hblno'],
    mbl: ['mbl', 'mblno'],
    customer: ['customer', 'client', 'cust', 'customername', 'clientname'],
    vendor: ['vendor', 'vendorname', 'vender', 'vendername'],
    salesRep: ['salesrep', 'rep', 'salesagent', 'seller', 'sales'],
    shipper: ['shipper', 'shippername', 'shipperconsignee'],
    consignee: ['consignee', 'consigneename', 'shipperconsignee'],
    subType: ['subtype', 'type', 'jobsubtypename'],
    containerString: ['containerstring', 'container', 'containers', 'contstring', 'cont'],
    wt: ['wt', 'weight', 'gw', 'grossweight'],
    vol: ['vol', 'volume', 'cbm'],
    carrierBookingNo: ['carrierbookingno', 'bookingno', 'bookingnumber'],
    por: ['por', 'portofreceipt', 'placeofreceipt'],
    finalDestination: ['finaldestination', 'destination', 'placeofdelivery', 'finaldestinationcode', 'finaldestinationname'],
    realizedRevenue: ['realizedrevenue', 'realizedrev', 'realizedrevenueusd', 'revenue'],
    unrealizedRevenue: ['unrealizedrevenue', 'unrealizedrev', 'unrealizedrevenueusd'],
    realizedCost: ['realizedcost', 'realizedcostusd', 'cost'],
    unrealizedCost: ['unrealizedcost', 'unrealizedcostusd'],
    profitLoss: ['profitloss', 'pl', 'pandl', 'netprofit', 'profitandloss', 'profit/loss', 'profit / loss'],
    containerPicked: ['containerpicked', 'contpicked', 'pickedcont'],
    paymentReceived: ['paymentreceived', 'paid', 'payment']
  }

  const targets = matchers[key] || []
  
  // 1. Exact normalized match first
  for (let i = 0; i < normalizedHeaders.length; i++) {
    const h = normalizedHeaders[i]
    if (targets.some(t => h === t)) return i
  }

  // 2. Substring match next
  for (let i = 0; i < normalizedHeaders.length; i++) {
    const h = normalizedHeaders[i]
    if (targets.some(t => h.includes(t) || t.includes(h))) return i
  }

  // 3. Clean match with key itself or label
  const cleanKey = key.toLowerCase().replace(/[^a-z0-9]/g, '')
  const cleanLabel = label.toLowerCase().replace(/[^a-z0-9]/g, '')
  for (let i = 0; i < normalizedHeaders.length; i++) {
    const h = normalizedHeaders[i]
    if (h === cleanKey || h === cleanLabel || h.includes(cleanKey) || h.includes(cleanLabel)) {
      return i
    }
  }

  return -1
}

function parseClimaxBuffer(buffer: ArrayBuffer): {
  rows: JobPnLRow[]
  periodLabel: string
  fromDate: string
  tillDate: string
  periodError: string | null
} {
  const wb = XLSX.read(buffer, { type: 'array', cellDates: true })
  const ws = wb.Sheets[wb.SheetNames[0]]
  const allRows: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null }) as any[][]

  // Extract period info by searching the first 5 rows
  let fromDate = '', tillDate = '', periodLabel = ''
  try {
    for (let r = 0; r < Math.min(5, allRows.length); r++) {
      const row = allRows[r] || []
      let rowFromDate = '', rowTillDate = ''
      
      for (let c = 0; c < row.length; c++) {
        const cellVal = String(row[c] || '')
        const lowerVal = cellVal.toLowerCase()
        
        if (lowerVal.includes('date') || lowerVal.includes('from') || lowerVal.includes('till') || lowerVal.includes('period') || lowerVal.includes('to')) {
          const dates = cellVal.match(/\d{2}[-\/\s](?:[a-zA-Z]{3}|\d{2})[-\/\s]\d{4}/g)
          if (dates && dates.length >= 2) {
            rowFromDate = dates[0].trim()
            rowTillDate = dates[1].trim()
            break // Found both dates in a single cell
          } else if (dates && dates.length === 1) {
            if (lowerVal.includes('from')) {
              rowFromDate = dates[0].trim()
            } else if (lowerVal.includes('till') || lowerVal.includes('to') || lowerVal.includes('end')) {
              rowTillDate = dates[0].trim()
            }
          }
        }
      }
      
      if (rowFromDate && rowTillDate) {
        fromDate = rowFromDate
        tillDate = rowTillDate
        break
      }
    }
    
    periodLabel = fromDate && tillDate ? `${fromDate} → ${tillDate}` :
      new Date().toLocaleDateString('vi-VN', { month: '2-digit', year: 'numeric' })
  } catch { /* ignore */ }

  // The source period is normally stored in a merged heading such as
  // "Job Date From = 01-Apr-2026 Till = 30-Jun-2026". Read worksheet cells
  // directly so the heading cannot be missed by `sheet_to_json`.
  let periodError: string | null = null
  const topCellTexts: string[] = []
  const rangeRef = ws['!ref']
  if (rangeRef) {
    const range = XLSX.utils.decode_range(rangeRef)
    for (let row = range.s.r; row <= Math.min(range.e.r, range.s.r + 39); row += 1) {
      for (let col = range.s.c; col <= range.e.c; col += 1) {
        const cell = ws[XLSX.utils.encode_cell({ r: row, c: col })]
        if (!cell) continue
        const text = String(cell.w ?? cell.v ?? '').replace(/\u00a0/g, ' ').trim()
        if (text) topCellTexts.push(text)
      }
    }
  }
  if (topCellTexts.length === 0) {
    for (const row of allRows.slice(0, 40)) {
      for (const cell of row || []) {
        const text = String(cell ?? '').replace(/\u00a0/g, ' ').trim()
        if (text) topCellTexts.push(text)
      }
    }
  }

  const datePattern = /(?:\d{4}[-\/.]\d{1,2}[-\/.]\d{1,2}|\d{1,2}[-\/.\s][A-Za-z]{3,9}[-\/.\s,]\d{4}|\d{1,2}[-\/.]\d{1,2}[-\/.]\d{4})/g
  const periodHeader = topCellTexts.find((text) => {
    const normalized = text.toLowerCase()
    return (normalized.includes('job date') || normalized.includes('date from') || normalized.includes('period')) &&
      (normalized.includes('till') || normalized.includes('until') || normalized.includes('to')) &&
      (text.match(datePattern) || []).length >= 2
  }) || topCellTexts.find((text) => (text.match(datePattern) || []).length >= 2)

  if (!periodHeader) {
    fromDate = ''
    tillDate = ''
    periodLabel = ''
    periodError = 'Không đọc được khoảng ngày nguồn trong tiêu đề file Climax. Hệ thống sẽ không tự gán tháng import.'
  } else {
    const dateTokens = periodHeader.match(datePattern) || []
    const start = parseDateStringToDate(dateTokens[0] || '')
    const end = parseDateStringToDate(dateTokens[1] || '')
    if (!start || !end) {
      fromDate = ''
      tillDate = ''
      periodLabel = ''
      periodError = `Không phân tích được ngày từ tiêu đề: “${periodHeader}”.`
    } else if (start > end) {
      fromDate = ''
      tillDate = ''
      periodLabel = ''
      periodError = `Khoảng ngày trong file không hợp lệ: ${toClimaxDate(start)} lớn hơn ${toClimaxDate(end)}. Vui lòng sửa tiêu đề file trước khi lưu.`
    } else {
      fromDate = toIsoDate(start)
      tillDate = toIsoDate(end)
      periodLabel = `${toClimaxDate(start)} → ${toClimaxDate(end)}`
    }
  }

  const headerIdx = findHeaderRowIndex(allRows)
  const headerRow = allRows[headerIdx] || []

  // Map keys to resolved column indices
  const colIndices: Record<string, number> = {}
  const claimedIndices = new Set<number>()

  for (const col of CLIMAX_COLUMNS) {
    const idx = findHeaderColIndex(headerRow, col.key, col.label)
    if (idx !== -1) {
      colIndices[col.key] = idx
      claimedIndices.add(idx)
    } else {
      colIndices[col.key] = -1
    }
  }

  // Fallback to default col.idx if default index is not claimed by any other mapped column
  for (const col of CLIMAX_COLUMNS) {
    if (colIndices[col.key] === -1) {
      if (!claimedIndices.has(col.idx) && col.idx < headerRow.length) {
        colIndices[col.key] = col.idx
        claimedIndices.add(col.idx)
      }
    }
  }

  const jobNoIdx = colIndices['jobNo']
  const dataRows = allRows.slice(headerIdx + 2)

  const rows: JobPnLRow[] = dataRows
    .filter((row: any[]) => {
      if (jobNoIdx === -1 || jobNoIdx >= row.length) return false
      const cellVal = row[jobNoIdx]
      return cellVal != null && String(cellVal).trim() !== ''
    })
    .map((row: any[]) => {
      const result: JobPnLRow = {}
      for (const col of CLIMAX_COLUMNS) {
        const colIdx = colIndices[col.key]
        const raw = colIdx !== -1 && colIdx < row.length ? row[colIdx] : null
        
        if (col.num) {
          result[col.key] = typeof raw === 'number' ? raw : parseFloat(String(raw ?? '0')) || 0
        } else if (col.key === 'jobDate') {
          if (raw instanceof Date) result[col.key] = raw.toLocaleDateString('vi-VN')
          else if (typeof raw === 'number') {
            try { result[col.key] = new Date(Math.round((raw - 25569) * 86400000)).toLocaleDateString('vi-VN') }
            catch { result[col.key] = '' }
          } else result[col.key] = String(raw ?? '')
        } else {
          result[col.key] = String(raw ?? '')
        }
      }
      return result
    })

  return { rows, periodLabel, fromDate, tillDate, periodError }
}

function calculateDynamicSalesBonusJS(grossProfit: number, employeeSalary: number, rules: any[], targetOverride?: number) {
  const profitLoss = Number(grossProfit || 0) * 0.95;
  if (employeeSalary <= 0) {
    return {
      target: targetOverride === undefined ? 0 : Math.max(0, targetOverride),
      bonusRate: 0,
      totalBonusQuarter: 0,
      bonusPerMonth: 0,
      coefficient: 0
    };
  }

  // Use default rules if none are provided
  const defaultRules = [
    { min: 0, max: 2.0, rate: 0.0 },
    { min: 2.01, max: 4.0, rate: 0.20 },
    { min: 4.01, max: 6.0, rate: 0.25 },
    { min: 6.01, max: 8.0, rate: 0.30 },
    { min: 8.01, max: 999.0, rate: 0.35 }
  ];
  const activeRules = rules && rules.length > 0 ? rules : defaultRules;
  const sortedRules = [...activeRules].sort((a, b) => a.min - b.min);
  const baseCoef = sortedRules[0].max;

  const target = targetOverride === undefined ? employeeSalary * baseCoef : Math.max(0, targetOverride);
  const pfCountBn = profitLoss - target;
  
  let totalBonusQuarter = 0;
  let effectiveRate = 0;

  if (pfCountBn > 0) {
    let remaining = pfCountBn;
    let prevMax = baseCoef;

    for (let i = 1; i < sortedRules.length; i++) {
      const rule = sortedRules[i];
      const rate = rule.rate;
      const ruleMax = rule.max;

      if (ruleMax >= 999.0) {
        if (remaining > 0) {
          totalBonusQuarter += remaining * rate;
          remaining = 0;
        }
      } else {
        const tierCoefSize = ruleMax - prevMax;
        if (tierCoefSize > 0 && remaining > 0) {
          const tierProfitSize = tierCoefSize * employeeSalary;
          const amount = Math.min(remaining, tierProfitSize);
          totalBonusQuarter += amount * rate;
          remaining -= amount;
        }
        prevMax = ruleMax;
      }
    }
    effectiveRate = totalBonusQuarter / pfCountBn;
  }

  const bonusPerMonth = totalBonusQuarter / 3;
  
  return {
    target,
    bonusRate: effectiveRate,
    totalBonusQuarter,
    bonusPerMonth,
    coefficient: employeeSalary > 0 && pfCountBn > 0 ? Math.round((profitLoss / employeeSalary) * 100) / 100 : 0
  };
}

function calculateEmployeeBonusJS(
  grossProfit: number,
  employeeSalary: number,
  rules: any[],
  usesProgressiveBonus: boolean,
  targetOverride?: number,
) {
  if (usesProgressiveBonus) {
    return calculateDynamicSalesBonusJS(grossProfit, employeeSalary, rules, targetOverride)
  }

  const profitLoss = Number(grossProfit || 0) * 0.95
  const target = targetOverride === undefined ? Math.max(0, employeeSalary * 2) : Math.max(0, targetOverride)
  const eligibleProfit = Math.max(0, profitLoss - target)
  const coefficient = eligibleProfit > 0 ? 0.20 : 0
  const totalBonusQuarter = eligibleProfit * coefficient
  return {
    target,
    bonusRate: coefficient,
    totalBonusQuarter,
    bonusPerMonth: totalBonusQuarter / 3,
    coefficient: employeeSalary > 0 && eligibleProfit > 0 ? Math.round((profitLoss / employeeSalary) * 100) / 100 : 0,
  }
}

type HistoryFlatRow = {
  periodId: number
  periodLabel: string
  fromDate?: string | null
  tillDate?: string | null
  payoutPeriods: string[]
  createdAt: string
  totalPeriodPnL: number
  jobCount: number
  salesRep: string
  repJobCount: number
  repPnL: number
  repBonus: number
  repTarget: number
  repRate: number
  repTotalBonus: number
  repPaymentReceivedTotal: number
  repHoldBonusTotal: number
  repCoefficient: number
  isFirstRep: boolean
  repCount: boolean | number
  sourceFilename?: string | null
  employeeSalary: number
  isPnLOverridden: boolean
  isTargetOverridden: boolean
  isRateOverridden: boolean
  isTotalBonusOverridden: boolean
  isMonthlyBonusOverridden: boolean
  remark: string
  repBonusRules: any[]
  usesProgressiveBonus: boolean
  repMonthlyPayouts: Array<{
    payout_period: string
    amount: number
    base_amount?: number
    released_amount?: number
  }>
}

type EditDraftState = {
  repJobCount: string
  repPnL: string
  repTarget: string
  repRate: string
  repTotalBonus: string
  repBonus: string
  remark: string
}

function recalculateDraft(
  currentDraft: EditDraftState,
  currentManualChecked: {
    repPnL: boolean
    repTarget: boolean
    repRate: boolean
    repTotalBonus: boolean
    repBonus: boolean
  },
  row: HistoryFlatRow
): EditDraftState {
  const profitLoss = currentManualChecked.repPnL
    ? parseVndInput(currentDraft.repPnL)
    : row.repPnL * 0.95;

  const grossProfit = profitLoss / 0.95;
  const defaultCalc = calculateEmployeeBonusJS(
    grossProfit,
    row.employeeSalary,
    row.repBonusRules,
    row.usesProgressiveBonus,
  );

  const target = currentManualChecked.repTarget
    ? parseVndInput(currentDraft.repTarget)
    : defaultCalc.target;

  const pfCountBn = Math.max(0, profitLoss - target);

  let totalBonus = 0;
  let rate = 0;
  
  if (currentManualChecked.repRate) {
    rate = (parseFloat(currentDraft.repRate) || 0) * 0.01;
    if (!currentManualChecked.repTotalBonus) {
      totalBonus = pfCountBn > 0 ? pfCountBn * rate : 0;
    }
  } else {
    // Re-run calc with override target if target was overridden but not rate
    const customCalc = calculateEmployeeBonusJS(
      grossProfit,
      target > 0 ? target / (row.repBonusRules[0]?.max || 2) : row.employeeSalary,
      row.repBonusRules,
      row.usesProgressiveBonus,
      target,
    );
    totalBonus = customCalc.totalBonusQuarter;
    rate = customCalc.bonusRate;
  }

  if (currentManualChecked.repTotalBonus) {
    totalBonus = parseVndInput(currentDraft.repTotalBonus);
  }

  let monthlyBonus = 0;
  if (currentManualChecked.repBonus) {
    monthlyBonus = parseVndInput(currentDraft.repBonus);
  } else {
    monthlyBonus = totalBonus / 3;
  }

  if (pfCountBn <= 0) {
    rate = 0;
    totalBonus = 0;
    monthlyBonus = 0;
  }

  return {
    ...currentDraft,
    repPnL: currentManualChecked.repPnL ? currentDraft.repPnL : String(profitLoss),
    repTarget: currentManualChecked.repTarget ? currentDraft.repTarget : String(target),
    repRate: currentManualChecked.repRate ? currentDraft.repRate : String(Math.round(rate * 100)),
    repTotalBonus: currentManualChecked.repTotalBonus ? currentDraft.repTotalBonus : String(totalBonus),
    repBonus: currentManualChecked.repBonus ? currentDraft.repBonus : String(monthlyBonus),
  };
}

function HistoryMonthFloatingTooltip({ ariaLabel, children }: { ariaLabel: string; children: ReactNode }) {
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [position, setPosition] = useState<{ left: number; bottom: number; width: number } | null>(null)

  function showTooltip() {
    const trigger = triggerRef.current
    if (!trigger) return
    const rect = trigger.getBoundingClientRect()
    const width = Math.min(350, Math.max(240, window.innerWidth - 24))
    const halfWidth = width / 2
    setPosition({
      left: Math.min(window.innerWidth - halfWidth - 12, Math.max(halfWidth + 12, rect.left + rect.width / 2)),
      bottom: Math.max(12, window.innerHeight - rect.top + 9),
      width,
    })
  }

  useEffect(() => {
    if (!position) return
    const closeTooltip = () => setPosition(null)
    window.addEventListener('resize', closeTooltip)
    window.addEventListener('scroll', closeTooltip, true)
    return () => {
      window.removeEventListener('resize', closeTooltip)
      window.removeEventListener('scroll', closeTooltip, true)
    }
  }, [position])

  return (
    <>
      <span
        ref={triggerRef}
        className="commission-tooltip-icon"
        tabIndex={0}
        role="button"
        aria-label={ariaLabel}
        aria-expanded={!!position}
        onMouseEnter={showTooltip}
        onMouseLeave={() => setPosition(null)}
        onFocus={showTooltip}
        onBlur={() => setPosition(null)}
        onClick={() => position ? setPosition(null) : showTooltip()}
      >?</span>
      {position && createPortal(
        <div
          role="tooltip"
          style={{
            position: 'fixed',
            left: position.left,
            bottom: position.bottom,
            transform: 'translateX(-50%)',
            zIndex: 10000,
            width: position.width,
            maxHeight: 'min(420px, calc(100vh - 24px))',
            overflowY: 'auto',
            background: '#1e293b',
            color: '#fff',
            textAlign: 'left',
            padding: '12px 14px',
            borderRadius: 8,
            fontSize: 11,
            fontWeight: 500,
            lineHeight: 1.5,
            whiteSpace: 'normal',
            boxShadow: '0 10px 24px rgba(0,0,0,.38)',
          }}
        >
          {children}
          <span aria-hidden="true" style={{ position: 'absolute', top: '100%', left: '50%', marginLeft: -6, borderWidth: 6, borderStyle: 'solid', borderColor: '#1e293b transparent transparent transparent' }} />
        </div>,
        document.body,
      )}
    </>
  )
}

// ══════════════════════════════════════════════════════════
// Main Component
// ══════════════════════════════════════════════════════════
export function CommissionTab({ apiBase, token, notificationFocus, externalRefreshVersion = 0 }: Props) {
  const confirm = useConfirmDialog()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const receivableFileInputRef = useRef<HTMLInputElement>(null)

  // ── Import state ──────────────────────────────────────
  const [step, setStep] = useState<'idle' | 'preview' | 'saving' | 'done' | 'detail'>('idle')
  const [isDragging, setIsDragging] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Parsed data
  const [rows, setRows] = useState<JobPnLRow[]>([])
  const [fileName, setFileName] = useState<string | null>(null)
  const [periodLabel, setPeriodLabel] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [tillDate, setTillDate] = useState('')
  const [periodParseError, setPeriodParseError] = useState<string | null>(null)
  const [pendingImports, setPendingImports] = useState<PendingCommissionImport[]>([])
  const [activeImportIndex, setActiveImportIndex] = useState(0)

  // ── Detail state ──────────────────────────────────────
  const [detailPeriodLabel, setDetailPeriodLabel] = useState('')
  const [detailPeriodId, setDetailPeriodId] = useState<number | null>(null)
  const [detailSalesRep, setDetailSalesRep] = useState('')
  const [detailFileName, setDetailFileName] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailJobTab, setDetailJobTab] = useState<DetailJobTab>('source')
  const [manualJobEditorOpen, setManualJobEditorOpen] = useState(false)
  const [receivableOpen, setReceivableOpen] = useState(false)
  const [receivableJob, setReceivableJob] = useState<JobPnLRow | null>(null)
  const [receivableAttachments, setReceivableAttachments] = useState<CommissionReceivableAttachment[]>([])
  const [receivableNote, setReceivableNote] = useState('')
  const [receivableLoading, setReceivableLoading] = useState(false)
  const [selectedReceivableJobIds, setSelectedReceivableJobIds] = useState<Set<number>>(new Set())
  const detailCloseButtonRef = useRef<HTMLButtonElement>(null)
  const detailReturnFocusRef = useRef<HTMLElement | null>(null)

  // ── History ───────────────────────────────────────────
  const [savedPeriods, setSavedPeriods] = useState<SavedPeriod[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [wallets, setWallets] = useState<CommissionWalletSummary[]>([])
  const [, setWalletLoading] = useState(false)
  const [walletFocus, setWalletFocus] = useState<CommissionNotificationFocus | null>(null)
  const [commissionRefreshVersion, setCommissionRefreshVersion] = useState(0)

  // ── Edit overrides state ──────────────────────────────
  const [editingRowKey, setEditingRowKey] = useState<string | null>(null) // periodId-salesRep
  const [editDraft, setEditDraft] = useState<{
    repJobCount: string
    repPnL: string
    repTarget: string
    repRate: string
    repTotalBonus: string
    repBonus: string
    remark: string
  } | null>(null)
  const [manualChecked, setManualChecked] = useState<{
    repPnL: boolean
    repTarget: boolean
    repRate: boolean
    repTotalBonus: boolean
    repBonus: boolean
  }>({
    repPnL: false,
    repTarget: false,
    repRate: false,
    repTotalBonus: false,
    repBonus: false,
  })

  const [remarkModalData, setRemarkModalData] = useState<{
    row: any
    remark: string
  } | null>(null)

  const [overlapWarningData, setOverlapWarningData] = useState<{
    conflicts: Array<{ id: number, label: string, from: string, till: string, isExact: boolean }>
    onConfirm: () => void
    mergePreview?: CommissionMergePreviewSummary
    selectedManualJobIds: number[]
    onMerge?: (manualJobIds: number[]) => void
  } | null>(null)

  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

  async function loadHistory(showLoading = true) {
    if (showLoading) setLoadingHistory(true)
    try {
      const res = await credentialedFetch(`${apiBase}/api/commission/periods`, { headers: authHeader })
      if (res.ok) setSavedPeriods(await res.json())
    } catch { /* ignore */ } finally { if (showLoading) setLoadingHistory(false) }
  }

  async function loadWallet(showLoading = true) {
    if (showLoading) setWalletLoading(true)
    try {
      // Lịch sử import có thể chứa nhiều nhân viên và nhiều kỳ. Luôn tải toàn bộ
      // ví để cột "Đang giữ" được ghép đúng theo từng sales + period, không lấy
      // nhầm số tổng hợp của kỳ đang được focus.
      const res = await credentialedFetch(`${apiBase}/api/commission/wallet`, { headers: authHeader })
      if (res.ok) setWallets(await res.json())
    } finally { if (showLoading) setWalletLoading(false) }
  }

  async function refreshCommissionViews(refreshFunnel = true, showLoading = true) {
    await Promise.all([loadHistory(showLoading), loadWallet(showLoading)])
    if (refreshFunnel) setCommissionRefreshVersion(version => version + 1)
  }

  function focusWalletFromHistory(row: { periodId: number; periodLabel: string; salesRep: string }) {
    const focus = { periodId: row.periodId, periodLabel: row.periodLabel, salesRep: row.salesRep }
    setWalletFocus(focus)
    void loadWallet()
    window.setTimeout(() => document.getElementById('commission-wallet-focus')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0)
  }

  async function syncWallet(periodId?: number) {
    setWalletLoading(true)
    try {
      const res = await credentialedFetch(`${apiBase}/api/commission/wallet/sync`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify(periodId ? { period_id: periodId } : {}),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể đồng bộ ví thưởng.')
      await refreshCommissionViews()
      setSuccessMsg(data.message)
    } catch (err: any) { setError(err.message) } finally { setWalletLoading(false) }
  }

  async function updateJobPayment(jobId: number, paymentReceived: string) {
    if (!detailPeriodId) return
    setIsLoading(true)
    try {
      const res = await credentialedFetch(`${apiBase}/api/commission/periods/${detailPeriodId}/jobs/${jobId}/payment`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({ payment_received: paymentReceived }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể cập nhật Payment Received.')
      setRows(previous => previous.map(row => Number(row.id) === jobId ? { ...row, paymentReceived } : row))
      await syncWallet(detailPeriodId)
      setSuccessMsg(data.message)
    } catch (err: any) { setError(err.message) } finally { setIsLoading(false) }
  }

  useEffect(() => {
    if (!token) return
    void loadHistory()
    void loadWallet()
  }, [apiBase, token])

  useEffect(() => {
    if (!token || externalRefreshVersion <= 0) return
    void refreshCommissionViews()
  }, [externalRefreshVersion])

  useEffect(() => {
    if (!notificationFocus || !token) return
    setStep('idle')
    setWalletFocus(notificationFocus)
    void loadWallet()
    window.setTimeout(() => {
      document.getElementById('commission-wallet-focus')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 0)
  }, [notificationFocus?.requestKey, token])

  useEffect(() => {
    if (!detailOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    if (!manualJobEditorOpen) detailCloseButtonRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (receivableOpen) closeReceivableModal()
      else if (manualJobEditorOpen) setManualJobEditorOpen(false)
      else closeDetailModal()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [detailOpen, manualJobEditorOpen, receivableOpen])

  async function deleteSalesRepCommission(id: number, label: string, salesRep: string) {
    if (!await confirm({ title: 'Xóa commission nhân viên', message: `Chỉ xóa JOB, commission và phễu thưởng của ${salesRep} trong kỳ "${label}". Các nhân viên commission khác không bị ảnh hưởng.`, confirmLabel: 'Xóa nhân viên này', tone: 'danger' })) return
    try {
      const res = await credentialedFetch(`${apiBase}/api/commission/periods/${id}/reps/${encodeURIComponent(salesRep)}`, {
        method: 'DELETE', headers: authHeader,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể xóa commission của nhân viên.')
      await refreshCommissionViews()
      setSuccessMsg(data.message)
    } catch (err: any) { setError(err.message) }
  }

  async function handleSaveOverride(periodId: number, salesRep: string) {
    if (!editDraft) return
    setIsLoading(true)
    setError(null)
    try {
      const payload = {
        override_job_count: editDraft.repJobCount === '' ? null : parseInt(editDraft.repJobCount, 10),
        override_profit_loss: manualChecked.repPnL ? (editDraft.repPnL === '' ? null : parseVndInput(editDraft.repPnL) / 0.95) : null,
        override_target: manualChecked.repTarget ? (editDraft.repTarget === '' ? null : parseVndInput(editDraft.repTarget)) : null,
        override_bonus_rate: manualChecked.repRate ? (editDraft.repRate === '' ? null : parseFloat(editDraft.repRate) * 0.01) : null,
        override_total_bonus: manualChecked.repTotalBonus ? (editDraft.repTotalBonus === '' ? null : parseVndInput(editDraft.repTotalBonus)) : null,
        override_monthly_bonus: manualChecked.repBonus ? (editDraft.repBonus === '' ? null : parseVndInput(editDraft.repBonus)) : null,
        remark: editDraft.remark,
      }
      const res = await credentialedFetch(`${apiBase}/api/commission/periods/${periodId}/reps/${encodeURIComponent(salesRep)}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi lưu chỉnh sửa.')
      
      setEditingRowKey(null)
      setEditDraft(null)
      await syncWallet(periodId)
      setSuccessMsg(data.message || 'Đã lưu chỉnh sửa thành công.')
    } catch (err: any) {
      setError(`Lỗi: ${err.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleSaveRemark(row: any, newRemark: string) {
    setIsLoading(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const payload = {
        override_job_count: row.repJobCount,
        override_profit_loss: row.isPnLOverridden ? row.repPnL : null,
        override_target: row.isTargetOverridden ? row.repTarget : null,
        override_bonus_rate: row.isRateOverridden ? row.repRate : null,
        override_total_bonus: row.isTotalBonusOverridden ? row.repTotalBonus : null,
        override_monthly_bonus: row.isMonthlyBonusOverridden ? row.repBonus : null,
        remark: newRemark,
      }
      const res = await credentialedFetch(`${apiBase}/api/commission/periods/${row.periodId}/reps/${encodeURIComponent(row.salesRep)}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi lưu ghi chú.')
      
      setSuccessMsg(`Đã lưu ghi chú cho ${row.salesRep} thành công.`)
      setRemarkModalData(null)
      await loadHistory()
    } catch (err: any) {
      setError(`Lỗi: ${err.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  function handleCheckboxChange(
    field: 'repPnL' | 'repTarget' | 'repRate' | 'repTotalBonus' | 'repBonus',
    checked: boolean,
    row: HistoryFlatRow
  ) {
    if (!editDraft) return;
    const newManualChecked = { ...manualChecked, [field]: checked };
    setManualChecked(newManualChecked);
    setEditDraft(recalculateDraft(editDraft, newManualChecked, row));
  }

  // ── File handling ─────────────────────────────────────
  function applyPendingImport(item: PendingCommissionImport, index: number) {
    setActiveImportIndex(index)
    setRows(item.rows)
    setFileName(item.fileName)
    setPeriodLabel(item.periodLabel)
    setFromDate(item.fromDate)
    setTillDate(item.tillDate)
    setPeriodParseError(item.periodParseError)
  }

  function importsWithActiveEdits(): PendingCommissionImport[] {
    if (pendingImports.length === 0) {
      return fileName ? [{ fileName, rows, periodLabel, fromDate, tillDate, periodParseError }] : []
    }
    return pendingImports.map((item, index) => index === activeImportIndex
      ? { ...item, rows, periodLabel, fromDate, tillDate, periodParseError }
      : item)
  }

  function selectPendingImport(index: number) {
    const updated = importsWithActiveEdits()
    const selected = updated[index]
    if (!selected) return
    setPendingImports(updated)
    applyPendingImport(selected, index)
  }

  async function handleFiles(fileList: FileList | File[]) {
    const selected = Array.from(fileList)
    if (selected.length === 0) return
    if (selected.length > 50) {
      setError('Mỗi lần chỉ được chọn tối đa 50 file Excel.')
      return
    }

    const excelFiles = selected.filter(file => /\.(xlsx|xls)$/i.test(file.name))
    const rejectedNames = selected.filter(file => !/\.(xlsx|xls)$/i.test(file.name)).map(file => file.name)
    setIsLoading(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const parsedResults = await Promise.all(excelFiles.map(async file => {
        try {
          const buf = await file.arrayBuffer()
          const parsed = parseClimaxBuffer(buf)
          if (parsed.rows.length === 0) throw new Error('không tìm thấy dữ liệu JOB')
          return {
            item: {
              fileName: file.name,
              rows: parsed.rows,
              periodLabel: parsed.periodLabel,
              fromDate: parsed.fromDate,
              tillDate: parsed.tillDate,
              periodParseError: parsed.periodError,
            } satisfies PendingCommissionImport,
          }
        } catch (err: any) {
          return { fileName: file.name, error: err?.message || 'không đọc được file' }
        }
      }))
      const validImports = parsedResults.flatMap(result => 'item' in result && result.item ? [result.item] : [])
      const parseErrors = parsedResults.flatMap(result => 'error' in result ? [`${result.fileName}: ${result.error}`] : [])
      if (validImports.length === 0) {
        const details = [...rejectedNames.map(name => `${name}: không phải file Excel`), ...parseErrors]
        setError(details.length ? details.join(' · ') : 'Không tìm thấy file Excel hợp lệ.')
        return
      }

      setPendingImports(validImports)
      applyPendingImport(validImports[0], 0)
      setStep('preview')
      const skipped = [...rejectedNames.map(name => `${name}: không phải file Excel`), ...parseErrors]
      const periodErrors = validImports.filter(item => item.periodParseError).map(item => `${item.fileName}: ${item.periodParseError}`)
      if (skipped.length || periodErrors.length) {
        setError([...skipped, ...periodErrors].join(' · '))
      }
    } finally {
      setIsLoading(false)
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setIsDragging(false)
    if (step === 'preview') return
    if (e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files)
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.length) void handleFiles(e.target.files)
    e.target.value = ''
  }

  function resetImport() {
    setStep('idle'); setRows([]); setFileName(null)
    setPeriodLabel(''); setFromDate(''); setTillDate('')
    setPeriodParseError(null)
    setPendingImports([]); setActiveImportIndex(0)
    setError(null); setSuccessMsg(null)
  }

  function closeDetailModal() {
    closeReceivableModal()
    setManualJobEditorOpen(false)
    setDetailOpen(false)
    setRows([])
    setSelectedReceivableJobIds(new Set())
    setReceivableNote('')
    setDetailPeriodLabel('')
    setDetailPeriodId(null)
    setDetailSalesRep('')
    setDetailFileName(null)
    setDetailJobTab('source')
    window.setTimeout(() => detailReturnFocusRef.current?.focus(), 0)
  }

  function closeReceivableModal() {
    setReceivableOpen(false)
    setReceivableJob(null)
    setReceivableAttachments([])
  }

  async function fetchJobReceivables(job: JobPnLRow) {
    if (detailPeriodId == null) return []
    const jobId = Number(job.id)
    const res = await credentialedFetch(
      `${apiBase}/api/commission/periods/${detailPeriodId}/jobs/${jobId}/receivables`,
      { headers: authHeader },
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Không thể tải chi tiết công nợ của JOB.')
    return data as CommissionReceivableAttachment[]
  }

  async function openReceivableModal(job: JobPnLRow) {
    setReceivableLoading(true)
    setError(null)
    try {
      const attachments = await fetchJobReceivables(job)
      setReceivableJob(job)
      setReceivableAttachments(attachments)
      setReceivableOpen(true)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setReceivableLoading(false)
    }
  }

  function chooseBulkReceivableFiles() {
    if (!rows.length) {
      setError('Không có JOB nào để đối chiếu công nợ.')
      return
    }
    receivableFileInputRef.current?.click()
  }

  async function handleReceivableFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files || [])
    event.target.value = ''
    const selectedJobIds = selectedReceivableJobIds.size
      ? Array.from(selectedReceivableJobIds)
      : rows.map(row => Number(row.id)).filter(Number.isFinite)
    if (!selectedFiles.length || !selectedJobIds.length || detailPeriodId == null) return
    setReceivableLoading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', selectedFiles[0])
      formData.append('note', receivableNote.trim())
      formData.append('job_ids', JSON.stringify(selectedJobIds))
      const res = await credentialedFetch(
        `${apiBase}/api/commission/periods/${detailPeriodId}/receivables/reconcile`,
        { method: 'POST', headers: authHeader, body: formData },
      )
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể đối chiếu hồ sơ công nợ.')
      const result = data as CommissionReceivableReconciliation
      const updatesById = new Map(result.updates.map(update => [update.job_id, update]))
      setRows(previous => previous.map(row => {
        const update = updatesById.get(Number(row.id))
        return update ? {
          ...row,
          paymentReceived: 'YES',
          receivableAmount: update.receivable_amount,
          balanceAmount: update.balance_amount,
          paymentReceivedAmount: update.payment_received_amount,
          holdBonusPercent: update.hold_bonus_percent,
          holdBonusAmount: update.hold_bonus_amount,
          receivableCount: Number(row.receivableCount || 0) + 1,
        } : row
      }))
      setSelectedReceivableJobIds(new Set())
      setReceivableNote('')
      await refreshCommissionViews()
      setSuccessMsg(`Đã đối chiếu ${result.matched_jobs} JOB, bỏ qua ${result.ignored_non_positive_rows} dòng Balance âm${result.unmatched_positive_jobs ? `; ${result.unmatched_positive_jobs} JOB Balance bằng 0 hoặc dương không thuộc SALE/kỳ đang xem` : ''}.`)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setReceivableLoading(false)
    }
  }

  function toggleReceivableJob(jobId: number) {
    setSelectedReceivableJobIds(previous => {
      const next = new Set(previous)
      if (next.has(jobId)) next.delete(jobId)
      else next.add(jobId)
      return next
    })
  }

  async function downloadReceivable(attachment: CommissionReceivableAttachment) {
    if (detailPeriodId == null || !receivableJob) return
    setReceivableLoading(true)
    try {
      const res = await credentialedFetch(
        `${apiBase}/api/commission/periods/${detailPeriodId}/jobs/${Number(receivableJob.id)}/receivables/${attachment.id}/file`,
        { headers: authHeader },
      )
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Không thể tải tệp công nợ.')
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = attachment.original_filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setReceivableLoading(false)
    }
  }

  async function deleteReceivable(attachment: CommissionReceivableAttachment) {
    if (detailPeriodId == null || !receivableJob) return
    if (!await confirm({
      title: 'Xóa hồ sơ công nợ',
      message: `Xóa tệp “${attachment.original_filename}” khỏi JOB ${String(receivableJob.jobNo || '')}?`,
      confirmLabel: 'Xóa tệp',
      tone: 'danger',
    })) return
    setReceivableLoading(true)
    try {
      const jobId = Number(receivableJob.id)
      const res = await credentialedFetch(
        `${apiBase}/api/commission/periods/${detailPeriodId}/jobs/${jobId}/receivables/${attachment.id}`,
        { method: 'DELETE', headers: authHeader },
      )
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Không thể xóa hồ sơ công nợ.')
      }
      const attachments = receivableAttachments.filter(item => item.id !== attachment.id)
      setReceivableAttachments(attachments)
      setRows(previous => previous.map(row => Number(row.id) === jobId
        ? { ...row, receivableCount: attachments.length }
        : row))
      setSuccessMsg(`Đã xóa tệp công nợ ${attachment.original_filename}.`)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setReceivableLoading(false)
    }
  }

  function openManualJobEditor() {
    if (detailPeriodId == null || !detailSalesRep) return
    setWalletFocus({
      periodId: detailPeriodId,
      periodLabel: detailPeriodLabel,
      salesRep: detailSalesRep,
      target: 'job-detail',
      requestKey: Date.now(),
    })
    setManualJobEditorOpen(true)
  }

  async function closeManualJobEditorAndRefresh() {
    setManualJobEditorOpen(false)
    if (detailPeriodId == null) return
    try {
      let url = `${apiBase}/api/commission/periods/${detailPeriodId}/jobs`
      if (detailSalesRep && detailSalesRep !== '—') url += `?sales_rep=${encodeURIComponent(detailSalesRep)}`
      const res = await credentialedFetch(url, { headers: authHeader })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể đồng bộ lại chi tiết JOB.')
      setRows(data)
      await refreshCommissionViews()
    } catch (err: any) {
      setError(err.message)
    }
  }

  async function viewPeriodJobs(periodId: number, periodLabel: string, salesRep: string, sourceFilename: string | null) {
    detailReturnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setIsLoading(true);
    setError(null);
    try {
      let url = `${apiBase}/api/commission/periods/${periodId}/jobs`;
      if (salesRep && salesRep !== '—') {
        url += `?sales_rep=${encodeURIComponent(salesRep)}`;
      }
      const res = await credentialedFetch(url, { headers: authHeader });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Không thể tải chi tiết công việc.');
      }
      const jobs = await res.json();
      setRows(jobs);
      setDetailPeriodLabel(periodLabel);
      setDetailPeriodId(periodId);
      setDetailSalesRep(salesRep);
      setDetailFileName(sourceFilename);
      setDetailJobTab('source');
      setSelectedReceivableJobIds(new Set());
      setReceivableNote('');
      setDetailOpen(true);
    } catch (err: any) {
      setError(`Lỗi: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  }

  // ── Save to DB ─────────────────────────────────────────
  function buildImportPayloads(imports: PendingCommissionImport[]) {
    return imports.map(item => ({
      period_label: item.periodLabel,
      from_date: item.fromDate || null,
      till_date: item.tillDate || null,
      source_filename: item.fileName,
      jobs: item.rows.map(r => ({
        job_no: String(r.jobNo),
        job_date: r.jobDate ? String(r.jobDate) : null,
        hbl: r.hbl || null, mbl: r.mbl || null,
        customer: r.customer || null, vendor: r.vendor || null,
        sales_rep: r.salesRep || null, shipper: r.shipper || null,
        consignee: r.consignee || null, sub_type: r.subType || null,
        container_string: r.containerString || null,
        wt: Number(r.wt) || null, vol: Number(r.vol) || null,
        carrier_booking_no: r.carrierBookingNo || null,
        por: r.por || null, final_destination: r.finalDestination || null,
        realized_revenue: Number(r.realizedRevenue),
        unrealized_revenue: Number(r.unrealizedRevenue),
        realized_cost: Number(r.realizedCost),
        unrealized_cost: Number(r.unrealizedCost),
        profit_loss: Number(r.profitLoss),
        container_picked: r.containerPicked || null,
        payment_received: r.paymentReceived || null,
      })),
    }))
  }

  async function executeSave() {
    setStep('saving'); setError(null)
    try {
      const imports = importsWithActiveEdits()
      const payloads = buildImportPayloads(imports)
      const isBatch = payloads.length > 1
      const res = await credentialedFetch(`${apiBase}/api/commission/import${isBatch ? '/batch' : ''}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify(isBatch ? { imports: payloads } : payloads[0]),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi lưu.')
      const totalJobs = imports.reduce((sum, item) => sum + item.rows.length, 0)
      setSuccessMsg(data.message || `Đã lưu ${imports.length} file với ${totalJobs} jobs vào cơ sở dữ liệu.`)
      setStep('done')
      await loadHistory()
      await syncWallet(isBatch ? undefined : data.period_id)
    } catch (err: any) {
      setError(err.message); setStep('preview')
    }
  }

  async function executeMerge(imports: PendingCommissionImport[], overwriteManualJobIds: number[]) {
    setOverlapWarningData(null)
    setStep('saving')
    setError(null)
    try {
      const res = await credentialedFetch(`${apiBase}/api/commission/import/merge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({
          imports: buildImportPayloads(imports),
          overwrite_manual_job_ids: overwriteManualJobIds,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể gộp dữ liệu Commission vào kỳ hiện tại.')
      setSuccessMsg(data.message || 'Đã gộp dữ liệu Commission an toàn theo từng JOB.')
      setStep('done')
      await loadHistory()
      const periodIds = Array.isArray(data.period_ids) ? data.period_ids : []
      for (const periodId of periodIds) await syncWallet(Number(periodId))
    } catch (err: any) {
      setError(err.message)
      setStep('preview')
    }
  }

  async function handleConfirmSave() {
    const imports = importsWithActiveEdits()
    const invalidImport = imports.find(item => {
      const start = parseDateStringToDate(item.fromDate)
      const end = parseDateStringToDate(item.tillDate)
      return item.periodParseError || !start || !end || start > end
    })
    if (invalidImport) {
      setError(`${invalidImport.fileName}: ${invalidImport.periodParseError || 'Khoảng ngày nguồn chưa hợp lệ. Hãy kiểm tra tiêu đề “Job Date From … Till …”.'}`)
      return
    }

    setPendingImports(imports)
    const conflicts = imports.flatMap(item => {
      const newStart = parseDateStringToDate(item.fromDate)!
      const newEnd = parseDateStringToDate(item.tillDate)!
      return savedPeriods.filter(p => {
          if (!p.from_date || !p.till_date) return false
          const savedStart = parseDateStringToDate(p.from_date)
          const savedEnd = parseDateStringToDate(p.till_date)
          return !!savedStart && !!savedEnd && doMonthsOverlap(newStart, newEnd, savedStart, savedEnd)
        }).map(p => {
          const savedStart = parseDateStringToDate(p.from_date || '')
          const savedEnd = parseDateStringToDate(p.till_date || '')
          const isExact = !!(savedStart && savedEnd && savedStart.getTime() === newStart.getTime() && savedEnd.getTime() === newEnd.getTime())
          return { id: p.id, label: `${item.fileName} ↔ ${p.period_label}`, from: p.from_date || '', till: p.till_date || '', isExact }
        })
    })

    if (conflicts.length > 0) {
      let mergePreview: CommissionMergePreviewSummary | undefined
      const hasExactConflict = conflicts.some(conflict => conflict.isExact)
      if (hasExactConflict) {
        try {
          const previewRes = await credentialedFetch(`${apiBase}/api/commission/import/merge-preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeader },
            body: JSON.stringify({ imports: buildImportPayloads(imports) }),
          })
          const previewData = await previewRes.json()
          if (!previewRes.ok) throw new Error(previewData.detail || 'Không thể kiểm tra các JOB trùng.')

          const manualById = new Map<number, CommissionMergeManualJob>()
          let newJobs = 0
          let automaticUpdates = 0
          for (const preview of Array.isArray(previewData.imports) ? previewData.imports : []) {
            newJobs += Number(preview.new_jobs) || 0
            automaticUpdates += Number(preview.automatic_updates) || 0
            for (const job of Array.isArray(preview.manual_jobs) ? preview.manual_jobs : []) {
              const jobId = Number(job.job_id)
              const sourceFilename = String(preview.source_filename || 'File đang tải lên')
              const previous = manualById.get(jobId)
              if (previous) {
                if (!previous.sourceFilename.split('; ').includes(sourceFilename)) {
                  previous.sourceFilename = `${previous.sourceFilename}; ${sourceFilename}`
                }
                continue
              }
              manualById.set(jobId, {
                jobId,
                jobNo: String(job.job_no || '—'),
                salesRep: job.sales_rep ? String(job.sales_rep) : null,
                reasons: Array.isArray(job.reasons) ? job.reasons.map(String) : [],
                sourceFilename,
                periodId: Number(preview.period_id),
                periodLabel: String(preview.period_label || ''),
              })
            }
          }
          mergePreview = { newJobs, automaticUpdates, manualJobs: Array.from(manualById.values()) }
        } catch (err: any) {
          setError(err.message)
          return
        }
      }

      setOverlapWarningData({
        conflicts,
        mergePreview,
        selectedManualJobIds: [],
        onConfirm: () => {
          setOverlapWarningData(null)
          void executeSave()
        },
        onMerge: hasExactConflict
          ? (manualJobIds: number[]) => { void executeMerge(imports, manualJobIds) }
          : undefined,
      })
      return
    }
    await executeSave()
  }

  // ── Computed totals ────────────────────────────────────
  const totalPnL = rows.reduce((s, r) => s + Number(r.profitLoss), 0)
  const totalRevRealized = rows.reduce((s, r) => s + Number(r.realizedRevenue), 0)
  const detailRows = useMemo(() => {
    if (detailJobTab === 'source') return rows
    const paymentStatus = detailJobTab === 'payable' ? 'YES' : 'NO'
    return rows.filter(row => String(row.paymentReceived || 'NO').trim().toUpperCase() === paymentStatus)
  }, [detailJobTab, rows])
  const detailJobIds = useMemo(() => detailRows.map(row => Number(row.id)), [detailRows])
  const allDetailRowsSelected = detailJobIds.length > 0
    && detailJobIds.every(jobId => selectedReceivableJobIds.has(jobId))
  function toggleAllDetailReceivableJobs() {
    setSelectedReceivableJobIds(previous => {
      const next = new Set(previous)
      if (allDetailRowsSelected) detailJobIds.forEach(jobId => next.delete(jobId))
      else detailJobIds.forEach(jobId => next.add(jobId))
      return next
    })
  }
  const detailPayableCount = useMemo(
    () => rows.filter(row => String(row.paymentReceived || 'NO').trim().toUpperCase() === 'YES').length,
    [rows],
  )
  const detailHeldCount = rows.length - detailPayableCount
  const detailTotalPnL = detailRows.reduce((sum, row) => sum + Number(row.profitLoss || 0), 0)
  const detailTotalRevRealized = detailRows.reduce((sum, row) => sum + Number(row.realizedRevenue || 0), 0)

  // ── Flatten history rows ───────────────────────────────
  // Each period × sales_rep = one flat row
  const historyRows: HistoryFlatRow[] = savedPeriods.flatMap(p => {
    const reps = p.sales_rep_summary?.length ? p.sales_rep_summary : [
      { sales_rep: '—', job_count: p.job_count, total_profit_loss: p.total_profit_loss, sales_bonus: 0, target: 0, bonus_rate: 0, total_bonus_quarter: 0, employee_salary: 0, is_pnl_overridden: false, is_target_overridden: false, is_rate_overridden: false, is_total_bonus_overridden: false, is_monthly_bonus_overridden: false, remark: '' }
    ]
    return reps.map((s, si) => ({
      periodId: p.id,
      periodLabel: p.period_label,
      fromDate: p.from_date,
      tillDate: p.till_date,
      payoutPeriods: p.payout_periods || [],
      createdAt: p.created_at,
      totalPeriodPnL: p.total_profit_loss,
      jobCount: p.job_count,
      salesRep: s.sales_rep,
      repJobCount: s.job_count,
      repPnL: s.total_profit_loss,
      repBonus: s.sales_bonus ?? 0,
      repTarget: s.target ?? 0,
      repRate: s.bonus_rate ?? 0,
      repTotalBonus: s.total_bonus_quarter ?? 0,
      repPaymentReceivedTotal: s.payment_received_total ?? 0,
      repHoldBonusTotal: s.hold_bonus_total ?? 0,
      repCoefficient: s.coefficient ?? 0,
      isFirstRep: si === 0,
      repCount: reps.length,
      sourceFilename: p.source_filename,
      employeeSalary: s.employee_salary ?? 0,
      isPnLOverridden: !!s.is_pnl_overridden,
      isTargetOverridden: !!s.is_target_overridden,
      isRateOverridden: !!s.is_rate_overridden,
      isTotalBonusOverridden: !!s.is_total_bonus_overridden,
      isMonthlyBonusOverridden: !!s.is_monthly_bonus_overridden,
      remark: s.remark ?? '',
      repBonusRules: s.bonus_rules || [],
      usesProgressiveBonus: s.uses_progressive_bonus !== false,
      repMonthlyPayouts: s.monthly_payouts || [],
    }))
  })

  function getWalletPeriodView(row: HistoryFlatRow) {
    const wallet = wallets.find(item => item.sales_rep === row.salesRep && (
      item.period_summaries?.some(period => period.period_id === row.periodId) ||
      item.period_labels?.includes(row.periodLabel)
    ))
    const period = wallet?.period_summaries?.find(item => item.period_id === row.periodId)
    const heldAmount = Number(period?.quarter_hold_amount ?? row.repHoldBonusTotal)
    const paymentReceivedTotal = Number(period?.payment_received_total ?? period?.gross_total_bonus_quarter ?? row.repPaymentReceivedTotal)
    const target = getTargetView(row)
    const isAboveTarget = row.repPnL * 0.95 > target
    const formulaTotalBonus = isAboveTarget
      ? Number(period?.formula_total_bonus_quarter ?? row.repTotalBonus)
      : 0
    const formulaCoefficient = isAboveTarget
      ? Number(period?.formula_effective_coefficient ?? row.repRate ?? row.repCoefficient ?? 0)
      : 0
    const formulaMonthlyBonus = isAboveTarget
      ? Number(period?.formula_monthly_bonus ?? row.repBonus ?? formulaTotalBonus / 3)
      : 0
    const monthlyPayout = isAboveTarget
      ? Number(period?.monthly_payout ?? Math.max(0, formulaMonthlyBonus - heldAmount))
      : 0
    const temporaryBonusAvailable = isAboveTarget
      ? Number(period?.temporary_bonus_available ?? Math.max(0, formulaTotalBonus - monthlyPayout * 3))
      : 0
    return {
      heldAmount,
      policyHoldAmount: Number(period?.policy_hold_amount ?? row.repHoldBonusTotal),
      holdsEntireProfit: period?.holds_entire_profit ?? heldAmount >= row.repPnL * 0.95 - 0.005,
      paymentReceivedTotal,
      formulaTotalBonus,
      formulaCoefficient,
      formulaMonthlyBonus,
      monthlyPayout,
      temporaryBonusOpening: Number(period?.temporary_bonus_opening ?? Math.max(0, formulaTotalBonus - monthlyPayout * 3)),
      temporaryBonusAvailable,
      monthlyAvailableAmounts: period?.monthly_available_amounts ?? [],
    }
  }

  function getHistoryMonthlyPayouts(row: HistoryFlatRow) {
    const cashView = getWalletPeriodView(row)
    const backendRows = cashView.monthlyAvailableAmounts.length === 3
      ? cashView.monthlyAvailableAmounts
      : row.repMonthlyPayouts.length === 3
        ? row.repMonthlyPayouts
        : []
    const periods = row.payoutPeriods.length === 3
      ? row.payoutPeriods
      : backendRows.map(item => item.payout_period)
    return [0, 1, 2].map(index => ({
      payout_period: backendRows[index]?.payout_period || periods[index] || '',
      amount: Number(backendRows[index]?.amount ?? cashView.monthlyPayout ?? 0),
      base_amount: Number(backendRows[index]?.base_amount ?? backendRows[index]?.amount ?? cashView.monthlyPayout ?? 0),
      released_amount: Number(backendRows[index]?.released_amount ?? 0),
    }))
  }

  function getTargetView(row: Pick<HistoryFlatRow, 'repTarget' | 'employeeSalary' | 'isTargetOverridden'>) {
    return row.isTargetOverridden ? Number(row.repTarget || 0) : Math.max(0, Number(row.employeeSalary || 0) * 2)
  }

  function renderExcelTooltip(row: HistoryFlatRow, idx: number) {
    const cashView = getWalletPeriodView(row)
    const defaultRules = [
      { min: 0, max: 2.0, rate: 0.0 },
      { min: 2.01, max: 4.0, rate: 0.20 },
      { min: 4.01, max: 6.0, rate: 0.25 },
      { min: 6.01, max: 8.0, rate: 0.30 },
      { min: 8.01, max: 999.0, rate: 0.35 }
    ];
    const rulesToUse = row.usesProgressiveBonus
      ? (row.repBonusRules && row.repBonusRules.length > 0 ? row.repBonusRules : defaultRules)
      : [{ min: 0, max: 999, rate: 0.20 }];
    const sortedRules = [...rulesToUse].sort((a, b) => a.min - b.min);
    
    // The base coefficient is the max of the first tier (where rate is usually 0)
    const baseCoef = row.usesProgressiveBonus ? sortedRules[0].max : 0;
    
    const target = getTargetView(row);
    const profitLoss = row.repPnL * 0.95;
    const pfCountBn = Math.max(0, profitLoss - target);
    const referenceLevel = pfCountBn > 0 ? getBonusReferenceLevel(row.repPnL, row.employeeSalary) : 0;
    
    // Calculate progressive breakdown dynamically
    const tiers: any[] = [];
    
    if (!row.usesProgressiveBonus) {
      tiers.push({
        name: 'Profit vượt Target',
        rate: '20%',
        amount: pfCountBn,
        bonus: pfCountBn * 0.20,
      });
    } else if (pfCountBn > 0) {
      let remaining = pfCountBn;
      let prevMax = baseCoef;
      
      for (let i = 1; i < sortedRules.length; i++) {
        const rule = sortedRules[i];
        const ruleMax = rule.max;
        const rate = rule.rate;
        const name = ruleMax >= 999.0 ? `>${prevMax}` : `${prevMax + 0.01} - ${ruleMax}`;
        
        let amount = 0;
        let bonus = 0;
        
        if (ruleMax >= 999.0) {
          if (remaining > 0) {
            amount = remaining;
            bonus = remaining * rate;
            remaining = 0;
          }
        } else {
          const tierCoefSize = ruleMax - prevMax;
          if (tierCoefSize > 0 && remaining > 0) {
            const tierProfitSize = tierCoefSize * row.employeeSalary;
            amount = Math.min(remaining, tierProfitSize);
            bonus = amount * rate;
            remaining -= amount;
          }
          prevMax = ruleMax;
        }
        
        tiers.push({
          name: name,
          rate: `${Math.round(rate * 100)}%`,
          amount: amount,
          bonus: bonus
        });
      }
    } else {
      // If no profit, just show the tiers with 0 amounts
      for (let i = 1; i < sortedRules.length; i++) {
        const rule = sortedRules[i];
        const name = rule.max >= 999.0 ? `>${sortedRules[i-1].max}` : `${sortedRules[i-1].max + 0.01} - ${rule.max}`;
        tiers.push({
          name: name,
          rate: `${Math.round(rule.rate * 100)}%`,
          amount: 0,
          bonus: 0
        });
      }
    }

    return (
      <div className={`commission-tooltip-text tooltip-excel ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ display: 'flex', gap: '16px' }}>
        {/* Left Side: Calculations */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, minWidth: '200px' }}>
          <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '2px', fontWeight: 700, letterSpacing: '0.02em' }}>
            Chi tiết hệ số thưởng ({row.salesRep})
          </strong>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', padding: '2px 0' }}>
            <span style={{ color: '#34d399', fontWeight: 600 }}>Tổng thưởng:</span>
            <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#34d399', fontSize: '11px' }}>
              {fmtNum(cashView.formulaTotalBonus)}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', padding: '8px 10px', backgroundColor: '#1e293b', borderRadius: '8px', gap: '6px', border: '1px solid #334155' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>Salary:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#93c5fd' }}>
                {fmtNum(row.employeeSalary)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>Profit/Loss gốc:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#34d399' }}>
                {fmtNum(row.repPnL)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>Profit Sale (95%):</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#6ee7b7' }}>
                {fmtNum(profitLoss)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>Target:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#fca5a5' }}>
                {fmtNum(target)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', borderTop: '1px solid #334155', paddingTop: '6px', marginTop: '2px' }}>
              <span style={{ color: '#cbd5e1', fontWeight: 600 }}>Chênh lệch:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#38bdf8' }}>
                {fmtNum(pfCountBn)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
              <span style={{ color: '#cbd5e1', fontWeight: 600 }}>Level tham chiếu:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#a78bfa' }}>
                {fmtBonusReferenceLevel(referenceLevel)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
              <span style={{ color: '#cbd5e1', fontWeight: 600 }}>Tỷ lệ thưởng hiệu dụng:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#93c5fd' }}>
                {fmtBonusCoefficient(cashView.formulaCoefficient)}
              </span>
            </div>
          </div>
        </div>

        {/* Right Side: Progressive Tier Grid */}
        <div style={{ width: '250px', flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
          {/* Header Row */}
          <div style={{ display: 'flex', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '4px', alignItems: 'center' }}>
            <div style={{ width: '45%', fontWeight: 700, color: '#94a3b8', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>THAM CHIẾU P/L CŨ</div>
            <div style={{ width: '20%', fontWeight: 700, color: '#94a3b8', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'center' }}>% RATE</div>
            <div style={{ width: '35%', fontWeight: 700, color: '#94a3b8', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'right' }}>BONUS</div>
          </div>

          {/* Rows (Dynamic Tiers) */}
          {tiers.map((tier, i) => {
            const isActive = tier.amount > 0;
            return (
              <div key={i} style={{
                display: 'flex',
                alignItems: 'center',
                padding: '4px 6px',
                margin: '1px -6px',
                borderRadius: '6px',
                fontWeight: isActive ? '700' : '400',
                backgroundColor: isActive ? '#0f766e' : 'transparent',
                boxShadow: isActive ? '0 2px 4px rgba(0,0,0,0.1)' : 'none',
                fontSize: '11px'
              }}>
                <div style={{ width: '45%', color: isActive ? '#ffffff' : '#e2e8f0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {tier.name}
                </div>
                <div style={{ width: '20%', textAlign: 'center', color: isActive ? '#ffffff' : '#e2e8f0' }}>{tier.rate}</div>
                <div style={{ width: '35%', textAlign: 'right', color: isActive ? '#34d399' : '#64748b', fontFamily: 'monospace' }}>
                  {isActive ? fmtNum(tier.bonus) : '-'}
                </div>
              </div>
            );
          })}

          {/* Row: TOTAL */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            padding: '6px 6px 4px 6px',
            margin: '4px -6px 0 -6px',
            borderTop: '1px solid #334155',
            fontWeight: '700',
            color: '#ffffff',
            fontSize: '11px'
          }}>
            <div style={{ width: '45%', color: '#ffffff' }}>
              TỔNG CÔNG THỨC CŨ
            </div>
            <div style={{ width: '20%', textAlign: 'center', color: '#6ee7b7' }}>
              {fmtBonusCoefficient(cashView.formulaCoefficient)}
            </div>
            <div style={{ width: '35%', textAlign: 'right', color: '#fca5a5', fontFamily: 'monospace', fontSize: '11px' }}>
              {cashView.formulaTotalBonus > 0 ? fmtNum(cashView.formulaTotalBonus) : '-'}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ════════════════════════════════════════════════════
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <style>{`
        .commission-tooltip-container {
          position: relative;
          display: inline-flex;
          align-items: center;
          margin-left: 5px;
          cursor: help;
          vertical-align: middle;
        }
        .commission-tooltip-icon {
          font-size: 11px;
          color: #2563eb;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          border: 1.5px solid #2563eb;
          background: #eff6ff;
          font-weight: 800;
          font-family: Roboto, "Segoe UI", Arial, sans-serif;
          line-height: 1;
        }
        .commission-tooltip-text {
          visibility: hidden;
          position: absolute;
          left: 50%;
          transform: translateX(-50%);
          background-color: #1e293b;
          color: #fff;
          text-align: left;
          padding: 10px 14px;
          border-radius: 8px;
          font-size: 11px;
          font-weight: 500;
          line-height: 1.5;
          z-index: 9999;
          box-shadow: 0 10px 15px -3px rgba(0,0,0,0.3), 0 4px 6px -4px rgba(0,0,0,0.3);
          width: 270px;
          white-space: normal;
          letter-spacing: normal;
          text-transform: none;
        }
        .commission-tooltip-text.tooltip-down {
          top: 125%;
          bottom: auto;
        }
        .commission-tooltip-text.tooltip-down::after {
          content: "";
          position: absolute;
          bottom: 100%;
          left: 50%;
          margin-left: -5px;
          border-width: 5px;
          border-style: solid;
          border-color: transparent transparent #1e293b transparent;
        }
        .commission-tooltip-text.tooltip-up {
          bottom: 125%;
          top: auto;
        }
        .commission-tooltip-text.tooltip-up::after {
          content: "";
          position: absolute;
          top: 100%;
          left: 50%;
          margin-left: -5px;
          border-width: 5px;
          border-style: solid;
          border-color: #1e293b transparent transparent transparent;
        }
        .commission-tooltip-container:hover .commission-tooltip-text {
          visibility: visible;
        }
        .commission-tooltip-container:focus-within .commission-tooltip-text {
          visibility: visible;
        }
        .commission-tooltip-container.commission-tooltip-value {
          justify-content: flex-end;
          gap: 5px;
          margin-left: 0;
        }
        .commission-tooltip-container.commission-tooltip-value .commission-tooltip-icon {
          width: 12px;
          height: 12px;
          font-size: 11px;
          flex: 0 0 auto;
        }
        .commission-tooltip-text.tooltip-align-right {
          left: auto;
          right: -4px;
          transform: none;
        }
        .commission-tooltip-text.tooltip-align-right::after {
          left: auto;
          right: 10px;
          margin-left: 0;
        }
        .commission-tooltip-matrix {
          width: 480px !important;
        }
        .commission-tooltip-text.tooltip-excel {
          background-color: #1e293b !important;
          color: #ffffff !important;
          border: 1px solid #334155 !important;
          width: max-content !important;
          min-width: 480px !important;
          max-width: 600px !important;
          padding: 12px 16px !important;
          box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.4) !important;
          border-radius: 12px !important;
        }
        .commission-tooltip-text.tooltip-excel.tooltip-down::after {
          border-color: transparent transparent #1e293b transparent !important;
        }
        .commission-tooltip-text.tooltip-excel.tooltip-up::after {
          border-color: #1e293b transparent transparent transparent !important;
        }
        .commission-upload-section { order: 10; }
        .commission-history-section { order: 20; }
        .commission-history-table th,
        .commission-history-table td {
          padding-left: 7px !important;
          padding-right: 7px !important;
          overflow-wrap: anywhere;
        }
        .commission-history-table .commission-history-period-cell {
          overflow-wrap: normal;
        }
        .commission-history-table-shell {
          width: 100%;
          max-width: 100%;
          overflow-x: auto;
          overscroll-behavior-inline: contain;
          scrollbar-gutter: stable;
          scrollbar-width: thin;
          scrollbar-color: #94a3b8 #e2e8f0;
        }
        .commission-history-table-shell::-webkit-scrollbar {
          height: 10px;
        }
        .commission-history-table-shell::-webkit-scrollbar-track {
          background: #e2e8f0;
          border-radius: 999px;
        }
        .commission-history-table-shell::-webkit-scrollbar-thumb {
          background: #94a3b8;
          border: 2px solid #e2e8f0;
          border-radius: 999px;
        }
        .commission-history-table {
          min-width: 1450px;
        }
        .commission-history-scroll-hint {
          display: none;
        }
        .commission-history-sticky-start,
        .commission-history-sticky-end {
          position: sticky;
          z-index: 6;
        }
        .commission-history-sticky-start {
          left: 0;
          box-shadow: 5px 0 10px -8px rgba(15, 23, 42, .65);
        }
        .commission-history-sticky-end {
          right: 0;
          box-shadow: -5px 0 10px -8px rgba(15, 23, 42, .65);
        }
        thead .commission-history-sticky-start,
        thead .commission-history-sticky-end {
          z-index: 8;
          background: #f1f5f9;
        }
        @media (max-width: 1539px) {
          .commission-history-scroll-hint {
            display: flex;
            align-items: center;
            gap: 6px;
            margin: 0 0 7px;
            color: #475569;
            font-size: 11px;
            font-weight: 650;
          }
        }
        .commission-funnel-section { order: 40; }
      `}</style>

      {/* ── HEADER ──────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#0f172a' }}>
            <AppIcon name="chart" size={20} /> Commission &amp; Job PnL
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>
            Import báo cáo từ Climax · Xác nhận &amp; lưu vào cơ sở dữ liệu
          </p>
        </div>
        {step !== 'idle' && (
          <button onClick={resetImport} style={{
            height: 36, padding: '0 16px', borderRadius: 10,
            border: '1.5px solid #cbd5e1', background: '#f8fafc',
            color: '#475569', fontSize: 12, fontWeight: 600, cursor: 'pointer',
          }}>
            <AppIcon name="arrow-left" size={15} /> {step === 'detail' ? 'Quay lại lịch sử' : 'Import file mới'}
          </button>
        )}
      </div>

      {/* ── MESSAGES ────────────────────────────────── */}
      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 12, padding: '12px 16px', color: '#dc2626', fontSize: 13, fontWeight: 500 }}>
          {error}
        </div>
      )}
      {successMsg && (
        <div style={{ background: '#ecfdf5', border: '1px solid #6ee7b7', borderRadius: 12, padding: '12px 16px', color: '#065f46', fontSize: 13, fontWeight: 600 }}>
          {successMsg}
        </div>
      )}

      {(step === 'idle' || step === 'done') && (
        <div id="commission-wallet-focus" className="commission-funnel-section">
          <BonusFunnelPanel
            apiBase={apiBase}
            token={token}
            focus={walletFocus}
            refreshVersion={commissionRefreshVersion}
            onDataChanged={() => refreshCommissionViews(false, false)}
            jobEditorOpen={manualJobEditorOpen}
            onJobEditorClose={() => void closeManualJobEditorAndRefresh()}
          />
        </div>
      )}

      {/* ════════════════════════════════════════════════
          STEP: IDLE — Drop zone
      ════════════════════════════════════════════════ */}
      {step === 'idle' && (
        <div className="commission-upload-section"
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: `2px dashed ${isDragging ? '#1d4ed8' : '#cbd5e1'}`,
            borderRadius: 20, padding: '44px 24px', textAlign: 'center', cursor: 'pointer',
            background: isDragging ? 'linear-gradient(135deg,#eff6ff,#dbeafe)' : 'linear-gradient(135deg,#f8fafc,#f1f5f9)',
            transition: 'all 0.2s ease',
          }}
        >
          <input ref={fileInputRef} type="file" accept=".xlsx,.xls" multiple style={{ display: 'none' }} onChange={handleInputChange} />
          {isLoading
            ? <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: '#1d4ed8', fontSize: 14, fontWeight: 600 }}><AppIcon name="refresh" size={18} className="animate-spin" /> Đang đọc file Excel...</div>
            : <>
              <AppIcon name={isDragging ? 'download' : 'upload'} size={48} style={{ margin: '0 auto 10px' }} />
              <div style={{ fontSize: 15, fontWeight: 700, color: '#1e40af', marginBottom: 6 }}>
                {isDragging ? 'Thả các file vào đây' : 'Kéo thả hoặc click để chọn nhiều file Excel'}
              </div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                Chọn tối đa 50 file <b>"Job PnL With Realize/Unrealize Detail"</b> (.xlsx/.xls) từ Climax
              </div>
            </>
          }
        </div>
      )}

      {/* ════════════════════════════════════════════════
          STEP: PREVIEW — Full 23-column table
      ════════════════════════════════════════════════ */}
      {(step === 'preview' || step === 'saving') && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

          {pendingImports.length > 1 && (
            <div style={{ border: '1px solid #bfdbfe', borderRadius: 14, padding: '12px 14px', background: '#f8fbff' }}>
              <div style={{ color: '#1e3a8a', fontSize: 12, fontWeight: 800, marginBottom: 8 }}>
                Đã chọn {pendingImports.length} file · Nhấp tên file để xem trước
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                {pendingImports.map((item, index) => (
                  <button
                    key={`${item.fileName}-${index}`}
                    type="button"
                    onClick={() => selectPendingImport(index)}
                    disabled={step === 'saving'}
                    style={{
                      height: 32, padding: '0 11px', borderRadius: 8,
                      border: index === activeImportIndex ? '1px solid #1d4ed8' : '1px solid #cbd5e1',
                      background: index === activeImportIndex ? '#dbeafe' : '#ffffff',
                      color: index === activeImportIndex ? '#1d4ed8' : '#475569',
                      fontSize: 11, fontWeight: 700, cursor: step === 'saving' ? 'not-allowed' : 'pointer',
                      maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}
                    title={item.fileName}
                  >
                    {index + 1}. {item.fileName} · {item.rows.length} JOB
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* File info banner */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            background: 'linear-gradient(135deg,#eff6ff,#dbeafe)',
            border: '1px solid #93c5fd', borderRadius: 14, padding: '14px 18px',
          }}>
            <AppIcon name="folder" size={24} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: '#1e3a8a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {fileName}
              </div>
              <div style={{ fontSize: 12, color: '#3b82f6', marginTop: 2 }}>
                {fromDate && `Từ: ${fromDate}`}{tillDate && ` → ${tillDate}`} · <b>{rows.length} jobs</b> · <b>23 cột</b>
              </div>
              {periodParseError && <div style={{ fontSize: 12, color: '#b91c1c', fontWeight: 700, marginTop: 5 }}>
                Không thể lưu: {periodParseError}
              </div>}
            </div>
            {/* KPIs inline */}
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ background: totalPnL >= 0 ? 'linear-gradient(135deg,#065f46,#059669)' : 'linear-gradient(135deg,#991b1b,#dc2626)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}>
                <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Tổng P&L</div>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{fmtNum(totalPnL)}</div>
              </div>
              <div style={{ background: 'linear-gradient(135deg,#1e3a5f,#1d4ed8)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}>
                <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Realized Rev</div>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{fmtNum(totalRevRealized)}</div>
              </div>
            </div>
            {/* Period label editable */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <label style={{ fontSize: 11, fontWeight: 700, color: '#000000', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Nhãn kỳ</label>
              <input
                value={periodLabel}
                onChange={(e) => {
                  const value = e.target.value
                  setPeriodLabel(value)
                  setPendingImports(previous => previous.map((item, index) => index === activeImportIndex ? { ...item, periodLabel: value } : item))
                }}
                style={{ height: 32, padding: '0 10px', borderRadius: 8, border: '1.5px solid #cbd5e1', fontSize: 12, fontWeight: 600, color: '#000000', background: 'white', outline: 'none', minWidth: 200 }}
              />
            </div>
          </div>

          {/* ── FULL 23-COLUMN TABLE ───────────────────── */}
          <div style={{ border: '1px solid #cbd5e1', borderRadius: 14, overflow: 'auto', maxHeight: 520 }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 12, whiteSpace: 'nowrap' }}>
              <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
                <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
                  <th style={{
                    padding: '10px 10px', textAlign: 'center',
                    fontWeight: 700, fontSize: 11, minWidth: 40,
                    borderRight: '1px solid #cbd5e1',
                    color: '#000000',
                  }}>#</th>
                  {CLIMAX_COLUMNS.map(col => (
                    <th key={col.key} style={{
                      padding: '10px 12px', textAlign: col.num ? 'right' : 'left',
                      fontWeight: 700, fontSize: 11, letterSpacing: '0.03em',
                      minWidth: col.width, borderRight: '1px solid #cbd5e1',
                      color: '#000000',
                    }}>
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, idx) => {
                  const pnl = Number(r.profitLoss)
                  return (
                    <tr key={idx} style={{ background: idx % 2 === 0 ? '#fff' : '#f8fafc', borderBottom: '1px solid #cbd5e1' }}>
                      <td style={{ padding: '7px 10px', textAlign: 'center', color: '#000000', fontSize: 11, borderRight: '1px solid #cbd5e1' }}>{idx + 1}</td>
                      {CLIMAX_COLUMNS.map(col => {
                        const v = r[col.key]
                        const isPnL = col.key === 'profitLoss'
                        return (
                          <td key={col.key} style={{
                            padding: '7px 12px',
                            textAlign: col.num ? 'right' : 'left',
                            fontFamily: col.num ? 'monospace' : 'inherit',
                            fontWeight: isPnL || col.key === 'jobNo' ? 700 : col.key === 'salesRep' ? 600 : 400,
                            color: isPnL ? (pnl >= 0 ? '#15803d' : '#b91c1c') : '#000000',
                            borderRight: '1px solid #cbd5e1',
                            maxWidth: col.width,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}>
                            {col.key === 'paymentReceived' && r.id ? (
                              <select aria-label={`Payment Received ${String(r.jobNo)}`} value={String(v || 'NO').toUpperCase() === 'YES' ? 'YES' : 'NO'} disabled={isLoading} onChange={(event) => updateJobPayment(Number(r.id), event.target.value)} style={{ border: '1px solid #cbd5e1', borderRadius: 6, padding: '3px 6px', color: String(v).toUpperCase() === 'YES' ? '#047857' : '#b45309', fontWeight: 700, background: '#fff' }}><option value="NO">NO — đang giữ</option><option value="YES">YES — mở khóa</option></select>
                            ) : col.num
                              ? fmtNum(Number(v), col.key === 'wt' || col.key === 'vol' ? 3 : 0)
                              : (v === null || v === undefined || v === '') ? '—' : String(v)
                            }
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
                {/* Totals row */}
                <tr style={{ background: '#e2e8f0', fontWeight: 800, position: 'sticky', bottom: 0, borderTop: '2px solid #cbd5e1' }}>
                  <td style={{ padding: '9px 10px', textAlign: 'center', color: '#000000', fontSize: 14, fontWeight: 900 }}>Σ</td>
                  {CLIMAX_COLUMNS.map(col => {
                    if (!col.num) return (
                      <td key={col.key} style={{ padding: '9px 12px', color: '#000000', fontSize: 12, fontWeight: 700 }}>
                        {col.key === 'jobNo' ? `${rows.length} jobs` : ''}
                      </td>
                    )
                    const total = rows.reduce((s, r) => s + Number(r[col.key] ?? 0), 0)
                    const isPnL = col.key === 'profitLoss'
                    return (
                      <td key={col.key} style={{
                        padding: '9px 12px', textAlign: 'right',
                        fontFamily: 'monospace', fontSize: 13, fontWeight: 800,
                        color: isPnL ? (total >= 0 ? '#15803d' : '#b91c1c') : '#000000',
                      }}>
                        {fmtNum(total, col.key === 'wt' || col.key === 'vol' ? 3 : 0)}
                      </td>
                    )
                  })}
                </tr>
              </tbody>
            </table>
          </div>

          {/* ── ACTION BUTTONS ────────────────────────── */}
          <div style={{
            display: 'flex', gap: 12, justifyContent: 'flex-end', alignItems: 'center',
            padding: '14px 18px', borderRadius: 14,
            background: 'linear-gradient(135deg,#f8fafc,#f1f5f9)',
            border: '1px solid #e2e8f0',
          }}>
            <button onClick={resetImport} disabled={step === 'saving'} style={{
              height: 40, padding: '0 20px', borderRadius: 10,
              border: '1.5px solid #cbd5e1', background: '#fff',
              color: '#475569', fontSize: 13, fontWeight: 600, cursor: 'pointer',
            }}><AppIcon name="close" size={15} /> Hủy bỏ</button>
            <button onClick={handleConfirmSave} disabled={step === 'saving' || !!periodParseError || !fromDate || !tillDate} style={{
              height: 40, padding: '0 28px', borderRadius: 10,
              background: step === 'saving' || periodParseError || !fromDate || !tillDate ? '#94a3b8' : 'linear-gradient(135deg,#059669,#047857)',
              border: 'none', color: '#fff', fontSize: 13, fontWeight: 700,
              cursor: step === 'saving' || periodParseError || !fromDate || !tillDate ? 'not-allowed' : 'pointer',
              boxShadow: step === 'saving' || periodParseError || !fromDate || !tillDate ? 'none' : '0 6px 20px rgba(5,150,105,0.4)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <AppIcon name={step === 'saving' ? 'refresh' : 'check'} size={16} className={step === 'saving' ? 'animate-spin' : ''} />
              {step === 'saving'
                ? `Đang lưu ${pendingImports.length > 1 ? `${pendingImports.length} file` : ''}...`
                : pendingImports.length > 1
                  ? `Xác nhận & Lưu ${pendingImports.length} file`
                  : 'Xác nhận & Lưu vào Database'}
            </button>
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════
          STEP: DETAIL — Full 23-column detail view for a specific sales rep & period
      ════════════════════════════════════════════════ */}
      <input
        ref={receivableFileInputRef}
        type="file"
        hidden
        accept=".xlsx"
        onChange={handleReceivableFiles}
      />
      {detailOpen && createPortal(
        <div
          className="ui-modal-backdrop"
          role="presentation"
          onMouseDown={closeDetailModal}
          style={{ padding: 16 }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="commission-job-detail-title"
            onMouseDown={(event) => event.stopPropagation()}
            style={{
              width: 'min(96vw, 1760px)',
              height: 'min(92vh, 920px)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              background: '#fff',
              border: '1px solid #cbd5e1',
              borderRadius: 18,
              boxShadow: '0 28px 70px rgba(15, 23, 42, 0.35)',
            }}
          >
            <div style={{
              minHeight: 58,
              padding: '10px 16px 10px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 16,
              borderBottom: '1px solid #e2e8f0',
              background: '#f8fafc',
            }}>
              <div>
                <div id="commission-job-detail-title" style={{ color: '#0f172a', fontSize: 16, fontWeight: 800 }}>
                  Chi tiết JOB của {detailSalesRep}
                </div>
                <div style={{ marginTop: 2, color: '#64748b', fontSize: 12 }}>
                  Xem ngay trên trang Commission · Nhấn Esc hoặc nút đóng để quay lại
                </div>
              </div>
              <button
                ref={detailCloseButtonRef}
                type="button"
                className="ui-button ui-button-secondary app-close-button"
                aria-label="Đóng chi tiết JOB"
                onClick={closeDetailModal}
                style={{ width: 38, minWidth: 38, height: 38, padding: 0, borderRadius: 10, fontSize: 22, lineHeight: 1 }}
              >
                <AppIcon name="close" size={17} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 18, padding: 18, overflow: 'auto', overscrollBehavior: 'contain' }}>

          {/* Banner thông tin chi tiết */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            background: 'linear-gradient(135deg,#eff6ff,#dbeafe)',
            border: '1px solid #93c5fd', borderRadius: 14, padding: '14px 18px',
          }}>
            <AppIcon name="user" size={24} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 800, fontSize: 16, color: '#1e3a8a' }}>
                Chi tiết công việc: {detailSalesRep}
              </div>
              <div style={{ fontSize: 13, color: '#3b82f6', marginTop: 4 }}>
                Kỳ commission: <b>{detailPeriodLabel}</b> {detailFileName && `· File gốc: ${detailFileName}`} · <b>{detailRows.length} jobs</b>
              </div>
            </div>
            {/* KPIs inline */}
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ background: detailTotalPnL >= 0 ? 'linear-gradient(135deg,#065f46,#059669)' : 'linear-gradient(135deg,#991b1b,#dc2626)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}>
                <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Tổng P&L</div>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{fmtNum(detailTotalPnL)}</div>
              </div>
              <div style={{ background: 'linear-gradient(135deg,#1e3a5f,#1d4ed8)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}>
                <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Realized Rev</div>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{fmtNum(detailTotalRevRealized)}</div>
              </div>
            </div>
          </div>

          <div className="app-segmented-tabs commission-tablist commission-tablist--three" role="tablist" aria-label="Lọc dữ liệu JOB chi tiết">
            <button type="button" className="app-segmented-tab" role="tab" aria-selected={detailJobTab === 'source'} onClick={() => setDetailJobTab('source')}>Data gốc <span>{rows.length}</span></button>
            <button type="button" className="app-segmented-tab" role="tab" aria-selected={detailJobTab === 'payable'} onClick={() => setDetailJobTab('payable')}>Các JOB cần chi <span>{detailPayableCount}</span></button>
            <button type="button" className="app-segmented-tab" role="tab" aria-selected={detailJobTab === 'held'} onClick={() => setDetailJobTab('held')}>Các JOB đang giữ <span>{detailHeldCount}</span></button>
          </div>

          <div style={{
            display: 'flex', alignItems: 'end', gap: 12, flexWrap: 'wrap',
            padding: '12px 14px', border: '1px solid #bae6fd', borderRadius: 12, background: '#f0f9ff',
          }}>
            <div style={{ minWidth: 190 }}>
              <div style={{ color: '#0c4a6e', fontSize: 13, fontWeight: 800 }}>
                Upload & đối chiếu công nợ
              </div>
              <div style={{ marginTop: 3, color: '#475569', fontSize: 11 }}>
                Khớp tự động theo JOB NO · bỏ qua Balance âm, Balance = 0 ghi nhận đã trả đủ · {selectedReceivableJobIds.size ? `${selectedReceivableJobIds.size} JOB đã chọn` : `toàn bộ ${rows.length} JOB của SALE`}
              </div>
            </div>
            <label style={{ flex: '1 1 360px', color: '#334155', fontSize: 11, fontWeight: 700 }}>
              Ghi chú chung
              <input
                value={receivableNote}
                onChange={event => setReceivableNote(event.target.value)}
                maxLength={2000}
                placeholder="Ví dụ: Đối chiếu công nợ tháng 08/2026..."
                style={{
                  display: 'block', width: '100%', height: 38, marginTop: 5,
                  border: '1px solid #cbd5e1', borderRadius: 9, padding: '0 11px',
                  color: '#0f172a', background: '#fff', font: 'inherit',
                }}
              />
            </label>
            <button
              type="button"
              className="ui-button ui-button-primary"
              onClick={chooseBulkReceivableFiles}
              disabled={receivableLoading || rows.length === 0}
              style={{ height: 38, padding: '0 16px' }}
            >
              <AppIcon name="upload" size={16} /> {receivableLoading ? 'Đang đối chiếu...' : 'Chọn file AGEING'}
            </button>
          </div>

          {/* Bảng 23 cột */}
          <div style={{ border: '1px solid #cbd5e1', borderRadius: 14, overflow: 'auto', minHeight: 280, flex: 1 }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 12, whiteSpace: 'nowrap' }}>
              <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
                <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
                  <th style={{ padding: '8px', textAlign: 'center', minWidth: 42, borderRight: '1px solid #cbd5e1' }}>
                    <input
                      type="checkbox"
                      aria-label="Chọn tất cả JOB đang hiển thị"
                      checked={allDetailRowsSelected}
                      onChange={toggleAllDetailReceivableJobs}
                    />
                  </th>
                  <th style={{
                    padding: '10px 10px', textAlign: 'center',
                    fontWeight: 700, fontSize: 11, minWidth: 40,
                    borderRight: '1px solid #cbd5e1',
                    color: '#000000',
                  }}>#</th>
                  <th style={{
                    padding: '10px 10px', textAlign: 'center',
                    fontWeight: 700, fontSize: 11, minWidth: 105,
                    borderRight: '1px solid #cbd5e1', color: '#000000',
                  }}>Công nợ</th>
                  {CLIMAX_COLUMNS.map(col => (
                    <th key={col.key} style={{
                      padding: '10px 12px', textAlign: col.num ? 'right' : 'left',
                      fontWeight: 700, fontSize: 11, letterSpacing: '0.03em',
                      minWidth: col.width, borderRight: '1px solid #cbd5e1',
                      color: '#000000',
                    }}>
                      {col.label}
                    </th>
                  ))}
                  <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, fontSize: 11, minWidth: 125, borderRight: '1px solid #cbd5e1', color: '#000' }}>
                    <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'flex-end', width: '100%' }}>
                      <span>Hold Bonus 30%</span>
                      <span className="commission-tooltip-container" tabIndex={0} aria-label={`Hold 30 phần trăm Profit/Loss JOB. ${HOLD_30_HELP}`}>
                        <span className="commission-tooltip-icon" aria-hidden="true">?</span>
                        <div className="commission-tooltip-text tooltip-down tooltip-align-right" style={{ width: 290, padding: '12px 14px' }}>
                          <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block', fontWeight: 700 }}>
                            Công thức tính Hold 30%
                          </strong>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 7, fontSize: 11, color: '#cbd5e1' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                              <span style={{ color: '#38bdf8', fontWeight: 700 }}>Công thức</span>
                              <span style={{ fontFamily: 'monospace', textAlign: 'right' }}>Profit/Loss dương × 30%</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, borderTop: '1px solid #334155', paddingTop: 6 }}>
                              <span style={{ color: '#34d399', fontWeight: 700 }}>Tỷ lệ cố định</span>
                              <span style={{ fontFamily: 'monospace', textAlign: 'right', fontWeight: 700 }}>30%</span>
                            </div>
                            <div style={{ color: '#94a3b8', fontSize: 11, fontStyle: 'italic' }}>* Áp dụng cho cả JOB chưa có dữ liệu công nợ; không chỉnh sửa thủ công.</div>
                          </div>
                        </div>
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {detailRows.map((r, idx) => {
                  const pnl = Number(r.profitLoss)
                  return (
                    <tr key={Number(r.id)} style={{ background: idx % 2 === 0 ? '#fff' : '#f8fafc', borderBottom: '1px solid #cbd5e1' }}>
                      <td style={{ padding: '7px 8px', textAlign: 'center', borderRight: '1px solid #cbd5e1' }}>
                        <input
                          type="checkbox"
                          aria-label={`Chọn JOB ${String(r.jobNo || '')} để upload công nợ`}
                          checked={selectedReceivableJobIds.has(Number(r.id))}
                          onChange={() => toggleReceivableJob(Number(r.id))}
                        />
                      </td>
                      <td style={{ padding: '7px 10px', textAlign: 'center', color: '#000000', fontSize: 11, borderRight: '1px solid #cbd5e1' }}>{idx + 1}</td>
                      <td style={{ padding: '6px 8px', borderRight: '1px solid #cbd5e1' }}>
                        <div style={{ display: 'flex', justifyContent: 'center', gap: 6 }}>
                          <button
                            type="button"
                            onClick={() => void openReceivableModal(r)}
                            disabled={receivableLoading}
                            title={`Xem chi tiết công nợ JOB ${String(r.jobNo || '')}`}
                            style={{
                              height: 30, padding: '0 9px', borderRadius: 7,
                              border: '1px solid #cbd5e1', background: '#fff',
                              color: '#334155', fontSize: 11, fontWeight: 700,
                              display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer',
                            }}
                          >
                            <AppIcon name="document" size={13} /> Xem ({Number(r.receivableCount || 0)})
                          </button>
                        </div>
                      </td>
                      {CLIMAX_COLUMNS.map(col => {
                        const v = r[col.key]
                        const isPnL = col.key === 'profitLoss'
                        return (
                          <td key={col.key} style={{
                            padding: '7px 12px',
                            textAlign: col.num ? 'right' : 'left',
                            fontFamily: col.num ? 'monospace' : 'inherit',
                            fontWeight: isPnL || col.key === 'jobNo' ? 700 : col.key === 'salesRep' ? 600 : 400,
                            color: isPnL ? (pnl >= 0 ? '#15803d' : '#b91c1c') : '#000000',
                            borderRight: '1px solid #cbd5e1',
                            maxWidth: col.width,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}>
                            {col.key === 'paymentReceived'
                              ? String(v || 'NO').toUpperCase() === 'YES'
                                ? <span style={{ color: '#047857', fontWeight: 800 }}>YES <small style={{ display: 'block', color: '#475569', fontWeight: 700 }}>Đã trả: {fmtNum(Number(r.paymentReceivedAmount || 0), 2)}</small></span>
                                : <span style={{ color: '#b45309', fontWeight: 800 }}>NO</span>
                              : col.num
                                ? fmtNum(Number(v), col.key === 'wt' || col.key === 'vol' ? 3 : 0)
                                : (v === null || v === undefined || v === '') ? '—' : String(v)
                            }
                          </td>
                        )
                      })}
                      <td style={{ padding: '5px 8px', textAlign: 'right', borderRight: '1px solid #cbd5e1', background: '#fffbeb' }}>
                          <span className="commission-tooltip-container commission-tooltip-value" aria-label={hold30CellHelp(r)}>
                            <span style={{ color: '#92400e', fontWeight: 800 }}>{fmtNum(Number(r.holdBonusAmount ?? Math.round(Math.max(0, Number(r.profitLoss || 0)) * 30) / 100), 2)}</span>
                            <span className="commission-tooltip-icon" tabIndex={0} aria-label={`Xem công thức Hold 30% của JOB ${String(r.jobNo || '—')}`}>?</span>
                            <div className={`commission-tooltip-text tooltip-align-right ${idx < 2 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: 300, padding: '12px 14px' }}>
                              <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block', fontWeight: 700 }}>
                                Kiểm tra Hold 30% · {String(r.jobNo || '—')}
                              </strong>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11, color: '#cbd5e1' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                                  <span style={{ color: '#94a3b8' }}>Profit/Loss dương</span>
                                  <span style={{ fontFamily: 'monospace', textAlign: 'right' }}>{fmtNum(Math.max(0, Number(r.profitLoss || 0)), 2)}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #334155', paddingTop: 6 }}>
                                  <span style={{ color: '#34d399', fontWeight: 700 }}>Số tiền giữ</span>
                                  <span style={{ color: '#34d399', fontFamily: 'monospace', fontWeight: 800 }}>{fmtNum(Number(r.holdBonusAmount ?? Math.round(Math.max(0, Number(r.profitLoss || 0)) * 30) / 100), 2)}</span>
                                </div>
                                <div style={{ color: '#94a3b8', fontSize: 11, fontStyle: 'italic' }}>* Profit/Loss × 30%; áp dụng cả khi chưa có dữ liệu công nợ.</div>
                              </div>
                            </div>
                          </span>
                      </td>
                    </tr>
                  )
                })}
                {detailRows.length === 0 && (
                  <tr><td colSpan={CLIMAX_COLUMNS.length + 4} style={{ padding: 28, textAlign: 'center', color: '#64748b' }}>Không có JOB phù hợp với tab đang chọn.</td></tr>
                )}
                {/* Totals row */}
                <tr style={{ background: '#e2e8f0', fontWeight: 800, position: 'sticky', bottom: 0, borderTop: '2px solid #cbd5e1' }}>
                  <td style={{ padding: '9px 8px', textAlign: 'center', color: '#334155', fontSize: 11 }}>{selectedReceivableJobIds.size}</td>
                  <td style={{ padding: '9px 10px', textAlign: 'center', color: '#000000', fontSize: 14, fontWeight: 900 }}>Σ</td>
                  <td style={{ padding: '9px 10px', textAlign: 'center', color: '#334155', fontSize: 11 }}>
                    {detailRows.reduce((sum, row) => sum + Number(row.receivableCount || 0), 0)} tệp
                  </td>
                  {CLIMAX_COLUMNS.map(col => {
                    if (!col.num) return (
                      <td key={col.key} style={{ padding: '9px 12px', color: '#000000', fontSize: 12, fontWeight: 700 }}>
                        {col.key === 'jobNo' ? `${detailRows.length} jobs` : ''}
                      </td>
                    )
                    const total = detailRows.reduce((s, r) => s + Number(r[col.key] ?? 0), 0)
                    const isPnL = col.key === 'profitLoss'
                    return (
                      <td key={col.key} style={{
                        padding: '9px 12px', textAlign: 'right',
                        fontFamily: 'monospace', fontSize: 13, fontWeight: 800,
                        color: isPnL ? (total >= 0 ? '#15803d' : '#b91c1c') : '#000000',
                      }}>
                        {fmtNum(total, col.key === 'wt' || col.key === 'vol' ? 3 : 0)}
                      </td>
                    )
                  })}
                  <td style={{ padding: '9px 12px', textAlign: 'right', color: '#92400e', fontSize: 12, fontWeight: 800 }}>
                    <span className="commission-tooltip-container commission-tooltip-value">
                      <span>{fmtNum(detailRows.reduce((sum, row) => sum + Number(row.holdBonusAmount ?? Math.round(Math.max(0, Number(row.profitLoss || 0)) * 30) / 100), 0), 2)}</span><span className="commission-tooltip-icon" tabIndex={0} aria-label="Giải thích tổng Hold 30 phần trăm">?</span>
                      <div className="commission-tooltip-text tooltip-up tooltip-align-right" style={{ width: 270 }}>
                        <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>Tổng tiền Hold 30%</strong>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: '#cbd5e1', fontSize: 11 }}>
                          <span>Σ {detailRows.length} JOB đang hiển thị</span>
                          <span style={{ color: '#34d399', fontFamily: 'monospace', fontWeight: 800 }}>{fmtNum(detailRows.reduce((sum, row) => sum + Number(row.holdBonusAmount ?? Math.round(Math.max(0, Number(row.profitLoss || 0)) * 30) / 100), 0), 2)}</span>
                        </div>
                      </div>
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Action button để đóng popup */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', gap: 12,
            padding: '2px 0 0',
          }}>
            <button type="button" onClick={openManualJobEditor} className="ui-button ui-button-primary" style={{ height: 40, padding: '0 20px' }}>
              <AppIcon name="edit" size={16} /> Sửa thủ công
            </button>
            <button type="button" onClick={closeDetailModal} style={{
              height: 40, padding: '0 24px', borderRadius: 10,
              border: '1.5px solid #cbd5e1', background: '#fff',
              color: '#475569', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              Đóng chi tiết
            </button>
          </div>
            </div>
          </section>
        </div>
      , document.body)}

      {receivableOpen && receivableJob && createPortal(
        <div
          className="ui-modal-backdrop"
          role="presentation"
          onMouseDown={closeReceivableModal}
          style={{ zIndex: 3600, padding: 16 }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="commission-receivable-detail-title"
            onMouseDown={event => event.stopPropagation()}
            style={{
              width: 'min(92vw, 920px)', maxHeight: 'min(88vh, 760px)',
              display: 'flex', flexDirection: 'column', overflow: 'hidden',
              background: '#fff', border: '1px solid #cbd5e1', borderRadius: 18,
              boxShadow: '0 30px 80px rgba(15,23,42,.4)',
            }}
          >
            <header style={{
              minHeight: 62, padding: '12px 16px 12px 20px', display: 'flex',
              alignItems: 'center', justifyContent: 'space-between', gap: 16,
              borderBottom: '1px solid #e2e8f0', background: '#f8fafc',
            }}>
              <div>
                <div id="commission-receivable-detail-title" style={{ color: '#0f172a', fontSize: 17, fontWeight: 800 }}>
                  Chi tiết công nợ JOB {String(receivableJob.jobNo || '')}
                </div>
                <div style={{ marginTop: 3, color: '#64748b', fontSize: 12 }}>
                  SALE: <b>{String(receivableJob.salesRep || detailSalesRep || '—')}</b> · Kỳ: <b>{detailPeriodLabel}</b>
                </div>
              </div>
              <button
                type="button"
                className="app-close-button"
                aria-label="Đóng chi tiết công nợ"
                onClick={closeReceivableModal}
                style={{ width: 38, minWidth: 38, height: 38, padding: 0, borderRadius: 10 }}
              >
                <AppIcon name="close" size={17} />
              </button>
            </header>

            <div style={{ padding: 18, overflow: 'auto', display: 'grid', gap: 16 }}>
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))',
                gap: 10, padding: 14, borderRadius: 14, border: '1px solid #bae6fd', background: '#f0f9ff',
              }}>
                {[
                  ['Customer', receivableJob.customer],
                  ['HBL/HAWB', receivableJob.hbl],
                  ['MBL', receivableJob.mbl],
                  ['Payment Received', receivableJob.paymentReceived],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <div style={{ color: '#64748b', fontSize: 11, fontWeight: 800, textTransform: 'uppercase' }}>{String(label)}</div>
                    <div style={{ marginTop: 4, color: '#0f172a', fontSize: 13, fontWeight: 700, overflowWrap: 'anywhere' }}>
                      {value === null || value === undefined || value === '' ? '—' : String(value)}
                    </div>
                  </div>
                ))}
              </div>

              <div>
                <div style={{ marginBottom: 9, color: '#0f172a', fontSize: 14, fontWeight: 800 }}>
                  Hồ sơ đã tải ({receivableAttachments.length})
                </div>
                {receivableAttachments.length === 0 ? (
                  <div style={{ padding: 28, textAlign: 'center', color: '#64748b', border: '1px solid #e2e8f0', borderRadius: 14 }}>
                    JOB này chưa có hồ sơ công nợ.
                  </div>
                ) : (
                  <div style={{ display: 'grid', gap: 8 }}>
                    {receivableAttachments.map(attachment => (
                      <div key={attachment.id} style={{
                        display: 'flex', alignItems: 'center', gap: 12, padding: '11px 12px',
                        border: '1px solid #e2e8f0', borderRadius: 12, background: '#fff',
                      }}>
                        <div style={{
                          width: 38, height: 38, borderRadius: 10, background: '#e0f2fe', color: '#0369a1',
                          display: 'grid', placeItems: 'center', flex: '0 0 auto',
                        }}><AppIcon name="document" size={19} /></div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ color: '#0f172a', fontSize: 13, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {attachment.original_filename}
                          </div>
                          <div style={{ marginTop: 3, color: '#64748b', fontSize: 11 }}>
                            {fmtFileSize(attachment.size_bytes)} · {new Date(attachment.created_at).toLocaleString('vi-VN')}
                            {attachment.uploaded_by ? ` · ${attachment.uploaded_by}` : ''}
                          </div>
                          {attachment.note && <div style={{ marginTop: 4, color: '#475569', fontSize: 12 }}>{attachment.note}</div>}
                        </div>
                        <button
                          type="button"
                          onClick={() => void downloadReceivable(attachment)}
                          disabled={receivableLoading}
                          title="Tải tệp công nợ"
                          style={{ height: 34, padding: '0 10px', border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', color: '#334155', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 700 }}
                        ><AppIcon name="download" size={14} /> Tải</button>
                        <button
                          type="button"
                          onClick={() => void deleteReceivable(attachment)}
                          disabled={receivableLoading}
                          title="Xóa tệp công nợ"
                          style={{ width: 34, height: 34, padding: 0, border: '1px solid #fecaca', borderRadius: 8, background: '#fff1f2', color: '#be123c', display: 'grid', placeItems: 'center' }}
                        ><AppIcon name="trash" size={14} /></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <footer style={{ padding: '12px 18px', borderTop: '1px solid #e2e8f0', background: '#f8fafc', display: 'flex', justifyContent: 'flex-end' }}>
              <button type="button" className="ui-button ui-button-secondary" onClick={closeReceivableModal} style={{ height: 38, padding: '0 18px' }}>
                Đóng chi tiết công nợ
              </button>
            </footer>
          </section>
        </div>
      , document.body)}

      {/* ════════════════════════════════════════════════

      {/* ════════════════════════════════════════════════
          STEP: DONE
      ════════════════════════════════════════════════ */}
      {step === 'done' && (
        <div style={{ textAlign: 'center', padding: '32px 20px', background: 'linear-gradient(135deg,#ecfdf5,#d1fae5)', borderRadius: 20, border: '1px solid #6ee7b7' }}>
          <AppIcon name="check" size={48} style={{ margin: '0 auto 10px' }} />
          <div style={{ fontSize: 16, fontWeight: 800, color: '#065f46', marginBottom: 14 }}>{successMsg}</div>
          <button onClick={resetImport} style={{
            height: 38, padding: '0 20px', borderRadius: 10,
            background: 'linear-gradient(135deg,#163b66,#1d4ed8)',
            border: 'none', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer',
          }}><AppIcon name="folder" size={16} /> Import file mới</button>
        </div>
      )}

      {(step === 'idle' || step === 'done') && (
      <div className="commission-history-section">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#1e293b' }}>
            <AppIcon name="history" size={17} /> Lịch sử Import đã lưu
          </h3>
          <button
            type="button"
            className="commission-icon-action commission-history-refresh"
            aria-label="Làm mới lịch sử Import"
            data-tooltip="Làm mới"
            title="Làm mới lịch sử Import"
            onClick={() => void loadHistory()}
            style={{
            height: 32, padding: '0 14px', borderRadius: 8,
            border: '1.5px solid #e2e8f0', background: '#fff',
            color: '#64748b', fontSize: 11, fontWeight: 600, cursor: 'pointer',
          }}><AppIcon name="refresh" size={16} /></button>
        </div>

        {loadingHistory && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: '#526979', fontSize: 13, padding: '12px 0' }}><AppIcon name="refresh" size={15} className="animate-spin" /> Đang tải...</div>
        )}

        {!loadingHistory && savedPeriods.length === 0 && (
          <div style={{ textAlign: 'center', padding: '28px 20px', background: '#f8fafc', borderRadius: 14, border: '1px dashed #cbd5e1', color: '#526979', fontSize: 13 }}>
            Chưa có dữ liệu commission nào được lưu.
          </div>
        )}

        {historyRows.length > 0 && (
          <>
          <div className="commission-history-scroll-hint" aria-hidden="true"><span>↔</span> Cuộn ngang để xem đủ ba tháng thưởng; cột Kỳ và Tác vụ luôn được giữ cố định.</div>
          <div className="commission-history-table-shell" role="region" aria-label="Bảng lịch sử Import — có thể cuộn ngang trên màn hình nhỏ" tabIndex={0} style={{ border: '1px solid #cbd5e1', borderRadius: 14 }}>
            <table className="commission-history-table" style={{ width: '100%', tableLayout: 'fixed', borderCollapse: 'collapse', fontSize: 13 }}>
              <colgroup>
                {[126, 126, 52, 116, 96, 62, 108, 100, 100, 108, 108, 108, 82, 158].map((width, index) => <col key={index} style={{ width }} />)}
              </colgroup>
              <thead>
                <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
                  {['KỲ', 'SALE REP', 'JOBS', 'TỔNG PROFIT / LOSS', 'TARGET', 'HỆ SỐ', 'TỔNG THƯỞNG', 'ĐANG GIỮ', 'KHẢ DỤNG', 'THÁNG ĐẦU TIÊN', 'THÁNG THỨ HAI', 'THÁNG THỨ BA', 'NGÀY LƯU', 'TÁC VỤ'].map(h => {
                    const isPayoutMonthHeader = h.startsWith('THÁNG ')
                    let tooltipContent: React.ReactNode = null
                    if (h === 'TARGET') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '250px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>Công thức Target</strong>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: '#cbd5e1', fontSize: 11 }}>
                            <span style={{ color: '#93c5fd', fontWeight: 700 }}>Target</span>
                            <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>Lương HĐLĐ × 2</span>
                          </div>
                          <div style={{ color: '#94a3b8', fontSize: 11, borderTop: '1px solid #334155', paddingTop: 6, marginTop: 7 }}>* Giá trị sửa thủ công, nếu có, sẽ được ưu tiên.</div>
                        </div>
                      )
                    } else if (h === 'ĐANG GIỮ') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '280px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>Công thức Đang giữ</strong>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: '#cbd5e1', fontSize: 11 }}>
                            <span style={{ color: '#fbbf24', fontWeight: 700 }}>Điều kiện</span>
                            <span style={{ textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>Hold 30% ≥ Tổng thưởng / 3</span>
                          </div>
                          <div style={{ color: '#94a3b8', fontSize: 11, borderTop: '1px solid #334155', paddingTop: 6, marginTop: 7 }}>* Đúng điều kiện: giữ toàn bộ Profit Sale = Profit/Loss × 95%.</div>
                        </div>
                      )
                    } else if (h === 'KHẢ DỤNG') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: 290, padding: '12px 14px' }}>
                          <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>Ví bonus tạm giữ</strong>
                          <div style={{ color: '#cbd5e1', fontSize: 11, lineHeight: 1.5 }}>Chứa toàn bộ tiền thưởng đang tạm giữ. Số này có thể chuyển sang kỳ khác hoặc lên lịch trả vào tháng khác.</div>
                        </div>
                      )
                    } else if (h === 'HỆ SỐ') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '220px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                            Mốc Level &amp; % Bonus
                          </strong>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '7px 16px', fontSize: 11, color: '#cbd5e1' }}>
                            <span style={{ color: '#94a3b8', fontWeight: 700 }}>HỆ SỐ (COEF)</span>
                            <span style={{ color: '#94a3b8', fontWeight: 700, textAlign: 'right' }}>% RATE</span>
                            {[
                              ['≤ 2', '0%'],
                              ['2.01 - 4', '20%'],
                              ['4.01 - 6', '25%'],
                              ['6.01 - 8', '30%'],
                              ['> 8', '35%'],
                            ].map(([level, rate]) => (
                              <div key={level} style={{ display: 'contents' }}>
                                <span style={{ fontWeight: 700, color: '#e2e8f0' }}>{level}</span>
                                <span style={{ fontWeight: 800, color: rate === '0%' ? '#94a3b8' : '#34d399', textAlign: 'right' }}>{rate}</span>
                              </div>
                            ))}
                          </div>
                          <div style={{ color: '#94a3b8', fontSize: 11, borderTop: '1px solid #334155', paddingTop: 6, marginTop: 8, fontStyle: 'italic' }}>
                            * Level = Profit Sale (95% Profit/Loss) ÷ Lương HĐLĐ. Level vượt ngưỡng cao nhất được hiển thị “&gt; 8”.
                          </div>
                        </div>
                      )
                    } else if (h === 'TỔNG PROFIT / LOSS') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '280px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                            Thông tin cột Tổng Profit / Loss
                          </strong>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '11px', color: '#cbd5e1', lineHeight: '1.4' }}>
                            <div>
                              • <b>Mỗi dòng:</b> Hiển thị Profit Sale = 95% Profit/Loss gốc hoặc giá trị điều chỉnh thủ công.
                            </div>
                            <div style={{ borderTop: '1px solid #334155', paddingTop: '6px', marginTop: '2px' }}>
                              • <b>Số tổng cộng (dòng cuối):</b> Tổng Profit Sale của tất cả Sales Rep.
                            </div>
                            <div style={{ color: '#34d399', fontWeight: 700, fontSize: '11px', marginTop: '2px' }}>
                              Công thức: Tổng cộng = &sum;(Profit/Loss × 95%)
                            </div>
                          </div>
                        </div>
                      )
                    } else if (h === 'TỔNG THƯỞNG') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '280px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                            Công thức tính Tổng Thưởng
                          </strong>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '11px', color: '#cbd5e1' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                              <span style={{ color: '#38bdf8', fontWeight: 600 }}>1. Chênh lệch</span>
                              <span style={{ textAlign: 'right', fontWeight: 500 }}>max(0, Profit/Loss × 95% − Target)</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                              <span style={{ color: '#fca5a5', fontWeight: 600 }}>2. Hệ số</span>
                              <span style={{ textAlign: 'right', fontWeight: 500 }}>0 nếu chưa vượt Target; ngược lại theo bậc thưởng</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                              <span style={{ color: '#c084fc', fontWeight: 600 }}>3. Tổng thưởng</span>
                              <span style={{ textAlign: 'right', fontWeight: 500 }}>Chênh lệch × Hệ số</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', color: '#34d399' }}>
                              <span style={{ fontWeight: 700 }}>4. Điều kiện</span>
                              <span style={{ textAlign: 'right', fontWeight: 700 }}>Profit Sale ≤ Target ⇒ thưởng = 0</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderTop: '1px solid #334155', paddingTop: '4px', color: '#fbbf24' }}>
                              <span style={{ fontWeight: 700 }}>5. Thưởng / tháng</span>
                              <span style={{ textAlign: 'right', fontWeight: 700 }}>Tổng thưởng / 3</span>
                            </div>
                            <div style={{ fontSize: '11px', color: '#94a3b8', fontStyle: 'italic', marginTop: '2px' }}>
                              * Payment Received và Hold Bonus chỉ dùng đối soát/chi trả, không cộng vào Tổng thưởng.
                            </div>
                          </div>
                        </div>
                      )
                    } else if (isPayoutMonthHeader) {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '240px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                            Ba tháng chi trả của kỳ Commission
                          </strong>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '11px', color: '#cbd5e1' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#38bdf8' }}>
                              <span style={{ fontWeight: 700 }}>Mỗi cột tháng</span>
                              <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>max(0, Tổng thưởng / 3 − Đang giữ)</span>
                            </div>
                            <div style={{ fontSize: '11px', color: '#94a3b8', borderTop: '1px solid #334155', paddingTop: '6px', marginTop: '2px', lineHeight: '1.4' }}>
                              * Tháng/năm được xác định từ ngày kết thúc kỳ nguồn; ba tháng chi trả là ba tháng kế tiếp.
                            </div>
                          </div>
                        </div>
                      )
                    }

                    return (
                      <th key={h} className={h === 'KỲ' ? 'commission-history-sticky-start' : h === 'TÁC VỤ' ? 'commission-history-sticky-end' : undefined} style={{
                        padding: '12px 16px',
                        textAlign: h === 'JOBS' || h === 'TÁC VỤ' || h === 'HỆ SỐ' ? 'center' : h === 'TỔNG PROFIT / LOSS' || h === 'TARGET' || h === 'TỔNG THƯỞNG' || h === 'ĐANG GIỮ' || h === 'KHẢ DỤNG' || isPayoutMonthHeader ? 'right' : 'left',
                        fontWeight: 700, fontSize: 12, letterSpacing: '0.04em',
                        color: '#000000',
                      }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: h === 'JOBS' || h === 'TÁC VỤ' || h === 'HỆ SỐ' ? 'center' : h === 'TỔNG PROFIT / LOSS' || h === 'TARGET' || h === 'TỔNG THƯỞNG' || h === 'ĐANG GIỮ' || h === 'KHẢ DỤNG' || isPayoutMonthHeader ? 'flex-end' : 'flex-start', width: '100%', gap: 4 }}>
                          <span>{h}</span>
                          {tooltipContent && (
                            <span className="commission-tooltip-container">
                              <span className="commission-tooltip-icon">?</span>
                              {tooltipContent}
                            </span>
                          )}
                        </div>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {historyRows.map((row, idx) => (
                  <tr key={`${row.periodId}-${row.salesRep}`} style={{
                    background: idx % 2 === 0 ? '#fff' : '#f8fafc',
                    borderTop: row.isFirstRep && idx > 0 ? '2px solid #cbd5e1' : '1px solid #cbd5e1',
                  }}>
                    {/* KỲ */}
                    <td className="commission-history-period-cell commission-history-sticky-start" style={{
                      padding: '12px 16px',
                      borderRight: '1px solid #cbd5e1',
                      background: idx % 2 === 0 ? '#fff' : '#f8fafc',
                    }}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 5 }}>
                        <span style={{ alignSelf: 'center', padding: '3px 7px', borderRadius: 999, background: '#e0f2fe', color: '#075985', fontSize: 11, lineHeight: 1, fontWeight: 800, whiteSpace: 'nowrap' }}>
                          {commissionQuarterLabel(row.fromDate, row.tillDate)}
                        </span>
                        <button
                          onClick={() => viewPeriodJobs(row.periodId, row.periodLabel, row.salesRep, row.sourceFilename || null)}
                          title={`Mở chi tiết ${row.periodLabel}`}
                          style={{ width: '100%', minHeight: 42, border: '1px solid #0369a1', borderRadius: 9, padding: '5px 7px', background: 'linear-gradient(135deg,#0ea5e9,#0369a1)', color: '#fff', fontWeight: 800, fontSize: 11, lineHeight: 1.25, cursor: 'pointer', textAlign: 'center', whiteSpace: 'normal', overflowWrap: 'normal', wordBreak: 'normal' }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}><AppIcon name="calendar" size={13} /> {row.periodLabel}</span>
                        </button>
                      </div>
                    </td>

                    {/* SALES REP */}
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: '#000000', fontSize: 14, borderRight: '1px solid #cbd5e1' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}><AppIcon name="user" size={14} /> {row.salesRep}</div>
                      {row.remark ? (
                        <div style={{ fontSize: 11, fontWeight: 400, color: '#475569', fontStyle: 'italic', marginTop: 4, whiteSpace: 'pre-wrap', maxWidth: 180, textAlign: 'left' }}>
                          <AppIcon name="message" size={13} /> {row.remark}
                        </div>
                      ) : null}
                    </td>

                    {/* JOBS */}
                    <td style={{ padding: '8px 10px', textAlign: 'center', fontWeight: 700, color: '#000000', borderRight: '1px solid #cbd5e1' }}>
                      {editingRowKey === `${row.periodId}-${row.salesRep}` && editDraft ? (
                        <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                          <input
                            type="number"
                            value={editDraft.repJobCount}
                            onChange={(e) => setEditDraft({ ...editDraft, repJobCount: e.target.value })}
                            style={{
                              width: 70,
                              textAlign: 'center',
                              height: 28,
                              borderRadius: 5,
                              border: '1px solid #cbd5e1',
                              borderColor: '#3b82f6',
                              background: '#fff',
                              color: '#000',
                              fontSize: 13,
                              outline: 'none',
                            }}
                          />
                        </div>
                      ) : (
                        row.repJobCount
                      )}
                    </td>

                    {/* TỔNG PROFIT / LOSS */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'right',
                      fontWeight: 800, fontFamily: 'monospace', fontSize: 15,
                      color: row.repPnL * 0.95 >= 0 ? '#15803d' : '#b91c1c',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {editingRowKey === `${row.periodId}-${row.salesRep}` && editDraft ? (
                        <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                          <input
                            type="checkbox"
                            checked={manualChecked.repPnL}
                            onChange={(e) => handleCheckboxChange('repPnL', e.target.checked, row)}
                            title="Sửa thủ công"
                            style={{ cursor: 'pointer', width: '14px', height: '14px', minWidth: '14px', minHeight: '14px', flexShrink: 0, margin: 0, padding: 0 }}
                          />
                          <VndInput
                            value={editDraft.repPnL}
                            disabled={!manualChecked.repPnL}
                            onValueChange={(value) => {
                              if (editDraft) {
                                const nextDraft = { ...editDraft, repPnL: String(value) };
                                setEditDraft(recalculateDraft(nextDraft, manualChecked, row));
                              }
                            }}
                            style={{
                              width: 130,
                              textAlign: 'right',
                              height: 28,
                              borderRadius: 5,
                              border: '1px solid #cbd5e1',
                              borderColor: manualChecked.repPnL ? '#3b82f6' : '#cbd5e1',
                              background: manualChecked.repPnL ? '#fff' : '#f1f5f9',
                              color: manualChecked.repPnL ? '#000' : '#64748b',
                              fontSize: 13,
                              outline: 'none',
                              fontFamily: 'monospace',
                              fontWeight: 700,
                            }}
                          />
                        </div>
                      ) : (
                        <span>
                          {fmtNum(row.repPnL * 0.95)}
                          {row.isPnLOverridden && (
                            <span style={{ display: 'inline-flex', color: '#b96a06', marginLeft: 4, cursor: 'help' }} title="Đã sửa thủ công"><AppIcon name="edit" size={12} /></span>
                          )}
                          <span className="commission-tooltip-container" style={{ marginLeft: 4 }}>
                            <span className="commission-tooltip-icon">?</span>
                            <div className={`commission-tooltip-text ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: '220px', padding: '12px 14px' }}>
                              <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                                Công thức Profit Sale dùng tính thưởng
                              </strong>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: '#cbd5e1' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                  <span>Profit/Loss gốc:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>{fmtNum(row.repPnL)}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                  <span>Tỷ lệ Profit Sale:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>95%</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #334155', paddingTop: '4px', marginTop: '2px', color: '#34d399' }}>
                                  <span style={{ fontWeight: 600 }}>Profit Sale:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>{fmtNum(row.repPnL * 0.95)}</span>
                                </div>
                              </div>
                            </div>
                          </span>
                        </span>
                      )}
                    </td>

                    {/* TARGET */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'right',
                      fontWeight: 800, fontFamily: 'monospace', fontSize: 15,
                      color: '#475569',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {editingRowKey === `${row.periodId}-${row.salesRep}` && editDraft ? (
                        <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                          <input
                            type="checkbox"
                            checked={manualChecked.repTarget}
                            onChange={(e) => handleCheckboxChange('repTarget', e.target.checked, row)}
                            title="Sửa thủ công"
                            style={{ cursor: 'pointer', width: '14px', height: '14px', minWidth: '14px', minHeight: '14px', flexShrink: 0, margin: 0, padding: 0 }}
                          />
                          <VndInput
                            value={editDraft.repTarget}
                            disabled={!manualChecked.repTarget}
                            onValueChange={(value) => {
                              if (editDraft) {
                                const nextDraft = { ...editDraft, repTarget: String(value) };
                                setEditDraft(recalculateDraft(nextDraft, manualChecked, row));
                              }
                            }}
                            style={{
                              width: 120,
                              textAlign: 'right',
                              height: 28,
                              borderRadius: 5,
                              border: '1px solid #cbd5e1',
                              borderColor: manualChecked.repTarget ? '#3b82f6' : '#cbd5e1',
                              background: manualChecked.repTarget ? '#fff' : '#f1f5f9',
                              color: manualChecked.repTarget ? '#000' : '#64748b',
                              fontSize: 13,
                              outline: 'none',
                              fontFamily: 'monospace',
                              fontWeight: 700,
                            }}
                          />
                        </div>
                      ) : (
                        <span>
                          {getTargetView(row) > 0 ? fmtNum(getTargetView(row)) : '—'}
                          {row.isTargetOverridden && (
                            <span style={{ display: 'inline-flex', color: '#b96a06', marginLeft: 4, cursor: 'help' }} title="Đã sửa thủ công"><AppIcon name="edit" size={12} /></span>
                          )}
                          <span className="commission-tooltip-container">
                            <span className="commission-tooltip-icon" tabIndex={0} aria-label={`Xem công thức Target của ${row.salesRep}`}>?</span>
                            <div className={`commission-tooltip-text ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: 280, padding: '12px 14px' }}>
                              <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>Target · {row.salesRep}</strong>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, color: '#cbd5e1', fontSize: 11 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Lương HĐLĐ</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(row.employeeSalary)} VND</b></div>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Hệ số Target</span><b>× 2</b></div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #334155', paddingTop: 6, color: '#34d399' }}><span style={{ fontWeight: 700 }}>Target</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(getTargetView(row))} VND</b></div>
                              </div>
                            </div>
                          </span>
                        </span>
                      )}
                    </td>

                    {/* HỆ SỐ */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'center',
                      fontWeight: 700, fontSize: 13,
                      color: getWalletPeriodView(row).formulaCoefficient > 0 ? '#b45309' : '#64748b',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      <span>
                        {(() => {
                          const referenceLevel = row.repPnL * 0.95 > getTargetView(row)
                            ? getBonusReferenceLevel(row.repPnL, row.employeeSalary)
                            : 0;
                          return fmtBonusReferenceLevel(referenceLevel);
                        })()}
                        {row.isRateOverridden && (
                          <span style={{ display: 'inline-flex', color: '#b96a06', marginLeft: 4, cursor: 'help' }} title="Đã sửa thủ công"><AppIcon name="edit" size={12} /></span>
                        )}
                        <span className="commission-tooltip-container">
                          <span className="commission-tooltip-icon">?</span>
                          {renderExcelTooltip(row, idx)}
                        </span>
                      </span>
                    </td>

                    {/* TỔNG THƯỞNG */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'right',
                      fontWeight: 800, fontFamily: 'monospace', fontSize: 15,
                      color: getWalletPeriodView(row).formulaTotalBonus > 0 ? '#0d9488' : '#64748b',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {editingRowKey === `${row.periodId}-${row.salesRep}` && editDraft ? (
                        <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                          <input
                            type="checkbox"
                            checked={manualChecked.repTotalBonus}
                            onChange={(e) => handleCheckboxChange('repTotalBonus', e.target.checked, row)}
                            title="Sửa thủ công"
                            style={{ cursor: 'pointer', width: '14px', height: '14px', minWidth: '14px', minHeight: '14px', flexShrink: 0, margin: 0, padding: 0 }}
                          />
                          <VndInput
                            value={editDraft.repTotalBonus}
                            disabled={!manualChecked.repTotalBonus}
                            onValueChange={(value) => {
                              if (editDraft) {
                                const nextDraft = { ...editDraft, repTotalBonus: String(value) };
                                setEditDraft(recalculateDraft(nextDraft, manualChecked, row));
                              }
                            }}
                            style={{
                              width: 120,
                              textAlign: 'right',
                              height: 28,
                              borderRadius: 5,
                              border: '1px solid #cbd5e1',
                              borderColor: manualChecked.repTotalBonus ? '#3b82f6' : '#cbd5e1',
                              background: manualChecked.repTotalBonus ? '#fff' : '#f1f5f9',
                              color: manualChecked.repTotalBonus ? '#000' : '#64748b',
                              fontSize: 13,
                              outline: 'none',
                              fontFamily: 'monospace',
                              fontWeight: 700,
                            }}
                          />
                        </div>
                      ) : (
                        <span>
                          {getWalletPeriodView(row).formulaTotalBonus > 0 ? fmtNum(getWalletPeriodView(row).formulaTotalBonus) : '—'}
                          {row.isTotalBonusOverridden && (
                            <span style={{ display: 'inline-flex', color: '#b96a06', marginLeft: 4, cursor: 'help' }} title="Đã sửa thủ công"><AppIcon name="edit" size={12} /></span>
                          )}
                           <span className="commission-tooltip-container">
                            <span className="commission-tooltip-icon">?</span>
                            <div className={`commission-tooltip-text ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: '280px', padding: '12px 14px' }}>
                              <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                                Cách tính Tổng Thưởng ({row.salesRep})
                              </strong>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '11px', color: '#cbd5e1' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Chênh lệch (Profit Sale − Target):</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#fca5a5' }}>
                                    {fmtNum(Math.max(0, row.repPnL * 0.95 - getTargetView(row)))} VND
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Tỷ lệ thưởng hiệu dụng sau lũy tiến:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#93c5fd' }}>
                                    {fmtBonusCoefficient(getWalletPeriodView(row).formulaCoefficient)}
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Tỷ lệ công thức đang lưu:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#a78bfa' }}>
                                    {fmtBonusCoefficient(row.repRate)}
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#38bdf8' }}>
                                  <span style={{ fontWeight: 700 }}>Tổng theo công thức P/L (tham chiếu):</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 800 }}>
                                    {fmtNum(getWalletPeriodView(row).formulaTotalBonus)} VND
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #334155', paddingTop: 5, color: '#34d399' }}>
                                  <span style={{ fontWeight: 700 }}>Tổng thưởng:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 800 }}>{fmtNum(getWalletPeriodView(row).formulaTotalBonus)} VND</span>
                                </div>
                                <div style={{ fontSize: 11, color: '#94a3b8', fontStyle: 'italic' }}>Payment Received không tham gia phép tính này.</div>
                              </div>
                            </div>
                          </span>
                        </span>
                      )}
                    </td>

                    {/* ĐANG GIỮ — giữ toàn bộ Profit Sale khi Hold 30% ăn hết thưởng tháng */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'right',
                      fontWeight: 800, fontFamily: 'monospace', fontSize: 15,
                      color: getWalletPeriodView(row).heldAmount > 0 ? '#b45309' : '#64748b',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      <span>
                        {getWalletPeriodView(row).heldAmount > 0 ? fmtNum(getWalletPeriodView(row).heldAmount) : '0'}
                        <span className="commission-tooltip-container">
                          <span className="commission-tooltip-icon" tabIndex={0} aria-label={`Xem chi tiết Đang giữ của ${row.salesRep}`}>?</span>
                          <div className={`commission-tooltip-text ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: 300, padding: '12px 14px' }}>
                            <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>Đang giữ · {row.salesRep}</strong>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, color: '#cbd5e1', fontSize: 11 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Hold 30% JOB</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(getWalletPeriodView(row).policyHoldAmount)} VND</b></div>
                              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Thưởng cơ sở / tháng</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(getWalletPeriodView(row).formulaMonthlyBonus)} VND</b></div>
                              <div style={{ color: '#94a3b8', fontSize: 11 }}>{getWalletPeriodView(row).holdsEntireProfit ? 'Hold 30% ≥ thưởng tháng nên giữ toàn bộ Profit Sale.' : 'Hold 30% chưa vượt thưởng tháng nên chỉ giữ theo mức Hold.'}</div>
                              <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #334155', paddingTop: 6, color: '#fbbf24' }}><span style={{ fontWeight: 700 }}>Tổng đang giữ</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(getWalletPeriodView(row).heldAmount)} VND</b></div>
                            </div>
                          </div>
                        </span>
                      </span>
                    </td>

                    {/* KHẢ DỤNG — ví bonus tạm giữ có thể điều chuyển/lên lịch */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'right',
                      fontWeight: 800, fontFamily: 'monospace', fontSize: 15,
                      color: getWalletPeriodView(row).temporaryBonusAvailable > 0 ? '#047857' : '#64748b',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      <span>
                        {fmtNum(getWalletPeriodView(row).temporaryBonusAvailable)}
                        <span className="commission-tooltip-container">
                          <span className="commission-tooltip-icon" tabIndex={0} aria-label={`Xem ví bonus tạm giữ của ${row.salesRep}`}>?</span>
                          <div className={`commission-tooltip-text ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: 320, padding: '12px 14px' }}>
                            <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 7, display: 'block' }}>Khả dụng · {row.salesRep}</strong>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, color: '#cbd5e1', fontSize: 11 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Tổng thưởng quý</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(getWalletPeriodView(row).formulaTotalBonus)} VND</b></div>
                              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Thưởng trả mỗi tháng</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(getWalletPeriodView(row).monthlyPayout)} VND</b></div>
                              <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Ví tạm giữ ban đầu</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(getWalletPeriodView(row).temporaryBonusOpening)} VND</b></div>
                              <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #334155', paddingTop: 6, color: '#34d399' }}><span style={{ fontWeight: 700 }}>Bonus đang tạm giữ</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(getWalletPeriodView(row).temporaryBonusAvailable)} VND</b></div>
                              <div style={{ color: '#94a3b8', fontSize: 11, lineHeight: 1.45 }}>Có thể chuyển sang kỳ khác hoặc lên lịch trả vào tháng khác.</div>
                            </div>
                          </div>
                        </span>
                      </span>
                    </td>

                    {/* BA THÁNG CHI TRẢ — xác định từ kỳ nguồn */}
                    {getHistoryMonthlyPayouts(row).map((payout, monthIndex) => (
                      <td key={`${row.periodId}-${row.salesRep}-${payout.payout_period || monthIndex}`} style={{ padding: '8px 7px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace', fontSize: 13, color: payout.amount > 0 ? '#1d4ed8' : '#64748b', borderRight: '1px solid #cbd5e1' }}>
                        {monthIndex === 0 && editingRowKey === `${row.periodId}-${row.salesRep}` && editDraft ? (
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                            <input type="checkbox" checked={manualChecked.repBonus} onChange={(e) => handleCheckboxChange('repBonus', e.target.checked, row)} title="Sửa mức thưởng cơ sở áp dụng cho cả 3 tháng" style={{ cursor: 'pointer', width: 14, height: 14, flexShrink: 0, margin: 0 }} />
                            <VndInput value={editDraft.repBonus} disabled={!manualChecked.repBonus} onValueChange={(value) => setEditDraft(recalculateDraft({ ...editDraft, repBonus: String(value) }, manualChecked, row))} style={{ width: 112, textAlign: 'right', height: 28, borderRadius: 5, border: '1px solid', borderColor: manualChecked.repBonus ? '#3b82f6' : '#cbd5e1', background: manualChecked.repBonus ? '#fff' : '#f1f5f9', color: manualChecked.repBonus ? '#000' : '#64748b', fontSize: 12, outline: 'none', fontFamily: 'monospace', fontWeight: 700 }} />
                          </div>
                        ) : (
                          <span>
                            <small style={{ display: 'block', marginBottom: 4, color: '#475569', fontFamily: 'sans-serif', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>{payoutPeriodLabel(payout.payout_period)}</small>
                            <span>{fmtNum(payout.amount)}</span>
                            {monthIndex === 0 && row.isMonthlyBonusOverridden && <span style={{ display: 'inline-flex', color: '#b96a06', marginLeft: 4, cursor: 'help' }} title="Mức thưởng tháng đã sửa thủ công"><AppIcon name="edit" size={12} /></span>}
                            <span className="commission-tooltip-container">
                              <HistoryMonthFloatingTooltip ariaLabel={`Xem thưởng ${payoutPeriodLabel(payout.payout_period)} của ${row.salesRep}`}>
                                <strong style={{ fontSize: 11, color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: 5, marginBottom: 6, display: 'block' }}>{payoutPeriodLabel(payout.payout_period)} · {commissionQuarterLabel(row.fromDate, row.tillDate)}</strong>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 7, fontSize: 11, color: '#cbd5e1' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Kỳ nguồn</span><b>{row.periodLabel}</b></div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Tổng thưởng</span><b style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{fmtNum(getWalletPeriodView(row).formulaTotalBonus)} VND</b></div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Thưởng ban đầu</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(payout.base_amount)} VND</b></div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Hold được giải phóng</span><b style={{ fontFamily: 'monospace', color: payout.released_amount > 0 ? '#a7f3d0' : '#94a3b8' }}>{fmtNum(payout.released_amount)} VND</b></div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>Đang giữ</span><b style={{ fontFamily: 'monospace', color: '#fbbf24' }}>{fmtNum(getWalletPeriodView(row).heldAmount)} VND</b></div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, borderTop: '1px solid #334155', paddingTop: 6, color: '#34d399' }}><span style={{ fontWeight: 700 }}>Thực trả tháng</span><b style={{ fontFamily: 'monospace' }}>{fmtNum(payout.amount)} VND</b></div>
                                  <div style={{ color: '#94a3b8', fontSize: 11 }}>* Thưởng ban đầu được chia đều và giữ nguyên ở cả 3 tháng. Hold được giải phóng chỉ chia đều và cộng vào các tháng đã chọn; các tháng không chọn không thay đổi.</div>
                                  <div style={{ color: '#94a3b8', fontSize: 11 }}>* Tháng chi đầu tiên chỉ được chọn khi khách thanh toán chậm nhất ngày 25; thanh toán sau ngày 25 thì phần Hold chỉ có thể phân bổ vào các tháng chi còn lại.</div>
                                </div>
                              </HistoryMonthFloatingTooltip>
                            </span>
                          </span>
                        )}
                      </td>
                    ))}

                    {/* NGÀY LƯU — only show on first rep row */}
                    <td style={{
                      padding: '12px 16px', textAlign: 'left',
                      color: '#000000', fontSize: 12,
                      opacity: row.isFirstRep ? 1 : 0,
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {row.isFirstRep ? fmtDate(row.createdAt) : ''}
                    </td>

                    {/* TÁC VỤ */}
                    <td className="commission-history-sticky-end" style={{ padding: '12px 16px', textAlign: 'center', background: idx % 2 === 0 ? '#fff' : '#f8fafc' }}>
                      {editingRowKey === `${row.periodId}-${row.salesRep}` && editDraft ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
                          <textarea
                            value={editDraft.remark}
                            onChange={(e) => setEditDraft({ ...editDraft, remark: e.target.value })}
                            placeholder="Ghi chú (remark)..."
                            style={{
                              width: '180px',
                              height: '50px',
                              fontSize: '11px',
                              borderRadius: '5px',
                              border: '1px solid #cbd5e1',
                              padding: '4px 6px',
                              outline: 'none',
                              resize: 'vertical',
                              fontFamily: 'sans-serif'
                            }}
                          />
                          <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                            <button
                              onClick={() => handleSaveOverride(row.periodId, row.salesRep)}
                              style={{
                                height: 28, padding: '0 12px', borderRadius: 7,
                                border: 'none', background: 'linear-gradient(135deg,#059669,#047857)',
                                color: '#fff', fontSize: 11, fontWeight: 700, cursor: 'pointer',
                                boxShadow: '0 2px 6px rgba(5,150,105,0.2)',
                              }}
                            >Lưu</button>
                            <button
                              onClick={() => { setEditingRowKey(null); setEditDraft(null); }}
                              style={{
                                height: 28, padding: '0 12px', borderRadius: 7,
                                border: '1.5px solid #cbd5e1', background: '#fff',
                                color: '#475569', fontSize: 11, fontWeight: 600, cursor: 'pointer',
                              }}
                            >Hủy</button>
                          </div>
                        </div>
                      ) : (
                        <div className="commission-history-actions" style={{ display: 'flex', gap: 6, justifyContent: 'center', alignItems: 'center' }}>
                          <button
                            type="button"
                            className="commission-icon-action"
                            aria-label={`Mở ví thưởng của ${row.salesRep}`}
                            data-tooltip="Mở ví thưởng"
                            onClick={() => focusWalletFromHistory(row)}
                            style={{
                              height: 28, padding: '0 12px', borderRadius: 7,
                              border: '1px solid #7c3aed', background: '#f5f3ff',
                              color: '#6d28d9', fontSize: 11, fontWeight: 700, cursor: 'pointer',
                            }}
                            title={`Mở ví thưởng của ${row.salesRep} cho kỳ ${row.periodLabel}`}
                          ><AppIcon name="wallet" size={16} /></button>
                          <button
                            type="button"
                            className="commission-icon-action"
                            aria-label={`Sửa commission của ${row.salesRep}`}
                            data-tooltip="Sửa"
                            title={`Sửa commission của ${row.salesRep}`}
                            onClick={() => {
                              console.log('DEBUG: Edit button clicked!');
                              console.log('row info:', {
                                salesRep: row.salesRep,
                                periodId: row.periodId,
                                repPnL: row.repPnL,
                                employeeSalary: row.employeeSalary,
                                repTarget: row.repTarget,
                                repRate: row.repRate,
                                repTotalBonus: row.repTotalBonus,
                                repBonus: row.repBonus
                              });
                              try {
                                const autoVals = calculateEmployeeBonusJS(
                                  row.repPnL,
                                  row.employeeSalary,
                                  row.repBonusRules,
                                  row.usesProgressiveBonus,
                                );
                                console.log('DEBUG: autoVals computed:', autoVals);
                                
                                const isTargetManual = Math.abs(row.repTarget - autoVals.target) > 0.01;
                                const isRateManual = Math.abs(row.repRate - autoVals.bonusRate) > 0.0001;
                                const isTotalBonusManual = Math.abs(row.repTotalBonus - autoVals.totalBonusQuarter) > 0.1;
                                const isBonusManual = Math.abs(row.repBonus - autoVals.bonusPerMonth) > 0.1;

                                console.log('DEBUG: manual checks:', { isTargetManual, isRateManual, isTotalBonusManual, isBonusManual });

                                setEditingRowKey(`${row.periodId}-${row.salesRep}`);
                                setManualChecked({
                                  repPnL: row.isPnLOverridden,
                                  repTarget: row.isTargetOverridden,
                                  repRate: row.isRateOverridden,
                                  repTotalBonus: row.isTotalBonusOverridden,
                                  repBonus: row.isMonthlyBonusOverridden
                                });
                                setEditDraft({
                                  repJobCount: String(row.repJobCount),
                                  repPnL: String(row.repPnL * 0.95),
                                  repTarget: String(row.repTarget),
                                  repRate: String(Math.round(row.repRate * 100)),
                                  repTotalBonus: String(row.repTotalBonus),
                                  repBonus: String(row.repBonus),
                                  remark: row.remark || '',
                                });
                                console.log('DEBUG: States set successfully!');
                              } catch (e: any) {
                                console.error('DEBUG ERROR during onClick:', e);
                              }
                            }}
                            style={{
                              height: 28, padding: '0 12px', borderRadius: 7,
                              border: '1px solid #3b82f6', background: '#eff6ff',
                              color: '#1d4ed8', fontSize: 11, fontWeight: 600, cursor: 'pointer',
                            }}
                          ><AppIcon name="edit" size={16} /></button>
                          <button
                            type="button"
                            className="commission-icon-action"
                            aria-label={`Thêm hoặc sửa ghi chú của ${row.salesRep}`}
                            data-tooltip="Ghi chú"
                            title={`Thêm hoặc sửa ghi chú của ${row.salesRep}`}
                            onClick={() => {
                              setRemarkModalData({
                                row: row,
                                remark: row.remark || '',
                              });
                            }}
                            style={{
                              height: 28, padding: '0 12px', borderRadius: 7,
                              border: '1px solid #10b981', background: '#ecfdf5',
                              color: '#047857', fontSize: 11, fontWeight: 600, cursor: 'pointer',
                              display: 'flex', alignItems: 'center', gap: 4
                            }}
                          ><AppIcon name="message" size={16} /></button>
                          <button
                              type="button"
                              aria-label={`Xóa commission của ${row.salesRep}`}
                              data-tooltip="Xóa"
                              title={`Xóa commission của ${row.salesRep}`}
                              onClick={() => deleteSalesRepCommission(row.periodId, row.periodLabel, row.salesRep)}
                              className="app-delete-button commission-icon-action"
                              style={{
                                height: 28, padding: '0 12px', borderRadius: 7,
                                border: '1px solid #fca5a5', background: '#fef2f2',
                                color: '#dc2626', fontSize: 11, fontWeight: 600, cursor: 'pointer',
                              }}
                            ><AppIcon name="trash" size={16} /></button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}

                {/* Grand total row across all periods */}
                {historyRows.length > 1 && (
                  <tr style={{ background: '#e2e8f0', fontWeight: 800, borderTop: '2px solid #cbd5e1' }}>
                    <td style={{ padding: '12px 16px', color: '#000000', fontSize: 13, fontWeight: 700, borderRight: '1px solid #cbd5e1' }}>TỔNG TẤT CẢ</td>
                    <td style={{ padding: '12px 16px', color: '#000000', fontSize: 12, fontWeight: 600, borderRight: '1px solid #cbd5e1' }}>
                      {historyRows.length} Sales Rep(s)
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center', color: '#000000', fontWeight: 800, borderRight: '1px solid #cbd5e1' }}>
                      {historyRows.reduce((s, r) => s + r.repJobCount, 0)}
                    </td>
                    <td style={{
                      padding: '12px 16px', textAlign: 'right',
                      fontFamily: 'monospace', fontSize: 16, fontWeight: 900,
                      color: historyRows.reduce((s, r) => s + r.repPnL, 0) * 0.95 >= 0 ? '#15803d' : '#b91c1c',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {fmtNum(historyRows.reduce((s, r) => s + r.repPnL, 0) * 0.95)}
                    </td>
                    
                    {/* TARGET total - showing sum or empty? Usually target sum is not meaningful, so we can just display '-' or the sum if we want */}
                    <td style={{
                      padding: '12px 16px', textAlign: 'right',
                      fontFamily: 'monospace', fontSize: 15, fontWeight: 800,
                      color: '#cbd5e1',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      —
                    </td>

                    {/* HỆ SỐ total - empty */}
                    <td style={{
                      padding: '12px 16px', textAlign: 'center',
                      fontFamily: 'monospace', fontSize: 15, fontWeight: 800,
                      color: '#cbd5e1',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      —
                    </td>

                    {/* TỔNG THƯỞNG total */}
                    <td style={{
                      padding: '12px 16px', textAlign: 'right',
                      fontFamily: 'monospace', fontSize: 16, fontWeight: 900,
                      color: '#0d9488',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {fmtNum(historyRows.reduce((sum, row) => sum + getWalletPeriodView(row).formulaTotalBonus, 0))}
                    </td>

                    {/* ĐANG GIỮ total */}
                    <td style={{
                      padding: '12px 16px', textAlign: 'right',
                      fontFamily: 'monospace', fontSize: 16, fontWeight: 900,
                      color: '#b45309',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {fmtNum(historyRows.reduce((sum, row) => sum + getWalletPeriodView(row).heldAmount, 0))}
                    </td>

                    <td style={{
                      padding: '12px 16px', textAlign: 'right',
                      fontFamily: 'monospace', fontSize: 16, fontWeight: 900,
                      color: '#047857',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {fmtNum(historyRows.reduce((sum, row) => sum + getWalletPeriodView(row).temporaryBonusAvailable, 0))}
                    </td>

                    <td style={{
                      padding: '12px 16px', textAlign: 'right',
                      fontFamily: 'monospace', fontSize: 16, fontWeight: 900,
                      color: '#1d4ed8',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {fmtNum(historyRows.reduce((sum, row) => sum + getWalletPeriodView(row).monthlyPayout, 0))}
                    </td>
                    <td colSpan={2} />
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          </>
        )}
      </div>
      )}

      {/* ── REMARK MODAL ── */}
      {remarkModalData && (
        <div className="app-modal-overlay" style={{
          position: 'fixed',
          inset: 0,
          zIndex: 99999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '16px',
        }}>
          <div style={{
            background: '#ffffff',
            borderRadius: '16px',
            padding: '24px',
            width: '100%',
            maxWidth: '480px',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#1e293b' }}>
                <AppIcon name="message" size={17} /> Thêm/Sửa Ghi chú (Remark)
              </h3>
              <button 
                onClick={() => setRemarkModalData(null)}
                className="app-close-button app-close-button--compact"
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '18px',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '4px',
                  lineHeight: 1
                }}
              >
                <AppIcon name="close" size={15} />
              </button>
            </div>
            
            <div style={{ fontSize: '13px', color: '#64748b' }}>
              Nhân viên: <strong style={{ color: '#0f172a' }}>{remarkModalData.row.salesRep}</strong><br />
              Kỳ commission: <strong style={{ color: '#0f172a' }}>{remarkModalData.row.periodLabel}</strong>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', fontWeight: 700, color: '#475569' }}>Nội dung ghi chú:</label>
              <textarea
                value={remarkModalData.remark}
                onChange={(e) => setRemarkModalData({ ...remarkModalData, remark: e.target.value })}
                placeholder="Nhập nội dung ghi chú (được ghi nhiều nội dung/multiline)..."
                style={{
                  width: '100%',
                  height: '150px',
                  borderRadius: '10px',
                  border: '1.5px solid #cbd5e1',
                  padding: '12px',
                  fontSize: '13px',
                  color: '#000',
                  background: '#fff',
                  outline: 'none',
                  resize: 'vertical',
                  fontFamily: 'sans-serif',
                  lineHeight: '1.5',
                  boxSizing: 'border-box'
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '4px' }}>
              <button
                onClick={() => setRemarkModalData(null)}
                style={{
                  height: '36px',
                  padding: '0 16px',
                  borderRadius: '8px',
                  border: '1.5px solid #cbd5e1',
                  background: '#fff',
                  color: '#475569',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Hủy bỏ
              </button>
              <button
                onClick={() => handleSaveRemark(remarkModalData.row, remarkModalData.remark)}
                style={{
                  height: '36px',
                  padding: '0 20px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'linear-gradient(135deg,#059669,#047857)',
                  color: '#fff',
                  fontSize: '13px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  boxShadow: '0 4px 12px rgba(5,150,105,0.2)',
                }}
              >
                Lưu ghi chú
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── OVERLAP WARNING MODAL ── */}
      {overlapWarningData && (
        <div className="app-modal-overlay" style={{
          position: 'fixed',
          inset: 0,
          zIndex: 99999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '16px',
        }}>
          <div style={{
            background: '#ffffff',
            borderRadius: '16px',
            padding: '24px',
            width: '100%',
            maxWidth: '720px',
            maxHeight: 'calc(100vh - 32px)',
            overflowY: 'auto',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#b91c1c', display: 'flex', alignItems: 'center', gap: 6 }}>
                <AppIcon name="warning" size={17} /> Cảnh báo trùng kỳ Commission
              </h3>
              <button 
                onClick={() => setOverlapWarningData(null)}
                className="app-close-button app-close-button--compact"
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '18px',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '4px',
                  lineHeight: 1
                }}
              >
                <AppIcon name="close" size={15} />
              </button>
            </div>
            
            <div style={{ fontSize: '14px', color: '#334155', lineHeight: '1.6' }}>
              File đang tải lên có khoảng ngày trùng với kỳ Commission đã lưu:
            </div>

            <div style={{
              maxHeight: '180px',
              overflowY: 'auto',
              border: '1px solid #fee2e2',
              borderRadius: '10px',
              backgroundColor: '#fef2f2',
              padding: '12px'
            }}>
              {overlapWarningData.conflicts.map((c, i) => (
                <div key={i} style={{ 
                  fontSize: '12.5px', 
                  color: '#991b1b', 
                  marginBottom: i < overlapWarningData.conflicts.length - 1 ? '8px' : 0,
                  paddingBottom: i < overlapWarningData.conflicts.length - 1 ? '8px' : 0,
                  borderBottom: i < overlapWarningData.conflicts.length - 1 ? '1px solid #fca5a5' : 'none'
                }}>
                  • <b>{c.label}</b> (Kỳ: {c.from} → {c.till})
                </div>
              ))}
            </div>

            {overlapWarningData.mergePreview && (
              <div style={{ display: 'grid', gap: '12px' }}>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
                  gap: '8px',
                }}>
                  {[
                    ['JOB mới sẽ thêm', overlapWarningData.mergePreview.newJobs, '#047857', '#ecfdf5'],
                    ['JOB thường cập nhật', overlapWarningData.mergePreview.automaticUpdates, '#0369a1', '#f0f9ff'],
                    ['JOB đã sửa thủ công', overlapWarningData.mergePreview.manualJobs.length, '#b45309', '#fffbeb'],
                  ].map(([label, value, color, background]) => (
                    <div key={String(label)} style={{ padding: '10px', borderRadius: '9px', background: String(background), color: String(color) }}>
                      <div style={{ fontSize: '11px', fontWeight: 700 }}>{label}</div>
                      <div style={{ marginTop: 2, fontSize: '18px', fontWeight: 800 }}>{value}</div>
                    </div>
                  ))}
                </div>

                {overlapWarningData.mergePreview.manualJobs.length > 0 ? (
                  <div style={{ border: '1px solid #fcd34d', borderRadius: '10px', overflow: 'hidden' }}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '10px 12px',
                      background: '#fffbeb',
                    }}>
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: 800, color: '#92400e' }}>JOB đã có chỉnh sửa thủ công</div>
                        <div style={{ marginTop: 2, fontSize: '11.5px', color: '#a16207' }}>
                          Chỉ JOB được chọn mới nhận dữ liệu P&amp;L từ file mới. Dữ liệu Hold Bonus, công nợ và lịch sử vẫn được bảo toàn.
                        </div>
                      </div>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap', fontSize: '12px', fontWeight: 700, color: '#92400e', cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={overlapWarningData.selectedManualJobIds.length === overlapWarningData.mergePreview.manualJobs.length}
                          onChange={event => setOverlapWarningData(previous => previous ? {
                            ...previous,
                            selectedManualJobIds: event.target.checked
                              ? previous.mergePreview?.manualJobs.map(job => job.jobId) || []
                              : [],
                          } : previous)}
                        />
                        Chọn tất cả
                      </label>
                    </div>
                    <div style={{ maxHeight: '230px', overflowY: 'auto', background: '#fff' }}>
                      {overlapWarningData.mergePreview.manualJobs.map((job, index) => {
                        const checked = overlapWarningData.selectedManualJobIds.includes(job.jobId)
                        return (
                          <label key={job.jobId} style={{
                            display: 'grid',
                            gridTemplateColumns: '20px minmax(110px, .7fr) minmax(140px, 1fr) minmax(180px, 1.4fr)',
                            gap: '10px',
                            alignItems: 'start',
                            padding: '10px 12px',
                            borderTop: index === 0 ? '1px solid #fde68a' : '1px solid #f1f5f9',
                            cursor: 'pointer',
                            background: checked ? '#fff7ed' : '#fff',
                          }}>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => setOverlapWarningData(previous => previous ? {
                                ...previous,
                                selectedManualJobIds: previous.selectedManualJobIds.includes(job.jobId)
                                  ? previous.selectedManualJobIds.filter(id => id !== job.jobId)
                                  : [...previous.selectedManualJobIds, job.jobId],
                              } : previous)}
                            />
                            <div style={{ fontSize: '12px', fontWeight: 800, color: '#0f172a' }}>
                              {job.jobNo}
                              <div style={{ marginTop: 2, fontSize: '11px', fontWeight: 500, color: '#64748b' }}>{job.salesRep || 'Chưa có Sales'}</div>
                            </div>
                            <div style={{ fontSize: '11px', color: '#475569', wordBreak: 'break-word' }}>
                              {job.sourceFilename}
                              <div style={{ marginTop: 2, color: '#64748b' }}>{job.periodLabel}</div>
                            </div>
                            <div style={{ fontSize: '11px', color: '#92400e' }}>{job.reasons.join(' · ') || 'Đã sửa thủ công'}</div>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: '10px 12px', borderRadius: '9px', background: '#ecfdf5', color: '#047857', fontSize: '12.5px', fontWeight: 650 }}>
                    Không có JOB đã sửa thủ công. JOB trùng sẽ được cập nhật và JOB mới sẽ được thêm tự động.
                  </div>
                )}
              </div>
            )}

            <div style={{ fontSize: '13.5px', color: '#475569', fontWeight: 500 }}>
              {overlapWarningData.onMerge
                ? 'Hãy kiểm tra lựa chọn rồi cập nhật vào kỳ hiện tại. JOB thủ công không chọn sẽ giữ nguyên dữ liệu cũ.'
                : 'Khoảng ngày chỉ trùng một phần nên không thể gộp theo JOB. Bạn có muốn lưu thành một kỳ riêng không?'}
            </div>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', flexWrap: 'wrap', marginTop: '4px' }}>
              <button
                onClick={() => setOverlapWarningData(null)}
                style={{
                  height: '38px',
                  padding: '0 18px',
                  borderRadius: '8px',
                  border: '1.5px solid #cbd5e1',
                  background: '#fff',
                  color: '#475569',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Hủy bỏ
              </button>
              {overlapWarningData.onMerge && overlapWarningData.conflicts.some(c => c.isExact) && (
                <button
                  onClick={() => {
                    overlapWarningData.onMerge?.(overlapWarningData.selectedManualJobIds)
                  }}
                  style={{
                    height: '38px',
                    padding: '0 20px',
                    borderRadius: '8px',
                    border: 'none',
                    background: 'linear-gradient(135deg,#0284c7,#0369a1)',
                    color: '#fff',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    boxShadow: '0 4px 12px rgba(2,132,199,0.2)',
                  }}
                >
                  Cập nhật kỳ hiện tại
                </button>
              )}
              <button
                onClick={overlapWarningData.onConfirm}
                style={{
                  height: '38px',
                  padding: '0 22px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'linear-gradient(135deg,#dc2626,#b91c1c)',
                  color: '#fff',
                  fontSize: '13px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  boxShadow: '0 4px 12px rgba(220,38,38,0.2)',
                }}
              >
                {overlapWarningData.onMerge ? 'Lưu thành kỳ riêng' : 'Tiếp tục import'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
