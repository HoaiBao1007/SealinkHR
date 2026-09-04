export const TIMESHEET_PAGE_SIZE = 10

export type TimesheetAbnormalFilter = 'all' | 'abnormal' | 'normal'

export type TimesheetSearchableRow = {
  employee_id: number
  machine_employee_id: string
  full_name: string
  department_name: string | null
  days: Record<string, string>
  abnormal_days: number
  total_late_minutes: number
  total_early_minutes: number
  total_absent_days: number
  total_work_days: number
  total_payroll_days: number
  unpaid_leave_days: number
  paid_leave_days: number
  previous_paid_leave_balance: number
  current_month_paid_leave_credit: number
  remaining_paid_leave_days: number
}

function normalizeSearchText(value: unknown): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('vi')
    .replace(/\s+/g, ' ')
    .trim()
}

function rowSearchText(row: TimesheetSearchableRow): string {
  const abnormalLabel = row.abnormal_days > 0 ? 'có bất thường' : 'không bất thường bình thường'
  return normalizeSearchText([
    row.employee_id,
    row.machine_employee_id,
    row.full_name,
    row.department_name,
    abnormalLabel,
    ...Object.keys(row.days),
    ...Object.values(row.days),
    row.abnormal_days,
    row.total_late_minutes,
    row.total_early_minutes,
    row.total_absent_days,
    row.total_work_days,
    row.total_payroll_days,
    row.unpaid_leave_days,
    row.paid_leave_days,
    row.previous_paid_leave_balance,
    row.current_month_paid_leave_credit,
    row.remaining_paid_leave_days,
  ].join(' '))
}

export function filterTimesheetRows<T extends TimesheetSearchableRow>(
  rows: T[],
  options: {
    search: string
    department: string
    abnormal: TimesheetAbnormalFilter
    symbol: string
  },
): T[] {
  const search = normalizeSearchText(options.search)
  return rows.filter((row) => {
    if (search && !rowSearchText(row).includes(search)) return false
    if (options.department !== 'all' && (row.department_name ?? 'N/A') !== options.department) return false
    if (options.abnormal === 'abnormal' && row.abnormal_days <= 0) return false
    if (options.abnormal === 'normal' && row.abnormal_days > 0) return false
    if (options.symbol !== 'all' && !Object.values(row.days).includes(options.symbol)) return false
    return true
  })
}

export function paginateTimesheetRows<T>(rows: T[], requestedPage: number, pageSize = TIMESHEET_PAGE_SIZE) {
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize))
  const currentPage = Math.min(Math.max(1, requestedPage), totalPages)
  const startIndex = (currentPage - 1) * pageSize
  return {
    rows: rows.slice(startIndex, startIndex + pageSize),
    currentPage,
    totalPages,
    startIndex,
  }
}
