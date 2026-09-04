import assert from 'node:assert/strict'
import {
  EMPLOYEE_DIRECTORY_PAGE_SIZE,
  filterEmployeeDirectoryRows,
  paginateEmployeeDirectoryRows,
} from '../src/shared/utils/employeeDirectory.ts'

const rows = Array.from({ length: 24 }, (_, index) => ({
  machine_employee_id: String(index + 1),
  employee_code: `SL${String(index + 1).padStart(3, '0')}`,
  full_name: index === 21 ? 'Nguyễn Thị Thực Tập' : `Nhân viên ${index + 1}`,
  notion_name: index === 14 ? 'DOCS - PARADO QUANG' : null,
  department_name: index % 2 === 0 ? 'IT' : 'SALE',
  employee_type: index === 21 ? 'TRAINEE' : 'FULLTIME',
  is_active: index !== 23,
}))

const searched = filterEmployeeDirectoryRows(rows, {
  search: 'nguyen thi thuc tap',
  department: 'all',
  status: 'all',
  employeeType: 'all',
})
assert.equal(searched.length, 1, 'Tìm kiếm phải bỏ dấu và chạy trên toàn bộ dữ liệu')
assert.equal(searched[0].machine_employee_id, '22', 'Tìm kiếm phải thấy bản ghi nằm ngoài trang đầu')

const filtered = filterEmployeeDirectoryRows(rows, {
  search: '',
  department: 'IT',
  status: 'active',
  employeeType: 'FULLTIME',
})
assert.equal(filtered.length, 12, 'Các filter phải được kết hợp trước khi phân trang')

const pageOne = paginateEmployeeDirectoryRows(rows, 1)
const pageThree = paginateEmployeeDirectoryRows(rows, 3)
assert.equal(pageOne.rows.length, EMPLOYEE_DIRECTORY_PAGE_SIZE)
assert.equal(pageThree.rows.length, 4)
assert.equal(pageThree.currentPage, 3)
assert.equal(paginateEmployeeDirectoryRows(rows.slice(0, 3), 9).currentPage, 1, 'Trang vượt phạm vi phải tự hiệu chỉnh')

console.log('Employee directory filter/pagination checks passed.')
