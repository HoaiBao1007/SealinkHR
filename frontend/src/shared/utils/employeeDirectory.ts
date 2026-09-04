export type EmployeeDirectoryStatusFilter = 'all' | 'active' | 'inactive'

export type EmployeeDirectoryFilters = {
  search: string
  department: string
  status: EmployeeDirectoryStatusFilter
  employeeType: string
}

export const EMPLOYEE_DIRECTORY_PAGE_SIZE = 10

type EmployeeDirectoryRow = {
  machine_employee_id?: string | null
  full_name?: string | null
  notion_name?: string | null
  department_code?: string | null
  department_name?: string | null
  employee_code?: string | null
  position?: string | null
  employee_type?: string | null
  is_active?: boolean
  status?: string | null
  account_number?: string | null
  bank_name?: string | null
  tax_code?: string | null
  phone_number?: string | null
  company_phone_number?: string | null
  social_insurance_number?: string | null
  pvi_insurance?: string | null
  health_insurance_number?: string | null
  company_email?: string | null
  personal_email?: string | null
  notes?: string | null
  username?: string | null
  account_role?: string | null
}

const normalizeSearchText = (value: unknown) => String(value ?? '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi')
  .trim()

const typeSearchAliases: Record<string, string> = {
  FULLTIME: 'chính thức fulltime',
  PROBATION: 'thử việc probation',
  INTERN: 'học việc intern',
  TRAINEE: 'thực tập trainee',
}

export function filterEmployeeDirectoryRows<T extends EmployeeDirectoryRow>(
  rows: T[],
  filters: EmployeeDirectoryFilters,
): T[] {
  const search = normalizeSearchText(filters.search)

  return rows.filter((row) => {
    const department = row.department_name || row.department_code || 'N/A'
    if (filters.department !== 'all' && department !== filters.department) return false
    if (filters.status === 'active' && !row.is_active) return false
    if (filters.status === 'inactive' && row.is_active) return false
    if (filters.employeeType !== 'all' && row.employee_type !== filters.employeeType) return false
    if (!search) return true

    const typeAlias = typeSearchAliases[String(row.employee_type || '').toUpperCase()] || ''
    const statusAlias = row.is_active ? 'đang hoạt động active' : 'đã nghỉ việc inactive'
    const haystack = [
      row.machine_employee_id,
      row.full_name,
      row.notion_name,
      row.department_code,
      row.department_name,
      row.employee_code,
      row.position,
      row.employee_type,
      typeAlias,
      row.status,
      statusAlias,
      row.account_number,
      row.bank_name,
      row.tax_code,
      row.phone_number,
      row.company_phone_number,
      row.social_insurance_number,
      row.pvi_insurance,
      row.health_insurance_number,
      row.company_email,
      row.personal_email,
      row.notes,
      row.username,
      row.account_role,
    ].map(normalizeSearchText).join(' ')

    return haystack.includes(search)
  })
}

export function paginateEmployeeDirectoryRows<T>(rows: T[], requestedPage: number, pageSize = EMPLOYEE_DIRECTORY_PAGE_SIZE) {
  const safePageSize = Math.max(1, pageSize)
  const totalPages = Math.max(1, Math.ceil(rows.length / safePageSize))
  const currentPage = Math.min(Math.max(1, requestedPage), totalPages)
  const startIndex = (currentPage - 1) * safePageSize

  return {
    rows: rows.slice(startIndex, startIndex + safePageSize),
    currentPage,
    totalPages,
    startIndex,
  }
}
