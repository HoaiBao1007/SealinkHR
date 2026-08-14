/**
 * SalaryDataGrid — Bảng lương tổng hợp dành riêng ADMIN (Kế toán trưởng)
 * Đặc tả: FULLTIME (Khối A) + PROBATION (Khối B) + Sub-total + Grand Total
 * Màu sắc: Ô nhập tay = #fff2cc (vàng kem) | Ô công thức = #f5f5f5 (xám khói)
 *
 * v2 — Bổ sung:
 *   • Ô "Ngày công mặc định" trên toolbar → áp dụng cho tất cả nhân viên một lần
 *   • Checkbox chọn nhân viên → bulk-edit: sửa 1 người trong nhóm tick, toàn nhóm cập nhật
 */

import { useMemo, useCallback, useState, useEffect, type ReactNode } from 'react'
import { cake_salary } from '../../shared/utils/salary'
import type { SalaryPolicy } from '../../shared/utils/salary'
import { VndInput } from '../../shared/ui/VndInput'
import { formatVnd } from '../../shared/utils/currency'

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────
interface SalaryEmployee {
  id: number
  employee_code?: string
  machine_employee_id?: string
  fullname: string
  position?: string
  employee_type: 'FULLTIME' | 'PROBATION' | 'INTERN'
  contract_salary: number
  dependents_count: number
  account_number?: string
  bank_name?: string
  is_mid_month_change?: boolean
  prorated_old_salary?: number
  prorated_new_salary?: number
  prorated_days_old?: number
  prorated_days_new?: number
  mid_month_effective_date?: string
}

interface SalaryInput {
  employee_id: number
  actual_working_days: number
  meal_allowance_free: number
  meal_allowance_tax: number
  phone_allowance_free: number
  trans_allowance_tax: number
  perf_allowance_tax: number
  other_income: number
  other_income_note?: string | null
  other_income_document_name?: string | null
  other_income_document_content_type?: string | null
  other_income_document_size?: number | null
  other_income_document_uploaded_at?: string | null
  bonus: number
  bonus_14?: number
  sales_bonus?: number
  advance_payment: number
  pit_refund: number
  other_deductions: number
}

interface EditedInputs {
  [empId: number]: Partial<SalaryInput>
}

interface SalaryDataGridProps {
  employees: SalaryEmployee[]
  inputs: SalaryInput[]
  editedInputs: EditedInputs
  salaryPeriod: string
  onCellChange: (empId: number, field: keyof SalaryInput, value: number) => void
  onOpenOtherIncomeEvidence: (employee: SalaryEmployee, input: SalaryInput) => void
  isSalaryLocked: boolean
  onToggleLock: () => void
  toolbarActions?: ReactNode
  salaryPolicy?: SalaryPolicy
  focusEmployeeId?: number | null
  focusKey?: number | null
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
const fmt = (n: number) => formatVnd(n)

const formatDateStr = (dateStr?: string) => {
  if (!dateStr) return '?'
  const parts = dateStr.split('-')
  if (parts.length !== 3) return dateStr
  return `${parts[2]}/${parts[1]}/${parts[0]}`
}

const getDayBefore = (dateStr?: string) => {
  if (!dateStr) return '?'
  try {
    const d = new Date(dateStr + 'T00:00:00')
    d.setDate(d.getDate() - 1)
    const dd = String(d.getDate()).padStart(2, '0')
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const yyyy = d.getFullYear()
    return `${dd}/${mm}/${yyyy}`
  } catch (e) {
    return '?'
  }
}

const getMonthBounds = (period: string) => {
  if (!period) return { start: '?', end: '?' }
  try {
    const [year, month] = period.split('-')
    const currentYear = parseInt(year)
    const currentMonth = parseInt(month)
    
    let prevYear = currentYear
    let prevMonth = currentMonth - 1
    if (prevMonth === 0) {
      prevMonth = 12
      prevYear--
    }
    
    const prevMonthStr = String(prevMonth).padStart(2, '0')
    const currMonthStr = String(currentMonth).padStart(2, '0')
    
    return {
      start: `23/${prevMonthStr}/${prevYear}`,
      end: `22/${currMonthStr}/${currentYear}`
    }
  } catch(e) {
    return { start: '?', end: '?' }
  }
}

const calculatePeriodWorkingDays = (period: string): number => {
  if (!period) return 26
  try {
    const [year, month] = period.split('-')
    const currentYear = parseInt(year)
    const currentMonth = parseInt(month)
    
    let prevYear = currentYear
    let prevMonth = currentMonth - 1
    if (prevMonth === 0) {
      prevMonth = 12
      prevYear--
    }
    
    const startD = new Date(prevYear, prevMonth - 1, 23)
    const endD = new Date(currentYear, currentMonth - 1, 22)
    
    let workingDays = 0
    let cur = new Date(startD)
    while (cur <= endD) {
      if (cur.getDay() !== 0 && cur.getDay() !== 6) { // Exclude Saturdays (6) and Sundays (0)
        workingDays++
      }
      cur.setDate(cur.getDate() + 1)
    }
    return workingDays
  } catch (e) {
    return 26
  }
}

// CSS class shorthands
const CL = {
  // Ô công thức (read-only) — xám khói, không sửa được
  formula:
    'h-8 w-full rounded border-0 bg-[#f5f5f5] px-2 text-right text-[13px] font-semibold text-slate-700 cursor-not-allowed select-none outline-none',
  // Ô nhập tay — vàng kem, có thể sửa
  editable:
    'h-8 w-full rounded border border-amber-200 bg-[#fff2cc] px-2 text-center text-[13px] font-medium text-slate-800 outline-none focus:border-[#163B66] focus:ring-2 focus:ring-[#163B66]/20 transition-all',
  // Header cell
  th: 'px-2 py-2 text-center text-[11px] font-bold uppercase tracking-wider whitespace-nowrap',
  // Data cell
  td: 'px-1 py-1 text-right text-[13px]',
  // Sub-total / Grand-total cell
  subtd: 'px-2 py-2 text-right text-[13px] font-bold',
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-row calculation helper
// ─────────────────────────────────────────────────────────────────────────────
function computeRow(emp: SalaryEmployee, input: SalaryInput, standardDays: number, salaryPolicy?: SalaryPolicy) {
  return cake_salary({
    type: emp.employee_type,
    contract_salary: Number(emp.contract_salary) || 0,
    actual_working_days: input.actual_working_days,
    standard_working_days: standardDays,
    meal_allowance_free: input.meal_allowance_free,
    meal_allowance_tax: input.meal_allowance_tax,
    phone_allowance_free: input.phone_allowance_free,
    trans_allowance_tax: input.trans_allowance_tax,
    perf_allowance_tax: input.perf_allowance_tax,
    other_income: input.other_income,
    bonus: input.bonus + (input.sales_bonus ?? 0),
    bonus_14: input.bonus_14,
    dependents_count: emp.dependents_count,
    other_deductions: input.other_deductions,
    pit_refund: input.pit_refund,
    advance_payment: input.advance_payment,
  }, salaryPolicy)
}

// Merge editedInputs onto base input
function mergeInput(base: SalaryInput | undefined, edits: Partial<SalaryInput> | undefined, empId: number, salaryPeriod: string, employeeType: SalaryEmployee['employee_type']): SalaryInput {
  const stdDays = calculatePeriodWorkingDays(salaryPeriod)
  const defaults: SalaryInput = {
    employee_id: empId,
    actual_working_days: stdDays, // Mặc định stdDays ngày công / kỳ
    meal_allowance_free: 1200000, // Mặc định cơm miễn thuế 1.200.000 VND
    meal_allowance_tax: 0,
    phone_allowance_free: 2000000, // Mặc định ĐT miễn thuế 2.000.000 VND
    trans_allowance_tax: 2000000, // Mặc định xăng xe 2.000.000 VND
    perf_allowance_tax: 0,
    other_income: 0,
    bonus: 0,
    bonus_14: 0,
    sales_bonus: 0,
    advance_payment: 0,
    pit_refund: 0,
    other_deductions: 0,
  }
  if (employeeType !== 'FULLTIME') {
    defaults.meal_allowance_free = 0
    defaults.phone_allowance_free = 0
    defaults.trans_allowance_tax = 0
  }
  const mergedBase = base ? {
    ...base,
    actual_working_days: base.actual_working_days ?? stdDays,
    meal_allowance_free: base.meal_allowance_free ?? defaults.meal_allowance_free,
    phone_allowance_free: base.phone_allowance_free ?? defaults.phone_allowance_free,
    trans_allowance_tax: base.trans_allowance_tax ?? defaults.trans_allowance_tax,
  } : {};
  return { ...defaults, ...mergedBase, ...(edits ?? {}) } as SalaryInput
}

// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// Sub-total row
// ─────────────────────────────────────────────────────────────────────────────
interface SubTotalData {
  contract_salary: number
  actual_salary: number
  meal_allowance_free: number
  meal_allowance_tax: number
  phone_allowance_free: number
  trans_allowance_tax: number
  perf_allowance_tax: number
  other_income: number
  bonus: number
  bonus_14: number
  sales_bonus: number
  ins_salary: number
  social_emp: number
  health_emp: number
  unemp_emp: number
  total_ins_emp: number
  social_comp: number
  health_comp: number
  unemp_comp: number
  total_ins_comp: number
  union_fund_comp: number
  taxable_income: number
  assessable_income: number
  pit_tax: number
  net_salary: number
  union_fee: number
  other_deductions: number
  pit_refund: number
  total_transfer: number
  advance_payment: number
  final_transfer: number
}

function emptySubTotal(): SubTotalData {
  return {
    contract_salary: 0, actual_salary: 0,
    meal_allowance_free: 0, meal_allowance_tax: 0,
    phone_allowance_free: 0, trans_allowance_tax: 0,
    perf_allowance_tax: 0, other_income: 0, bonus: 0, bonus_14: 0,
    sales_bonus: 0,
    ins_salary: 0,
    social_emp: 0, health_emp: 0, unemp_emp: 0, total_ins_emp: 0,
    social_comp: 0, health_comp: 0, unemp_comp: 0, total_ins_comp: 0, union_fund_comp: 0,
    taxable_income: 0, assessable_income: 0, pit_tax: 0,
    net_salary: 0, union_fee: 0, other_deductions: 0, pit_refund: 0,
    total_transfer: 0, advance_payment: 0, final_transfer: 0,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// COLUMN HEADERS — defined once, rendered twice (FULLTIME + PROBATION)
// Thêm cột checkbox (key='__check__') vào đầu
// ─────────────────────────────────────────────────────────────────────────────
const COL_GROUPS = [
  {
    label: '',
    cols: [
      { key: '__check__',        label: '',                        w: 28 },
      { key: 'stt',              label: 'STT',                     w: 32 },
    ],
    bg: '#163b66', color: '#fff',
  },
  {
    label: 'Thông tin NV & Ngày công',
    cols: [
      { key: 'actual_working_days',  label: 'Ngày công',           w: 70,  editable: true },
      { key: 'fullname',         label: 'Họ và tên',               w: 160, sticky: true },
    ],
    bg: '#163b66', color: '#fff',
    sticky: true,
  },
  {
    label: 'Vị trí & NPT',
    cols: [
      { key: 'dependents_count', label: 'NPT',                     w: 44 },
      { key: 'position',         label: 'Vị trí',                  w: 100 },
    ],
    bg: '#163b66', color: '#fff',
  },
  {
    label: 'Lương thực tế',
    cols: [
      { key: 'contract_salary',      label: 'L.HĐLĐ',             w: 120, formula: true },
      { key: 'actual_salary',        label: 'L.Thực tế',           w: 120, formula: true },
    ],
    bg: '#1e40af', color: '#fff',
  },
  {
    label: 'Biến động & Phụ cấp',
    cols: [
      { key: 'meal_allowance_free',  label: 'Cơm (Miễn)',         w: 96,  formula: true },
      { key: 'meal_allowance_tax',   label: 'Cơm (Thuế)',         w: 96,  formula: true },
      { key: 'phone_allowance_free', label: 'ĐT (Miễn)',          w: 90,  formula: true },
      { key: 'trans_allowance_tax',  label: 'Xăng xe',            w: 90,  formula: true },
      { key: 'perf_allowance_tax',   label: 'KPI',                w: 90,  editable: true },
      { key: 'other_income',         label: 'TN khác',            w: 90,  editable: true },
      { key: 'bonus',                label: 'Thưởng',             w: 96,  editable: true },
      { key: 'sales_bonus',          label: 'Thưởng doanh số',    w: 125, formula: true },
      { key: 'bonus_14',             label: 'Lương T14',          w: 96,  editable: true },
    ],
    bg: '#1d4ed8', color: '#fff',
  },
  {
    label: 'Bảo hiểm NLĐ',
    cols: [
      { key: 'ins_salary',    label: 'Lương nộp BHXH',  w: 110, formula: true },
      { key: 'social_emp',    label: 'BHXH 8%',  w: 90, formula: true },
      { key: 'health_emp',    label: 'BHYT 1.5%', w: 90, formula: true },
      { key: 'unemp_emp',     label: 'BHTN 1%',  w: 80, formula: true },
      { key: 'total_ins_emp', label: 'Tổng bảo hiểm NLĐ',  w: 110, formula: true },
    ],
    bg: '#7c3aed', color: '#fff',
  },
  {
    label: 'Chi phí DN chịu',
    cols: [
      { key: 'social_comp',    label: 'BHXH 17.5%',   w: 90, formula: true },
      { key: 'health_comp',    label: 'BHYT 3%',      w: 80, formula: true },
      { key: 'unemp_comp',     label: 'BHTN 1%',      w: 72, formula: true },
      { key: 'total_ins_comp', label: 'Tổng BH DN',   w: 95, formula: true },
      { key: 'union_fund_comp',label: 'KP CĐ 2%',    w: 80, formula: true },
    ],
    bg: '#0369a1', color: '#fff',
  },
  {
    label: 'Thuế TNCN',
    cols: [
      { key: 'taxable_income',   label: 'TN chịu thuế',   w: 100, formula: true },
      { key: 'assessable_income',label: 'TN tính thuế', w: 100, formula: true },
      { key: 'pit_tax',          label: 'Thuế PIT',   w: 90,  formula: true },
    ],
    bg: '#b91c1c', color: '#fff',
  },
  {
    label: 'Thanh toán',
    cols: [
      { key: 'net_salary',      label: 'Lương NET', w: 120, formula: true },
      { key: 'union_fee',       label: 'Đoàn phí', w: 90,  formula: true },
      { key: 'pit_refund',      label: 'Hoàn thuế PIT',     w: 90,  editable: true },
      { key: 'other_deductions', label: 'Khấu trừ khác', w: 96,  editable: true },
      { key: 'total_transfer',  label: 'Tổng chuyển', w: 125, formula: true },
      { key: 'advance_payment', label: 'Tạm ứng',       w: 90,  editable: true },
      { key: 'final_transfer',  label: 'Còn lại',  w: 125, formula: true },
    ],
    bg: '#065f46', color: '#fff',
  },
  {
    label: 'Đối soát Bank',
    cols: [
      { key: 'account_number',  label: 'Số tài khoản',  w: 110, formula: true },
      { key: 'bank_name',       label: 'Tên ngân hàng', w: 130, formula: true },
      { key: 'bank_branch',     label: 'Chi nhánh',     w: 100, formula: true },
      { key: 'bank_city',       label: 'Tỉnh/TP',       w: 80,  formula: true },
      { key: 'transfer_notes',  label: 'Ghi chú',       w: 130, formula: true },
      { key: 'other_income_evidence', label: 'Chứng từ TN khác', w: 112, formula: true },
    ],
    bg: '#334155', color: '#fff',
  }
]

// Flat list of all columns (bao gồm __check__)
const ALL_COLS = COL_GROUPS.flatMap(g => g.cols)
// Số cột trước các numeric cols = 6 (check, stt, days, name, npt, position)
const INFO_COL_SPAN = 6

const stickyStyles = (key: string, bg: string, isHeader = false) => {
  const stickyMap: Record<string, number> = {
    'actual_working_days': 0,
    'fullname': 70,
  }
  if (stickyMap[key] === undefined) return {}
  return {
    position: 'sticky' as const,
    left: stickyMap[key],
    zIndex: isHeader ? 6 : 2,
    background: bg,
    ...(key === 'fullname' ? { 
      borderRight: '2px solid #cbd5e1',
      boxShadow: '3px 0 6px -2px rgba(0,0,0,0.1)'
    } : {}),
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Total Row Component
// ─────────────────────────────────────────────────────────────────────────────
function SubTotalRow({ label, data }: { label: string; data: SubTotalData }) {
  const cellStyle = {
    background: '#d9e1f2',
    color: '#1f4e78',
    fontWeight: 700,
    fontSize: 11,
    padding: '5px 6px',
    textAlign: 'right' as const,
    whiteSpace: 'nowrap' as const,
    borderTop: '2px solid #1f4e78',
  }

  // Map col key to value
  function val(key: string): string {
    const numericKeys: Record<string, number> = {
      contract_salary: data.contract_salary,
      actual_salary: data.actual_salary,
      meal_allowance_free: data.meal_allowance_free,
      meal_allowance_tax: data.meal_allowance_tax,
      phone_allowance_free: data.phone_allowance_free,
      trans_allowance_tax: data.trans_allowance_tax,
      perf_allowance_tax: data.perf_allowance_tax,
      other_income: data.other_income,
      bonus: data.bonus,
      sales_bonus: data.sales_bonus,
      bonus_14: data.bonus_14,
      ins_salary: data.ins_salary,
      social_emp: data.social_emp,
      health_emp: data.health_emp,
      unemp_emp: data.unemp_emp,
      total_ins_emp: data.total_ins_emp,
      social_comp: data.social_comp,
      health_comp: data.health_comp,
      unemp_comp: data.unemp_comp,
      total_ins_comp: data.total_ins_comp,
      union_fund_comp: data.union_fund_comp,
      taxable_income: data.taxable_income,
      assessable_income: data.assessable_income,
      pit_tax: data.pit_tax,
      net_salary: data.net_salary,
      union_fee: data.union_fee,
      other_deductions: data.other_deductions,
      pit_refund: data.pit_refund,
      total_transfer: data.total_transfer,
      advance_payment: data.advance_payment,
      final_transfer: data.final_transfer,
    }
    return numericKeys[key] !== undefined ? fmt(numericKeys[key]) : '—'
  }

  const skipKeys = new Set(['__check__', 'stt', 'employee_code', 'fullname', 'dependents_count', 'position', 'actual_working_days'])

  const emptyCellStyle = {
    ...cellStyle,
    textAlign: 'center' as const,
  }
  const daysStyle = {
    ...cellStyle,
    position: 'sticky' as const,
    left: 0,
    zIndex: 2,
    textAlign: 'center' as const,
  }
  const stickyLabelStyle = { 
    ...cellStyle, 
    textAlign: 'left' as const, 
    fontSize: 11,
    position: 'sticky' as const,
    left: 70,
    zIndex: 2,
    borderRight: '2px solid #cbd5e1',
    boxShadow: '3px 0 6px -2px rgba(0,0,0,0.1)',
  }

  return (
    <tr>
      <td colSpan={2} style={emptyCellStyle}>—</td>
      <td style={daysStyle}>—</td>
      <td colSpan={3} style={stickyLabelStyle}>{label}</td>
      {ALL_COLS.slice(INFO_COL_SPAN).map(col => (
        <td key={col.key} style={{ ...cellStyle, width: `${col.w}px`, minWidth: `${col.w}px` }}>
          {skipKeys.has(col.key) ? '—' : val(col.key)}
        </td>
      ))}
    </tr>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────
export function SalaryDataGrid({
  employees,
  inputs,
  editedInputs,
  salaryPeriod,
  isSalaryLocked,
  onToggleLock,
  toolbarActions,
  salaryPolicy,
  onCellChange,
  onOpenOtherIncomeEvidence,
  focusEmployeeId,
  focusKey,
}: SalaryDataGridProps) {

  // ── State: ngày công mặc định + ô nhập nháp ─────────────────────────────
  const [defaultDaysInput, setDefaultDaysInput] = useState('26')

  useEffect(() => {
    setDefaultDaysInput(String(calculatePeriodWorkingDays(salaryPeriod)))
  }, [salaryPeriod])

  // ── State: danh sách nhân viên được tick (bulk-edit) ────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [highlightEmployeeId, setHighlightEmployeeId] = useState<number | null>(null)

  useEffect(() => {
    if (!focusEmployeeId || !employees.some((employee) => employee.id === focusEmployeeId)) return
    setHighlightEmployeeId(focusEmployeeId)
    const scrollTimer = window.setTimeout(() => {
      document.getElementById(`salary-employee-${focusEmployeeId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 180)
    const highlightTimer = window.setTimeout(() => setHighlightEmployeeId(null), 6000)
    return () => {
      window.clearTimeout(scrollTimer)
      window.clearTimeout(highlightTimer)
    }
  }, [focusEmployeeId, focusKey, employees])

  const getInput = useCallback((employee: SalaryEmployee): SalaryInput => {
    const base = inputs.find(x => x.employee_id === employee.id)
    const edits = editedInputs[employee.id]
    return mergeInput(base, edits, employee.id, salaryPeriod, employee.employee_type)
  }, [inputs, editedInputs, salaryPeriod])

  // Split employees
  const fulltimeEmps = useMemo(
    () => employees.filter(e => e.employee_type === 'FULLTIME'),
    [employees]
  )
  const probationEmps = useMemo(
    () => employees.filter(e => e.employee_type === 'PROBATION' || e.employee_type === 'INTERN'),
    [employees]
  )

  // Compute all rows
  type RowData = { emp: SalaryEmployee; inp: SalaryInput; calc: ReturnType<typeof computeRow> }

  const standardDays = parseFloat(defaultDaysInput) || 26

  const fulltimeRows = useMemo<RowData[]>(() =>
    fulltimeEmps.map(emp => {
      const inp = getInput(emp)
      return { emp, inp, calc: computeRow(emp, inp, standardDays, salaryPolicy) }
    }), [fulltimeEmps, getInput, standardDays, salaryPolicy]
  )

  const probationRows = useMemo<RowData[]>(() =>
    probationEmps.map(emp => {
      const inp = getInput(emp)
      return { emp, inp, calc: computeRow(emp, inp, standardDays, salaryPolicy) }
    }), [probationEmps, getInput, standardDays, salaryPolicy]
  )

  // Sub-totals
  function calcSubTotal(rows: RowData[]): SubTotalData {
    const st = emptySubTotal()
    for (const { emp, inp, calc } of rows) {
      st.contract_salary     += Number(emp.contract_salary) || 0
      st.actual_salary       += calc.actual_salary
      st.meal_allowance_free += calc.meal_allowance_free
      st.meal_allowance_tax  += calc.meal_allowance_tax
      st.phone_allowance_free+= calc.phone_allowance_free
      st.trans_allowance_tax += calc.trans_allowance_tax
      st.perf_allowance_tax  += inp.perf_allowance_tax
      st.other_income        += inp.other_income
      st.bonus               += inp.bonus
      st.sales_bonus         += inp.sales_bonus ?? 0
      st.bonus_14            += inp.bonus_14 ?? 0
      st.ins_salary          += calc.ins_salary
      st.social_emp          += calc.social_emp
      st.health_emp          += calc.health_emp
      st.unemp_emp           += calc.unemp_emp
      st.total_ins_emp       += calc.total_ins_emp
      st.social_comp         += calc.social_comp
      st.health_comp         += calc.health_comp
      st.unemp_comp          += calc.unemp_comp
      st.total_ins_comp      += calc.total_ins_comp
      st.union_fund_comp     += calc.union_fund_comp
      st.taxable_income      += calc.taxable_income
      st.assessable_income   += calc.assessable_income
      st.pit_tax             += calc.pit_tax
      st.net_salary          += calc.net_salary
      st.union_fee           += calc.union_fee
      st.other_deductions    += inp.other_deductions
      st.pit_refund          += inp.pit_refund
      st.total_transfer      += calc.total_transfer
      st.advance_payment     += inp.advance_payment
      st.final_transfer      += calc.final_transfer
    }
    return st
  }

  const subTotalA = useMemo(() => calcSubTotal(fulltimeRows), [fulltimeRows])
  const subTotalB = useMemo(() => calcSubTotal(probationRows), [probationRows])

  // Grand total = SubTotal A + SubTotal B
  const grandTotal = useMemo<SubTotalData>(() => {
    const g = emptySubTotal()
    const keys = Object.keys(g) as (keyof SubTotalData)[]
    for (const k of keys) {
      ;(g as any)[k] = (subTotalA as any)[k] + (subTotalB as any)[k]
    }
    return g
  }, [subTotalA, subTotalB])

  // ── Áp dụng ngày công mặc định cho toàn bộ nhân viên ───────────────────
  function applyDefaultDays() {
    const days = parseFloat(defaultDaysInput)
    if (isNaN(days) || days < 0) return
    for (const emp of employees) {
      onCellChange(emp.id, 'actual_working_days', days)
    }
  }



  // ── Bulk-edit handler: nếu nhân viên đang được tick, áp cho toàn bộ tick ─
  function handleCellChange(empId: number, field: keyof SalaryInput, value: number) {
    onCellChange(empId, field, value)
    // Nếu nhân viên này đang được tick và có nhân viên khác cũng tick
    if (selectedIds.has(empId) && selectedIds.size > 1) {
      for (const otherId of selectedIds) {
        if (otherId !== empId) {
          onCellChange(otherId, field, value)
        }
      }
    }
  }

  // ── Checkbox helpers ──────────────────────────────────────────────────────
  function toggleSelect(empId: number) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(empId)) {
        next.delete(empId)
      } else {
        next.add(empId)
      }
      return next
    })
  }

  function toggleSelectAll() {
    if (selectedIds.size === employees.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(employees.map(e => e.id)))
    }
  }

  const allSelected = employees.length > 0 && selectedIds.size === employees.length
  const someSelected = selectedIds.size > 0 && selectedIds.size < employees.length

  // ── Render a data row ─────────────────────────────────────────────────────
  function renderRow(row: RowData, idx: number, block: 'A' | 'B') {
    const { emp, inp, calc } = row
    const isSelected = selectedIds.has(emp.id)

    const fieldValue = (key: string): string | number => {
      const inputMap: Record<string, number> = {
        actual_working_days:  inp.actual_working_days,
        perf_allowance_tax:   inp.perf_allowance_tax,
        other_income:         inp.other_income,
        bonus:                inp.bonus,
        sales_bonus:          inp.sales_bonus ?? 0,
        bonus_14:             inp.bonus_14 ?? 0,
        advance_payment:      inp.advance_payment,
        pit_refund:           inp.pit_refund,
        other_deductions:     inp.other_deductions,
      }
      const calcMap: Record<string, number> = {
        meal_allowance_free: calc.meal_allowance_free,
        meal_allowance_tax:  calc.meal_allowance_tax,
        phone_allowance_free:calc.phone_allowance_free,
        trans_allowance_tax: calc.trans_allowance_tax,
        actual_salary:    calc.actual_salary,
        ins_salary:       calc.ins_salary,
        social_emp:       calc.social_emp,
        health_emp:       calc.health_emp,
        unemp_emp:        calc.unemp_emp,
        total_ins_emp:    calc.total_ins_emp,
        social_comp:      calc.social_comp,
        health_comp:      calc.health_comp,
        unemp_comp:       calc.unemp_comp,
        total_ins_comp:   calc.total_ins_comp,
        union_fund_comp:  calc.union_fund_comp,
        taxable_income:   calc.taxable_income,
        assessable_income:calc.assessable_income,
        pit_tax:          calc.pit_tax,
        net_salary:       calc.net_salary,
        union_fee:        calc.union_fee,
        total_transfer:   calc.total_transfer,
        final_transfer:   calc.final_transfer,
        contract_salary:  emp.contract_salary,
      }
      const periodParts = salaryPeriod.split('-')
      const periodStr = periodParts.length === 2 ? `${periodParts[1]}/${periodParts[0]}` : salaryPeriod
      const stringMap: Record<string, string> = {
        account_number:   emp.account_number || '—',
        bank_name:        emp.bank_name || '—',
        bank_branch:      'Chi nhánh chính',
        bank_city:        'HCM',
        transfer_notes:   `Luong thang ${periodStr}`,
      }
      if (inputMap[key] !== undefined) return inputMap[key]
      if (calcMap[key] !== undefined) return calcMap[key]
      if (stringMap[key] !== undefined) return stringMap[key]
      return ''
    }

    const isEditable = (key: string) =>
      ['actual_working_days', 'perf_allowance_tax',
       'other_income','bonus','bonus_14','advance_payment','pit_refund','other_deductions'].includes(key)

    const rowBg = isSelected
      ? '#eff6ff'   // xanh nhạt khi được chọn
      : idx % 2 === 0 ? '#ffffff' : '#f9fafb'

    return (
      <tr
        key={emp.id}
        id={`salary-employee-${emp.id}`}
        style={{
          background: highlightEmployeeId === emp.id ? '#fef3c7' : rowBg,
          outline: highlightEmployeeId === emp.id ? '3px solid #f59e0b' : isSelected ? '2px solid #3b82f6' : 'none',
          scrollMarginTop: 120,
          outlineOffset: -1,
        }}
      >
        {/* Checkbox */}
        <td
          style={{
            width: '28px',
            minWidth: '28px',
            padding: '0',
            textAlign: 'center',
            borderRight: '1px solid #e2e8f0',
            verticalAlign: 'middle',
            ...stickyStyles('__check__', rowBg),
          }}
        >
          <input
            type="checkbox"
            id={`chk-emp-${emp.id}`}
            checked={isSelected}
            onChange={() => toggleSelect(emp.id)}
            style={{
              width: 12,
              height: 12,
              accentColor: '#163b66',
              cursor: 'pointer',
              display: 'inline-block',
              verticalAlign: 'middle',
              margin: 0,
              padding: 0,
              border: 'none',
              borderRadius: 0,
              background: 'transparent',
              boxShadow: 'none',
              transform: 'none',
              transition: 'none',
            }}
            title={isSelected
              ? `${emp.fullname} đang được chọn — thay đổi sẽ áp cho toàn nhóm tick (${selectedIds.size} NV)`
              : `Tick để gộp vào nhóm bulk-edit`
            }
          />
        </td>
        {/* STT */}
        <td
          style={{
            width: '32px',
            minWidth: '32px',
            padding: '4px 2px',
            textAlign: 'center',
            fontSize: 11,
            color: '#64748b',
            borderRight: '1px solid #e2e8f0',
            verticalAlign: 'middle',
            ...stickyStyles('stt', rowBg),
          }}
        >
          {idx + 1}
        </td>
        {/* Ngày công */}
        <td style={{ padding: '3px 4px', borderRight: '1px solid #e2e8f0', width: '70px', minWidth: '70px', ...stickyStyles('actual_working_days', rowBg) }}>
          <input
            type="number"
            step="any"
            value={inp.actual_working_days}
            onChange={e => handleCellChange(emp.id, 'actual_working_days', parseFloat(e.target.value) || 0)}
            className={CL.editable}
            style={{ minWidth: '62px' }}
            title="Sửa: Ngày công"
          />
        </td>
        {/* Họ tên — sticky */}
        <td
          style={{
            padding: '4px 8px', fontSize: 12, fontWeight: 600, color: '#0f172a',
            borderRight: '2px solid #cbd5e1', whiteSpace: 'nowrap',
            width: '160px',
            minWidth: '160px',
            ...stickyStyles('fullname', rowBg),
          }}
        >
          {/* Badge tick nhóm */}
          {isSelected && selectedIds.size > 1 && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 3,
              marginRight: 6, background: '#dbeafe', color: '#1d4ed8',
              borderRadius: 999, fontSize: 10, fontWeight: 700,
              padding: '1px 6px',
            }}>
              ✦ Nhóm {selectedIds.size}
            </span>
          )}
          {emp.fullname}
          <span style={{ display: 'block', fontSize: 10, fontWeight: 400, color: '#94a3b8' }}>
            {block === 'A' ? '● Chính thức' : '○ Thử việc'}
          </span>
        </td>
        {/* NPT */}
        <td style={{ padding: '4px 6px', textAlign: 'center', fontSize: 11, borderRight: '1px solid #e2e8f0', width: '44px', minWidth: '44px' }}>
          {emp.dependents_count}
        </td>
        {/* Vị trí */}
        <td style={{ padding: '4px 8px', fontSize: 11, color: '#475569', borderRight: '1px solid #e2e8f0', whiteSpace: 'nowrap', maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis', width: '100px', minWidth: '100px' }}>
          {emp.position || '—'}
        </td>

        {/* Numeric & Info columns */}
        {ALL_COLS.slice(INFO_COL_SPAN).map(col => {
          const v = fieldValue(col.key)
          const editable = isEditable(col.key)
          // Disable BH columns for PROBATION
          const forcedZero = block === 'B' && ['ins_salary','social_emp','health_emp','unemp_emp','total_ins_emp','social_comp','health_comp','unemp_comp','total_ins_comp','union_fund_comp','union_fee'].includes(col.key)

          let isStackedCell = emp.is_mid_month_change && (col.key === 'contract_salary' || col.key === 'actual_salary');
          
          let actual_salary_old = 0;
          let actual_salary_new = 0;
          if (col.key === 'actual_salary' && emp.is_mid_month_change) {
            const actual_val = typeof v === 'number' ? v : 0;
            const ratio = Math.min(1.0, inp.actual_working_days / (standardDays || 26));
            const total_days = (emp.prorated_days_old || 0) + (emp.prorated_days_new || 0);
            if (total_days > 0) {
              const old_base = ((emp.prorated_old_salary || 0) * (emp.prorated_days_old || 0)) / total_days;
              actual_salary_old = Math.round(old_base * ratio);
              actual_salary_new = actual_val - actual_salary_old;
            }
          }

          return (
            <td key={col.key} style={{ padding: '3px 4px', borderRight: '1px solid #e2e8f0', width: `${col.w}px`, minWidth: `${col.w}px` }}>
              {col.key === 'other_income_evidence' ? (
                <button
                  type="button"
                  onClick={() => onOpenOtherIncomeEvidence(emp, inp)}
                  className="h-8 w-full rounded-lg border border-slate-300 bg-slate-50 px-2 text-[11px] font-semibold text-slate-800 transition hover:border-slate-400 hover:bg-white focus:outline-none focus:ring-2 focus:ring-slate-300"
                  title={inp.other_income_document_name
                    ? `Xem hoặc thay chứng từ: ${inp.other_income_document_name}`
                    : 'Nhập lý do và tải chứng từ cho Thu nhập khác'}
                >
                  {inp.other_income_document_name ? '📎 Đã tải' : '＋ Tải tệp'}
                </button>
              ) : editable && !forcedZero ? (
                <VndInput
                  value={typeof v === 'number' ? v : 0}
                  onValueChange={value => handleCellChange(emp.id, col.key as keyof SalaryInput, value)}
                  className={CL.editable}
                  style={{ minWidth: `${col.w - 8}px` }}
                  title={`Sửa: ${col.label}`}
                />
              ) : (
                <div className="relative group flex items-center justify-end w-full">
                  {!isStackedCell && (
                    <input
                      readOnly
                      disabled
                      value={forcedZero ? '0' : typeof v === 'number' ? fmt(v) : v}
                      className={CL.formula}
                      style={{
                        minWidth: `${col.w - 8}px`,
                        color: col.key === 'final_transfer' ? '#059669'
                          : col.key === 'pit_tax' ? '#dc2626'
                          : col.key === 'net_salary' ? '#1d4ed8'
                          : col.key === 'total_ins_emp' ? '#7c3aed'
                          : typeof v === 'string' ? '#475569' : '#374151',
                        textAlign: typeof v === 'string' ? 'left' : 'right'
                      }}
                      title={`Công thức tự động/Thông tin: ${col.label}`}
                    />
                  )}
                  {col.key === 'contract_salary' && emp.is_mid_month_change && (
                    <div className="flex flex-col w-full text-right gap-[1px]">
                      <div className="relative group/old w-full text-[10px] leading-tight text-slate-500 font-medium line-through">
                        {fmt(emp.prorated_old_salary || 0)}
                      </div>
                      <div className="relative group/new w-full text-[11px] leading-tight text-emerald-600 font-bold border-t border-slate-200/50 pt-[1px]">
                        {fmt(emp.prorated_new_salary || 0)}
                        <div className="absolute bottom-full right-0 mb-1 hidden group-hover/new:block z-50 w-auto whitespace-nowrap bg-emerald-800 text-white text-[10px] rounded px-3 py-1.5 shadow-lg pointer-events-none">
                          Ngày biến động: {formatDateStr(emp.mid_month_effective_date)}
                        </div>
                      </div>
                    </div>
                  )}
                  {col.key === 'actual_salary' && emp.is_mid_month_change && (
                    <div className="flex flex-col w-full text-right gap-[1px]">
                      <div className="relative group/oldact w-full text-[10px] leading-tight text-slate-500 font-medium">
                        {fmt(actual_salary_old)}
                        <div className="absolute bottom-full right-0 mb-1 hidden group-hover/oldact:block z-50 w-auto whitespace-nowrap bg-slate-800 text-white text-[10px] rounded px-3 py-1.5 shadow-lg pointer-events-none text-left">
                          <span className="block text-[9px] text-slate-400 mb-0.5 uppercase tracking-wider">Mức lương cũ:</span>
                          Từ {getMonthBounds(salaryPeriod).start} đến {getDayBefore(emp.mid_month_effective_date)}
                        </div>
                      </div>
                      <div className="relative group/newact w-full text-[11px] leading-tight text-emerald-600 font-bold border-t border-slate-200/50 pt-[1px]">
                        {fmt(actual_salary_new)}
                        <div className="absolute bottom-full right-0 mb-1 hidden group-hover/newact:block z-50 w-auto whitespace-nowrap bg-emerald-800 text-white text-[10px] rounded px-3 py-1.5 shadow-lg pointer-events-none text-left">
                          <span className="block text-[9px] text-emerald-400/80 mb-0.5 uppercase tracking-wider">Mức lương mới:</span>
                          Từ {formatDateStr(emp.mid_month_effective_date)} đến {getMonthBounds(salaryPeriod).end}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </td>
          )
        })}
      </tr>
    )
  }

  // ─── Column total width ───────────────────────────────────────────────────
  const totalWidth = ALL_COLS.reduce((s, c) => s + c.w, 0) + 20

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-[250px] h-auto w-full" style={{ fontFamily: 'Roboto, Arial, sans-serif', display: 'flex', flexDirection: 'column', gap: 0, minWidth: 0 }}>
      <style>{`
        /* Reset min-width of inputs inside the salary table to prevent overflow and overlapping */
        .salary-grid-table td input {
          min-width: 0 !important;
        }

        /* Keep the matrix in one bounded workspace with its own scrollbars. */
        #root .salary-grid-scroll-region {
          position: relative !important;
          height: clamp(420px, 62vh, 720px) !important;
          min-height: 360px !important;
          max-height: calc(100vh - 250px) !important;
          overflow-x: auto !important;
          overflow-y: scroll !important;
          overscroll-behavior: contain;
          scrollbar-gutter: stable both-edges;
          scrollbar-width: thin;
          scrollbar-color: #94a3b8 #f1f5f9;
        }

        #root .salary-grid-scroll-region::-webkit-scrollbar {
          width: 10px;
          height: 10px;
        }

        #root .salary-grid-scroll-region::-webkit-scrollbar-track {
          background: #f1f5f9;
          border-radius: 999px;
        }

        #root .salary-grid-scroll-region::-webkit-scrollbar-thumb {
          background: #94a3b8;
          border: 2px solid #f1f5f9;
          border-radius: 999px;
        }

        #root .salary-grid-scroll-region::-webkit-scrollbar-thumb:hover {
          background: #64748b;
        }

        @media (max-height: 700px) {
          #root .salary-grid-scroll-region {
            height: calc(100vh - 220px) !important;
            min-height: 300px !important;
          }
        }
      `}</style>

      {/* ── Toolbar ── */}
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
          background: '#ffffff', borderRadius: '16px 16px 0 0',
          border: '1px solid #e2e8f0', borderBottom: 'none',
          padding: '8px 14px',
        }}
      >
        {/* Legend */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10, color: '#64748b' }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: '#fff2cc', border: '1px solid #f59e0b', display: 'inline-block', flexShrink: 0 }} />
            Ô nhập tay
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10, color: '#64748b' }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: '#f5f5f5', border: '1px solid #d1d5db', display: 'inline-block', flexShrink: 0 }} />
            Công thức tự động
          </span>
        </div>

        {/* Divider */}
        <span style={{ width: 1, height: 20, background: '#e2e8f0', flexShrink: 0 }} />

        {/* ── Ngày công mặc định — compact inline ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: '#166534', whiteSpace: 'nowrap' }}>🗓 Ngày công:</span>
          <input
            id="salary-default-days"
            type="number"
            min={0}
            max={31}
            step={0.5}
            value={defaultDaysInput}
            onChange={e => setDefaultDaysInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') applyDefaultDays() }}
            style={{
              width: 70, height: 28, borderRadius: 6,
              border: '1px solid #86efac', background: '#f0fdf4',
              padding: '0 6px', fontSize: 12, fontWeight: 700,
              color: '#166534', outline: 'none', textAlign: 'center',
              fontFamily: 'inherit',
            }}
            title="Nhập ngày công mặc định rồi bấm Áp dụng (hoặc Enter)"
          />
          <button
            type="button"
            onClick={applyDefaultDays}
            style={{
              height: 28, padding: '0 10px', borderRadius: 6,
              background: '#16a34a', color: '#ffffff',
              border: 'none', cursor: 'pointer',
              fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
              whiteSpace: 'nowrap',
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = '#15803d' }}
            onMouseLeave={e => { e.currentTarget.style.background = '#16a34a' }}
            title="Áp ngày công này cho toàn bộ nhân viên"
          >
            Áp tất cả
          </button>
        </div>



        {/* ── Bulk-select badge (chỉ hiện khi có tick) ── */}
        {selectedIds.size > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 1, height: 20, background: '#e2e8f0', flexShrink: 0 }} />
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              background: '#eff6ff', border: '1px solid #93c5fd',
              borderRadius: 999, padding: '2px 10px',
              fontSize: 11, fontWeight: 700, color: '#1d4ed8',
            }}>
              ✦ {selectedIds.size} NV — sửa 1 → áp cả nhóm
            </span>
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              style={{
                height: 24, padding: '0 8px', borderRadius: 5,
                background: '#dbeafe', color: '#1d4ed8',
                border: '1px solid #93c5fd', cursor: 'pointer',
                fontSize: 10, fontWeight: 700, fontFamily: 'inherit',
              }}
            >
              Bỏ chọn
            </button>
          </div>
        )}

        {toolbarActions && (
          <>
            <span className="salary-grid-toolbar-divider" aria-hidden="true" />
            <div className="salary-grid-toolbar-actions">
              {toolbarActions}
            </div>
          </>
        )}

        {/* Keep the right-side status group aligned when no custom actions are supplied. */}
        {!toolbarActions && <div style={{ flex: 1 }} />}

        {/* Group: Lock Icon + Badges (Right Aligned) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Nút Khóa / Mở khóa bảng lương (Icon only) */}
          <button
            type="button"
            onClick={onToggleLock}
            title={isSalaryLocked ? 'Bảng lương đang khóa. Nhấp để mở khóa.' : 'Nhấp để khóa bảng lương'}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 18,
              padding: '0 4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'transform 0.1s ease',
              opacity: isSalaryLocked ? 1 : 0.6,
            }}
            onMouseDown={e => { e.currentTarget.style.transform = 'scale(0.9)' }}
            onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)' }}
            onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)' }}
          >
            {isSalaryLocked ? '🔒' : '🔓'}
          </button>

          {/* Employee count badges */}
          <span style={{ fontSize: 10, background: '#dbeafe', color: '#1d4ed8', borderRadius: 999, padding: '2px 8px', fontWeight: 600 }}>
            Chính thức: {fulltimeEmps.length} NV
          </span>
          <span style={{ fontSize: 10, background: '#fef3c7', color: '#92400e', borderRadius: 999, padding: '2px 8px', fontWeight: 600 }}>
            Thử việc: {probationEmps.length} NV
          </span>
        </div>

      </div>

      {/* ── Scrollable grid container ── */}
      <div
        className="salary-grid-scroll-region w-full border border-slate-200 rounded-b-2xl bg-white shadow-sm"
        style={{
          width: '100%',
          maxWidth: '100%',
        }}
      >
        <table
          className="salary-grid-table"
          style={{
            width: `${totalWidth}px`, minWidth: '100%', borderCollapse: 'collapse',
            tableLayout: 'fixed',
            fontSize: 12, fontFamily: 'Roboto, Arial, sans-serif',
          }}
        >
          {/* ── COLGROUP for width hints ── */}
          <colgroup>
            {ALL_COLS.map(c => <col key={c.key} width={c.w} style={{ width: `${c.w}px`, minWidth: `${c.w}px` }} />)}
          </colgroup>

          {/* ── HEADER ── */}
          <thead style={{ position: 'sticky', top: 0, zIndex: 10 }}>
            {/* Group header row */}
            <tr>
              {COL_GROUPS.map(g => (
                <th
                   key={g.label}
                   colSpan={g.cols.length}
                   style={{
                     background: g.bg, color: g.color,
                     padding: '7px 8px', textAlign: 'center',
                     fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
                     textTransform: 'uppercase', whiteSpace: 'nowrap',
                     borderRight: '2px solid rgba(255,255,255,0.25)',
                     ...(g.sticky ? { 
                       position: 'sticky' as const, 
                       left: 0, 
                       zIndex: 11,
                       borderRight: '2px solid #cbd5e1',
                       boxShadow: '3px 0 6px -2px rgba(0,0,0,0.1)'
                     } : {}),
                   }}
                >
                  {g.label}
                </th>
              ))}
            </tr>
            {/* Column name row */}
            <tr style={{ background: '#f1f5f9' }}>
              {ALL_COLS.map(col => {
                const sStyle = stickyStyles(col.key, '#f1f5f9', true)
                return (
                  <th
                    key={col.key}
                    style={{
                      padding: '5px 4px', textAlign: 'center',
                      fontSize: 9, fontWeight: 700, color: '#334155',
                      letterSpacing: '0.06em', textTransform: 'uppercase',
                      borderRight: '1px solid #e2e8f0', whiteSpace: 'nowrap',
                      borderBottom: '2px solid #cbd5e1',
                      width: `${col.w}px`,
                      minWidth: `${col.w}px`,
                      ...sStyle,
                    }}
                  >
                  {/* Select-all checkbox */}
                  {col.key === '__check__' ? (
                    <input
                      type="checkbox"
                      id="chk-select-all"
                      checked={allSelected}
                      ref={el => { if (el) el.indeterminate = someSelected }}
                      onChange={toggleSelectAll}
                      style={{
                        width: 12,
                        height: 12,
                        accentColor: '#163b66',
                        cursor: 'pointer',
                        verticalAlign: 'middle',
                        margin: 0,
                        padding: 0,
                        border: 'none',
                        borderRadius: 0,
                        background: 'transparent',
                        boxShadow: 'none',
                        transform: 'none',
                        transition: 'none',
                      }}
                      title={allSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả nhân viên'}
                    />
                  ) : (
                    <>
                      {/* Editable indicator dot */}
                      {(col as any).editable && (
                        <span style={{ display: 'block', width: 5, height: 5, borderRadius: '50%', background: '#f59e0b', margin: '0 auto 2px' }} />
                      )}
                      {col.label}
                    </>
                  )}
                </th>
              )
            })}
            </tr>
          </thead>

          <tbody>
            {/* ════ KHỐI A: CHÍNH THỨC ════ */}
            <tr>
              <td
                colSpan={ALL_COLS.length}
                style={{
                  background: '#1d4ed8', color: '#ffffff',
                  padding: '6px 14px', fontSize: 11, fontWeight: 700,
                  letterSpacing: '0.12em', textTransform: 'uppercase',
                }}
              >
                🅐  KHỐI A — NHÂN VIÊN CHÍNH THỨC (FULL-TIME) &nbsp;·&nbsp; {fulltimeEmps.length} người
              </td>
            </tr>

            {fulltimeEmps.length === 0 ? (
              <tr>
                <td colSpan={ALL_COLS.length} style={{ textAlign: 'center', padding: 32, color: '#94a3b8', fontSize: 13 }}>
                  Chưa có nhân viên chính thức trong tháng này.
                </td>
              </tr>
            ) : (
              fulltimeRows.map((row, i) => renderRow(row, i, 'A'))
            )}

            {/* Sub-total A */}
            <SubTotalRow label="▶ CỘNG KHỐI A — Nhân viên chính thức" data={subTotalA} />

            {/* ════ KHỐI B: THỬ VIỆC ════ */}
            <tr>
              <td
                colSpan={ALL_COLS.length}
                style={{
                  background: '#92400e', color: '#fef3c7',
                  padding: '6px 14px', fontSize: 11, fontWeight: 700,
                  letterSpacing: '0.12em', textTransform: 'uppercase',
                  borderTop: '3px solid #ffffff',
                }}
              >
                🅑  KHỐI B — NHÂN VIÊN THỬ VIỆC / HỌC VIỆC (PROBATIONARY) &nbsp;·&nbsp; {probationEmps.length} người
              </td>
            </tr>

            {probationEmps.length === 0 ? (
              <tr>
                <td colSpan={ALL_COLS.length} style={{ textAlign: 'center', padding: 32, color: '#94a3b8', fontSize: 13 }}>
                  Chưa có nhân viên thử việc trong tháng này.
                </td>
              </tr>
            ) : (
              probationRows.map((row, i) => renderRow(row, i, 'B'))
            )}

            {/* Sub-total B */}
            <SubTotalRow label="▶ CỘNG KHỐI B — Nhân viên thử việc" data={subTotalB} />

            {/* ════ GRAND TOTAL ════ */}
            <tr>
              {/* Checkbox & STT */}
              <td
                colSpan={2}
                style={{
                  background: '#0f172a', color: '#f8fafc',
                  padding: '8px 14px', fontSize: 12, fontWeight: 800,
                  borderTop: '3px solid #163b66',
                  textAlign: 'center',
                }}
              >
                —
              </td>
              {/* Ngày công (sticky) */}
              <td
                style={{
                  background: '#0f172a', color: '#f8fafc',
                  padding: '8px 6px', fontSize: 12, fontWeight: 800,
                  borderTop: '3px solid #163b66',
                  position: 'sticky',
                  left: 0,
                  zIndex: 2,
                  textAlign: 'center',
                }}
              >
                —
              </td>
              {/* Họ tên, NPT, Vị trí (sticky) */}
              <td
                colSpan={3}
                style={{
                  background: '#0f172a', color: '#f8fafc',
                  padding: '8px 14px', fontSize: 12, fontWeight: 800,
                  borderTop: '3px solid #163b66',
                  position: 'sticky',
                  left: 70,
                  zIndex: 2,
                  borderRight: '2px solid #cbd5e1',
                  boxShadow: '3px 0 6px -2px rgba(0,0,0,0.1)',
                  textAlign: 'left',
                  textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                }}
              >
                ∑ TỔNG CỘNG HỆ THỐNG (A + B) &nbsp;—&nbsp; {employees.length} nhân viên
              </td>
              {ALL_COLS.slice(INFO_COL_SPAN).map(col => {
                const skipKeys = new Set(['actual_working_days'])
                const numericKeys: Record<string, number> = {
                  contract_salary: grandTotal.contract_salary,
                  actual_salary: grandTotal.actual_salary,
                  meal_allowance_free: grandTotal.meal_allowance_free,
                  meal_allowance_tax: grandTotal.meal_allowance_tax,
                  phone_allowance_free: grandTotal.phone_allowance_free,
                  trans_allowance_tax: grandTotal.trans_allowance_tax,
                  perf_allowance_tax: grandTotal.perf_allowance_tax,
                  other_income: grandTotal.other_income,
                  bonus: grandTotal.bonus,
                  sales_bonus: grandTotal.sales_bonus,
                  bonus_14: grandTotal.bonus_14,
                  ins_salary: grandTotal.ins_salary,
                  social_emp: grandTotal.social_emp,
                  health_emp: grandTotal.health_emp,
                  unemp_emp: grandTotal.unemp_emp,
                  total_ins_emp: grandTotal.total_ins_emp,
                  social_comp: grandTotal.social_comp,
                  health_comp: grandTotal.health_comp,
                  unemp_comp: grandTotal.unemp_comp,
                  total_ins_comp: grandTotal.total_ins_comp,
                  union_fund_comp: grandTotal.union_fund_comp,
                  taxable_income: grandTotal.taxable_income,
                  assessable_income: grandTotal.assessable_income,
                  pit_tax: grandTotal.pit_tax,
                  net_salary: grandTotal.net_salary,
                  union_fee: grandTotal.union_fee,
                  other_deductions: grandTotal.other_deductions,
                  pit_refund: grandTotal.pit_refund,
                  total_transfer: grandTotal.total_transfer,
                  advance_payment: grandTotal.advance_payment,
                  final_transfer: grandTotal.final_transfer,
                }
                const textColor =
                  col.key === 'final_transfer' ? '#34d399'
                  : col.key === 'pit_tax'       ? '#fca5a5'
                  : col.key === 'net_salary'    ? '#93c5fd'
                  : '#e2e8f0'
                return (
                  <td
                    key={col.key}
                    style={{
                      background: '#0f172a', color: textColor,
                      padding: '7px 6px', fontSize: 11, fontWeight: 800,
                      textAlign: 'right', whiteSpace: 'nowrap',
                      borderTop: '3px solid #163b66',
                      borderRight: '1px solid #1e293b',
                      width: `${col.w}px`,
                      minWidth: `${col.w}px`,
                    }}
                  >
                    {skipKeys.has(col.key) ? '—' : numericKeys[col.key] !== undefined ? fmt(numericKeys[col.key]) : '—'}
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>

        {/* Empty state */}
        {employees.length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#94a3b8' }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#64748b' }}>Chưa có dữ liệu bảng lương</p>
            <p style={{ fontSize: 12 }}>Nhấn "Tải dữ liệu" hoặc chọn tháng lương khác để bắt đầu.</p>
          </div>
        )}
      </div>

      {/* ── Bottom note ── */}
      <div
        style={{
          display: 'flex', gap: 20, flexWrap: 'wrap',
          padding: '10px 4px', fontSize: 11, color: '#64748b',
        }}
      >
        <span>
          🔵 <b>BHXH NLĐ</b>: 8% &nbsp;|&nbsp;
          <b>BHYT</b>: 1.5% &nbsp;|&nbsp;
          <b>BHTN</b>: 1% &nbsp;=&nbsp; <b>10.5% tổng NLĐ chịu</b>
        </span>
        <span>
          🟣 <b>BHXH DN</b>: 17.5% &nbsp;|&nbsp;
          <b>BHYT</b>: 3% &nbsp;|&nbsp;
          <b>BHTN</b>: 1% &nbsp;+&nbsp;
          <b>KP CĐ</b>: 2% &nbsp;=&nbsp; <b>23.5% chi phí DN</b>
        </span>
        <span>
          🔴 <b>Giảm trừ BT</b>: 15,500,000đ &nbsp;|&nbsp;
          <b>NPT</b>: 6,200,000đ/người
        </span>
        <span style={{ marginLeft: 'auto', fontStyle: 'italic' }}>
          ✦ Thuế TNCN thử việc: 10% cào bằng nếu TN ≥ 2,000,000đ
        </span>
      </div>
    </div>
  )
}
