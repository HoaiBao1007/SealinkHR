import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import * as XLSX from 'xlsx'
import { useConfirmDialog } from '../../shared/ui/ConfirmDialog'
import { credentialedFetch } from '../../shared/api/credentialedFetch'
import { BonusFunnelPanel } from './BonusFunnelPanel'
import { VndInput } from '../../shared/ui/VndInput'
import { formatVietnameseNumber, parseVndInput } from '../../shared/utils/currency'

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

interface SalesRepSummaryIn {
  sales_rep: string
  job_count: number
  total_profit_loss: number
  sales_bonus?: number
  target?: number
  bonus_rate?: number
  total_bonus_quarter?: number
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
}

interface CommissionWalletSummary {
  sales_rep: string
  period_labels?: string[]
  period_summaries?: Array<{
    period_id: number
    period_label: string
    payout_periods?: string[]
    total_bonus_quarter: number
    monthly_bonus: number
    quarter_hold_amount?: number
    monthly_available_amounts?: Array<{ payout_period: string; amount: number }>
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
}

// ══════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════
function fmtNum(v: number, decimals = 0) {
  return formatVietnameseNumber(v, { maximumFractionDigits: decimals })
}
function fmtDate(iso: string | null) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleDateString('vi-VN') } catch { return iso }
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

function calculateDynamicSalesBonusJS(grossProfit: number, employeeSalary: number, rules: any[]) {
  const netProfit = grossProfit * 0.95;
  if (employeeSalary <= 0) {
    return {
      target: 0,
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

  const target = employeeSalary * baseCoef;
  const pfCountBn = netProfit - target;
  
  const coefficient = Math.round((netProfit / employeeSalary) * 100) / 100;
  
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
    coefficient
  };
}

function calculateEmployeeBonusJS(
  grossProfit: number,
  employeeSalary: number,
  rules: any[],
  usesProgressiveBonus: boolean,
) {
  if (usesProgressiveBonus) {
    return calculateDynamicSalesBonusJS(grossProfit, employeeSalary, rules)
  }

  const netProfit = grossProfit * 0.95
  const totalBonusQuarter = Math.max(netProfit, 0) * 0.20
  return {
    target: 0,
    bonusRate: 0.20,
    totalBonusQuarter,
    bonusPerMonth: totalBonusQuarter / 3,
    coefficient: employeeSalary > 0
      ? Math.round((netProfit / employeeSalary) * 100) / 100
      : 0,
  }
}

function getLevelName(level: number): string {
  if (level <= 2) return 'Cấp 1';
  if (level <= 4) return 'Cấp 2';
  if (level <= 6) return 'Cấp 3';
  if (level <= 8) return 'Cấp 4';
  return 'Cấp 5';
}

type HistoryFlatRow = {
  periodId: number
  periodLabel: string
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
  const netProfit = currentManualChecked.repPnL
    ? parseVndInput(currentDraft.repPnL)
    : row.repPnL * 0.95;

  const grossProfit = netProfit / 0.95;
  const defaultCalc = calculateEmployeeBonusJS(
    grossProfit,
    row.employeeSalary,
    row.repBonusRules,
    row.usesProgressiveBonus,
  );

  const target = currentManualChecked.repTarget
    ? parseVndInput(currentDraft.repTarget)
    : defaultCalc.target;

  const pfCountBn = row.usesProgressiveBonus
    ? netProfit - target
    : Math.max(netProfit, 0);

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

  return {
    ...currentDraft,
    repPnL: currentManualChecked.repPnL ? currentDraft.repPnL : String(netProfit),
    repTarget: currentManualChecked.repTarget ? currentDraft.repTarget : String(target),
    repRate: currentManualChecked.repRate ? currentDraft.repRate : String(Math.round(rate * 100)),
    repTotalBonus: currentManualChecked.repTotalBonus ? currentDraft.repTotalBonus : String(totalBonus),
    repBonus: currentManualChecked.repBonus ? currentDraft.repBonus : String(monthlyBonus),
  };
}

// ══════════════════════════════════════════════════════════
// Main Component
// ══════════════════════════════════════════════════════════
export function CommissionTab({ apiBase, token, notificationFocus }: Props) {
  const confirm = useConfirmDialog()
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  // ── Detail state ──────────────────────────────────────
  const [detailPeriodLabel, setDetailPeriodLabel] = useState('')
  const [detailPeriodId, setDetailPeriodId] = useState<number | null>(null)
  const [detailSalesRep, setDetailSalesRep] = useState('')
  const [detailFileName, setDetailFileName] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [manualJobEditorOpen, setManualJobEditorOpen] = useState(false)
  const detailCloseButtonRef = useRef<HTMLButtonElement>(null)
  const detailReturnFocusRef = useRef<HTMLElement | null>(null)

  // ── History ───────────────────────────────────────────
  const [savedPeriods, setSavedPeriods] = useState<SavedPeriod[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [wallets, setWallets] = useState<CommissionWalletSummary[]>([])
  const [, setWalletLoading] = useState(false)
  const [walletFocus, setWalletFocus] = useState<CommissionNotificationFocus | null>(null)

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
    onUpdate?: (periodId: number) => void
  } | null>(null)

  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

  async function loadHistory() {
    setLoadingHistory(true)
    try {
      const res = await credentialedFetch(`${apiBase}/api/commission/periods`, { headers: authHeader })
      if (res.ok) setSavedPeriods(await res.json())
    } catch { /* ignore */ } finally { setLoadingHistory(false) }
  }

  async function loadWallet() {
    setWalletLoading(true)
    try {
      // Lịch sử import có thể chứa nhiều nhân viên và nhiều kỳ. Luôn tải toàn bộ
      // ví để cột "Đang giữ" được ghép đúng theo từng sales + period, không lấy
      // nhầm số tổng hợp của kỳ đang được focus.
      const res = await credentialedFetch(`${apiBase}/api/commission/wallet`, { headers: authHeader })
      if (res.ok) setWallets(await res.json())
    } finally { setWalletLoading(false) }
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
      setSuccessMsg(data.message)
      await loadWallet()
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
      if (manualJobEditorOpen) setManualJobEditorOpen(false)
      else closeDetailModal()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [detailOpen, manualJobEditorOpen])

  async function deleteSalesRepCommission(id: number, label: string, salesRep: string) {
    if (!await confirm({ title: 'Xóa commission nhân viên', message: `Chỉ xóa JOB, commission và phễu thưởng của ${salesRep} trong kỳ "${label}". Các nhân viên commission khác không bị ảnh hưởng.`, confirmLabel: 'Xóa nhân viên này', tone: 'danger' })) return
    try {
      const res = await credentialedFetch(`${apiBase}/api/commission/periods/${id}/reps/${encodeURIComponent(salesRep)}`, {
        method: 'DELETE', headers: authHeader,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Không thể xóa commission của nhân viên.')
      await loadHistory()
      await loadWallet()
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
      
      setSuccessMsg(data.message || '✅ Đã lưu chỉnh sửa thành công.')
      setEditingRowKey(null)
      setEditDraft(null)
      await loadHistory()
    } catch (err: any) {
      setError(`❌ Lỗi: ${err.message}`)
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
      
      setSuccessMsg(`✅ Đã lưu ghi chú cho ${row.salesRep} thành công.`)
      setRemarkModalData(null)
      await loadHistory()
    } catch (err: any) {
      setError(`❌ Lỗi: ${err.message}`)
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
  function handleFile(file: File) {
    if (!file.name.match(/\.(xlsx|xls)$/i)) {
      setError('❌ Chỉ chấp nhận file Excel (.xlsx/.xls) từ Climax.'); return
    }
    setIsLoading(true); setError(null); setSuccessMsg(null)
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const buf = e.target?.result as ArrayBuffer
        const { rows: parsed, periodLabel: pl, fromDate: fd, tillDate: td, periodError } = parseClimaxBuffer(buf)
        if (parsed.length === 0) {
          setError('⚠️ Không tìm thấy dữ liệu. Vui lòng kiểm tra định dạng file.')
          setIsLoading(false); return
        }
        setRows(parsed); setFileName(file.name)
        setPeriodLabel(pl); setFromDate(fd); setTillDate(td); setPeriodParseError(periodError)
        if (periodError) setError(`⚠️ ${periodError}`)
        setStep('preview')
      } catch (err: any) {
        setError(`❌ Lỗi đọc file: ${err.message}`)
      } finally { setIsLoading(false) }
    }
    reader.readAsArrayBuffer(file)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setIsDragging(false)
    if (step === 'preview') return
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0])
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.[0]) handleFile(e.target.files[0])
    e.target.value = ''
  }

  function resetImport() {
    setStep('idle'); setRows([]); setFileName(null)
    setPeriodLabel(''); setFromDate(''); setTillDate('')
    setPeriodParseError(null)
    setError(null); setSuccessMsg(null)
  }

  function closeDetailModal() {
    setManualJobEditorOpen(false)
    setDetailOpen(false)
    setRows([])
    setDetailPeriodLabel('')
    setDetailPeriodId(null)
    setDetailSalesRep('')
    setDetailFileName(null)
    window.setTimeout(() => detailReturnFocusRef.current?.focus(), 0)
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
      setDetailOpen(true);
    } catch (err: any) {
      setError(`❌ Lỗi: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  }

  // ── Save to DB ─────────────────────────────────────────
  async function executeSave() {
    setStep('saving'); setError(null)
    try {
      const payload = {
        period_label: periodLabel,
        from_date: fromDate || null,
        till_date: tillDate || null,
        source_filename: fileName,
        jobs: rows.map(r => ({
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
      }
      const res = await credentialedFetch(`${apiBase}/api/commission/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi lưu.')
      setSuccessMsg(data.message || `✅ Đã lưu ${rows.length} jobs vào cơ sở dữ liệu.`)
      setStep('done')
      await loadHistory()
      await syncWallet(data.period_id)
    } catch (err: any) {
      setError(`❌ ${err.message}`); setStep('preview')
    }
  }

  async function handleConfirmSave() {
    const newStart = parseDateStringToDate(fromDate)
    const newEnd = parseDateStringToDate(tillDate)

    if (periodParseError || !newStart || !newEnd || newStart > newEnd) {
      setError(`⚠️ ${periodParseError || 'Khoảng ngày nguồn chưa hợp lệ. Hãy kiểm tra tiêu đề “Job Date From … Till …” của file trước khi lưu.'}`)
      return
    }

    if (newStart && newEnd) {
      const conflicts = savedPeriods.filter(p => {
        if (!p.from_date || !p.till_date) return false
        const savedStart = parseDateStringToDate(p.from_date)
        const savedEnd = parseDateStringToDate(p.till_date)
        if (!savedStart || !savedEnd) return false
        return doMonthsOverlap(newStart, newEnd, savedStart, savedEnd)
      }).map(p => {
        const savedStart = parseDateStringToDate(p.from_date || '')
        const savedEnd = parseDateStringToDate(p.till_date || '')
        const isExact = !!(
          savedStart && savedEnd &&
          savedStart.getFullYear() === newStart.getFullYear() &&
          savedStart.getMonth() === newStart.getMonth() &&
          savedStart.getDate() === newStart.getDate() &&
          savedEnd.getFullYear() === newEnd.getFullYear() &&
          savedEnd.getMonth() === newEnd.getMonth() &&
          savedEnd.getDate() === newEnd.getDate()
        )
        return {
          id: p.id,
          label: p.period_label,
          from: p.from_date || '',
          till: p.till_date || '',
          isExact
        }
      })

      if (conflicts.length > 0) {
        setOverlapWarningData({
          conflicts,
          onConfirm: () => {
            setOverlapWarningData(null)
            executeSave()
          },
          onUpdate: async (periodId: number) => {
            setOverlapWarningData(null)
            setStep('saving')
            setError(null)
            try {
              // Delete existing period first
              const delRes = await credentialedFetch(`${apiBase}/api/commission/periods/${periodId}`, {
                method: 'DELETE',
                headers: authHeader,
              })
              if (!delRes.ok) {
                const delData = await delRes.json()
                throw new Error(delData.detail || 'Không thể xóa kỳ cũ để cập nhật.')
              }
              // Save the new period
              await executeSave()
            } catch (err: any) {
              setError(`❌ ${err.message}`)
              setStep('preview')
            }
          }
        })
        return
      }
    }
    await executeSave()
  }

  // ── Computed totals ────────────────────────────────────
  const totalPnL = rows.reduce((s, r) => s + Number(r.profitLoss), 0)
  const totalRevRealized = rows.reduce((s, r) => s + Number(r.realizedRevenue), 0)

  // ── Flatten history rows ───────────────────────────────
  // Each period × sales_rep = one flat row
  const historyRows: HistoryFlatRow[] = savedPeriods.flatMap(p => {
    const reps = p.sales_rep_summary?.length ? p.sales_rep_summary : [
      { sales_rep: '—', job_count: p.job_count, total_profit_loss: p.total_profit_loss, sales_bonus: 0, target: 0, bonus_rate: 0, total_bonus_quarter: 0, employee_salary: 0, is_pnl_overridden: false, is_target_overridden: false, is_rate_overridden: false, is_total_bonus_overridden: false, is_monthly_bonus_overridden: false, remark: '' }
    ]
    return reps.map((s, si) => ({
      periodId: p.id,
      periodLabel: p.period_label,
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
    }))
  })

  function getWalletPeriodView(row: Pick<HistoryFlatRow, 'periodId' | 'periodLabel' | 'salesRep'>) {
    const wallet = wallets.find(item => item.sales_rep === row.salesRep && (
      item.period_summaries?.some(period => period.period_id === row.periodId) ||
      item.period_labels?.includes(row.periodLabel)
    ))
    const period = wallet?.period_summaries?.find(item => item.period_id === row.periodId)
    return {
      heldAmount: Number(period?.quarter_hold_amount ?? 0),
      monthlyAvailableAmounts: period?.monthly_available_amounts ?? [],
    }
  }

  function renderExcelTooltip(row: HistoryFlatRow, idx: number) {
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
    
    const target = row.usesProgressiveBonus && row.employeeSalary > 0
      ? row.employeeSalary * baseCoef
      : 0;
    const netProfit = row.repPnL * 0.95;
    const pfCountBn = row.usesProgressiveBonus ? netProfit - target : Math.max(netProfit, 0);
    
    // Calculate progressive breakdown dynamically
    const tiers: any[] = [];
    
    if (!row.usesProgressiveBonus) {
      tiers.push({
        name: '95% tổng Profit',
        rate: '20%',
        amount: Math.max(netProfit, 0),
        bonus: Math.max(netProfit, 0) * 0.20,
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
            Chi tiết tính toán ({row.salesRep})
          </strong>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '10px', padding: '2px 0' }}>
            <span style={{ color: '#34d399', fontWeight: 600 }}>Profit Sale:</span>
            <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#34d399', fontSize: '11px' }}>
              {fmtNum(netProfit)}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', padding: '8px 10px', backgroundColor: '#1e293b', borderRadius: '8px', gap: '6px', border: '1px solid #334155' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '10px' }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>Salary:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#93c5fd' }}>
                {fmtNum(row.employeeSalary)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '10px' }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>Target:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#fca5a5' }}>
                {fmtNum(target)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '10px' }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>PF_BN:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#c084fc' }}>
                {fmtNum(Math.max(pfCountBn, 0))}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '10px', borderTop: '1px solid #334155', paddingTop: '6px', marginTop: '2px' }}>
              <span style={{ color: '#cbd5e1', fontWeight: 600 }}>Bonus:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#38bdf8' }}>
                {fmtNum(row.repTotalBonus)}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '10px' }}>
              <span style={{ color: '#cbd5e1', fontWeight: 600 }}>Avg / Month:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#a78bfa' }}>
                {fmtNum(row.repBonus)}
              </span>
            </div>
          </div>
        </div>

        {/* Right Side: Progressive Tier Grid */}
        <div style={{ width: '250px', flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
          {/* Header Row */}
          <div style={{ display: 'flex', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '4px', alignItems: 'center' }}>
            <div style={{ width: '45%', fontWeight: 700, color: '#94a3b8', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>LEVEL RANGE</div>
            <div style={{ width: '20%', fontWeight: 700, color: '#94a3b8', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'center' }}>% RATE</div>
            <div style={{ width: '35%', fontWeight: 700, color: '#94a3b8', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'right' }}>BONUS</div>
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
                fontSize: '9.5px'
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
            fontSize: '9.5px'
          }}>
            <div style={{ width: '45%', color: '#ffffff' }}>
              {row.usesProgressiveBonus ? 'TOTAL LŨY TIẾN' : 'TOTAL CỐ ĐỊNH'}
            </div>
            <div style={{ width: '20%', textAlign: 'center', color: '#6ee7b7' }}>
              {(row.repRate * 100).toFixed(1)}%
            </div>
            <div style={{ width: '35%', textAlign: 'right', color: '#fca5a5', fontFamily: 'monospace', fontSize: '10.5px' }}>
              {row.repTotalBonus > 0 ? fmtNum(row.repTotalBonus) : '-'}
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
          font-size: 10px;
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
          font-family: Roboto, Arial, sans-serif;
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
        .commission-funnel-section { order: 40; }
      `}</style>

      {/* ── HEADER ──────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#0f172a' }}>
            📊 Commission &amp; Job PnL
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
            {step === 'detail' ? '← Quay lại lịch sử' : '← Import file mới'}
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
            jobEditorOpen={manualJobEditorOpen}
            onJobEditorClose={() => setManualJobEditorOpen(false)}
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
          <input ref={fileInputRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleInputChange} />
          {isLoading
            ? <div style={{ color: '#1d4ed8', fontSize: 14, fontWeight: 600 }}>⏳ Đang đọc file Excel...</div>
            : <>
              <div style={{ fontSize: 48, marginBottom: 10 }}>{isDragging ? '📥' : '📤'}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#1e40af', marginBottom: 6 }}>
                {isDragging ? 'Thả file vào đây' : 'Kéo thả hoặc click để chọn file Excel'}
              </div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                File <b>"Job PnL With Realize/Unrealize Detail"</b> (.xlsx/.xls) từ Climax
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

          {/* File info banner */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            background: 'linear-gradient(135deg,#eff6ff,#dbeafe)',
            border: '1px solid #93c5fd', borderRadius: 14, padding: '14px 18px',
          }}>
            <span style={{ fontSize: 24 }}>📂</span>
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
                <div style={{ fontSize: 9, fontWeight: 700, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Tổng P&L</div>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{fmtNum(totalPnL)}</div>
              </div>
              <div style={{ background: 'linear-gradient(135deg,#1e3a5f,#1d4ed8)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}>
                <div style={{ fontSize: 9, fontWeight: 700, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Realized Rev</div>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{fmtNum(totalRevRealized)}</div>
              </div>
            </div>
            {/* Period label editable */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <label style={{ fontSize: 10, fontWeight: 700, color: '#000000', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Nhãn kỳ</label>
              <input
                value={periodLabel}
                onChange={(e) => setPeriodLabel(e.target.value)}
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
            }}>✕ Hủy bỏ</button>
            <button onClick={handleConfirmSave} disabled={step === 'saving' || !!periodParseError || !fromDate || !tillDate} style={{
              height: 40, padding: '0 28px', borderRadius: 10,
              background: step === 'saving' || periodParseError || !fromDate || !tillDate ? '#94a3b8' : 'linear-gradient(135deg,#059669,#047857)',
              border: 'none', color: '#fff', fontSize: 13, fontWeight: 700,
              cursor: step === 'saving' || periodParseError || !fromDate || !tillDate ? 'not-allowed' : 'pointer',
              boxShadow: step === 'saving' || periodParseError || !fromDate || !tillDate ? 'none' : '0 6px 20px rgba(5,150,105,0.4)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              {step === 'saving' ? '⏳ Đang lưu...' : '✅ Xác nhận & Lưu vào Database'}
            </button>
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════
          STEP: DETAIL — Full 23-column detail view for a specific sales rep & period
      ════════════════════════════════════════════════ */}
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
                ×
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 18, padding: 18, overflow: 'auto', overscrollBehavior: 'contain' }}>

          {/* Banner thông tin chi tiết */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            background: 'linear-gradient(135deg,#eff6ff,#dbeafe)',
            border: '1px solid #93c5fd', borderRadius: 14, padding: '14px 18px',
          }}>
            <span style={{ fontSize: 24 }}>👤</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 800, fontSize: 16, color: '#1e3a8a' }}>
                Chi tiết công việc: {detailSalesRep}
              </div>
              <div style={{ fontSize: 13, color: '#3b82f6', marginTop: 4 }}>
                Kỳ commission: <b>{detailPeriodLabel}</b> {detailFileName && `· File gốc: ${detailFileName}`} · <b>{rows.length} jobs</b>
              </div>
            </div>
            {/* KPIs inline */}
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ background: totalPnL >= 0 ? 'linear-gradient(135deg,#065f46,#059669)' : 'linear-gradient(135deg,#991b1b,#dc2626)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}>
                <div style={{ fontSize: 9, fontWeight: 700, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Tổng P&L</div>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{fmtNum(totalPnL)}</div>
              </div>
              <div style={{ background: 'linear-gradient(135deg,#1e3a5f,#1d4ed8)', borderRadius: 10, padding: '8px 14px', color: '#fff' }}>
                <div style={{ fontSize: 9, fontWeight: 700, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Realized Rev</div>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{fmtNum(totalRevRealized)}</div>
              </div>
            </div>
          </div>

          {/* Bảng 23 cột */}
          <div style={{ border: '1px solid #cbd5e1', borderRadius: 14, overflow: 'auto', minHeight: 280, flex: 1 }}>
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
                            {col.num
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

          {/* Action button để đóng popup */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', gap: 12,
            padding: '2px 0 0',
          }}>
            <button type="button" onClick={openManualJobEditor} className="ui-button ui-button-primary" style={{ height: 40, padding: '0 20px' }}>
              ✎ Sửa thủ công
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

      {/* ════════════════════════════════════════════════

      {/* ════════════════════════════════════════════════
          STEP: DONE
      ════════════════════════════════════════════════ */}
      {step === 'done' && (
        <div style={{ textAlign: 'center', padding: '32px 20px', background: 'linear-gradient(135deg,#ecfdf5,#d1fae5)', borderRadius: 20, border: '1px solid #6ee7b7' }}>
          <div style={{ fontSize: 48, marginBottom: 10 }}>🎉</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: '#065f46', marginBottom: 14 }}>{successMsg}</div>
          <button onClick={resetImport} style={{
            height: 38, padding: '0 20px', borderRadius: 10,
            background: 'linear-gradient(135deg,#163b66,#1d4ed8)',
            border: 'none', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer',
          }}>📂 Import file mới</button>
        </div>
      )}

      {(step === 'idle' || step === 'done') && (
      <div className="commission-history-section">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#1e293b' }}>
            🗂️ Lịch sử Import đã lưu
          </h3>
          <button onClick={loadHistory} style={{
            height: 32, padding: '0 14px', borderRadius: 8,
            border: '1.5px solid #e2e8f0', background: '#fff',
            color: '#64748b', fontSize: 11, fontWeight: 600, cursor: 'pointer',
          }}>🔄 Làm mới</button>
        </div>

        {loadingHistory && (
          <div style={{ color: '#94a3b8', fontSize: 13, padding: '12px 0' }}>⏳ Đang tải...</div>
        )}

        {!loadingHistory && savedPeriods.length === 0 && (
          <div style={{ textAlign: 'center', padding: '28px 20px', background: '#f8fafc', borderRadius: 14, border: '1px dashed #cbd5e1', color: '#94a3b8', fontSize: 13 }}>
            Chưa có dữ liệu commission nào được lưu.
          </div>
        )}

        {historyRows.length > 0 && (
          <div style={{ border: '1px solid #cbd5e1', borderRadius: 14, overflow: 'visible' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
                  {['KỲ', 'TÊN SALES REP', 'JOBS', 'TỔNG PROFIT / LOSS', 'TARGET', 'HỆ SỐ', 'TỔNG THƯỞNG', 'ĐANG GIỮ', 'THƯỞNG / THÁNG', 'NGÀY LƯU', 'TÁC VỤ'].map(h => {
                    let tooltipContent: React.ReactNode = null
                    if (h === 'HỆ SỐ') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '220px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                            Mốc Level &amp; % Bonus
                          </strong>
                          
                          {/* Header Row */}
                          <div style={{ display: 'flex', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', alignItems: 'center' }}>
                            <div style={{ width: '60%', fontWeight: 700, color: '#94a3b8', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Hệ số (Coef)</div>
                            <div style={{ width: '40%', fontWeight: 700, color: '#94a3b8', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'right' }}>% RATE</div>
                          </div>

                          {/* Rows */}
                          {[
                            { range: '≤ 2', rate: '0%', color: '#94a3b8' },
                            { range: '2.01 - 4', rate: '20%', color: '#34d399' },
                            { range: '4.01 - 6', rate: '25%', color: '#34d399' },
                            { range: '6.01 - 8', rate: '30%', color: '#34d399' },
                            { range: '> 8', rate: '35%', color: '#34d399' }
                          ].map((item, idx) => (
                            <div key={idx} style={{
                              display: 'flex',
                              alignItems: 'center',
                              padding: '5px 6px',
                              margin: '1px -6px',
                              borderRadius: '6px',
                              fontSize: '9.5px',
                              backgroundColor: 'transparent',
                            }}>
                              <div style={{ width: '60%', color: '#e2e8f0', fontWeight: 500 }}>
                                {item.range}
                              </div>
                              <div style={{ width: '40%', textAlign: 'right', color: item.color, fontWeight: 700, fontFamily: 'monospace' }}>
                                {item.rate}
                              </div>
                            </div>
                          ))}
                        </div>
                      )
                    } else if (h === 'TỔNG PROFIT / LOSS') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '280px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                            Thông tin cột Tổng Profit / Loss
                          </strong>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '10px', color: '#cbd5e1', lineHeight: '1.4' }}>
                            <div>
                              • <b>Mỗi dòng:</b> Hiển thị Net Profit (Gross Profit × 95%) hoặc giá trị Net điều chỉnh thủ công.
                            </div>
                            <div style={{ borderTop: '1px solid #334155', paddingTop: '6px', marginTop: '2px' }}>
                              • <b>Số tổng cộng (dòng cuối):</b> Tổng Net Profit của tất cả các Sales Rep.
                            </div>
                            <div style={{ color: '#34d399', fontWeight: 700, fontSize: '9.5px', marginTop: '2px' }}>
                              Công thức: Tổng cộng = &sum;(Net Profit)
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
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '10px', color: '#cbd5e1' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                              <span style={{ color: '#38bdf8', fontWeight: 600 }}>1. Net Profit</span>
                              <span style={{ textAlign: 'right', fontWeight: 500 }}>Tổng Profit/Loss × 95%</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                              <span style={{ color: '#fca5a5', fontWeight: 600 }}>2. Target</span>
                              <span style={{ textAlign: 'right', fontWeight: 500 }}>Lương HĐLĐ × 2</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                              <span style={{ color: '#c084fc', fontWeight: 600 }}>3. Chênh lệch (PF_BN)</span>
                              <span style={{ textAlign: 'right', fontWeight: 500 }}>Net Profit − Target</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', color: '#34d399' }}>
                              <span style={{ fontWeight: 700 }}>4. Tổng thưởng</span>
                              <span style={{ textAlign: 'right', fontWeight: 700 }}>Chênh lệch × Hệ số</span>
                            </div>
                            <div style={{ fontSize: '9px', color: '#94a3b8', fontStyle: 'italic', marginTop: '2px' }}>
                              * Nếu Chênh lệch &le; 0 thì Tổng thưởng = 0
                            </div>
                          </div>
                        </div>
                      )
                    } else if (h === 'THƯỞNG / THÁNG') {
                      tooltipContent = (
                        <div className="commission-tooltip-text tooltip-down" style={{ width: '240px', padding: '12px 14px' }}>
                          <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                            Công thức tính Thưởng / Tháng
                          </strong>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '10px', color: '#cbd5e1' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#38bdf8' }}>
                              <span style={{ fontWeight: 700 }}>Thưởng / Tháng</span>
                              <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>Tổng thưởng / 3</span>
                            </div>
                            <div style={{ fontSize: '9px', color: '#94a3b8', borderTop: '1px solid #334155', paddingTop: '6px', marginTop: '2px', lineHeight: '1.4' }}>
                              * Áp dụng chi trả theo từng tháng trong kỳ lương.
                            </div>
                          </div>
                        </div>
                      )
                    }

                    return (
                      <th key={h} style={{
                        padding: '12px 16px',
                        textAlign: h === 'JOBS' || h === 'TÁC VỤ' || h === 'HỆ SỐ' ? 'center' : h === 'TỔNG PROFIT / LOSS' || h === 'TARGET' || h === 'TỔNG THƯỞNG' || h === 'ĐANG GIỮ' || h === 'THƯỞNG / THÁNG' ? 'right' : 'left',
                        fontWeight: 700, fontSize: 12, letterSpacing: '0.04em',
                        color: '#000000',
                      }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: h === 'JOBS' || h === 'TÁC VỤ' || h === 'HỆ SỐ' ? 'center' : h === 'TỔNG PROFIT / LOSS' || h === 'TARGET' || h === 'TỔNG THƯỞNG' || h === 'ĐANG GIỮ' || h === 'THƯỞNG / THÁNG' ? 'flex-end' : 'flex-start', width: '100%', gap: 4 }}>
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
                    <td style={{
                      padding: '12px 16px',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      <button
                        onClick={() => viewPeriodJobs(row.periodId, row.periodLabel, row.salesRep, row.sourceFilename || null)}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          color: '#2563eb',
                          textDecoration: 'underline',
                          fontWeight: 700,
                          fontSize: 13,
                          cursor: 'pointer',
                          textAlign: 'left',
                        }}
                      >
                        📅 {row.periodLabel}
                      </button>
                    </td>

                    {/* SALES REP */}
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: '#000000', fontSize: 14, borderRight: '1px solid #cbd5e1' }}>
                      <div>👤 {row.salesRep}</div>
                      {row.remark ? (
                        <div style={{ fontSize: 11, fontWeight: 400, color: '#475569', fontStyle: 'italic', marginTop: 4, whiteSpace: 'pre-wrap', maxWidth: 180, textAlign: 'left' }}>
                          💬 {row.remark}
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
                      color: (row.repPnL * 0.95) >= 0 ? '#15803d' : '#b91c1c',
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
                            <span style={{ color: '#f59e0b', marginLeft: 4, fontSize: 11, cursor: 'help' }} title="Đã sửa thủ công">✏️</span>
                          )}
                          <span className="commission-tooltip-container" style={{ marginLeft: 4 }}>
                            <span className="commission-tooltip-icon">?</span>
                            <div className={`commission-tooltip-text ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: '220px', padding: '12px 14px' }}>
                              <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                                Công thức tính Net Profit
                              </strong>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '9.5px', color: '#cbd5e1' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                  <span>Gross Profit/Loss:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>{fmtNum(row.repPnL)}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                  <span>Tỷ lệ Net:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>95%</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #334155', paddingTop: '4px', marginTop: '2px', color: '#34d399' }}>
                                  <span style={{ fontWeight: 600 }}>Thực nhận (Net):</span>
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
                          {row.repTarget > 0 ? fmtNum(row.repTarget) : '—'}
                          {row.isTargetOverridden && (
                            <span style={{ color: '#f59e0b', marginLeft: 4, fontSize: 11, cursor: 'help' }} title="Đã sửa thủ công">✏️</span>
                          )}
                        </span>
                      )}
                    </td>

                    {/* HỆ SỐ */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'center',
                      fontWeight: 700, fontSize: 13,
                      color: row.repRate > 0 ? '#b45309' : '#64748b',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      <span>
                        {(() => {
                          const displayCoef = row.repCoefficient || (row.employeeSalary > 0 ? (row.repPnL * 0.95 / row.employeeSalary) : 0);
                          return displayCoef > 0 ? displayCoef.toFixed(2) : '0.00';
                        })()}
                        {row.isRateOverridden && (
                          <span style={{ color: '#f59e0b', marginLeft: 4, fontSize: 11, cursor: 'help' }} title="Đã sửa thủ công">✏️</span>
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
                      color: row.repTotalBonus > 0 ? '#0d9488' : '#64748b',
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
                          {row.repTotalBonus > 0 ? fmtNum(row.repTotalBonus) : '—'}
                          {row.isTotalBonusOverridden && (
                            <span style={{ color: '#f59e0b', marginLeft: 4, fontSize: 11, cursor: 'help' }} title="Đã sửa thủ công">✏️</span>
                          )}
                           <span className="commission-tooltip-container">
                            <span className="commission-tooltip-icon">?</span>
                            <div className={`commission-tooltip-text ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: '280px', padding: '12px 14px' }}>
                              <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                                Cách tính Tổng Thưởng ({row.salesRep})
                              </strong>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '10px', color: '#cbd5e1' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Chênh lệch (Net PnL - Target):</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#fca5a5' }}>
                                    {fmtNum(row.repPnL * 0.95 - row.repTarget)} VND
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Coefficient (Net PnL / Salary):</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#93c5fd' }}>
                                    {row.repCoefficient ? row.repCoefficient.toFixed(2) : (row.employeeSalary > 0 ? (row.repPnL * 0.95 / row.employeeSalary).toFixed(2) : '0.00')}
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Level hiện tại:</span>
                                  <span style={{ fontWeight: 700, color: '#c084fc' }}>
                                    {getLevelName(row.repCoefficient || (row.employeeSalary > 0 ? (row.repPnL * 0.95 / row.employeeSalary) : 0))}
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Mức bonus (Hệ số):</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#a78bfa' }}>
                                    {Math.round(row.repRate * 100)}%
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#38bdf8' }}>
                                  <span style={{ fontWeight: 700 }}>Thưởng (Chênh lệch × Hệ số):</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 800 }}>
                                    {fmtNum(row.repTotalBonus)} VND
                                  </span>
                                </div>
                              </div>
                            </div>
                          </span>
                        </span>
                      )}
                    </td>

                    {/* ĐANG GIỮ — số chung của đúng kỳ/quý, không nhân theo tháng */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'right',
                      fontWeight: 800, fontFamily: 'monospace', fontSize: 15,
                      color: getWalletPeriodView(row).heldAmount > 0 ? '#b45309' : '#64748b',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {getWalletPeriodView(row).heldAmount > 0 ? fmtNum(getWalletPeriodView(row).heldAmount) : '0'}
                    </td>

                    {/* THƯỞNG / THÁNG */}
                    <td style={{
                      padding: '8px 16px', textAlign: 'right',
                      fontWeight: 800, fontFamily: 'monospace', fontSize: 15,
                      color: row.repBonus > 0 ? '#1d4ed8' : '#64748b',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {editingRowKey === `${row.periodId}-${row.salesRep}` && editDraft ? (
                        <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                          <input
                            type="checkbox"
                            checked={manualChecked.repBonus}
                            onChange={(e) => handleCheckboxChange('repBonus', e.target.checked, row)}
                            title="Sửa thủ công"
                            style={{ cursor: 'pointer', width: '14px', height: '14px', minWidth: '14px', minHeight: '14px', flexShrink: 0, margin: 0, padding: 0 }}
                          />
                          <VndInput
                            value={editDraft.repBonus}
                            disabled={!manualChecked.repBonus}
                            onValueChange={(value) => {
                              if (editDraft) {
                                const nextDraft = { ...editDraft, repBonus: String(value) };
                                setEditDraft(recalculateDraft(nextDraft, manualChecked, row));
                              }
                            }}
                            style={{
                              width: 120,
                              textAlign: 'right',
                              height: 28,
                              borderRadius: 5,
                              border: '1px solid #cbd5e1',
                              borderColor: manualChecked.repBonus ? '#3b82f6' : '#cbd5e1',
                              background: manualChecked.repBonus ? '#fff' : '#f1f5f9',
                              color: manualChecked.repBonus ? '#000' : '#64748b',
                              fontSize: 13,
                              outline: 'none',
                              fontFamily: 'monospace',
                              fontWeight: 700,
                            }}
                          />
                        </div>
                      ) : (
                        <span>
                          {row.repBonus > 0 ? fmtNum(row.repBonus) : '—'}
                          {row.isMonthlyBonusOverridden && (
                            <span style={{ color: '#f59e0b', marginLeft: 4, fontSize: 11, cursor: 'help' }} title="Đã sửa thủ công">✏️</span>
                          )}
                           <span className="commission-tooltip-container">
                            <span className="commission-tooltip-icon">?</span>
                            <div className={`commission-tooltip-text ${idx === 0 ? 'tooltip-down' : 'tooltip-up'}`} style={{ width: '340px', padding: '12px 14px' }}>
                              <strong style={{ fontSize: '11px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '5px', marginBottom: '6px', display: 'block', fontWeight: 700, letterSpacing: '0.02em' }}>
                                Cách tính Thưởng / Tháng ({row.salesRep})
                              </strong>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '10px', color: '#cbd5e1' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Tổng thưởng:</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#38bdf8' }}>
                                    {fmtNum(row.repTotalBonus)} VND
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Level hiện tại:</span>
                                  <span style={{ fontWeight: 700, color: '#c084fc' }}>
                                    {getLevelName(row.repCoefficient || (row.employeeSalary > 0 ? (row.repPnL * 0.95 / row.employeeSalary) : 0))}
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '4px' }}>
                                  <span style={{ color: '#cbd5e1' }}>Mức bonus (Hệ số):</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#a78bfa' }}>
                                    {Math.round(row.repRate * 100)}%
                                  </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#34d399' }}>
                                  <span style={{ fontWeight: 700 }}>Thưởng / Tháng (Tổng / 3):</span>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 800 }}>
                                    {fmtNum(row.repBonus)} VND
                                  </span>
                                </div>
                                <div style={{ borderTop: '1px solid #334155', paddingTop: 7 }}>
                                  <div style={{ color: '#fbbf24', fontWeight: 700, marginBottom: 5 }}>
                                    Đang giữ cả quý: {fmtNum(getWalletPeriodView(row).heldAmount)} VND
                                  </div>
                                  {getWalletPeriodView(row).monthlyAvailableAmounts.length > 0 ? getWalletPeriodView(row).monthlyAvailableAmounts.map(item => (
                                    <div key={item.payout_period} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: '#34d399', marginTop: 3 }}>
                                      <span>Khả dụng {item.payout_period.replace('-', '/')}:</span>
                                      <b style={{ fontFamily: 'monospace' }}>{fmtNum(item.amount)} VND</b>
                                    </div>
                                  )) : <div style={{ color: '#94a3b8' }}>Chưa có dữ liệu khả dụng theo tháng.</div>}
                                </div>
                                <div style={{ fontSize: 9, color: '#94a3b8', borderTop: '1px solid #334155', paddingTop: 6, lineHeight: 1.45 }}>
                                  Khả dụng/tháng là số có thể chi thực tế sau khi trừ phần bonus đang giữ của cả quý. Khoản đang giữ chỉ tính một lần cho quý, không nhân ba.
                                </div>
                              </div>
                            </div>
                          </span>
                        </span>
                      )}
                    </td>

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
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
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
                        <div style={{ display: 'flex', gap: 6, justifyContent: 'center', alignItems: 'center' }}>
                          <button
                            onClick={() => focusWalletFromHistory(row)}
                            style={{
                              height: 28, padding: '0 12px', borderRadius: 7,
                              border: '1px solid #7c3aed', background: '#f5f3ff',
                              color: '#6d28d9', fontSize: 11, fontWeight: 700, cursor: 'pointer',
                            }}
                            title={`Mở ví thưởng của ${row.salesRep} cho kỳ ${row.periodLabel}`}
                          >💼 Ví thưởng</button>
                          <button
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
                          >✏️ Sửa</button>
                          <button
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
                          >💬 Remark</button>
                          <button
                              onClick={() => deleteSalesRepCommission(row.periodId, row.periodLabel, row.salesRep)}
                              style={{
                                height: 28, padding: '0 12px', borderRadius: 7,
                                border: '1px solid #fca5a5', background: '#fef2f2',
                                color: '#dc2626', fontSize: 11, fontWeight: 600, cursor: 'pointer',
                              }}
                            >🗑 Xóa</button>
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
                      color: (historyRows.reduce((s, r) => s + r.repPnL, 0) * 0.95) >= 0 ? '#15803d' : '#b91c1c',
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
                      {fmtNum(historyRows.reduce((s, r) => s + r.repTotalBonus, 0))}
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
                      color: '#1d4ed8',
                      borderRight: '1px solid #cbd5e1',
                    }}>
                      {fmtNum(historyRows.reduce((s, r) => s + r.repBonus, 0))}
                    </td>
                    <td colSpan={2} />
                  </tr>
                )}
              </tbody>
            </table>
          </div>
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
                💬 Thêm/Sửa Ghi chú (Remark)
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
                ✕
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
            maxWidth: '520px',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#b91c1c', display: 'flex', alignItems: 'center', gap: 6 }}>
                ⚠️ Cảnh báo trùng kỳ Commission
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
                ✕
              </button>
            </div>
            
            <div style={{ fontSize: '14px', color: '#334155', lineHeight: '1.6' }}>
              Kỳ import mới này (<b>{periodLabel}</b>) có tháng trùng với các kỳ đã import trước đó trong cơ sở dữ liệu:
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

            <div style={{ fontSize: '13.5px', color: '#475569', fontWeight: 500 }}>
              Bạn có chắc chắn muốn tiếp tục import trùng không?
            </div>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '4px' }}>
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
              {overlapWarningData.conflicts.some(c => c.isExact) && (
                <button
                  onClick={() => {
                    const exact = overlapWarningData.conflicts.find(c => c.isExact)
                    if (exact && overlapWarningData.onUpdate) {
                      overlapWarningData.onUpdate(exact.id)
                    }
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
                  Cập nhật (Ghi đè)
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
                Tiếp tục import
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
