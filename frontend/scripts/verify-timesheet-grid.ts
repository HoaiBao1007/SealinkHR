import assert from 'node:assert/strict'

import {
  filterTimesheetRows,
  paginateTimesheetRows,
  type TimesheetSearchableRow,
} from '../src/shared/utils/timesheetGrid.ts'

const rows: TimesheetSearchableRow[] = Array.from({ length: 25 }, (_, index) => ({
  employee_id: index + 1,
  machine_employee_id: `M${String(index + 1).padStart(3, '0')}`,
  full_name: index === 20 ? 'Nguyễn Thị Tìm Kiếm' : `Nhân viên ${index + 1}`,
  department_name: index % 2 === 0 ? 'IT' : 'SALE LOCAL',
  days: { '2026-05-01': index === 20 ? 'CT' : index % 3 === 0 ? 'Ro' : 'X' },
  abnormal_days: index % 3 === 0 ? 1 : 0,
  total_late_minutes: 0,
  total_early_minutes: 0,
  total_absent_days: 0,
  total_work_days: 22,
  unpaid_leave_days: 0,
  paid_leave_days: 0,
  previous_paid_leave_balance: 0,
  current_month_paid_leave_credit: 1,
  remaining_paid_leave_days: 1,
}))

const allPages = paginateTimesheetRows(rows, 1)
assert.equal(allPages.rows.length, 10)
assert.equal(allPages.totalPages, 3)

const globalSearch = filterTimesheetRows(rows, {
  search: 'nguyen thi tim kiem',
  department: 'all',
  abnormal: 'all',
  symbol: 'all',
})
assert.equal(globalSearch.length, 1)
assert.equal(globalSearch[0].employee_id, 21)
assert.equal(paginateTimesheetRows(globalSearch, 3).currentPage, 1)

assert.ok(filterTimesheetRows(rows, { search: '', department: 'IT', abnormal: 'normal', symbol: 'X' }).length > 0)
assert.deepEqual(
  filterTimesheetRows(rows, { search: '', department: 'all', abnormal: 'all', symbol: 'CT' }).map((row) => row.employee_id),
  [21],
)

console.log('Timesheet grid search, filters, and pagination verified.')
