import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { cake_salary, DEFAULT_SALARY_POLICY, type SalaryPolicy, type SalaryTaxBracket } from './shared/utils/salary'
import { EMPLOYEE_CONTRACT_OPTIONS, isFixedTermEmployeeContract } from './shared/employeeContract'
import { formatVnd } from './shared/utils/currency'
import * as XLSX from 'xlsx'
import './App.css'
import { EnterpriseShell } from './modules/layout/EnterpriseShell'
import type { EnterpriseShellItem } from './modules/layout/EnterpriseShell'
import type { NotificationItem } from './modules/notifications/NotificationWidget'
import type { CommissionNotificationFocus } from './modules/commission/CommissionTab'
import { EmployeeBlockPreview } from './modules/import-data/EmployeeBlockPreview'
import logoSealink from './assets/LOGO SEALINK.jpg'
import Login3DGlobe from './components/Login3DGlobe'
import { LockWarningModal } from './components/LockWarningModal'
import { useConfirmDialog } from './shared/ui/ConfirmDialog'
import { LoadingState } from './shared/ui'
import { VndInput } from './shared/ui/VndInput'
import { BrandedDateInput } from './shared/ui/BrandedDateInput'
import { AppIcon } from './shared/ui/AppIcon'
import { closestMonthPeriod, currentMonthPeriod, MonthYearSelect } from './shared/ui/MonthYearSelect'
import {
  filterTimesheetRows,
  paginateTimesheetRows,
  TIMESHEET_PAGE_SIZE,
  type TimesheetAbnormalFilter,
} from './shared/utils/timesheetGrid'
import {
  EMPLOYEE_DIRECTORY_PAGE_SIZE,
  filterEmployeeDirectoryRows,
  paginateEmployeeDirectoryRows,
  type EmployeeDirectoryStatusFilter,
} from './shared/utils/employeeDirectory'
import { TimeOffDashboardForm } from './modules/time-off/TimeOffDashboardForm'
import {
  HrDashboard,
  HrEmployees,
  ItOperations,
  PersonalAccount,
  PersonalDashboard,
  PersonalAttendanceGrid,
} from './modules/roles/RolePortals'
import { OnboardingPublic } from './modules/onboarding/OnboardingPublic'
import { OffboardingPublic } from './modules/offboarding/OffboardingPublic'
import { notifyDataChanged, subscribeDataChanged, type DataChangedDetail } from './shared/api/dataSync'

const SalaryDataGrid = lazy(() => import('./modules/salary/SalaryDataGrid').then((module) => ({ default: module.SalaryDataGrid })))
const CommissionTab = lazy(() => import('./modules/commission/CommissionTab').then((module) => ({ default: module.CommissionTab })))
const DepartmentTab = lazy(() => import('./modules/departments/DepartmentTab').then((module) => ({ default: module.DepartmentTab })))
const SalaryDecisionsSection = lazy(() => import('./modules/employees/SalaryDecisionsSection').then((module) => ({ default: module.SalaryDecisionsSection })))
const HolidayConfigurator = lazy(() => import('./modules/timesheet/HolidayConfigurator').then((module) => ({ default: module.HolidayConfigurator })))
const TimeOffManagement = lazy(() => import('./modules/time-off/TimeOffManagement').then((module) => ({ default: module.TimeOffManagement })))
const OnboardingAdmin = lazy(() => import('./modules/onboarding/OnboardingAdmin').then((module) => ({ default: module.OnboardingAdmin })))
const OffboardingAdmin = lazy(() => import('./modules/offboarding/OffboardingAdmin').then((module) => ({ default: module.OffboardingAdmin })))

type SalaryApprovalStatus = 'DRAFT' | 'CONFIRMED' | 'PENDING_APPROVAL' | 'APPROVED'

type SalaryApprovalState = {
  period: string
  status: SalaryApprovalStatus
  confirmed_by_user_id: number | null
  confirmed_at: string | null
  requested_by_user_id: number | null
  requested_at: string | null
  approved_by_user_id: number | null
  approved_at: string | null
}

type SalaryPeriodItem = {
  period: string
  is_published: boolean
  input_count: number
  approval_status: SalaryApprovalStatus
}

type SalaryPolicyForm = SalaryPolicy & {
  name: string
  effective_from: string
  legal_basis: string
  note: string
}

type SalaryPolicyVndField = keyof Pick<
  SalaryPolicy,
  | 'common_minimum_wage'
  | 'social_health_salary_cap'
  | 'regional_minimum_wage_i'
  | 'regional_minimum_wage_ii'
  | 'regional_minimum_wage_iii'
  | 'regional_minimum_wage_iv'
  | 'union_employee_cap'
  | 'personal_deduction'
  | 'dependent_deduction'
  | 'probation_withholding_threshold'
>

const SALARY_POLICY_VND_FIELDS: SalaryPolicyVndField[] = [
  'common_minimum_wage',
  'social_health_salary_cap',
  'regional_minimum_wage_i',
  'regional_minimum_wage_ii',
  'regional_minimum_wage_iii',
  'regional_minimum_wage_iv',
  'union_employee_cap',
  'personal_deduction',
  'dependent_deduction',
  'probation_withholding_threshold',
]

const REMEMBER_LOGIN_PREFERENCE_KEY = 'sealink.remember-login'
const REMEMBER_LOGIN_USERNAME_KEY = 'sealink.remembered-username'

function usernameFromCompanyEmail(email: string): string {
  const localPart = email.trim().split('@', 1)[0] || ''
  return localPart
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]/g, '')
}

function secureRandomIndex(length: number): number {
  if (length <= 0) return 0
  const randomValue = new Uint32Array(1)
  window.crypto.getRandomValues(randomValue)
  return randomValue[0] % length
}

function generateEmployeePassword(): string {
  const groups = [
    'ABCDEFGHJKLMNPQRSTUVWXYZ',
    'abcdefghijkmnopqrstuvwxyz',
    '23456789',
    '!@#$%&*?',
  ]
  const allCharacters = groups.join('')
  const characters = groups.map((group) => group[secureRandomIndex(group.length)])
  while (characters.length < 12) characters.push(allCharacters[secureRandomIndex(allCharacters.length)])
  for (let index = characters.length - 1; index > 0; index -= 1) {
    const swapIndex = secureRandomIndex(index + 1)
    ;[characters[index], characters[swapIndex]] = [characters[swapIndex], characters[index]]
  }
  return characters.join('')
}

async function copyTextToClipboard(value: string): Promise<boolean> {
  if (!value) return false
  try {
    await navigator.clipboard.writeText(value)
    return true
  } catch {
    const temporaryInput = document.createElement('textarea')
    temporaryInput.value = value
    temporaryInput.setAttribute('readonly', '')
    temporaryInput.style.position = 'fixed'
    temporaryInput.style.opacity = '0'
    document.body.appendChild(temporaryInput)
    temporaryInput.select()
    const copied = document.execCommand('copy')
    temporaryInput.remove()
    return copied
  }
}

type EmployeePasswordFieldProps = {
  value: string
  onChange: (value: string) => void
  onNotice: (message: string) => void
  placeholder: string
  inputClassName?: string
}

function EmployeePasswordField({ value, onChange, onNotice, placeholder, inputClassName = '' }: EmployeePasswordFieldProps) {
  const copyPassword = async (password: string, generated = false) => {
    const copied = await copyTextToClipboard(password)
    onNotice(copied
      ? generated ? 'Đã tạo và sao chép mật khẩu 12 ký tự.' : 'Đã sao chép mật khẩu.'
      : 'Không thể sao chép tự động. Hãy chọn và sao chép mật khẩu thủ công.')
  }

  return (
    <span className="employee-password-field">
      <input
        type="password"
        className={inputClassName}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="new-password"
      />
      <span className="employee-password-actions">
        <button
          type="button"
          title="Tạo và sao chép mật khẩu ngẫu nhiên 12 ký tự"
          aria-label="Tạo và sao chép mật khẩu ngẫu nhiên 12 ký tự"
          onClick={() => {
            const password = generateEmployeePassword()
            onChange(password)
            void copyPassword(password, true)
          }}
        >
          <AppIcon name="bolt" size={15} />
        </button>
        <button
          type="button"
          title="Sao chép mật khẩu"
          aria-label="Sao chép mật khẩu"
          disabled={!value}
          onClick={() => void copyPassword(value)}
        >
          <AppIcon name="copy" size={15} />
        </button>
      </span>
    </span>
  )
}

/**
 * Currency fields are formatted while typing. Browser input can temporarily
 * produce strings such as "2.7770" after the fourth digit; that must mean
 * 27,770 VND, never the decimal number 2.777. Keep only whole-number digits.
 */
function parseSalaryPolicyVndInput(value: string): number | undefined {
  const digits = value.replace(/\D/g, '')
  if (!digits) return undefined
  const amount = Number(digits)
  return Number.isSafeInteger(amount) ? amount : undefined
}

function buildSalaryPolicyForm(period: string, policy?: Partial<SalaryPolicy>): SalaryPolicyForm {
  const source = policy || DEFAULT_SALARY_POLICY
  return {
    ...DEFAULT_SALARY_POLICY,
    ...source,
    name: String(source.name || `Chính sách lương ${period}`),
    effective_from: String(source.effective_from || `${period}-01`),
    legal_basis: String((source as any).legal_basis || ''),
    note: String((source as any).note || ''),
    pit_brackets: (source.pit_brackets || DEFAULT_SALARY_POLICY.pit_brackets).map((item) => ({ ...item })),
  }
}


// type TabKey = 'dashboard' | 'import' | 'employees' | 'timesheets' | 'export' | 'salary'

const navigationTabs: EnterpriseShellItem[] = [
  {
    key: 'dashboard',
    label: 'Dashboard',
    title: 'Tổng quan điều phối',
    description: 'Theo dõi KPI, xu hướng công và tình trạng toàn hệ thống trong một màn hình quản trị tập trung.',
    icon: 'dashboard',
  },
  {
    key: 'employees',
    label: 'Nhân sự',
    title: 'Danh mục nhân sự',
    description: 'Quản lý hồ sơ nhân viên, map mã máy chấm công và cập nhật thông tin phòng ban trong hệ thống.',
    icon: 'employees',
  },
  {
    key: 'departments',
    label: 'Phòng ban',
    title: 'Cơ cấu tổ chức',
    description: 'Quản lý danh sách các phòng ban, thiết lập trưởng phòng và gán nhân viên vào phòng ban tương ứng.',
    icon: 'departments',
  },
  {
    key: 'onboarding',
    label: 'Onboarding',
    title: 'Onboarding nhân viên mới',
    description: 'Tùy chỉnh biểu mẫu công khai, duyệt hồ sơ tạm và tạo nhân viên chính thức sau phê duyệt.',
    icon: 'employees',
  },
  {
    key: 'offboarding',
    label: 'Offboarding',
    title: 'Nghỉ việc & bàn giao',
    description: 'Gửi và xử lý đơn xin nghỉ việc theo luồng Trưởng bộ phận, Nhân sự và Giám đốc.',
    icon: 'leave',
  },
  {
    key: 'timesheets',
    label: 'Bảng công công ty',
    title: 'Bảng công và phê duyệt',
    description: 'Tra cứu tháng công 23 → 22, phê duyệt bảng công, theo dõi bất thường và quản lý lịch sử override.',
    icon: 'timesheets',
  },
  {
    key: 'time-off',
    label: 'Time Off',
    title: 'Time Off Management',
    description: 'Gửi, phê duyệt và theo dõi lịch nghỉ theo cơ cấu Manager trên website.',
    icon: 'timesheets',
  },
  {
    key: 'export',
    label: 'Xuất báo cáo',
    title: 'Xuất báo cáo HR',
    description: 'Xuất bảng công theo mẫu HR hoặc lấy báo cáo trực tiếp từ workbook upload mà không thay đổi logic dữ liệu hiện tại.',
    icon: 'export',
  },
  {
    key: 'salary',
    label: 'Bảng lương công ty',
    title: 'Tính toán & Quản lý lương',
    description: 'Nhập tay biến động lương theo tháng, quản lý cấu hình lương hợp đồng và xuất báo cáo lương Sealink tự động.',
    icon: 'salary' as any,
  },
]

const personalAccountNavigationTab: EnterpriseShellItem = {
  key: 'my-account',
  label: 'Thông tin cá nhân',
  title: 'Thông tin cá nhân',
  description: 'Cập nhật email, số điện thoại, tên đăng nhập và bảo mật tài khoản của bạn.',
  icon: 'employees',
}

const hrNavigationTabs: EnterpriseShellItem[] = [
  { key: 'dashboard', label: 'Dashboard', title: 'Tổng quan nhân sự', description: 'Theo dõi nhân sự và tình trạng bảng công, không hiển thị dữ liệu lương hoặc bonus.', icon: 'dashboard' },
  { key: 'employees', label: 'Nhân sự', title: 'Hồ sơ nhân sự', description: 'Thêm và chỉnh sửa hồ sơ nhân viên trong phạm vi vận hành, không có trường tài chính.', icon: 'employees' },
  { key: 'departments', label: 'Phòng ban', title: 'Cơ cấu tổ chức', description: 'Quản lý phòng ban, sơ đồ tổ chức và phân bổ nhân sự.', icon: 'departments' },
  { key: 'onboarding', label: 'Onboarding', title: 'Onboarding nhân viên mới', description: 'Tùy chỉnh biểu mẫu công khai, duyệt hồ sơ tạm và tạo nhân viên chính thức sau phê duyệt.', icon: 'employees' },
  { key: 'offboarding', label: 'Offboarding', title: 'Nghỉ việc & bàn giao', description: 'Tiếp nhận và xử lý đơn xin nghỉ việc theo quy trình nội bộ.', icon: 'leave' },
  { key: 'timesheets', label: 'Bảng công công ty', title: 'Bảng công và phê duyệt', description: 'Import, rà soát, chỉnh sửa và phê duyệt dữ liệu chấm công.', icon: 'timesheets' },
  { key: 'time-off', label: 'Time Off', title: 'Time Off Management', description: 'Quản lý yêu cầu nghỉ, duyệt theo Manager và lịch nghỉ chung.', icon: 'timesheets' },
  { key: 'export', label: 'Xuất báo cáo', title: 'Xuất báo cáo HR', description: 'Xuất báo cáo chấm công và KPI nhân sự.', icon: 'export' },
  { key: 'my-payslip', label: 'Phiếu lương của tôi', title: 'Phiếu Lương Cá Nhân', description: 'Xem phiếu lương của chính bạn theo từng tháng đã phát hành.', icon: 'salary' },
  { key: 'my-attendance', label: 'Chấm công của tôi', title: 'Chấm Công Cá Nhân', description: 'Đối chiếu ngày và ký hiệu chấm công của chính bạn.', icon: 'timesheets' },
  personalAccountNavigationTab,
]

const personalNavigationTabs: EnterpriseShellItem[] = [
  { key: 'personal-dashboard', label: 'Dashboard', title: 'Tổng quan cá nhân', description: 'Tóm tắt hồ sơ, phiếu lương và chấm công của bạn.', icon: 'dashboard' },
  { key: 'time-off', label: 'Time Off', title: 'Time Off Management', description: 'Gửi yêu cầu nghỉ, theo dõi trạng thái và xem lịch nghỉ đã duyệt.', icon: 'timesheets' },
  { key: 'my-payslip', label: 'Phiếu lương cá nhân', title: 'Phiếu Lương Cá Nhân', description: 'Xem chi tiết thu nhập, phụ cấp, bảo hiểm và thuế TNCN theo từng tháng lương.', icon: 'salary' },
  { key: 'my-attendance', label: 'Chấm công của tôi', title: 'Chấm Công Cá Nhân', description: 'Đối chiếu ngày và ký hiệu chấm công theo dạng lưới cô đọng.', icon: 'timesheets' },
  { key: 'my-held-bonuses', label: 'Bonus đang giữ', title: 'JOB Bonus Đang Giữ', description: 'Theo dõi JOB đang giữ bonus và gửi yêu cầu kế toán duyệt chi trả.', icon: 'salary' },
  personalAccountNavigationTab,
]

const chiefAccountantNavigationTabs: EnterpriseShellItem[] = [
  ...navigationTabs,
  { key: 'my-payslip', label: 'Phiếu lương của tôi', title: 'Phiếu Lương Cá Nhân', description: 'Xem phiếu lương của chính bạn theo từng tháng đã phát hành.', icon: 'salary' },
  { key: 'my-attendance', label: 'Chấm công của tôi', title: 'Chấm Công Cá Nhân', description: 'Đối chiếu ngày và ký hiệu chấm công của chính bạn.', icon: 'timesheets' },
  personalAccountNavigationTab,
]

const isBusinessAdminRole = (role?: string | null) => role === 'ADMIN' || role === 'DIRECTOR' || role === 'IT_ADMIN'

const itNavigationTabs: EnterpriseShellItem[] = [
  ...navigationTabs,
  { key: 'it-backups', label: 'Backup dữ liệu', title: 'Backup Cơ Sở Dữ Liệu', description: 'Theo dõi backup tự động hằng ngày và tạo bản backup có checksum.', icon: 'export' },
  { key: 'it-audit', label: 'Nhật ký hệ thống', title: 'Audit Hệ Thống', description: 'Tra cứu lịch sử thao tác ở chế độ chỉ đọc.', icon: 'timesheets' },
  personalAccountNavigationTab,
]

type Employee = {
  id: number
  machine_employee_id: string
  full_name: string
  notion_name: string | null
  department_code: string | null
  department_name: string | null
  department_id: number | null
  annual_leave_quota: number
  annual_leave_used: number
  paid_leave_balance: number
  unpaid_leave_balance: number
  is_active: boolean
  status: string
  employee_code: string | null
  position: string | null
  contract_salary: number
  meal_allowance: number
  phone_allowance: number
  trans_allowance: number
  other_allowance: number
  employee_type: string
  dependents_count: number
  account_number: string | null
  bank_name: string | null
  tax_code: string | null
  phone_number: string | null
  company_phone_number: string | null
  social_insurance_number: string | null
  pvi_insurance: string | null
  health_insurance_number: string | null
  company_email: string | null
  personal_email: string | null
  notes: string | null
  cccd_url: string[] | null
  contract_url: string[] | null
  username?: string | null
  account_role?: string | null
  access_role?: string
  access_role_reason?: string
  start_date: string | null
  contract_type: string | null
  contract_sign_date: string | null
  contract_start_date: string | null
  contract_end_date: string | null
  resignation_period: string | null
  last_working_date: string | null
  last_pay_date: string | null
  bonus_coefficient?: number
}

function employeeWithDerivedUsername(employee: Employee): Employee {
  // The API username is authoritative when a login account already exists.
  // For employees without an account, the email prefix is only a UI suggestion;
  // it must not make an unrelated profile update look like account creation.
  if (employee.username) return employee
  const username = usernameFromCompanyEmail(employee.company_email || '')
  return username ? { ...employee, username } : employee
}

type EmployeeFormState = {
  machine_employee_id: string
  full_name: string
  notion_name: string
  department_code: string
  department_name: string
  department_id: number | null
  annual_leave_quota: string
  employee_code: string
  position: string
  contract_salary: string
  meal_allowance: string
  phone_allowance: string
  trans_allowance: string
  other_allowance: string
  employee_type: string
  dependents_count: string
  account_number: string
  bank_name: string
  tax_code: string
  phone_number: string
  company_phone_number: string
  social_insurance_number: string
  pvi_insurance: string
  health_insurance_number: string
  company_email: string
  personal_email: string
  notes: string
  username: string
  password: string
  start_date: string
  contract_type: string
  contract_sign_date: string
  contract_start_date: string
  contract_end_date: string
  resignation_period: string
  last_working_date: string
  last_pay_date: string
  bonus_coefficient: string
}

type EmployeeType = 'FULLTIME' | 'PROBATION' | 'INTERN' | 'TRAINEE'

const ACCESS_ROLE_LABELS: Record<string, string> = {
  ADMIN: 'Kế toán trưởng · ADMIN',
  DIRECTOR: 'GIÁM ĐỐC · DIRECTOR',
  HR_ADMIN: 'Admin vận hành · HR_ADMIN',
  IT_ADMIN: 'Quản trị hệ thống cấp cao · IT_ADMIN',
  USER: 'Nhân viên · USER',
}

const inferAccessRolePreview = (
  departmentName?: string | null,
  position?: string | null,
  employeeName?: string | null,
) => {
  const normalize = (value?: string | null) => String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
  const department = normalize(departmentName)
  const title = normalize(position)
  const employee = normalize(employeeName)
  if (employee === 'ton that trung kien' || employee === 'to to van') return 'DIRECTOR'
  const isItAdminBranch = department === 'it' || department.includes('it admin')
  if (!isItAdminBranch) return 'USER'
  if (title === 'admin' || title.startsWith('admin ')) return 'HR_ADMIN'
  return 'USER'
}

const EMPLOYEE_TYPE_LABELS: Record<EmployeeType, string> = {
  FULLTIME: 'Chính thức',
  PROBATION: 'Thử việc',
  INTERN: 'Học việc',
  TRAINEE: 'Thực tập',
}

const getContractAllowanceDefaults = (employeeType: string) => (
  employeeType === 'FULLTIME'
    ? {
        meal_allowance: '1200000',
        phone_allowance: '2000000',
        trans_allowance: '2000000',
        other_allowance: '0',
      }
    : {
        meal_allowance: '0',
        phone_allowance: '0',
        trans_allowance: '0',
        other_allowance: '0',
      }
)

const getMonthlyAllowanceDefaults = (employeeType: string) => (
  employeeType === 'FULLTIME'
    ? {
        meal_allowance_free: '1200000',
        meal_allowance_tax: '0',
        phone_allowance_free: '2000000',
        trans_allowance_tax: '2000000',
        perf_allowance_tax: '0',
      }
    : {
        meal_allowance_free: '0',
        meal_allowance_tax: '0',
        phone_allowance_free: '0',
        trans_allowance_tax: '0',
        perf_allowance_tax: '0',
      }
)

const getEmployeeTypeLabel = (employeeType?: string) =>
  EMPLOYEE_TYPE_LABELS[employeeType as EmployeeType] ?? 'Thử việc'

const EMPTY_EMPLOYEE_FORM: EmployeeFormState = {
  machine_employee_id: '',
  full_name: '',
  notion_name: '',
  department_code: '',
  department_name: '',
  department_id: null,
  annual_leave_quota: '12',
  employee_code: '',
  position: '',
  contract_salary: '0',
  meal_allowance: '1200000',
  phone_allowance: '2000000',
  trans_allowance: '2000000',
  other_allowance: '0',
  employee_type: 'FULLTIME',
  dependents_count: '0',
  account_number: '',
  bank_name: '',
  tax_code: '',
  phone_number: '',
  company_phone_number: '',
  social_insurance_number: '',
  pvi_insurance: '',
  health_insurance_number: '',
  company_email: '',
  personal_email: '',
  notes: '',
  username: '',
  password: '',
  start_date: '',
  contract_type: '',
  contract_sign_date: '',
  contract_start_date: '',
  contract_end_date: '',
  resignation_period: '',
  last_working_date: '',
  last_pay_date: '',
  bonus_coefficient: '0',
}

const MONTHLY_SALARY_INPUT_FIELDS = [
  'actual_working_days', 'meal_allowance_free', 'meal_allowance_tax',
  'phone_allowance_free', 'trans_allowance_tax', 'perf_allowance_tax',
  'other_income', 'bonus', 'bonus_14', 'advance_payment', 'pit_refund',
  'other_deductions',
] as const

function salaryInputRestorePayload(input: any, employeeId: number, salaryPeriod: string) {
  const payload: Record<string, any> = { employee_id: employeeId, salary_period: salaryPeriod }
  for (const field of MONTHLY_SALARY_INPUT_FIELDS) payload[field] = Number(input?.[field] ?? 0)
  return payload
}

type Department = {
  id: number
  name: string
  manager_id: number | null
  manager: EmployeeMinimal | null
  employees: EmployeeMinimal[]
  current_bonus_rules?: Array<{ rate: number }>
}

type EmployeeMinimal = {
  id: number
  full_name: string
  notion_name: string | null
  position: string | null
}

function numberToVietnameseWords(num: number): string {
  if (num === 0) return "Không đồng"
  
  const units = ["", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
  const places = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"]
  
  function readGroup3(n: number, showZeroTen: boolean): string {
    let res = ""
    const h = Math.floor(n / 100)
    const t = Math.floor((n % 100) / 10)
    const u = n % 10
    
    if (h > 0 || showZeroTen) {
      res += units[h] + " trăm "
    }
    
    if (t > 0) {
      if (t === 1) res += "mười "
      else res += units[t] + " mươi "
    } else if (h > 0 && u > 0) {
      res += "lẻ "
    }
    
    if (u > 0) {
      if (u === 1 && t > 1) res += "mốt "
      else if (u === 5 && t > 0) res += "lăm "
      else res += units[u] + " "
    }
    
    return res
  }
  
  let strNum = Math.floor(num).toString()
  let groups: number[] = []
  while (strNum.length > 0) {
    let chunk = strNum.slice(-3)
    groups.push(parseInt(chunk, 10))
    strNum = strNum.slice(0, -3)
  }
  
  let words = ""
  for (let i = groups.length - 1; i >= 0; i--) {
    let g = groups[i]
    if (g > 0) {
      const showZeroTen = i < groups.length - 1
      let gText = readGroup3(g, showZeroTen)
      words += gText + places[i] + " "
    }
  }
  
  words = words.trim()
  if (!words) return "Không đồng"
  
  let capitalized = words.charAt(0).toUpperCase() + words.slice(1)
  capitalized = capitalized.replace(/\s+/g, ' ')
  return capitalized + " đồng chẵn."
}

type ImportPreviewRow = Record<string, unknown>

type AttendanceJsonDetail = {
  scheduled_to_work: boolean
  check_in: string | null
  check_out: string | null
  status: string
  late_minutes: number
  attendance_symbol?: string | null
  notion_submitted?: boolean
  notion_status?: string | null
}

type AttendanceJsonEmployee = {
  employee_id: string
  employee_name: string
  department: string
  summary_from_machine: {
    total_late_minutes: number
    total_absent_days: number
  }
  attendance_details: Record<string, AttendanceJsonDetail>
}

type AttendanceValidationSummaryRow = {
  computed_total_late_minutes: number
  computed_total_absent_days: number
  machine_total_late_minutes: number
  machine_total_absent_days: number
  late_minutes_match: boolean
  absent_days_match: boolean
}


type OverrideLog = {
  audit_id: number
  employee_id: string
  employee_name: string
  work_date: string
  old_symbol: string
  new_symbol: string
  reason: string
  changed_by_user_id: string
  changed_by_name: string
  changed_at: string
}

type TimesheetGridRow = {
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

type TimesheetDayColumn = {
  key: string
  day_number: number
  weekday_label: string
  is_weekend: boolean
}

type TimesheetGridResponse = {
  is_locked?: boolean
  day_keys: string[]
  day_columns: TimesheetDayColumn[]
  rows: TimesheetGridRow[]
}

type TimesheetPeriodRange = {
  period: string
  start: string
  end: string
}

function formatLocalDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function shiftMonthPeriod(period: string, offset: number): string {
  const [year, month] = period.split('-').map(Number)
  const shifted = new Date(year, month - 1 + offset, 1)
  return currentMonthPeriod(shifted)
}

function timesheetRangeForPeriod(period: string): TimesheetPeriodRange {
  const [year, month] = period.split('-').map(Number)
  const end = new Date(year, month - 1, 22)
  const start = new Date(year, month - 2, 23)
  return {
    period,
    start: formatLocalDate(start),
    end: formatLocalDate(end),
  }
}

const DEFAULT_TIMESHEET_RANGE = timesheetRangeForPeriod(shiftMonthPeriod(currentMonthPeriod(), -1))

type DashboardTrendPoint = {
  work_date: string
  present_count: number
  absent_count: number
  abnormal_count: number
}

type DashboardKpi = {
  period_start: string
  period_end: string
  total_employees: number
  active_employees: number
  present_days: number
  absent_days: number
  business_trip_days: number
  paid_leave_days: number
  unpaid_leave_days: number
  total_late_minutes: number
  total_early_minutes: number
  abnormal_days: number
  symbol_counts: Record<string, number>
  trend: DashboardTrendPoint[]
}

type ImportType = 'checkin' | 'abnormal'
type ImportMode = 'auto' | 'custom'

type WorkbookColumnOption = {
  index: number
  label: string
  display_label?: string
}

type RawCheckinDayEntry = {
  day_label: string
  time_values: string[]
  attendance_symbol?: string | null
}

type RawCheckinEmployeeBlock = {
  employee_id: string
  employee_name: string
  department_name: string
  day_entries: RawCheckinDayEntry[]
  row_start_index: number
  row_end_index: number
}

function normalizeMachineEmployeeId(value: string | null | undefined): string {
  return String(value ?? '').trim().replace(/^[#＃]+\s*/, '').replace(/\.0$/, '')
}

function mergeEmployeeCheckinBlocks(
  blocks: RawCheckinEmployeeBlock[],
  employees: Employee[],
): RawCheckinEmployeeBlock[] {
  const merged = new Map<string, RawCheckinEmployeeBlock>()
  const timeOrder = (value: string) => {
    const match = value.replace(/\*/g, '').match(/(?:[01]?\d|2[0-3]):[0-5]\d/)
    if (!match) return Number.MAX_SAFE_INTEGER
    const [hour, minute] = match[0].split(':').map(Number)
    return hour * 60 + minute
  }

  for (const block of blocks) {
    const normalizedBlockId = normalizeMachineEmployeeId(block.employee_id)
    const matchedEmployee = employees.find(
      (employee) => normalizeMachineEmployeeId(employee.machine_employee_id) === normalizedBlockId,
    )
    const canonicalId = normalizeMachineEmployeeId(matchedEmployee?.machine_employee_id || normalizedBlockId)
    const current = merged.get(canonicalId)
    if (!current) {
      merged.set(canonicalId, {
        ...block,
        employee_id: canonicalId,
        employee_name: matchedEmployee?.full_name || block.employee_name,
        department_name: matchedEmployee?.department_name || block.department_name,
        day_entries: block.day_entries.map((entry) => ({ ...entry, time_values: [...entry.time_values] })),
      })
      continue
    }

    current.row_start_index = Math.min(current.row_start_index, block.row_start_index)
    current.row_end_index = Math.max(current.row_end_index, block.row_end_index)
    const dayMap = new Map(current.day_entries.map((entry) => [entry.day_label, entry]))
    for (const entry of block.day_entries) {
      const existing = dayMap.get(entry.day_label)
      if (!existing) {
        const copied = { ...entry, time_values: [...entry.time_values] }
        current.day_entries.push(copied)
        dayMap.set(entry.day_label, copied)
        continue
      }
      existing.time_values = Array.from(new Set([...existing.time_values, ...entry.time_values]))
        .sort((left, right) => timeOrder(left) - timeOrder(right))
    }
    current.day_entries.sort((left, right) => Number(left.day_label) - Number(right.day_label))
  }

  return Array.from(merged.values())
}

type WorkbookSheetInspection = {
  sheet_name: string
  header_row_index: number
  columns: WorkbookColumnOption[]
  suggested_mapping: Record<string, number>
  match_score: number
  has_time_columns: boolean
  sample_rows: Record<string, string>[]
  raw_rows: Record<string, string>[]
  data_row_count: number
  employee_blocks: RawCheckinEmployeeBlock[]
  period_start?: string | null
  period_end?: string | null
}

type ImportTableColumn = {
  key: string
  label: string
}

type SheetInspectAttemptResult = {
  sheet: WorkbookSheetInspection | null
  loadedDetailedRows: boolean
  errorMessage: string | null
}

type WorkbookInspection = {
  import_type: ImportType
  sheets: WorkbookSheetInspection[]
  recommended_sheet_name: string | null
  recommended_header_row_index: number | null
  recommended_mapping: Record<string, number>
}

type ImportFieldConfig = {
  required: string[]
  optional: string[]
  labels: Record<string, string>
}

const IMPORT_FIELD_CONFIG: Record<ImportType, ImportFieldConfig> = {
  checkin: {
    required: ['ID', 'Ten', 'Ngay'],
    optional: ['Moc gio', 'In', 'Out'],
    labels: {
      ID: 'Mã nhân viên / Machine ID',
      Ten: 'Họ tên',
      Ngay: 'Ngày làm việc',
      'Moc gio': 'Mốc giờ / Scan Data',
      In: 'Giờ vào',
      Out: 'Giờ ra',
    },
  },
  abnormal: {
    required: ['ID', 'Ten', 'P.Ban', 'Ngay', 'Thoi gian tre', 'Thoi gian som', 'Ghi chu'],
    optional: [],
    labels: {
      ID: 'Mã nhân viên / Machine ID',
      Ten: 'Họ tên',
      'P.Ban': 'Phòng ban',
      Ngay: 'Ngày làm việc',
      'Thoi gian tre': 'Đi muộn',
      'Thoi gian som': 'Về sớm',
      'Ghi chu': 'Ghi chú',
    },
  },
}

const IMPORT_PREVIEW_LABELS: Record<string, string> = {
  machine_employee_id: 'Machine ID',
  full_name: 'Họ tên',
  department_name: 'Phòng ban',
  work_date: 'Ngày làm việc',
  raw_time_values: 'Dữ liệu quẹt gốc',
  check_in_time: 'Giờ vào',
  check_out_time: 'Giờ ra',
  missing_flag: 'Lỗi chấm công',
  missing_reason: 'Nguyên nhân lỗi',
  late_minutes: 'Đi muộn',
  early_minutes: 'Về sớm',
  note: 'Ghi chú',
  period_start: 'Ngày bắt đầu',
  period_end: 'Ngày kết thúc',
}

function getImportFields(importType: ImportType): string[] {
  return [...IMPORT_FIELD_CONFIG[importType].required, ...IMPORT_FIELD_CONFIG[importType].optional]
}

function getRequiredImportFields(importType: ImportType): string[] {
  return IMPORT_FIELD_CONFIG[importType].required
}

function normalizeSheetName(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function pickDefaultInspectionSheet(payload: WorkbookInspection, importType: ImportType): WorkbookSheetInspection | null {
  if (payload.recommended_sheet_name) {
    return payload.sheets.find((sheet) => sheet.sheet_name === payload.recommended_sheet_name) ?? null
  }

  if (importType === 'checkin') {
    const sheetNameMatches = [
      'ho so check in',
      'ho so checkin',
      'bao cao check in',
      'bao cao checkin',
    ]
    const preferredByName = payload.sheets.find((sheet) => {
      const normalizedName = normalizeSheetName(sheet.sheet_name)
      return sheetNameMatches.some((pattern) => normalizedName.includes(pattern))
    })
    if (preferredByName) {
      return preferredByName
    }

    return payload.sheets.find((sheet) => sheet.has_time_columns) ?? payload.sheets[0] ?? null
  }

  return payload.sheets[0] ?? null
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

function collectPreviewColumnKeys(rows: ImportPreviewRow[]): string[] {
  const keys: string[] = []
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!keys.includes(key)) {
        keys.push(key)
      }
    }
  }
  return keys
}

function formatImportPreviewColumnLabel(key: string): string {
  if (IMPORT_PREVIEW_LABELS[key]) {
    return IMPORT_PREVIEW_LABELS[key]
  }
  return key
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function normalizeImportFilterText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function getImportStickyColumnClass(columnIndex: number): string {
  if (columnIndex === 0) {
    return 'is-sticky-first'
  }
  if (columnIndex === 1) {
    return 'is-sticky-second'
  }
  return ''
}

function matchesNormalizedFilter(source: string, filterValue: string): boolean {
  if (!filterValue.trim()) {
    return true
  }
  return normalizeImportFilterText(source).includes(normalizeImportFilterText(filterValue))
}

function formatImportCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }
  if (typeof value === 'boolean') {
    return value ? 'Có' : 'Không'
  }
  return String(value)
}

function renderImportCellValue(value: unknown): React.ReactNode {
  const text = formatImportCellValue(value)
  if (text.toLowerCase().includes('bỏ lỡ') || text.toLowerCase().includes('bo lo')) {
    return <span className="text-rose-500 font-medium">{text}</span>
  }
  return text
}

function normalizeTimesheetSymbol(value: string | null | undefined): string {
  return String(value ?? '').trim().toUpperCase()
}

function getTimesheetSymbolNode(symbol: string) {
  if (!symbol) return null
  const text = normalizeTimesheetSymbol(symbol)
  let pillClass = 'inline-flex items-center justify-center whitespace-nowrap '
  if (text === 'X') {
    pillClass += 'px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200'
  } else if (text === 'P') {
    pillClass += 'px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200'
  } else if (text === 'X/P' || text === 'P/X') {
    pillClass += 'px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200'
  } else if (text === 'RO' || text === 'V' || text === 'O') {
    pillClass += 'px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200'
  } else if (text === 'CT') {
    pillClass += 'px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200'
  } else if (text === 'P/RO' || text === 'RO/P' || text === 'P/V' || text === 'V/P') {
    pillClass += 'px-2 py-0.5 rounded-full text-xs font-semibold bg-orange-50 text-orange-700 border border-orange-200'
  } else {
    pillClass += 'px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-50 text-gray-700 border border-gray-200'
  }
  return <span className={pillClass}>{symbol}</span>
}

function getTimesheetDayCellClass(value: string | null | undefined): string {
  switch (normalizeTimesheetSymbol(value)) {
    case 'X':
      return 'symbol-work'
    case 'P':
      return 'symbol-paid-leave'
    case 'O':
    case 'V':
    case 'RO':
      return 'symbol-absent'
    case 'CT':
      return 'symbol-business-trip'
    case 'X/P':
      return 'symbol-half-work-leave'
    case 'P/X':
      return 'symbol-half-leave-work'
    case 'P/V':
    case 'P/RO':
    case 'X/RO':
      return 'symbol-half-leave-absent'
    case 'V/P':
    case 'RO/P':
    case 'RO/X':
      return 'symbol-half-absent-leave'
    default:
      return ''
  }
}

const TimesheetCell = ({
  row,
  column,
  loadTimesheets,
  setMessage,
  setLoading,
  apiRequest,
  loadOverrideHistory,
  timesheetIsLocked,
}: {
  row: any
  column: any
  loadTimesheets: () => Promise<void>
  setMessage: (msg: string) => void
  setLoading: (loading: boolean) => void
  apiRequest: (path: string, init?: RequestInit) => Promise<any>
  loadOverrideHistory: (options?: { silent?: boolean }) => Promise<void>
  timesheetIsLocked: boolean
}) => {
  const [showReasonModal, setShowReasonModal] = useState(false)
  const [popoverStyle, setPopoverStyle] = useState<{ top: number; left: number; isAbove: boolean } | null>(null)
  const daySymbol = row.days[column.key] || ''
  const overrideReason = row.override_reasons?.[column.key]
  const [pendingSymbol, setPendingSymbol] = useState(daySymbol)
  const [customReason, setCustomReason] = useState('Chỉnh sửa quên chấm công')
  const [showLockWarningModal, setShowLockWarningModal] = useState(false)

  const handleSave = async (overrideLock: boolean = false) => {
    const finalReason = customReason.trim() || 'Chỉnh sửa quên chấm công'
    try {
      setLoading(true)
      setShowReasonModal(false)
      setShowLockWarningModal(false)
      
      const res = await apiRequest('/api/attendance/override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_id: Number(row.employee_id),
          work_date: column.key,
          new_symbol: pendingSymbol,
          reason: finalReason,
          new_check_in: null,
          new_check_out: null,
          override_lock: overrideLock
        }),
      })
      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.detail || 'Lỗi khi cập nhật')
      }
      await loadTimesheets()
      await loadOverrideHistory({ silent: true })
      setMessage(`Cập nhật thành công cho NV #${row.employee_id} ngày ${column.key}`)
    } catch (err) {
      setMessage(`Lỗi khi cập nhật: ${(err as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  const dayCellClass = [
    'timesheet-day-cell',
    column.is_weekend ? 'is-weekend' : '',
    getTimesheetDayCellClass(daySymbol),
    'relative group cursor-pointer hover:ring-2 hover:ring-inset hover:ring-blue-400',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <>
      <td 
      className={dayCellClass} 
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect()
        const popoverHeight = 220
        const spaceBelow = window.innerHeight - rect.bottom
        const isAbove = spaceBelow < popoverHeight && rect.top > popoverHeight

        setPopoverStyle({
          top: isAbove ? rect.top - 8 : rect.bottom + 8,
          left: rect.left + rect.width / 2,
          isAbove
        })
        setPendingSymbol(daySymbol)
        setCustomReason(overrideReason || 'Chỉnh sửa quên chấm công')
        setShowReasonModal(true)
      }}
      title={overrideReason ? `Đã chỉnh sửa: ${overrideReason}` : "Nhấp vào để ghi đè công/chỉnh sửa lý do"}
    >
      <div className="flex items-center justify-center w-full h-full relative">
        {overrideReason && (
          <div 
            className="absolute top-[2px] left-[2px] w-1.5 h-1.5 bg-orange-500 rounded-full" 
            title={`Lý do: ${overrideReason}`}
          ></div>
        )}
        {getTimesheetSymbolNode(daySymbol)}
        
        {/* Nút Edit nhỏ xíu hiện ra khi hover */}
        <div className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 transition-opacity bg-blue-500 text-white p-[1px] rounded-bl-sm">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-2 w-2" viewBox="0 0 20 20" fill="currentColor">
            <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
          </svg>
        </div>
      </div>

      {showReasonModal && popoverStyle && (
        <>
          {/* Lớp nền trong suốt để click ra ngoài thì đóng Popover */}
          <div 
            className="fixed inset-0 z-[80]" 
            onClick={(e) => {
              e.stopPropagation()
              setShowReasonModal(false)
            }}
          />
          
          {/* Popover nhỏ nhắn dùng fixed để hoàn toàn không ảnh hưởng tới layout bảng */}
          <div 
            className="fixed z-[90] w-56 bg-white rounded-xl p-3 shadow-[0_10px_40px_-10px_rgba(0,0,0,0.3)] border border-slate-200 text-left cursor-default animate-[fadeIn_0.1s_ease-out]" 
            style={{ 
              top: popoverStyle.top, 
              left: popoverStyle.left, 
              transform: popoverStyle.isAbove ? 'translate(-50%, -100%)' : 'translate(-50%, 0)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Mũi tên nhỏ */}
            <div 
              className={`absolute left-1/2 -translate-x-1/2 w-3 h-3 bg-white border-slate-200 rotate-45 ${
                popoverStyle.isAbove ? 'bottom-[-6px] border-b border-r' : 'top-[-6px] border-l border-t'
              }`} 
            />
            
            <div className="relative z-10">
              <h3 className="text-xs font-extrabold text-slate-800 border-b border-slate-100 pb-1.5 mb-2">Chỉnh sửa ngày {column.key}</h3>
              
              <div className="space-y-2">
                <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                  Ký hiệu công
                  <select
                    value={pendingSymbol}
                    onChange={(e) => setPendingSymbol(e.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 font-semibold"
                  >
                    <option value="">(Trống)</option>
                    <option value="X">X (Làm đủ ngày)</option>
                    <option value="Ro">Ro (Vắng không lương)</option>
                    <option value="P">P (Phép cả ngày)</option>
                    <option value="X/P">X/P (Làm sáng/Phép chiều)</option>
                    <option value="P/X">P/X (Phép sáng/Làm chiều)</option>
                    <option value="X/Ro">X/Ro (Làm sáng/Vắng chiều)</option>
                    <option value="Ro/X">Ro/X (Vắng sáng/Làm chiều)</option>
                    <option value="P/Ro">P/Ro (Phép sáng/Vắng chiều)</option>
                    <option value="Ro/P">Ro/P (Vắng sáng/Phép chiều)</option>
                    <option value="CT">CT (Công tác)</option>
                  </select>
                </label>

                <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                  Lý do ghi đè
                  <input
                    type="text"
                    value={customReason}
                    onChange={(e) => setCustomReason(e.target.value)}
                    placeholder="VD: Quên chấm công..."
                    className="mt-1 block w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    required
                    autoFocus
                  />
                </label>
              </div>

              <div className="mt-3 flex gap-1.5 justify-end">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setShowReasonModal(false)
                  }}
                  className="px-2.5 py-1.5 text-[11px] font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
                >
                  Hủy
                </button>
                <button
                  type="button"
                  onClick={async (e) => {
                    e.stopPropagation()
                    setShowLockWarningModal(true)
                  }}
                  className="px-2.5 py-1.5 text-[11px] font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition"
                >
                  Lưu
                </button>
              </div>
            </div>
          </div>
        </>
        )}
      </td>
      <LockWarningModal
        isOpen={showLockWarningModal}
        isLocked={timesheetIsLocked}
        onConfirm={() => handleSave(timesheetIsLocked)}
        onCancel={() => {
          setShowLockWarningModal(false)
          setShowReasonModal(true)
        }}
      />
    </>
  )
}


function buildSheetInspectionFallback(sheet: WorkbookSheetInspection): WorkbookSheetInspection {
  return {
    ...sheet,
    raw_rows: Array.isArray(sheet.raw_rows) ? sheet.raw_rows : [],
    data_row_count: typeof sheet.data_row_count === 'number' ? sheet.data_row_count : sheet.sample_rows.length,
  }
}

function pickSuggestedImportFilterColumns(columns: ImportTableColumn[]): ImportTableColumn[] {
  const priorities = [
    ['machine employee id', 'machine id', 'ma nhan vien', 'id'],
    ['ho ten', 'ten', 'full name', 'employee name'],
    ['ngay lam viec', 'work date', 'ngay', 'date'],
    ['gio vao', 'check in', 'first in', 'in'],
    ['gio ra', 'check out', 'last out', 'out'],
    ['phong ban', 'department', 'p ban'],
    ['du lieu quet goc', 'moc gio', 'scan data'],
    ['di muon', 'late'],
    ['ve som', 'early'],
    ['ghi chu', 'note'],
  ]

  const selected: ImportTableColumn[] = []
  for (const patterns of priorities) {
    const matchedColumn = columns.find((column) => {
      if (selected.some((item) => item.key === column.key)) {
        return false
      }
      const haystack = `${normalizeImportFilterText(column.label)} ${normalizeImportFilterText(column.key)}`
      return patterns.some((pattern) => haystack.includes(pattern))
    })
    if (matchedColumn) {
      selected.push(matchedColumn)
    }
    if (selected.length >= 6) {
      break
    }
  }

  if (selected.length >= 6) {
    return selected
  }

  for (const column of columns) {
    if (!selected.some((item) => item.key === column.key)) {
      selected.push(column)
    }
    if (selected.length >= 6) {
      break
    }
  }

  return selected
}

type PieChartSlice = {
  label: string
  value: number
  color: string
  formula: string
  description: string
}

function SalaryPieChart({ slices }: { slices: PieChartSlice[] }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0)
  
  const formattedSlices = slices.map((slice, index) => {
    const percentage = total > 0 ? (slice.value / total) * 100 : 0
    const angle = total > 0 ? (slice.value / total) * 360 : 0
    const startAngle = total > 0
      ? slices.slice(0, index).reduce((sum, item) => sum + (item.value / total) * 360, 0)
      : 0
    const endAngle = startAngle + angle
    
    const r = 80
    const cx = 100
    const cy = 100
    
    const x1 = cx + r * Math.cos((startAngle - 90) * Math.PI / 180)
    const y1 = cy + r * Math.sin((startAngle - 90) * Math.PI / 180)
    const x2 = cx + r * Math.cos((endAngle - 90) * Math.PI / 180)
    const y2 = cy + r * Math.sin((endAngle - 90) * Math.PI / 180)
    
    const largeArcFlag = angle > 180 ? 1 : 0
    
    const pathData = total > 0 && angle < 360 
      ? `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArcFlag} 1 ${x2} ${y2} Z`
      : ''
      
    return {
      ...slice,
      percentage,
      pathData,
      isFull: angle >= 360 || total === 0
    }
  })

  function formatCurrency(val: number) {
    if (val === null || val === undefined || isNaN(val)) return '0'
    return formatVnd(val)
  }

  return (
    <div className="salary-pie-chart bg-white rounded-[28px] border border-slate-200 p-5 shadow-sm flex flex-row items-center gap-8 w-full animate-[fadeIn_0.3s_ease-out_forwards] flex-shrink-0">

      {/* ── Biểu đồ tròn — BÊN TRÁI, cố định 200px, không co giãn ── */}
      <div className="salary-pie-chart__visual flex-shrink-0 flex flex-col items-center justify-center relative">
        {total === 0 ? (
          <svg width="200" height="200" viewBox="0 0 200 200">
            <circle cx="100" cy="100" r="80" fill="#f1f5f9" stroke="#e2e8f0" strokeWidth="2" />
            <text x="100" y="105" textAnchor="middle" fill="#94a3b8" fontSize="12" fontWeight="600">Không có dữ liệu</text>
          </svg>
        ) : (
          <div className="relative group">
            <div className="absolute inset-0 rounded-full bg-slate-100 opacity-40 blur-2xl scale-90 group-hover:scale-110 transition duration-700" />
            <svg width="200" height="200" viewBox="0 0 200 200" className="relative drop-shadow-lg overflow-visible">
              {formattedSlices.map((slice, i) => {
                if (slice.isFull) {
                  return (
                    <circle
                      key={i}
                      cx="100" cy="100" r="80"
                      fill={slice.color}
                      className="transition-all duration-300 hover:scale-[1.03] origin-center cursor-pointer"
                    />
                  )
                }
                return (
                  <path
                    key={i}
                    d={slice.pathData}
                    fill={slice.color}
                    stroke="#ffffff"
                    strokeWidth="2"
                    strokeLinejoin="round"
                    className="transition-all duration-300 hover:scale-[1.03] origin-center cursor-pointer"
                    style={{ transformOrigin: '100px 100px' }}
                  >
                    <title>{slice.label}: {formatCurrency(slice.value)} VND ({slice.percentage.toFixed(1)}%)</title>
                  </path>
                )
              })}
              {/* Donut hole */}
              <circle cx="100" cy="100" r="46" fill="#ffffff" />
              <text x="100" y="94" textAnchor="middle" fill="#64748b" fontSize="11" fontWeight="700" letterSpacing="0.08em">TỔNG CỘNG</text>
              <text x="100" y="110" textAnchor="middle" fill="#0f172a" fontSize="13" fontWeight="800">
                {total > 1000000000
                  ? `${(total / 1000000000).toFixed(2)}B`
                  : total > 1000000
                  ? `${(total / 1000000).toFixed(1)}M`
                  : formatCurrency(total)}
              </text>
            </svg>
          </div>
        )}
        <p className="mt-2 text-[11px] font-semibold text-slate-400 uppercase tracking-widest">Đơn vị: VND</p>
      </div>

      {/* ── Chú thích — BÊN PHẢI, lưới 2 cột trên màn rộng ── */}
      <div className="salary-pie-chart__legend flex-1 min-w-0 grid grid-cols-1 xl:grid-cols-2 gap-x-3 gap-y-1">
        {formattedSlices.map((slice, i) => (
          <div key={i} className="salary-pie-chart__legend-item flex items-start gap-2.5 px-2.5 py-2 rounded-xl hover:bg-slate-50 transition">
            {/* Màu + % */}
            <div className="flex-shrink-0 flex flex-col items-center gap-1 pt-0.5">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: slice.color, boxShadow: `0 0 6px ${slice.color}80` }}
              />
              <span
                className="text-[11px] font-bold leading-none px-1 py-0.5 rounded-sm tabular-nums"
                style={{ color: slice.color, background: `${slice.color}18` }}
              >
                {slice.percentage.toFixed(0)}%
              </span>
            </div>
            {/* Nội dung */}
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline justify-between gap-1 flex-wrap">
                <h4 className="text-[11px] font-semibold text-slate-700 leading-tight">{slice.label}</h4>
                <span className="text-[11px] font-bold text-slate-900 whitespace-nowrap tabular-nums">
                  {formatCurrency(slice.value)}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5 leading-snug line-clamp-1">{slice.description}</p>
              <code className="block text-[11px] font-mono text-slate-300 bg-slate-50 border border-slate-100 rounded px-1 py-0.5 mt-1 overflow-x-auto whitespace-nowrap">
                {slice.formula}
              </code>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function App() {
  const confirm = useConfirmDialog()
  const apiBase = useMemo(() => {
    const configuredApiBase = import.meta.env.VITE_API_BASE?.trim()
    if (configuredApiBase) {
      return configuredApiBase.replace(/\/$/, '')
    }
    return `http://${window.location.hostname}:8001`
  }, [])
  

  // Auth & Routing States
  const [token, setToken] = useState<string | null>(null)
  const [currentUser, setCurrentUser] = useState<any>(null)
  const [currentPath, setCurrentPath] = useState(window.location.pathname)
  const [notificationNotice, setNotificationNotice] = useState<NotificationItem | null>(null)
  const [commissionNotificationFocus, setCommissionNotificationFocus] = useState<CommissionNotificationFocus | null>(null)
  const [heldBonusNotificationJobId, setHeldBonusNotificationJobId] = useState<number | null>(null)
  const [employeeNotificationId, setEmployeeNotificationId] = useState<number | null>(null)
  const [salaryNotificationEmployeeId, setSalaryNotificationEmployeeId] = useState<number | null>(null)
  const [salaryApprovalNotificationFocus, setSalaryApprovalNotificationFocus] = useState<{
    period: string
    notificationId: number
  } | null>(null)
  const [timesheetNotificationEmployeeId, setTimesheetNotificationEmployeeId] = useState<number | null>(null)
  const [timeOffNotificationRequestId, setTimeOffNotificationRequestId] = useState<number | null>(null)

  // Login Form States
  const [rememberLogin, setRememberLogin] = useState(() => localStorage.getItem(REMEMBER_LOGIN_PREFERENCE_KEY) === 'true')
  const [loginUsername, setLoginUsername] = useState(() =>
    localStorage.getItem(REMEMBER_LOGIN_PREFERENCE_KEY) === 'true'
      ? localStorage.getItem(REMEMBER_LOGIN_USERNAME_KEY) || ''
      : '',
  )
  const [loginPassword, setLoginPassword] = useState('')
  const [showLoginPassword, setShowLoginPassword] = useState(false)
  const [loginError, setLoginError] = useState('')

  const [activeTab, setActiveTab] = useState<string>('dashboard')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('Sẵn sàng kết nối API backend.')
  const [employeeError, setEmployeeError] = useState<string | null>(null)
  const [lastDataChange, setLastDataChange] = useState<DataChangedDetail | null>(null)

  // User Portal States
  const [myPayslipData, setMyPayslipData] = useState<any>(null)
  const [myPayslipPeriod, setMyPayslipPeriod] = useState('')
  const [myPayslipPeriods, setMyPayslipPeriods] = useState<string[]>([])
  const myPayslipPeriodOptions = useMemo(
    () => Array.from(new Set(myPayslipPeriods)).sort().reverse(),
    [myPayslipPeriods],
  )
  const [isDownloadingPayslip, setIsDownloadingPayslip] = useState(false)
  const [payslipPdfStatus, setPayslipPdfStatus] = useState<{ tone: 'loading' | 'success' | 'error'; text: string } | null>(null)
  const myPayslipPdfRef = useRef<HTMLDivElement>(null)
  const [myAttendanceData, setMyAttendanceData] = useState<any[]>([])
  const [myAttendancePeriod, setMyAttendancePeriod] = useState(currentMonthPeriod)
  const [myHeldBonusJobs, setMyHeldBonusJobs] = useState<any[]>([])
  const [myHeldBonusNotes, setMyHeldBonusNotes] = useState<Record<number, string>>({})
  const [selectedHeldBonusPeriodId, setSelectedHeldBonusPeriodId] = useState<number | null>(null)
  const heldBonusPeriods = useMemo(() => {
    const unique = new Map<number, string>()
    myHeldBonusJobs.forEach((job) => {
      if (Number.isFinite(Number(job.period_id)) && job.period_label) {
        unique.set(Number(job.period_id), String(job.period_label))
      }
    })
    return Array.from(unique, ([id, label]) => ({ id, label }))
  }, [myHeldBonusJobs])
  const visibleMyHeldBonusJobs = useMemo(
    () => selectedHeldBonusPeriodId === null
      ? []
      : myHeldBonusJobs.filter((job) => Number(job.period_id) === selectedHeldBonusPeriodId),
    [myHeldBonusJobs, selectedHeldBonusPeriodId],
  )

  // Salary / Payroll States
  const [salaryPeriod, setSalaryPeriod] = useState(currentMonthPeriod)
  const [salaryPeriods, setSalaryPeriods] = useState<SalaryPeriodItem[]>([])
  const salaryPeriodTouchedRef = useRef(false)
  const salaryLoadSequenceRef = useRef(0)
  const salaryPeriodYearBounds = useMemo(() => {
    const currentYear = new Date().getFullYear()
    const dataYears = salaryPeriods.map((item) => Number(item.period.slice(0, 4))).filter(Number.isFinite)
    return {
      min: Math.min(currentYear - 2, ...dataYears),
      max: Math.max(currentYear + 3, ...dataYears),
    }
  }, [salaryPeriods])
  const [salarySubTab, setSalarySubTab] = useState<'contract' | 'grid' | 'commission'>('grid')
  const [salaryEmployees, setSalaryEmployees] = useState<any[]>([])
  const [salaryInputs, setSalaryInputs] = useState<any[]>([])
  const [editedInputs, setEditedInputs] = useState<Record<number, any>>({})
  const [salaryPolicy, setSalaryPolicy] = useState<SalaryPolicy>(DEFAULT_SALARY_POLICY)
  const [salaryPolicyHistory, setSalaryPolicyHistory] = useState<SalaryPolicy[]>([])
  const [salaryPolicyModalOpen, setSalaryPolicyModalOpen] = useState(false)
  const [salaryPolicyForm, setSalaryPolicyForm] = useState<SalaryPolicyForm>(() => buildSalaryPolicyForm('2026-05'))
  const [savingSalaryPolicy, setSavingSalaryPolicy] = useState(false)
  const [lastSalaryUndo, setLastSalaryUndo] = useState<{
    salaryPeriod: string
    entries: Array<{ employeeId: number; previousInput: any | null }>
  } | null>(null)
  const [isSalaryConfirmed, setIsSalaryConfirmed] = useState(false)
  const [salaryApproval, setSalaryApproval] = useState<SalaryApprovalState | null>(null)
  const [isSalaryLocked, setIsSalaryLocked] = useState(false)
  const [otherIncomeEvidenceEmployeeId, setOtherIncomeEvidenceEmployeeId] = useState<number | null>(null)
  const [otherIncomeEvidenceNote, setOtherIncomeEvidenceNote] = useState('')
  const [otherIncomeEvidenceFile, setOtherIncomeEvidenceFile] = useState<File | null>(null)
  const [isSavingOtherIncomeEvidence, setIsSavingOtherIncomeEvidence] = useState(false)
  const [editingSalaryEmployeeId, setEditingSalaryEmployeeId] = useState<number | null>(null)
  const [editSalaryEmployeeForm, setEditSalaryEmployeeForm] = useState({
    employee_code: '',
    fullname: '',
    position: '',
    contract_salary: 0,
    employee_type: 'FULLTIME' as EmployeeType,
    dependents_count: 0,
    account_number: '',
    bank_name: '',
  })
  const otherIncomeEvidenceEmployee = otherIncomeEvidenceEmployeeId === null
    ? null
    : salaryEmployees.find((employee) => Number(employee.id) === otherIncomeEvidenceEmployeeId) || null
  const otherIncomeEvidenceInput = otherIncomeEvidenceEmployeeId === null
    ? null
    : salaryInputs.find((item) => Number(item.employee_id) === otherIncomeEvidenceEmployeeId) || null
  const otherIncomeEvidenceAmount = otherIncomeEvidenceEmployeeId === null
    ? 0
    : Number(editedInputs[otherIncomeEvidenceEmployeeId]?.other_income ?? otherIncomeEvidenceInput?.other_income ?? 0)

  useEffect(() => {
    if (otherIncomeEvidenceEmployeeId === null) return

    const previousOverflow = document.body.style.overflow
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOtherIncomeEvidenceEmployeeId(null)
      setOtherIncomeEvidenceNote('')
      setOtherIncomeEvidenceFile(null)
    }

    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleEscape)
    }
  }, [otherIncomeEvidenceEmployeeId])

  // Routing sync
  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(window.location.pathname)
    }
    window.addEventListener('popstate', handlePopState)
    return () => {
      window.removeEventListener('popstate', handlePopState)
    }
  }, [])

  useEffect(() => subscribeDataChanged(setLastDataChange), [])

  const navigateTo = (path: string) => {
    window.history.pushState({}, '', path)
    setCurrentPath(path)
  }

  const handleNotificationNavigate = (path: string, item: NotificationItem) => {
    setNotificationNotice(item)
    const context = item.action_context || {}

    if (item.resource_type === 'TIME_OFF_REQUEST') {
      const requestId = Number(context.request_id || item.resource_id)
      setTimeOffNotificationRequestId(Number.isFinite(requestId) ? requestId : null)
      if (isBusinessAdminRole(currentUser?.role)) navigateTo('/admin/time-off')
      else if (currentUser?.role === 'HR_ADMIN') navigateTo('/hr/time-off')
      else navigateTo('/user/time-off')
      return
    }

    if (item.resource_type === 'COMMISSION_JOB' && isBusinessAdminRole(currentUser?.role)) {
      if (context.job_id && context.period_id && context.sales_rep) {
        setCommissionNotificationFocus({
          jobId: Number(context.job_id),
          periodId: Number(context.period_id),
          periodLabel: String(context.period_label || ''),
          salesRep: String(context.sales_rep),
          requestKey: item.id,
          target: item.event_type === 'BONUS_PAYOUT_REQUESTED' ? 'accounting-queue' : 'job-detail',
        })
      } else {
        setCommissionNotificationFocus(null)
        setMessage('JOB được nhắc trong thông báo không còn tồn tại; đang mở danh sách Commission để đối chiếu lịch sử.')
      }
      setSalarySubTab('commission')
      navigateTo('/admin/commission')
      return
    }

    if (item.event_type === 'BONUS_PAYOUT_APPROVED' && context.payout_periods?.length) {
      setMyPayslipPeriod(String(context.payout_periods[0]))
      navigateTo(currentUser?.role === 'HR_ADMIN' ? '/hr/my-payslip' : '/user/my-payslip')
      return
    }

    if (item.resource_type === 'COMMISSION_JOB' && context.job_id) {
      setHeldBonusNotificationJobId(Number(context.job_id))
      if (context.period_id) setSelectedHeldBonusPeriodId(Number(context.period_id))
      navigateTo('/user/my-held-bonuses')
      return
    }

    if (item.resource_type === 'SALARY_PERIOD' && (context.salary_period || item.resource_id)) {
      const period = String(context.salary_period || item.resource_id)
      if (isBusinessAdminRole(currentUser?.role)) {
        const isApprovalRequest = item.event_type === 'PAYROLL_APPROVAL_REQUESTED'
        salaryPeriodTouchedRef.current = true
        setSalaryPeriod(period)
        setSalarySubTab('grid')
        setSalaryNotificationEmployeeId(
          isApprovalRequest ? null : context.target_employee_id ? Number(context.target_employee_id) : null,
        )
        setSalaryApprovalNotificationFocus(
          isApprovalRequest ? { period, notificationId: item.id } : null,
        )
        navigateTo('/admin/salary-matrix')
        if (isApprovalRequest) {
          // Refresh the workflow independently from the salary grid. This is
          // important when the user opens an approval notification while the
          // grid is still showing data/state from another salary period.
          void refreshSalaryApproval(period)
        }
      } else {
        setMyPayslipPeriod(period)
        navigateTo(currentUser?.role === 'HR_ADMIN' ? '/hr/my-payslip' : '/user/my-payslip')
      }
      return
    }

    if (item.resource_type === 'TIMESHEET_PERIOD') {
      if (isBusinessAdminRole(currentUser?.role)) {
        if (context.period_start) setPeriodStart(String(context.period_start))
        if (context.period_end) setPeriodEnd(String(context.period_end))
        setTimesheetNotificationEmployeeId(context.target_employee_id ? Number(context.target_employee_id) : null)
        navigateTo('/admin/timesheets')
      } else {
        if (context.attendance_month) setMyAttendancePeriod(String(context.attendance_month))
        navigateTo(currentUser?.role === 'HR_ADMIN' ? '/hr/my-attendance' : '/user/my-attendance')
      }
      return
    }

    if (item.resource_type === 'EMPLOYEE' && context.employee_id) {
      setEmployeeNotificationId(Number(context.employee_id))
      navigateTo(currentUser?.role === 'HR_ADMIN' ? '/hr/employees' : '/admin/employees')
      return
    }

    navigateTo(path)
  }

  useEffect(() => {
    const focusRequest = salaryApprovalNotificationFocus
    if (
      !focusRequest ||
      currentPath !== '/admin/salary-matrix' ||
      salaryPeriod !== focusRequest.period
    ) {
      return
    }

    let attempt = 0
    let timerId: number | undefined

    const focusApprovalAction = () => {
      attempt += 1
      const approvalButton = document.getElementById('salary-approve-publish-button')
      const target = approvalButton || document.getElementById('salary-approval-actions')

      if (target) {
        target.scrollIntoView({
          behavior: attempt === 1 ? 'smooth' : 'auto',
          block: 'center',
        })
        if (approvalButton instanceof HTMLButtonElement) {
          approvalButton.focus({ preventScroll: true })
        }
      }

      // Salary data and approval state load asynchronously; keep the requested destination stable.
      if (attempt < 12) {
        timerId = window.setTimeout(focusApprovalAction, 250)
        return
      }

      setSalaryApprovalNotificationFocus((current) =>
        current?.notificationId === focusRequest.notificationId ? null : current,
      )
    }

    timerId = window.setTimeout(focusApprovalAction, 100)
    return () => {
      if (timerId !== undefined) window.clearTimeout(timerId)
    }
  }, [currentPath, salaryApprovalNotificationFocus, salaryPeriod])

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setLoginError('')
    try {
      const res = await fetch(`${apiBase}/api/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUsername, password: loginPassword })
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Đăng nhập thất bại')
      }
      const data = await res.json()
      if (rememberLogin) {
        localStorage.setItem(REMEMBER_LOGIN_PREFERENCE_KEY, 'true')
        localStorage.setItem(REMEMBER_LOGIN_USERNAME_KEY, loginUsername.trim())
      } else {
        localStorage.removeItem(REMEMBER_LOGIN_PREFERENCE_KEY)
        localStorage.removeItem(REMEMBER_LOGIN_USERNAME_KEY)
      }
      setToken(data.access_token)
      setCurrentUser(data)
      const loginTab = isBusinessAdminRole(data.role) || data.role === 'HR_ADMIN' ? 'dashboard' : 'personal-dashboard'
      setActiveTab(loginTab)
      setSalarySubTab('grid')
      setMyPayslipPeriod('')
      setMyPayslipPeriods([])
      
      // Redirect based on role
      if (isBusinessAdminRole(data.role)) navigateTo('/admin/dashboard')
      else if (data.role === 'HR_ADMIN') navigateTo('/hr/dashboard')
      else navigateTo('/user/dashboard')
      const roleLabels: Record<string, string> = {
        ADMIN: 'Kế toán trưởng',
        DIRECTOR: 'GIÁM ĐỐC',
        HR_ADMIN: 'Admin vận hành',
        IT_ADMIN: 'Quản trị hệ thống cấp cao',
        USER: 'Nhân viên',
      }
      setMessage(`Đăng nhập thành công với vai trò ${roleLabels[data.role] || data.role}`)
    } catch (err) {
      setLoginError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    setToken(null)
    setCurrentUser(null)
    setActiveTab('dashboard')
    setSalarySubTab('grid')
    setMyPayslipPeriod('')
    setMyPayslipPeriods([])
    salaryPeriodTouchedRef.current = false
    setLoginUsername(rememberLogin ? localStorage.getItem(REMEMBER_LOGIN_USERNAME_KEY) || '' : '')
    setLoginPassword('')
    navigateTo('/login')
    setMessage('Đã đăng xuất khỏi hệ thống.')
  }

  // Sync tab with path
  useEffect(() => {
    if (!currentUser) {
      if (currentPath !== '/login' && currentPath !== '/onboarding' && currentPath !== '/offboarding') {
        window.setTimeout(() => navigateTo('/login'), 0)
      }
      return
    }

    if (isBusinessAdminRole(currentUser.role)) {
      if (currentUser.role === 'IT_ADMIN' && currentPath === '/it/backups') {
        setActiveTab('it-backups')
      } else if (currentUser.role === 'IT_ADMIN' && currentPath === '/it/audit') {
        setActiveTab('it-audit')
      } else if (currentPath === '/admin/dashboard') {
        setActiveTab('dashboard')
      } else if (currentPath === '/admin/salary-matrix') {
        setActiveTab('salary')
      } else if (currentPath === '/admin/employees') {
        setActiveTab('employees')
      } else if (currentPath === '/admin/departments' || currentPath === '/admin/departments/chart') {
        setActiveTab('departments')
      } else if (currentPath === '/admin/onboarding') {
        setActiveTab('onboarding')
      } else if (currentPath.startsWith('/admin/offboarding')) {
        setActiveTab('offboarding')
      } else if (currentPath === '/admin/timesheets') {
        setActiveTab('timesheets')
      } else if (currentPath === '/admin/time-off') {
        setActiveTab('time-off')
      } else if (currentPath === '/admin/import') {
        setIsTimesheetUploadOpen(true)
        navigateTo('/admin/timesheets')
      } else if (currentPath === '/admin/export') {
        setActiveTab('export')
      } else if (currentPath === '/admin/commission') {
        navigateTo('/admin/salary-matrix')
        setSalarySubTab('commission')
      } else if ((currentUser.role === 'ADMIN' || currentUser.role === 'DIRECTOR') && currentPath === '/admin/my-payslip') {
        setActiveTab('my-payslip')
      } else if ((currentUser.role === 'ADMIN' || currentUser.role === 'DIRECTOR') && currentPath === '/admin/my-attendance') {
        setActiveTab('my-attendance')
      } else if (currentPath === '/admin/my-account') {
        setActiveTab('my-account')
      } else if (
        currentPath === '/'
        || currentPath.startsWith('/user')
        || currentPath === '/it/dashboard'
        || currentPath === '/login'
      ) {
        navigateTo('/admin/dashboard')
      }
    } else if (currentUser.role === 'HR_ADMIN') {
      if (currentPath === '/hr/dashboard') setActiveTab('dashboard')
      else if (currentPath === '/hr/employees') setActiveTab('employees')
      else if (currentPath === '/hr/departments' || currentPath === '/hr/departments/chart') setActiveTab('departments')
      else if (currentPath === '/hr/onboarding') setActiveTab('onboarding')
      else if (currentPath.startsWith('/hr/offboarding')) setActiveTab('offboarding')
      else if (currentPath === '/hr/timesheets') setActiveTab('timesheets')
      else if (currentPath === '/hr/time-off') setActiveTab('time-off')
      else if (currentPath === '/hr/export') setActiveTab('export')
      else if (currentPath === '/hr/my-payslip') setActiveTab('my-payslip')
      else if (currentPath === '/hr/my-attendance') setActiveTab('my-attendance')
      else if (currentPath === '/hr/my-account') setActiveTab('my-account')
      else navigateTo('/hr/dashboard')
    } else {
      const prefix = '/user'
      if (currentPath === `${prefix}/dashboard` || currentPath === '/user/dashboard') {
        setActiveTab('personal-dashboard')
      } else if (currentPath === `${prefix}/my-payslip` || currentPath === '/user/my-payslip') {
        setActiveTab('my-payslip')
      } else if (currentPath === `${prefix}/my-attendance` || currentPath === '/user/my-attendance') {
        setActiveTab('my-attendance')
      } else if (currentPath === `${prefix}/time-off` || currentPath === '/user/time-off') {
        setActiveTab('time-off')
      } else if (currentPath.startsWith(`${prefix}/offboarding`)) {
        navigateTo(`${prefix}/dashboard`)
        setActiveTab('personal-dashboard')
      } else if (currentPath === `${prefix}/my-timesheet` || currentPath === '/user/my-timesheet') {
        navigateTo(`${prefix}/my-attendance`)
        setActiveTab('my-attendance')
      } else if (currentPath === `${prefix}/my-held-bonuses` || currentPath === '/user/my-held-bonuses') {
        setActiveTab('my-held-bonuses')
      } else if (currentPath === `${prefix}/my-account` || currentPath === '/user/my-account') {
        setActiveTab('my-account')
      } else if (currentPath === '/' || currentPath.startsWith('/admin') || currentPath.startsWith('/hr') || currentPath === '/login') {
        navigateTo(`${prefix}/dashboard`)
      }
    }
  }, [currentPath, currentUser])

  const handleTabChange = (key: string) => {
    if (key === 'time-off') setTimeOffNotificationRequestId(null)
    if (isBusinessAdminRole(currentUser?.role)) {
      if (key === 'dashboard') navigateTo('/admin/dashboard')
      else if (key === 'salary') navigateTo('/admin/salary-matrix')
      else if (key === 'employees') navigateTo('/admin/employees')
      else if (key === 'departments') navigateTo('/admin/departments')
      else if (key === 'onboarding') navigateTo('/admin/onboarding')
      else if (key === 'offboarding') navigateTo('/admin/offboarding')
      else if (key === 'timesheets') navigateTo('/admin/timesheets')
      else if (key === 'time-off') navigateTo('/admin/time-off')
      else if (key === 'import') {
        setIsTimesheetUploadOpen(true)
        navigateTo('/admin/timesheets')
      }
      else if (key === 'export') navigateTo('/admin/export')
      else if (key === 'commission') navigateTo('/admin/commission')
      else if ((currentUser?.role === 'ADMIN' || currentUser?.role === 'DIRECTOR') && key === 'my-payslip') navigateTo('/admin/my-payslip')
      else if ((currentUser?.role === 'ADMIN' || currentUser?.role === 'DIRECTOR') && key === 'my-attendance') navigateTo('/admin/my-attendance')
      else if (key === 'my-account') navigateTo('/admin/my-account')
      else if (currentUser?.role === 'IT_ADMIN' && key === 'it-backups') navigateTo('/it/backups')
      else if (currentUser?.role === 'IT_ADMIN' && key === 'it-audit') navigateTo('/it/audit')
    } else if (currentUser?.role === 'HR_ADMIN') {
      if (key === 'dashboard') navigateTo('/hr/dashboard')
      else if (key === 'employees') navigateTo('/hr/employees')
      else if (key === 'departments') navigateTo('/hr/departments')
      else if (key === 'onboarding') navigateTo('/hr/onboarding')
      else if (key === 'offboarding') navigateTo('/hr/offboarding')
      else if (key === 'timesheets') navigateTo('/hr/timesheets')
      else if (key === 'time-off') navigateTo('/hr/time-off')
      else if (key === 'export') navigateTo('/hr/export')
      else if (key === 'my-payslip') navigateTo('/hr/my-payslip')
      else if (key === 'my-attendance') navigateTo('/hr/my-attendance')
      else if (key === 'my-account') navigateTo('/hr/my-account')
    } else {
      const prefix = '/user'
      if (key === 'personal-dashboard') navigateTo(`${prefix}/dashboard`)
      else if (key === 'time-off') navigateTo(`${prefix}/time-off`)
      else if (key === 'my-payslip') navigateTo(`${prefix}/my-payslip`)
      else if (key === 'my-attendance') navigateTo(`${prefix}/my-attendance`)
      else if (key === 'my-held-bonuses') navigateTo(`${prefix}/my-held-bonuses`)
      else if (key === 'my-account') navigateTo(`${prefix}/my-account`)
    }
  }

  const dynamicTabs = useMemo(() => {
    if (!currentUser) return []
    if (currentUser.role === 'IT_ADMIN') return itNavigationTabs
    if (currentUser.role === 'ADMIN' || currentUser.role === 'DIRECTOR') return chiefAccountantNavigationTabs
    if (currentUser.role === 'HR_ADMIN') return hrNavigationTabs
    return personalNavigationTabs
  }, [currentUser])

  async function confirmSalaryPeriod() {
    if (Object.keys(editedInputs).length > 0) {
      setMessage('Hãy lưu các thay đổi bảng lương vào DB trước khi xác nhận.')
      return
    }
    const accepted = await confirm({
      title: `Xác nhận bảng lương ${salaryPeriod}`,
      message: 'Bước này chỉ xác nhận số liệu bảng lương là chính xác, chưa phát hành phiếu lương. Sau đó bạn cần gửi yêu cầu phê duyệt. Tiếp tục?',
      confirmLabel: 'Xác nhận số liệu',
    })
    if (!accepted) return
    setLoading(true)
    try {
      const response = await apiRequest('/api/salary/approval/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: salaryPeriod }),
      })
      const result = await response.json() as SalaryApprovalState & { input_count: number }
      setSalaryApproval(result)
      await loadSalaryData()
      setMessage(`Đã xác nhận số liệu bảng lương tháng ${salaryPeriod}. Phiếu lương chưa phát hành; nút Yêu cầu phê duyệt đã sẵn sàng.`)
    } catch (error) {
      setMessage(`Xác nhận bảng lương thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function requestSalaryApproval() {
    const accepted = await confirm({
      title: `Gửi yêu cầu phê duyệt bảng lương ${salaryPeriod}`,
      message: 'Yêu cầu sẽ được gửi tới hai Giám đốc và IT_ADMIN. Phiếu lương chỉ phát hành sau khi một người có thẩm quyền phê duyệt.',
      confirmLabel: 'Gửi yêu cầu',
    })
    if (!accepted) return
    setLoading(true)
    try {
      const response = await apiRequest('/api/salary/approval/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: salaryPeriod }),
      })
      const result = await response.json() as SalaryApprovalState & { notified_count: number }
      setSalaryApproval(result)
      setMessage(`Đã gửi yêu cầu phê duyệt tới ${result.notified_count} tài khoản Giám đốc/IT cho bảng lương tháng ${salaryPeriod}.`)
      await loadSalaryPeriods()
    } catch (error) {
      setMessage(`Gửi yêu cầu phê duyệt thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function approveSalaryPeriod() {
    const accepted = await confirm({
      title: `Phê duyệt bảng lương ${salaryPeriod}`,
      message: 'Sau khi phê duyệt, hệ thống sẽ tự động phát hành phiếu lương và gửi thông báo đến nhân viên. Tiếp tục?',
      confirmLabel: 'Phê duyệt & phát hành',
    })
    if (!accepted) return
    setLoading(true)
    try {
      const response = await apiRequest('/api/salary/approval/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: salaryPeriod }),
      })
      const result = await response.json() as SalaryApprovalState & { published_count: number }
      setSalaryApproval(result)
      await Promise.all([loadSalaryData(), loadSalaryPeriods()])
      setMessage(`Đã phê duyệt và tự động phát hành ${result.published_count} phiếu lương tháng ${salaryPeriod}. Nhân viên đã nhận thông báo.`)
    } catch (error) {
      setMessage(`Phê duyệt bảng lương thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function loadMyPayslip() {
    if (!token || !myPayslipPeriod) return
    setLoading(true)
    try {
      const res = await apiRequest(`/api/user/my-payslip?period=${myPayslipPeriod}`)
      const data = await res.json()
      setMyPayslipData(data)
      setMessage(`Đã tải phiếu lương tháng ${myPayslipPeriod}.`)
    } catch (error) {
      setMyPayslipData(null)
      setMessage(`Không tải được phiếu lương: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function loadMyPayslipPeriods() {
    if (!token) return
    try {
      const res = await apiRequest('/api/user/my-payslip-periods')
      const periods = await res.json()
      const availablePeriods = Array.isArray(periods) ? periods.filter((value): value is string => typeof value === 'string') : []
      setMyPayslipPeriods(availablePeriods)
      setMyPayslipPeriod((current) => availablePeriods.includes(current) ? current : (availablePeriods[0] || ''))
    } catch (error) {
      setMyPayslipPeriods([])
      setMyPayslipPeriod('')
      setMyPayslipData(null)
      setMessage(`Không tải được danh sách tháng phiếu lương: ${(error as Error).message}`)
    }
  }

  async function downloadMyPayslipPdf() {
    return downloadTextPayslipPdf()

    if (!myPayslipData) {
      setPayslipPdfStatus({ tone: 'error', text: 'Chưa có phiếu lương để tải. Vui lòng chọn tháng đã được phát hành.' })
      return
    }

    setIsDownloadingPayslip(true)
    setPayslipPdfStatus({ tone: 'loading', text: 'Đang chuẩn bị phiếu lương dạng văn bản…' })
    try {
      const safeEmployeeCode = String(myPayslipData.employee_code || 'nhan-vien').replace(/[^a-zA-Z0-9_-]/g, '-')
      const safePeriod = String(myPayslipData.salary_period || myPayslipPeriod).replace(/[^0-9-]/g, '')
      const filename = `Phieu-luong_${safeEmployeeCode}_${safePeriod}.pdf`
      const escapeHtml = (value: unknown) => String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;')
      const currency = (value: unknown) => formatVnd(Math.round(Number(value) || 0), { suffix: true })
      const period = String(myPayslipData.salary_period || myPayslipPeriod)
      const [year, month] = period.split('-')
      const periodLabel = year && month ? `Tháng ${month}/${year}` : period
      const payMonth = Number(month) === 12 ? 1 : Number(month || 0) + 1
      const payYear = Number(month) === 12 ? Number(year) + 1 : Number(year)
      const payDate = Number.isFinite(payMonth) && payMonth > 0
        ? `25/${String(payMonth).padStart(2, '0')}/${payYear}`
        : 'N/A'
      const inputs = myPayslipData.inputs || {}
      const calculations = myPayslipData.calculations || {}
      const actualSalary = Number(calculations.actual_salary) || 0
      const mealAllowance = (Number(inputs.meal_allowance_free) || 0) + (Number(inputs.meal_allowance_tax) || 0)
      const phoneAllowance = Number(inputs.phone_allowance_free) || 0
      const transAllowance = Number(inputs.trans_allowance_tax) || 0
      const performanceAllowance = Number(inputs.perf_allowance_tax) || 0
      const otherIncome = Number(inputs.other_income) || 0
      const bonus = Number(inputs.bonus) || 0
      const salesBonus = Number(inputs.sales_bonus) || 0
      const pitRefund = Number(inputs.pit_refund) || 0
      const totalInsurance = Number(calculations.total_ins_emp) || 0
      const pitTax = Number(calculations.pit_tax) || 0
      const unionFee = Number(calculations.union_fee) || 0
      const advancePayment = Number(inputs.advance_payment) || 0
      const otherDeductions = Number(inputs.other_deductions) || 0
      const grossEarnings = actualSalary + mealAllowance + phoneAllowance + transAllowance + performanceAllowance + otherIncome + bonus + salesBonus + pitRefund
      const totalDeductions = totalInsurance + pitTax + unionFee + advancePayment + otherDeductions
      const finalTransfer = Number(calculations.final_transfer) || 0
      const standardDays = calculatePeriodWorkingDays(period)
      const earnings = [
        ['Lương thực tế theo ngày công', actualSalary],
        ['Phụ cấp ăn trưa', mealAllowance],
        ['Phụ cấp điện thoại', phoneAllowance],
        ['Phụ cấp xăng xe', transAllowance],
        ['Phụ cấp hiệu suất / khác', performanceAllowance],
        ['Thu nhập bổ sung khác', otherIncome],
        ['Tiền thưởng (Bonus)', bonus],
        ['Tiền thưởng doanh số', salesBonus],
        ['Hoàn thuế PIT', pitRefund],
      ].filter(([, amount]) => Number(amount) > 0)
      const deductions = [
        ['Bảo hiểm bắt buộc', totalInsurance],
        ['Thuế thu nhập cá nhân (PIT)', pitTax],
        ['Đoàn phí công đoàn', unionFee],
        ['Tạm ứng lương', advancePayment],
        ['Khấu trừ khác', otherDeductions],
      ].filter(([, amount]) => Number(amount) > 0)
      const renderRows = (rows: (string | number)[][], isDeduction = false) => rows.length > 0
        ? rows.map(([label, amount]) => `<tr><td>${escapeHtml(label)}</td><td class="amount${isDeduction ? ' deduction' : ''}">${isDeduction ? '-' : ''}${currency(amount)}</td></tr>`).join('')
        : '<tr><td colspan="2" class="empty">Không phát sinh</td></tr>'

      const printWindow = window.open('', '_blank')
      if (!printWindow) {
        throw new Error('Trình duyệt đã chặn cửa sổ xuất PDF. Hãy cho phép mở cửa sổ bật lên rồi thử lại.')
      }
      const nativePrintWindow = printWindow as Window
      nativePrintWindow.opener = null
      nativePrintWindow.document.write(`<!doctype html>
<html lang="vi"><head><meta charset="utf-8" /><title>${escapeHtml(filename)}</title>
<style>
  @page { size: A4; margin: 12mm; }
  * { box-sizing: border-box; }
  body { margin: 0; color: #172033; font-family: Roboto, "Segoe UI", Arial, sans-serif; font-size: 10.5pt; line-height: 1.42; }
  .payslip { border-top: 4px solid #163b66; }
  .header { display: flex; justify-content: space-between; gap: 18px; padding: 14px 0 16px; border-bottom: 1px solid #dbe3ed; }
  .brand { display: flex; align-items: center; gap: 12px; }
  .brand img { width: 48px; height: 48px; object-fit: contain; border: 1px solid #cbd5e1; border-radius: 8px; padding: 3px; }
  h1, h2, h3, p { margin: 0; } h1 { font-size: 17pt; } h2 { font-size: 15pt; text-align: right; } h3 { font-size: 10pt; letter-spacing: .05em; }
  .muted { color: #64748b; font-size: 8.5pt; } .eyebrow { color: #475569; font-size: 8pt; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
  .tag { display: inline-block; border-radius: 999px; background: #eef2f7; padding: 4px 8px; font-size: 8pt; font-weight: 700; }
  .summary { display: grid; grid-template-columns: 1.45fr .8fr; gap: 16px; margin-top: 16px; }
  .section-title { margin: 0 0 8px; color: #475569; font-size: 8.5pt; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
  .info { width: 100%; border-collapse: collapse; } .info td { width: 50%; padding: 6px 8px 6px 0; border-bottom: 1px solid #edf2f7; vertical-align: top; }
  .info strong { color: #0f172a; } .label { color: #64748b; }
  .net-box { border: 1px solid #a7f3d0; border-radius: 10px; background: #f0fdf4; padding: 14px; text-align: center; }
  .net-box .value { color: #047857; font-size: 19pt; font-weight: 700; margin: 7px 0; } .net-box .small { color: #065f46; font-size: 8.5pt; }
  .bank { margin: 14px 0; padding: 8px 0; border-top: 1px solid #dbe3ed; border-bottom: 1px solid #dbe3ed; display: flex; justify-content: space-between; gap: 12px; font-size: 9pt; }
  .tables { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
  table.data { width: 100%; border-collapse: collapse; } .data th { border-bottom: 1px solid #94a3b8; color: #475569; font-size: 8pt; letter-spacing: .04em; text-align: left; text-transform: uppercase; padding: 0 0 6px; }
  .data th:last-child, .data td:last-child { text-align: right; } .data td { border-bottom: 1px solid #e2e8f0; padding: 7px 0; } .amount { font-weight: 700; white-space: nowrap; } .deduction { color: #be123c; } .empty { color: #94a3b8; font-style: italic; }
  .total { display: flex; justify-content: space-between; margin-top: 10px; border: 1px solid #dbe3ed; border-radius: 7px; background: #f8fafc; padding: 9px 10px; font-weight: 700; }
  .net-total { display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-top: 20px; padding: 14px; border: 1px solid #a7f3d0; border-radius: 10px; background: #f0fdf4; } .net-total .amount { color: #047857; font-size: 18pt; }
  .words { margin-top: 10px; text-align: right; color: #475569; font-size: 9pt; font-style: italic; } .footer { margin-top: 24px; padding-top: 10px; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 8pt; display: flex; justify-content: space-between; gap: 10px; }
  @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
</style></head><body><main class="payslip">
  <header class="header"><div class="brand"><img src="${escapeHtml(logoSealink)}" alt="Sealink" /><div><h1>SEALINK INTERNATIONAL</h1><p class="eyebrow">Tiền lương &amp; Chế độ đãi ngộ</p></div></div><div><span class="tag">PHIẾU LƯƠNG / PAYSLIP</span><h2>${escapeHtml(periodLabel)}</h2><p class="muted" style="text-align:right">Ngày phát hành: ${new Date().toLocaleDateString('vi-VN')}</p></div></header>
  <section class="summary"><div><p class="section-title">Tóm tắt nhân viên / Employee summary</p><table class="info"><tr><td><span class="label">Họ và tên:</span> <strong>${escapeHtml(myPayslipData.employee_name)}</strong></td><td><span class="label">Mã nhân viên:</span> <strong>${escapeHtml(myPayslipData.employee_code || 'N/A')}</strong></td></tr><tr><td><span class="label">Chức vụ:</span> <strong>${escapeHtml(myPayslipData.position || 'N/A')}</strong></td><td><span class="label">Ngày vào làm:</span> <strong>${escapeHtml(myPayslipData.start_date || 'N/A')}</strong></td></tr><tr><td><span class="label">Tháng thanh toán:</span> <strong>${escapeHtml(periodLabel)}</strong></td><td><span class="label">Ngày chi trả:</span> <strong>${escapeHtml(payDate)}</strong></td></tr></table></div><aside class="net-box"><p class="section-title">Thực nhận chuyển khoản</p><p class="value">${currency(finalTransfer)}</p><p class="small">Ngày công: <strong>${escapeHtml(inputs.actual_working_days || 0)}</strong> / ${standardDays} ngày</p><p class="small">Nghỉ không công: <strong>${Math.max(0, standardDays - (Number(inputs.actual_working_days) || 0))}</strong> ngày</p></aside></section>
  <section class="bank"><span><strong>Tài khoản:</strong> ${escapeHtml(myPayslipData.account_number || 'N/A')} (${escapeHtml(myPayslipData.bank_name || 'N/A')})</span><span><strong>Hợp đồng:</strong> ${getEmployeeTypeLabel(myPayslipData.employee_type)}</span></section>
  <section class="tables"><div><p class="section-title">Thu nhập / Earnings</p><table class="data"><thead><tr><th>Khoản mục</th><th>Số tiền</th></tr></thead><tbody>${renderRows(earnings)}</tbody></table><div class="total"><span>Tổng thu nhập</span><span>${currency(grossEarnings)}</span></div></div><div><p class="section-title">Khấu trừ / Deductions</p><table class="data"><thead><tr><th>Khoản mục</th><th>Số tiền</th></tr></thead><tbody>${renderRows(deductions, true)}</tbody></table><div class="total"><span>Tổng khấu trừ</span><span>-${currency(totalDeductions)}</span></div></div></section>
  <section class="net-total"><div><h3>TỔNG THỰC NHẬN / TOTAL NET PAYABLE</h3><p class="muted">Lương thực chuyển = Tổng thu nhập - Tổng khấu trừ</p></div><span class="amount">${currency(finalTransfer)}</span></section><p class="words">Bằng chữ: ${escapeHtml(numberToVietnameseWords(finalTransfer))}</p>
  <footer class="footer"><span>Mọi thắc mắc về số liệu vui lòng liên hệ phòng Kế toán trước ngày 25 hàng tháng.</span><span>Tài liệu được hệ thống tự động xuất, không yêu cầu chữ ký tay.</span></footer>
</main><script>window.addEventListener('load', function () { setTimeout(function () { window.print(); }, 250); });</script></body></html>`)
      nativePrintWindow.document.close()
      nativePrintWindow.addEventListener('afterprint', () => nativePrintWindow.close(), { once: true })
      setMessage(`Đã mở mẫu ${filename} dạng văn bản. Chọn “Save as PDF” trong hộp thoại in để lưu tệp.`)
      setPayslipPdfStatus({ tone: 'success', text: 'Đã mở hộp thoại in. Chọn “Save as PDF” để lưu phiếu lương dạng văn bản có thể chọn và tìm kiếm.' })
    } catch (error) {
      const errorMessage = (error as Error).message || 'Lỗi không xác định'
      setMessage(`Không thể tạo PDF phiếu lương: ${errorMessage}`)
      setPayslipPdfStatus({ tone: 'error', text: `Không thể tạo PDF: ${errorMessage}` })
    } finally {
      setIsDownloadingPayslip(false)
    }
  }

  async function downloadTextPayslipPdf() {
    if (!myPayslipData || !myPayslipPeriod) {
      setPayslipPdfStatus({ tone: 'error', text: 'Chưa có phiếu lương để tải. Vui lòng chọn tháng đã được phát hành.' })
      return
    }

    setIsDownloadingPayslip(true)
    setPayslipPdfStatus({ tone: 'loading', text: 'Đang tạo tệp PDF dạng văn bản…' })
    try {
      const response = await apiRequest(`/api/user/my-payslip-pdf?period=${encodeURIComponent(myPayslipPeriod)}`)
      const blob = await response.blob()
      const safeEmployeeCode = String(myPayslipData.employee_code || 'nhan-vien').replace(/[^a-zA-Z0-9_-]/g, '-')
      const safePeriod = String(myPayslipData.salary_period || myPayslipPeriod).replace(/[^0-9-]/g, '')
      const fallbackFilename = `Phieu-luong_${safeEmployeeCode}_${safePeriod}.pdf`
      triggerBrowserDownload(blob, extractFilename(response.headers.get('content-disposition'), fallbackFilename))
      setMessage(`Đã tải phiếu lương PDF tháng ${myPayslipData.salary_period || myPayslipPeriod}.`)
      setPayslipPdfStatus({ tone: 'success', text: 'Đã tải tệp PDF dạng văn bản. Bạn có thể chọn, sao chép và tìm kiếm nội dung trong tệp.' })
    } catch (error) {
      const errorMessage = (error as Error).message || 'Lỗi không xác định'
      setMessage(`Không thể tạo PDF phiếu lương: ${errorMessage}`)
      setPayslipPdfStatus({ tone: 'error', text: `Không thể tạo PDF: ${errorMessage}` })
    } finally {
      setIsDownloadingPayslip(false)
    }
  }

  async function loadMyAttendance() {
    if (!token) return
    setLoading(true)
    try {
      const year = parseInt(myAttendancePeriod.split('-')[0])
      const month = parseInt(myAttendancePeriod.split('-')[1])
      const prevYear = month === 1 ? year - 1 : year
      const prevMonth = month === 1 ? 12 : month - 1
      const startStr = `${prevYear}-${String(prevMonth).padStart(2, '0')}-23`
      const endStr = `${year}-${String(month).padStart(2, '0')}-22`

      const res = await apiRequest(`/api/user/my-attendance?period_start=${startStr}&period_end=${endStr}`)
      const data = await res.json()
      setMyAttendanceData(data)
      setMessage(`Đã tải lịch công từ ${startStr} đến ${endStr}.`)
    } catch (error) {
      setMyAttendanceData([])
      setMessage(`Không tải được lịch công: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function loadMyHeldBonusJobs() {
    if (!token) return
    setLoading(true)
    try {
      const response = await apiRequest('/api/user/my-held-bonus-jobs')
      const jobs = await response.json()
      const nextJobs = Array.isArray(jobs) ? jobs : []
      setMyHeldBonusJobs(nextJobs)
      setSelectedHeldBonusPeriodId((currentPeriodId) => {
        if (currentPeriodId !== null && nextJobs.some((job) => Number(job.period_id) === currentPeriodId)) {
          return currentPeriodId
        }
        return nextJobs.length > 0 ? Number(nextJobs[0].period_id) : null
      })
    } catch (error) {
      setMyHeldBonusJobs([])
      setSelectedHeldBonusPeriodId(null)
      setMessage(`Không tải được JOB bonus đang giữ: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function requestAccountingForMyHeldBonus(job: any) {
    if (!job?.can_request) return
    const accepted = await confirm({
      title: `Gửi yêu cầu kế toán cho JOB ${job.job_no}`,
      message: `Gửi yêu cầu kế toán kiểm tra thanh toán và duyệt chi trả ${formatCurrency(job.payment_held || 0)} bonus đang giữ của JOB này? Yêu cầu không tự mở tiền hay thay đổi công thức bonus.`,
      confirmLabel: 'Gửi yêu cầu',
    })
    if (!accepted) return
    setLoading(true)
    try {
      const response = await apiRequest(`/api/user/my-held-bonus-jobs/${job.job_id}/request-accounting`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: myHeldBonusNotes[job.job_id] || undefined }),
      })
      const result = await response.json()
      setMessage(result.message || 'Đã gửi yêu cầu kế toán.')
      setMyHeldBonusNotes((previous) => ({ ...previous, [job.job_id]: '' }))
      await loadMyHeldBonusJobs()
    } catch (error) {
      setMessage(`Không thể gửi yêu cầu kế toán: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'my-payslip') {
      void loadMyPayslipPeriods()
    }
  }, [activeTab, token])

  useEffect(() => {
    if (activeTab === 'my-payslip' && myPayslipPeriod) {
      void loadMyPayslip()
    }
  }, [activeTab, myPayslipPeriod, token])

  useEffect(() => {
    if (activeTab === 'my-attendance') {
      void loadMyAttendance()
    }
  }, [activeTab, myAttendancePeriod, token])

  useEffect(() => {
    if (activeTab === 'my-held-bonuses') {
      void loadMyHeldBonusJobs()
    }
  }, [activeTab, token])

  useEffect(() => {
    if (activeTab !== 'my-held-bonuses' || heldBonusNotificationJobId === null) return
    const target = visibleMyHeldBonusJobs.find((job) => Number(job.job_id) === heldBonusNotificationJobId)
    if (!target) return
    const scrollTimer = window.setTimeout(() => {
      document.getElementById(`held-bonus-job-${heldBonusNotificationJobId}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    }, 180)
    const highlightTimer = window.setTimeout(() => setHeldBonusNotificationJobId(null), 6000)
    return () => {
      window.clearTimeout(scrollTimer)
      window.clearTimeout(highlightTimer)
    }
  }, [activeTab, heldBonusNotificationJobId, visibleMyHeldBonusJobs])

  const [importType] = useState<ImportType>('checkin')
  const [importMode, setImportMode] = useState<ImportMode>('auto')
  const [isTimesheetUploadOpen, setIsTimesheetUploadOpen] = useState(false)
  const [isImportPreviewDetailsOpen, setIsImportPreviewDetailsOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [notionFile, setNotionFile] = useState<File | null>(null)
  const [importPreview, setImportPreview] = useState<ImportPreviewRow[]>([])
  const [, setAttendanceJsonEmployees] = useState<AttendanceJsonEmployee[]>([])
  const [, setAttendanceValidationSummary] = useState<Record<string, AttendanceValidationSummaryRow>>({})
  // const [validatedColumns, setValidatedColumns] = useState<string[]>([])
  const [workbookInspection, setWorkbookInspection] = useState<WorkbookInspection | null>(null)
  const [selectedSheetInspection, setSelectedSheetInspection] = useState<WorkbookSheetInspection | null>(null)
  const [selectedImportSheet, setSelectedImportSheet] = useState('')
  const [selectedHeaderRowIndex, setSelectedHeaderRowIndex] = useState('0')
  const [customColumnMapping, setCustomColumnMapping] = useState<Record<string, string>>({})
  const [importTableSearch, setImportTableSearch] = useState('')
  const [importColumnFilters, setImportColumnFilters] = useState<Record<string, string>>({})
  const [selectedImportTableColumns, setSelectedImportTableColumns] = useState<string[]>([])
  const [employeeBlockFilters, setEmployeeBlockFilters] = useState({
    employee_id: '',
    employee_name: '',
    department_name: '',
  })
  const [employeeBlockPageSize, setEmployeeBlockPageSize] = useState('5')
  const [visibleEmployeeBlockCount, setVisibleEmployeeBlockCount] = useState(5)
  const [isInspectingImportFile, setIsInspectingImportFile] = useState(false)
  const [isLoadingImportSheetRows, setIsLoadingImportSheetRows] = useState(false)
  const [parserPeriodStart] = useState('')
  const importToolbarFormRef = useRef<HTMLFormElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const notionFileInputRef = useRef<HTMLInputElement | null>(null)

  const [employees, setEmployees] = useState<Employee[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [employeeSearch, setEmployeeSearch] = useState('')
  const [employeeDepartmentFilter, setEmployeeDepartmentFilter] = useState('all')
  const [employeeStatusFilter, setEmployeeStatusFilter] = useState<EmployeeDirectoryStatusFilter>('all')
  const [employeeTypeFilter, setEmployeeTypeFilter] = useState('all')
  const [employeeDirectoryPage, setEmployeeDirectoryPage] = useState(1)
  const employeeDepartmentOptions = useMemo(
    () => Array.from(new Set(employees.map((employee) => employee.department_name || employee.department_code || 'N/A')))
      .sort((a, b) => a.localeCompare(b, 'vi')),
    [employees],
  )
  const filteredEmployeeDirectoryRows = useMemo(
    () => filterEmployeeDirectoryRows(employees, {
      search: employeeSearch,
      department: employeeDepartmentFilter,
      status: employeeStatusFilter,
      employeeType: employeeTypeFilter,
    }),
    [employees, employeeSearch, employeeDepartmentFilter, employeeStatusFilter, employeeTypeFilter],
  )
  const employeeDirectoryPagination = useMemo(
    () => paginateEmployeeDirectoryRows(filteredEmployeeDirectoryRows, employeeDirectoryPage),
    [filteredEmployeeDirectoryRows, employeeDirectoryPage],
  )
  useEffect(() => {
    if (employeeDirectoryPage !== employeeDirectoryPagination.currentPage) {
      setEmployeeDirectoryPage(employeeDirectoryPagination.currentPage)
    }
  }, [employeeDirectoryPage, employeeDirectoryPagination.currentPage])
  const [employeeForm, setEmployeeForm] = useState<EmployeeFormState>(EMPTY_EMPLOYEE_FORM)
  const [isEmployeeModalOpen, setIsEmployeeModalOpen] = useState(false)
  const [editingEmployeeId, setEditingEmployeeId] = useState<number | null>(null)
  const [detailEmployee, setDetailEmployee] = useState<Employee | null>(null)
  const [detailEmployeePassword, setDetailEmployeePassword] = useState('')
  const [detailEmployeeOriginalType, setDetailEmployeeOriginalType] = useState<EmployeeType | null>(null)
  const [detailEmployeeTypeEffectiveDate, setDetailEmployeeTypeEffectiveDate] = useState('')
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [editEmployeeForm, setEditEmployeeForm] = useState({
    machine_employee_id: '',
    full_name: '',
    notion_name: '',
    department_code: '',
    department_name: '',
    department_id: null as number | null,
    annual_leave_quota: '12',
    is_active: true,
    status: 'ACTIVE',
    employee_code: '',
    position: '',
    contract_salary: '0',
    employee_type: 'FULLTIME',
    dependents_count: '0',
    account_number: '',
    bank_name: '',
    tax_code: '',
    phone_number: '',
    company_phone_number: '',
    social_insurance_number: '',
    username: '',
    password: '',
    start_date: '',
    resignation_period: '',
    last_working_date: '',
    last_pay_date: '',
    bonus_coefficient: '0',
    meal_allowance_free: '1200000',
    meal_allowance_tax: '0',
    phone_allowance_free: '2000000',
    trans_allowance_tax: '2000000',
    perf_allowance_tax: '0',
    other_income: '0',
    bonus: '0',
    bonus_14: '0',
  })

  const [periodStart, setPeriodStart] = useState(DEFAULT_TIMESHEET_RANGE.start)
  const [periodEnd, setPeriodEnd] = useState(DEFAULT_TIMESHEET_RANGE.end)
  const [dashboardKpi, setDashboardKpi] = useState<DashboardKpi | null>(null)
  const [dashboardTrendOpen, setDashboardTrendOpen] = useState(false)
  const [autoRefreshKpi, setAutoRefreshKpi] = useState(false)
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState('30')

  useEffect(() => {
    if (!dashboardTrendOpen) return
    const previousOverflow = document.body.style.overflow
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDashboardTrendOpen(false)
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [dashboardTrendOpen])

  const [timesheetGridRows, setTimesheetGridRows] = useState<TimesheetGridRow[]>([])
  const [timesheetDayColumns, setTimesheetDayColumns] = useState<TimesheetDayColumn[]>([])
  const [timesheetIsLocked, setTimesheetIsLocked] = useState(false)
  const [timesheetDefaultPeriodResolved, setTimesheetDefaultPeriodResolved] = useState(false)
  const [timesheetEmployeeFilter, setTimesheetEmployeeFilter] = useState('')
  const [timesheetDepartmentFilter, setTimesheetDepartmentFilter] = useState('all')
  const [timesheetAbnormalFilter, setTimesheetAbnormalFilter] = useState<TimesheetAbnormalFilter>('all')
  const [timesheetSymbolFilter, setTimesheetSymbolFilter] = useState('all')
  const [timesheetPage, setTimesheetPage] = useState(1)

  const timesheetDepartmentOptions = useMemo(
    () => Array.from(new Set(timesheetGridRows.map((row) => row.department_name ?? 'N/A'))).sort((a, b) => a.localeCompare(b, 'vi')),
    [timesheetGridRows],
  )
  const filteredTimesheetGridRows = useMemo(
    () => filterTimesheetRows(timesheetGridRows, {
      search: timesheetEmployeeFilter,
      department: timesheetDepartmentFilter,
      abnormal: timesheetAbnormalFilter,
      symbol: timesheetSymbolFilter,
    }),
    [timesheetGridRows, timesheetEmployeeFilter, timesheetDepartmentFilter, timesheetAbnormalFilter, timesheetSymbolFilter],
  )
  const timesheetPagination = useMemo(
    () => paginateTimesheetRows(filteredTimesheetGridRows, timesheetPage, TIMESHEET_PAGE_SIZE),
    [filteredTimesheetGridRows, timesheetPage],
  )

  useEffect(() => {
    if (timesheetPage !== timesheetPagination.currentPage) {
      setTimesheetPage(timesheetPagination.currentPage)
    }
  }, [timesheetPage, timesheetPagination.currentPage])


  const [overrideLogs, setOverrideLogs] = useState<OverrideLog[]>([])
  const [overrideHistoryEmployeeId, setOverrideHistoryEmployeeId] = useState('')
  const [overrideHistoryLimit, setOverrideHistoryLimit] = useState('200')
  const [overrideHistoryOpen, setOverrideHistoryOpen] = useState(false)

  useEffect(() => {
    if (!overrideHistoryOpen) return
    const previousOverflow = document.body.style.overflow
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOverrideHistoryOpen(false)
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [overrideHistoryOpen])

  useEffect(() => {
    if (activeTab !== 'timesheets') setOverrideHistoryOpen(false)
  }, [activeTab])


  const isShowingParsedImportPreview = importPreview.length > 0
  const parsedImportColumns = useMemo<ImportTableColumn[]>(() => {
    return collectPreviewColumnKeys(importPreview).map((key) => ({ key, label: formatImportPreviewColumnLabel(key) }))
  }, [importPreview])
  const fallbackSheetRows = selectedSheetInspection?.raw_rows.length
    ? selectedSheetInspection.raw_rows
    : (selectedSheetInspection?.sample_rows ?? [])
  const rawCheckinEmployeeBlocks = useMemo(
    () => (!isShowingParsedImportPreview
      ? mergeEmployeeCheckinBlocks(selectedSheetInspection?.employee_blocks ?? [], employees)
      : []),
    [isShowingParsedImportPreview, selectedSheetInspection, employees],
  )
  const activeImportTableRows: ImportPreviewRow[] = isShowingParsedImportPreview
    ? importPreview
    : fallbackSheetRows
  const activeImportTableColumns = isShowingParsedImportPreview
    ? parsedImportColumns
    : (selectedSheetInspection?.columns ?? []).map((column) => ({ key: column.label, label: column.label }))
  const activeImportSelectedColumnKeys = useMemo(
    () => selectedImportTableColumns.filter((key) => activeImportTableColumns.some((column) => column.key === key)),
    [selectedImportTableColumns, activeImportTableColumns],
  )
  const visibleImportTableColumns = useMemo(
    () => activeImportSelectedColumnKeys.length > 0
      ? activeImportTableColumns.filter((column) => activeImportSelectedColumnKeys.includes(column.key))
      : activeImportTableColumns,
    [activeImportSelectedColumnKeys, activeImportTableColumns],
  )
  const activeImportColumnFilterEntries = useMemo(
    () => Object.entries(importColumnFilters).filter(
      ([columnKey, filterValue]) => filterValue.trim() && activeImportTableColumns.some((column) => column.key === columnKey),
    ),
    [importColumnFilters, activeImportTableColumns],
  )
  const advancedImportFilterColumns = useMemo(
    () => activeImportSelectedColumnKeys.length > 0
      ? visibleImportTableColumns
      : pickSuggestedImportFilterColumns(activeImportTableColumns),
    [activeImportSelectedColumnKeys, visibleImportTableColumns, activeImportTableColumns],
  )
  const importColumnFilterOptions = useMemo(() => Object.fromEntries(
    advancedImportFilterColumns.map((column) => {
      const values = Array.from(new Set(
        activeImportTableRows
          .map((row) => formatImportCellValue(row[column.key]).trim())
          .filter(Boolean),
      )).sort((left, right) => left.localeCompare(right, 'vi', { numeric: true }))
      return [column.key, values]
    }),
  ) as Record<string, string[]>, [advancedImportFilterColumns, activeImportTableRows])
  const visibleImportTableRows = useMemo(() => {
    const keyword = importTableSearch.trim().toLowerCase()
    let nextRows = activeImportTableRows
    if (keyword) {
      nextRows = nextRows.filter((row) =>
        visibleImportTableColumns.some((column) => formatImportCellValue(row[column.key]).toLowerCase().includes(keyword)),
      )
    }
    if (activeImportColumnFilterEntries.length > 0) {
      nextRows = nextRows.filter((row) =>
        activeImportColumnFilterEntries.every(([columnKey, filterValue]) =>
          formatImportCellValue(row[columnKey]).toLowerCase().includes(filterValue.trim().toLowerCase()),
        ),
      )
    }
    return nextRows
  }, [activeImportTableRows, importTableSearch, visibleImportTableColumns, activeImportColumnFilterEntries])
  const employeeBlockPageSizeNumber = Math.max(5, Number(employeeBlockPageSize) || 5)
  const isShowingEmployeeBlockPreview = importType === 'checkin' && !isShowingParsedImportPreview && rawCheckinEmployeeBlocks.length > 0
  const filteredEmployeeBlocks = useMemo(() => {
    return rawCheckinEmployeeBlocks.filter((block) => {
      const matchedEmp = employees.find((emp) => emp.machine_employee_id === block.employee_id)
      const systemName = matchedEmp ? matchedEmp.full_name : ''

      const keywordMatches = !importTableSearch.trim()
        || matchesNormalizedFilter(block.employee_id, importTableSearch)
        || matchesNormalizedFilter(block.employee_name, importTableSearch)
        || (systemName && matchesNormalizedFilter(systemName, importTableSearch))
        || matchesNormalizedFilter(block.department_name, importTableSearch)
        || block.day_entries.some((entry) =>
          matchesNormalizedFilter(
            `${entry.day_label} ${entry.time_values.join(' ')}`,
            importTableSearch,
          ),
        )

      if (!keywordMatches) {
        return false
      }

      const nameFilter = employeeBlockFilters.employee_name.trim()
      const matchesName = !nameFilter
        || matchesNormalizedFilter(block.employee_name, nameFilter)
        || (systemName && matchesNormalizedFilter(systemName, nameFilter))

      return matchesNormalizedFilter(block.employee_id, employeeBlockFilters.employee_id)
        && matchesName
        && matchesNormalizedFilter(block.department_name, employeeBlockFilters.department_name)
    })
  }, [rawCheckinEmployeeBlocks, importTableSearch, employeeBlockFilters, employees])
  const visibleEmployeeBlocks = useMemo(
    () => filteredEmployeeBlocks.slice(0, visibleEmployeeBlockCount),
    [filteredEmployeeBlocks, visibleEmployeeBlockCount],
  )
  const isShowingFallbackSampleRows = !isShowingParsedImportPreview
    && (selectedSheetInspection?.raw_rows.length ?? 0) === 0
    && (selectedSheetInspection?.sample_rows.length ?? 0) > 0
  const activeImportTableTitle = isShowingEmployeeBlockPreview
    ? 'Dữ liệu thô theo từng nhân viên'
    : isShowingParsedImportPreview
      ? 'Dữ liệu đã bóc tách'
      : 'Dữ liệu thô từ file upload'
  const activeImportTableDescription = isShowingEmployeeBlockPreview
    ? 'Raw sheet Hồ sơ check-in đã được gom thành từng nhân viên để bạn kiểm tra đầy đủ mốc giờ mà không bị mất ngữ cảnh dữ liệu.'
    : isShowingParsedImportPreview
    ? 'Bảng đang hiển thị kết quả sau khi áp dụng mapping/logic bóc tách hiện tại.'
    : isShowingFallbackSampleRows
      ? 'Đang hiển thị trước một phần dữ liệu mẫu của sheet đang chọn. Khi đọc chi tiết hoàn tất, bảng này sẽ tự mở rộng ra toàn bộ dữ liệu thô.'
      : 'Bảng đang hiển thị toàn bộ cột và dữ liệu thô của sheet đang chọn. Khi bạn đổi sheet, header row hoặc bấm preview, bảng này sẽ cập nhật theo lựa chọn đó.'
  const importInspectStatusText = isInspectingImportFile
    ? 'Đang phân tích workbook và nhận diện cấu trúc sheet...'
    : isLoadingImportSheetRows
      ? `Đang nạp toàn bộ dữ liệu thô cho sheet ${selectedImportSheet || '-'}. Bạn vẫn có thể xem mapping hiện tại trong lúc hệ thống đọc tiếp dữ liệu.`
      : ''

  function resetImportTableFilters() {
    setImportTableSearch('')
    setImportColumnFilters({})
    setSelectedImportTableColumns([])
    setEmployeeBlockFilters({
      employee_id: '',
      employee_name: '',
      department_name: '',
    })
    setVisibleEmployeeBlockCount(Math.max(5, Number(employeeBlockPageSize) || 5))
  }

  function selectImportTableColumn(columnKey: string) {
    setSelectedImportTableColumns(columnKey ? [columnKey] : [])
  }

  function updateImportColumnFilter(columnKey: string, value: string) {
    setImportColumnFilters((prev) => {
      if (!value.trim()) {
        const next = { ...prev }
        delete next[columnKey]
        return next
      }
      return { ...prev, [columnKey]: value }
    })
  }

  function updateEmployeeBlockFilter(field: 'employee_id' | 'employee_name' | 'department_name', value: string) {
    setEmployeeBlockFilters((prev) => ({
      ...prev,
      [field]: value,
    }))
    setVisibleEmployeeBlockCount(Math.max(5, Number(employeeBlockPageSize) || 5))
  }

  function changeEmployeeBlockPageSize(value: string) {
    const nextPageSize = Math.max(5, Number(value) || 5)
    setEmployeeBlockPageSize(String(nextPageSize))
    setVisibleEmployeeBlockCount(nextPageSize)
  }

  function showMoreEmployeeBlocks() {
    setVisibleEmployeeBlockCount((prev) => prev + employeeBlockPageSizeNumber)
  }

  async function apiRequest(path: string, init?: RequestInit) {
    const headers = new Headers(init?.headers)
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    
    let response: Response
    try {
      response = await fetch(`${apiBase}${path}`, {
        ...init,
        headers,
        credentials: 'include',
      })
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error(`Không kết nối được API backend tại ${apiBase}. Hãy kiểm tra backend đang chạy và CORS cho cổng frontend hiện tại.`, { cause: error })
      }
      throw error
    }

    if (response.status === 401) {
      handleLogout()
      throw new Error('Phiên đăng nhập hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại.')
    }

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({ detail: 'Lỗi không xác định' }))
      let errMsg = 'Lỗi gọi API'
      if (errorPayload.detail) {
        if (typeof errorPayload.detail === 'string') {
          errMsg = errorPayload.detail
        } else if (Array.isArray(errorPayload.detail)) {
          errMsg = errorPayload.detail.map((err: any) => err.msg || JSON.stringify(err)).join(', ')
        } else {
          errMsg = JSON.stringify(errorPayload.detail)
        }
      }
      throw new Error(errMsg)
    }
    notifyDataChanged(`${apiBase}${path}`, init?.method)
    return response
  }

  function extractFilename(disposition: string | null, fallbackFilename: string) {
    if (!disposition) {
      return fallbackFilename
    }

    const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i)
    if (utfMatch?.[1]) {
      return decodeURIComponent(utfMatch[1])
    }

    const plainMatch = disposition.match(/filename="?([^";]+)"?/i)
    if (plainMatch?.[1]) {
      return plainMatch[1]
    }

    return fallbackFilename
  }

  function triggerBrowserDownload(blob: Blob, filename: string) {
    const href = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = href
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(href)
  }

  function hasCustomMappingOverride(nextImportType: ImportType, sheet: WorkbookSheetInspection | null) {
    const suggestedMapping = buildSuggestedMapping(sheet, nextImportType)
    return getImportFields(nextImportType).some((field) => (customColumnMapping[field] ?? '') !== (suggestedMapping[field] ?? ''))
  }

  function shouldUseSelectedSheetPreview() {
    if (!workbookInspection || !selectedSheetInspection) {
      return false
    }

    const recommendedSheetName = workbookInspection.recommended_sheet_name ?? ''
    const recommendedHeaderRowIndex = String(workbookInspection.recommended_header_row_index ?? selectedSheetInspection.header_row_index)

    if (importMode === 'custom') {
      return true
    }

    if ((selectedImportSheet || '') !== recommendedSheetName) {
      return true
    }

    if ((selectedHeaderRowIndex || '0') !== recommendedHeaderRowIndex) {
      return true
    }

    return hasCustomMappingOverride(importType, selectedSheetInspection)
  }

  function buildSuggestedMapping(sheet: WorkbookSheetInspection | null, nextImportType: ImportType) {
    const nextMapping: Record<string, string> = {}
    if (!sheet) {
      return nextMapping
    }
    for (const field of getImportFields(nextImportType)) {
      const columnIndex = sheet.suggested_mapping[field]
      if (typeof columnIndex === 'number') {
        nextMapping[field] = String(columnIndex)
      }
    }
    return nextMapping
  }

  function applySheetSuggestion(sheet: WorkbookSheetInspection | null, nextImportType: ImportType) {
    if (!sheet) {
      setSelectedSheetInspection(null)
      setSelectedImportSheet('')
      setSelectedHeaderRowIndex('0')
      setCustomColumnMapping({})
      return
    }
    const nextMapping = buildSuggestedMapping(sheet, nextImportType)
    setSelectedSheetInspection(sheet)
    setSelectedImportSheet(sheet.sheet_name)
    setSelectedHeaderRowIndex(String(sheet.header_row_index))
    setCustomColumnMapping(nextMapping)
    if (nextImportType === 'checkin' && sheet.period_start && sheet.period_end) {
      setPeriodStart(sheet.period_start)
      setPeriodEnd(sheet.period_end)
    }
  }

  async function inspectSelectedSheet(
    file: File,
    nextImportType: ImportType,
    sheetName: string,
    headerRowIndex: string,
  ): Promise<WorkbookSheetInspection> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('import_type', nextImportType)
    formData.append('sheet_name', sheetName)
    formData.append('header_row_index', headerRowIndex)

    const response = await apiRequest('/api/import/sheet-inspect', { method: 'POST', body: formData })
    const payload = (await response.json()) as WorkbookSheetInspection
    applySheetSuggestion(payload, nextImportType)
    return payload
  }

  async function inspectSelectedSheetSafely(
    file: File,
    nextImportType: ImportType,
    sheet: WorkbookSheetInspection,
    headerRowIndex: string,
  ): Promise<SheetInspectAttemptResult> {
    applySheetSuggestion(buildSheetInspectionFallback(sheet), nextImportType)
    setIsLoadingImportSheetRows(true)
    try {
      const detailedSheet = await inspectSelectedSheet(file, nextImportType, sheet.sheet_name, headerRowIndex)
      return { sheet: detailedSheet, loadedDetailedRows: true, errorMessage: null }
    } catch (error) {
      return {
        sheet: buildSheetInspectionFallback(sheet),
        loadedDetailedRows: false,
        errorMessage: (error as Error).message,
      }
    } finally {
      setIsLoadingImportSheetRows(false)
    }
  }

  async function inspectImportFile(file: File, nextImportType: ImportType): Promise<WorkbookInspection> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('import_type', nextImportType)
    const response = await apiRequest('/api/import/workbook-inspect', { method: 'POST', body: formData })
    const payload = (await response.json()) as WorkbookInspection
    setWorkbookInspection(payload)

    const recommendedSheet = payload.recommended_sheet_name
      ? payload.sheets.find((sheet) => sheet.sheet_name === payload.recommended_sheet_name) ?? null
      : null
    const initialSheet = pickDefaultInspectionSheet(payload, nextImportType)
    let detailedInspectError: string | null = null
    if (initialSheet) {
      const inspectResult = await inspectSelectedSheetSafely(file, nextImportType, initialSheet, String(initialSheet.header_row_index))
      detailedInspectError = inspectResult.errorMessage
    } else {
      applySheetSuggestion(null, nextImportType)
    }

    const autoReady = payload.recommended_mapping
      ? getRequiredImportFields(nextImportType).every((field) => typeof payload.recommended_mapping[field] === 'number')
      : false
    setImportMode(autoReady ? 'auto' : 'custom')
    if (recommendedSheet) {
      setMessage(
        detailedInspectError
          ? `Đã nhận diện ${payload.sheets.length} sheet. Gợi ý: ${payload.recommended_sheet_name}. Chưa tải được dữ liệu chi tiết: ${detailedInspectError}`
          : `Đã nhận diện ${payload.sheets.length} sheet. Gợi ý: ${payload.recommended_sheet_name}.`
      )
    } else {
      setMessage(
        detailedInspectError
          ? `Đã nhận diện ${payload.sheets.length} sheet nhưng chưa có sheet nào đủ cột bắt buộc để auto-map. Hệ thống đang mở dữ liệu mẫu của sheet ${initialSheet?.sheet_name ?? '-'}; đọc chi tiết đang lỗi: ${detailedInspectError}`
          : `Đã nhận diện ${payload.sheets.length} sheet nhưng chưa có sheet nào đủ cột bắt buộc để auto-map. Hệ thống đang mở dữ liệu thô của sheet ${initialSheet?.sheet_name ?? '-'} để bạn xem toàn bộ trước khi lọc.`
      )
    }
    return payload
  }

  async function setAndInspectImportFile(file: File | null, nextImportType: ImportType = importType) {
    if (!file) {
      return
    }
    setImportFile(file)
    setIsImportPreviewDetailsOpen(false)
    resetImportTableFilters()
    setImportPreview([])
    setAttendanceJsonEmployees([])
    setAttendanceValidationSummary({})
    setIsInspectingImportFile(true)
    setLoading(true)
    try {
      await inspectImportFile(file, nextImportType)
    } catch (error) {
      setWorkbookInspection(null)
      setSelectedSheetInspection(null)
      setSelectedImportSheet('')
      setSelectedHeaderRowIndex('0')
      setCustomColumnMapping({})
      setMessage(`Không nhận diện được file import: ${(error as Error).message}`)
    } finally {
      setIsInspectingImportFile(false)
      setLoading(false)
    }
  }

  async function onImportFileChange(event: ChangeEvent<HTMLInputElement>) {
    await setAndInspectImportFile(event.target.files?.[0] ?? null)
  }

  /*
  function handleStartDateChange(event: ChangeEvent<HTMLInputElement>) {
    setPeriodStart(event.target.value)
  }

  function handleEndDateChange(event: ChangeEvent<HTMLInputElement>) {
    setPeriodEnd(event.target.value)
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    void onImportFileChange(event)
  }

  function handleReadFile() {
    importToolbarFormRef.current?.requestSubmit()
  }

  function handleReadNotionFile() {
    void handleAttendanceJsonParse()
  }
  */

  function handleSaveData() {
    void handleCommit()
  }

  function onNotionFileChange(event: ChangeEvent<HTMLInputElement>) {
    setNotionFile(event.target.files?.[0] ?? null)
  }

  function clearNotionFile() {
    setNotionFile(null)
    if (notionFileInputRef.current) {
      notionFileInputRef.current.value = ''
    }
  }

  async function handleImportPreview(event: FormEvent) {
    event.preventDefault()
    if (!importFile) {
      setMessage('Vui lòng chọn file trước khi preview.')
      return
    }

    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('file', importFile)
      let path = importType === 'checkin' ? '/api/import/checkin-profile' : '/api/import/abnormal-report'
      const useSelectedSheetPreview = shouldUseSelectedSheetPreview()

      if (importMode === 'custom' || useSelectedSheetPreview) {
        const missingFields = getRequiredImportFields(importType).filter((field) => !customColumnMapping[field])
        if (missingFields.length > 0) {
          setMessage(`Chưa map đủ trường bắt buộc: ${missingFields.join(', ')}`)
          return
        }

        const customMappingPayload: Record<string, number> = {}
        for (const field of getImportFields(importType)) {
          const mappedValue = customColumnMapping[field]
          if (mappedValue) {
            customMappingPayload[field] = Number(mappedValue)
          }
        }

        path = '/api/import/custom-preview'
        formData.append('import_type', importType)
        if (selectedImportSheet) {
          formData.append('sheet_name', selectedImportSheet)
        }
        formData.append('header_row_index', selectedHeaderRowIndex)
        formData.append('column_mapping_json', JSON.stringify(customMappingPayload))
      }

      const response = await apiRequest(path, { method: 'POST', body: formData })
      const payload = (await response.json()) as { rows?: number; preview?: ImportPreviewRow[] }
      const preview = Array.isArray(payload.preview) ? payload.preview : []
      setImportPreview(preview)
      setMessage(`Preview thành công: ${preview.length} dòng hiển thị.`)
    } catch (error) {
      setMessage(`Preview thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleAttendanceJsonParse() {
    if (!importFile) {
      setMessage('Vui lòng chọn file workbook 5 sheet trước khi parse JSON.')
      return
    }

    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('file', importFile)
      if (notionFile) {
        formData.append('notion_file', notionFile)
      }
      if (parserPeriodStart) {
        formData.append('period_start', parserPeriodStart)
      }

      const response = await apiRequest('/api/import/attendance-json', { method: 'POST', body: formData })
      const payload = (await response.json()) as {
        employees?: AttendanceJsonEmployee[]
        validation_summary?: Record<string, AttendanceValidationSummaryRow>
      }

      const employees = Array.isArray(payload.employees) ? payload.employees : []
      const validationSummary = payload.validation_summary && typeof payload.validation_summary === 'object'
        ? payload.validation_summary
        : {}

      setAttendanceJsonEmployees(employees)
      setAttendanceValidationSummary(validationSummary)
      setMessage(`Parse JSON 5 sheet thành công: ${employees.length} nhân viên.`)
    } catch (error) {
      setMessage(`Parse JSON 5 sheet thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleCommit() {
    if (importType !== 'checkin') {
      setMessage('Commit hiện hỗ trợ luồng checkin profile.')
      return
    }
    if (importPreview.length === 0 || !importFile) {
      setMessage('Chưa có dữ liệu preview để commit.')
      return
    }

    const first = importPreview[0]
    const payload = {
      file_name: importFile.name,
      period_start: String(first.period_start ?? periodStart),
      period_end: String(first.period_end ?? periodEnd),
      items: importPreview.map((row) => ({
        machine_employee_id: String(row.machine_employee_id ?? ''),
        work_date: String(row.work_date ?? ''),
        check_in: row.check_in_time ? String(row.check_in_time) : null,
        check_out: row.check_out_time ? String(row.check_out_time) : null,
        period_start: row.period_start ? String(row.period_start) : null,
        period_end: row.period_end ? String(row.period_end) : null,
        raw_times: String(row.raw_time_values ?? row.raw_times ?? ''),
        department: row.department_name ? String(row.department_name) : null,
        error: row.missing_reason ? String(row.missing_reason) : null,
        attendance_symbol: row.attendance_symbol ? String(row.attendance_symbol) : null,
      })),
    }

    setLoading(true)
    try {
      const response = await apiRequest('/api/import/checkin-profile/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const result = await response.json()
      setMessage(`Commit thành công. Batch #${result.batch_id}, inserted=${result.inserted}.`)
      loadTimesheets()
    } catch (error) {
      setMessage(`Commit thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  // Hàm convert dữ liệu từ EmployeeBlockPreview (rawCheckinEmployeeBlocks) sang commit payload.
  // Dùng khi admin đang xem bảng dạng block (hồ sơ check-in theo từng nhân viên) và bấm "Lưu vào hệ thống".
  function resolveWorkDateFromBlock(dayLabel: string, pStart: string, pEnd: string): string {
    // dayLabel là số ngày (vd "23", "4", "15"). pStart và pEnd là "YYYY-MM-DD"
    const dayNum = parseInt(dayLabel, 10)
    if (isNaN(dayNum)) return ''
    const [startYear, startMonth] = pStart.split('-').map(Number)
    const [endYear, endMonth] = pEnd.split('-').map(Number)

    // Kỳ công từ ngày 23 tháng này đến ngày 22 tháng sau.
    // Nếu dayNum >= 23: thuộc tháng bắt đầu (startMonth/startYear)
    // Nếu dayNum <= 22: thuộc tháng kết thúc (endMonth/endYear)
    let year: number
    let month: number
    if (dayNum >= 23) {
      year = startYear
      month = startMonth
    } else {
      year = endYear
      month = endMonth
    }
    return `${year}-${String(month).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`
  }

  async function handleCommitFromBlocks() {
    if (!importFile) {
      setMessage('Chưa chọn file để commit.')
      return
    }
    if (rawCheckinEmployeeBlocks.length === 0) {
      setMessage('Không có dữ liệu block để commit. Hãy upload và đọc file trước.')
      return
    }
    if (!periodStart || !periodEnd) {
      setMessage('Vui lòng nhập ngày bắt đầu và ngày kết thúc trước khi lưu.')
      return
    }

    // Convert rawCheckinEmployeeBlocks → flat commit items
    const items: {
      machine_employee_id: string
      work_date: string
      check_in: string | null
      check_out: string | null
      period_start: string
      period_end: string
      raw_times: string
      department: string | null
      error: string | null
      attendance_symbol: string | null
    }[] = []

    for (const block of rawCheckinEmployeeBlocks) {
      for (const entry of block.day_entries) {
        const workDate = resolveWorkDateFromBlock(entry.day_label, periodStart, periodEnd)
        if (!workDate) continue

        const times = entry.time_values.filter(Boolean)
        const rawTimes = times.join(', ')

        // Lấy giờ vào đầu tiên và giờ ra cuối cùng từ time_values
        const timeRegex = /^([01]?\d|2[0-3]):[0-5]\d$/
        const validTimes = times.filter((t) => timeRegex.test(t.replace(/\*/g, '').trim()))
        const checkIn = validTimes.length > 0 ? validTimes[0].replace(/\*/g, '').trim() : null
        const checkOut = validTimes.length > 1 ? validTimes[validTimes.length - 1].replace(/\*/g, '').trim() : null

        // Xác định lỗi: chỉ có 1 mốc = thiếu check-out
        const errorReason = validTimes.length === 1
          ? 'missing_checkout'
          : validTimes.length === 0
            ? 'missing_all'
            : null

         items.push({
          machine_employee_id: block.employee_id,
          work_date: workDate,
          check_in: checkIn,
          check_out: checkOut,
          period_start: periodStart,
          period_end: periodEnd,
          raw_times: rawTimes,
          department: block.department_name || null,
          error: errorReason,
          attendance_symbol: entry.attendance_symbol || null,
        })
      }
    }

    if (items.length === 0) {
      setMessage('Không có dữ liệu ngày hợp lệ để commit từ block preview.')
      return
    }

    const payload = {
      file_name: importFile.name,
      period_start: periodStart,
      period_end: periodEnd,
      items,
    }

    setLoading(true)
    try {
      const response = await apiRequest('/api/import/checkin-profile/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const result = await response.json()
      const skippedCount = Array.isArray(result.skipped) ? result.skipped.length : 0
      setMessage(
        `Đã lưu thành công từ bảng block. Batch #${result.batch_id} | Đã lưu: ${result.inserted} ngày | Bỏ qua: ${skippedCount} (chưa có trong hệ thống nhân sự).`
      )
      loadTimesheets()
    } catch (error) {
      setMessage(`Lưu thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function loadDepartments() {
    if (!['ADMIN', 'DIRECTOR', 'HR_ADMIN', 'IT_ADMIN'].includes(currentUser?.role || '')) return
    try {
      const response = await apiRequest(currentUser?.role === 'HR_ADMIN' ? '/api/hr/departments' : '/api/departments')
      const payload = await response.json()
      setDepartments(payload)
    } catch (error) {
      console.error('Không tải được phòng ban:', error)
    }
  }

  async function loadEmployees() {
    if (!['ADMIN', 'DIRECTOR', 'HR_ADMIN', 'IT_ADMIN'].includes(currentUser?.role || '')) return
    setLoading(true)
    try {
      const baseEndpoint = currentUser?.role === 'HR_ADMIN' ? '/api/hr/employees' : '/api/employees'
      const response = await apiRequest(baseEndpoint)
      const payload = (await response.json()) as Employee[]
      setEmployees(payload)
      loadDepartments()

      if (isBusinessAdminRole(currentUser?.role)) {
        const inputRes = await apiRequest(`/api/salary/inputs?period=${salaryPeriod}`)
        const inputData = await inputRes.json()
        setSalaryInputs(inputData)
      }

      setMessage(`Đã tải ${payload.length} nhân viên.`)
    } catch (error) {
      setMessage(`Không tải được nhân viên: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function createEmployee(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setEmployeeError(null)
    try {
      await apiRequest('/api/employees', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...employeeForm,
          annual_leave_quota: Number(employeeForm.annual_leave_quota),
          contract_salary: Number(employeeForm.contract_salary),
          meal_allowance: Number(employeeForm.meal_allowance),
          phone_allowance: Number(employeeForm.phone_allowance),
          trans_allowance: Number(employeeForm.trans_allowance),
          other_allowance: Number(employeeForm.other_allowance),
          dependents_count: Number(employeeForm.dependents_count),
          bonus_coefficient: Number(employeeForm.bonus_coefficient),
          contract_type: employeeForm.contract_type || null,
          contract_sign_date: employeeForm.contract_sign_date || null,
          contract_start_date: isFixedTermEmployeeContract(employeeForm.contract_type)
            ? employeeForm.contract_start_date || null
            : null,
          contract_end_date: isFixedTermEmployeeContract(employeeForm.contract_type)
            ? employeeForm.contract_end_date || null
            : null,
          username: employeeForm.username.trim() || null,
          password: employeeForm.password.trim() || null,
        }),
      })
      setEmployeeForm(EMPTY_EMPLOYEE_FORM)
      setIsEmployeeModalOpen(false)
      await loadEmployees()
      setMessage('Tạo nhân viên thành công.')
    } catch (error) {
      const errMsg = (error as Error).message
      setEmployeeError(errMsg)
      setMessage(`Tạo nhân viên thất bại: ${errMsg}`)
      window.alert(`Tạo nhân viên thất bại:\n${errMsg}`)
    } finally {
      setLoading(false)
    }
  }

  function startEditEmployee(employee: Employee) {
    const inp = salaryInputs.find((x: any) => x.employee_id === employee.id)
    const monthlyDefaults = getMonthlyAllowanceDefaults(employee.employee_type)
    setEditingEmployeeId(employee.id)
    setEmployeeError(null)
    setEditEmployeeForm({
      machine_employee_id: employee.machine_employee_id,
      full_name: employee.full_name,
      notion_name: employee.notion_name ?? '',
      department_code: employee.department_code ?? '',
      department_name: employee.department_name ?? '',
      department_id: employee.department_id ?? null,
      annual_leave_quota: String(employee.annual_leave_quota),
      is_active: employee.is_active,
      status: employee.status ?? 'ACTIVE',
      employee_code: employee.employee_code ?? '',
      position: employee.position ?? '',
      contract_salary: String(employee.contract_salary),
      employee_type: employee.employee_type,
      dependents_count: String(employee.dependents_count),
      account_number: employee.account_number ?? '',
      bank_name: employee.bank_name ?? '',
      tax_code: employee.tax_code ?? '',
      phone_number: employee.phone_number ?? '',
      company_phone_number: employee.company_phone_number ?? '',
      social_insurance_number: employee.social_insurance_number ?? '',
      username: employee.username ?? '',
      password: '',
      start_date: employee.start_date ?? '',
      resignation_period: employee.resignation_period ?? '',
      last_working_date: employee.last_working_date ?? '',
      last_pay_date: employee.last_pay_date ?? '',
      bonus_coefficient: String(employee.bonus_coefficient ?? 0),
      meal_allowance_free: String(inp?.meal_allowance_free ?? monthlyDefaults.meal_allowance_free),
      meal_allowance_tax: String(inp?.meal_allowance_tax ?? monthlyDefaults.meal_allowance_tax),
      phone_allowance_free: String(inp?.phone_allowance_free ?? monthlyDefaults.phone_allowance_free),
      trans_allowance_tax: String(inp?.trans_allowance_tax ?? monthlyDefaults.trans_allowance_tax),
      perf_allowance_tax: String(inp?.perf_allowance_tax ?? monthlyDefaults.perf_allowance_tax),
      other_income: String(inp?.other_income ?? 0),
      bonus: String(inp?.bonus ?? 0),
      bonus_14: String(inp?.bonus_14 ?? 0),
    })
  }

  async function saveEmployeeInline(employeeId: number) {
    setLoading(true)
    setEmployeeError(null)
    try {
      await apiRequest(`/api/employees/${employeeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          machine_employee_id: editEmployeeForm.machine_employee_id,
          full_name: editEmployeeForm.full_name,
          notion_name: editEmployeeForm.notion_name,
          department_code: editEmployeeForm.department_code,
          department_name: editEmployeeForm.department_name,
          department_id: editEmployeeForm.department_id,
          annual_leave_quota: Number(editEmployeeForm.annual_leave_quota),
          is_active: editEmployeeForm.is_active,
          status: editEmployeeForm.status,
          bonus_coefficient: Number(editEmployeeForm.bonus_coefficient),
          employee_code: editEmployeeForm.employee_code || null,
          position: editEmployeeForm.position || null,
          contract_salary: Number(String(editEmployeeForm.contract_salary).replace(/\D/g, '') || 0),
          employee_type: editEmployeeForm.employee_type,
          dependents_count: Number(editEmployeeForm.dependents_count),
          account_number: editEmployeeForm.account_number || null,
          bank_name: editEmployeeForm.bank_name || null,
          tax_code: editEmployeeForm.tax_code || null,
          phone_number: editEmployeeForm.phone_number || null,
          company_phone_number: editEmployeeForm.company_phone_number || null,
          social_insurance_number: editEmployeeForm.social_insurance_number || null,
          username: editEmployeeForm.username || null,
          password: editEmployeeForm.password || null,
          start_date: editEmployeeForm.start_date || null,
          resignation_period: editEmployeeForm.resignation_period || null,
          last_working_date: editEmployeeForm.last_working_date || null,
          last_pay_date: editEmployeeForm.last_pay_date || null,
        }),
      })

      const existingInput = salaryInputs.find((x: any) => x.employee_id === employeeId)
      const stdDays = calculatePeriodWorkingDays(salaryPeriod)
      await apiRequest('/api/salary/inputs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([{
          employee_id: employeeId,
          salary_period: salaryPeriod,
          actual_working_days: existingInput?.actual_working_days ?? stdDays,
          meal_allowance_free: Number(editEmployeeForm.meal_allowance_free),
          meal_allowance_tax: Number(editEmployeeForm.meal_allowance_tax),
          phone_allowance_free: Number(editEmployeeForm.phone_allowance_free),
          trans_allowance_tax: Number(editEmployeeForm.trans_allowance_tax),
          perf_allowance_tax: Number(editEmployeeForm.perf_allowance_tax),
          other_income: Number(editEmployeeForm.other_income),
          bonus: Number(editEmployeeForm.bonus),
          bonus_14: Number(editEmployeeForm.bonus_14),
          advance_payment: existingInput?.advance_payment ?? 0,
          pit_refund: existingInput?.pit_refund ?? 0,
          other_deductions: existingInput?.other_deductions ?? 0,
        }]),
      })

      setEditingEmployeeId(null)
      await loadEmployees()
      setMessage(`Đã cập nhật nhân viên #${employeeId}.`)
    } catch (error) {
      const errMsg = (error as Error).message
      setEmployeeError(errMsg)
      setMessage(`Cập nhật nhân viên thất bại: ${errMsg}`)
      window.alert(`Cập nhật nhân viên thất bại:\n${errMsg}`)
    } finally {
      setLoading(false)
    }
  }

  async function uploadFile(type: 'cccd' | 'contract', fileList: FileList) {
    if (!detailEmployee) return
    setLoading(true)
    setEmployeeError(null)
    const formData = new FormData()
    for (let i = 0; i < fileList.length; i++) {
      formData.append('files', fileList[i])
    }
    try {
      const response = await apiRequest(`/api/employees/${detailEmployee.id}/upload-${type}`, {
        method: 'POST',
        body: formData,
      })
      const updatedEmp = await response.json()
      setDetailEmployee(employeeWithDerivedUsername(updatedEmp))
      setMessage(`Upload ${type.toUpperCase()} thành công.`)
      await loadEmployees()
    } catch (error) {
      const errMsg = (error as Error).message
      setEmployeeError(errMsg)
      setMessage(`Upload thất bại: ${errMsg}`)
    } finally {
      setLoading(false)
    }
  }

  async function deleteFile(type: 'cccd' | 'contract', url: string) {
    if (!detailEmployee) return
    if (!await confirm({ title: 'Xóa tài liệu', message: 'Bạn có chắc chắn muốn xóa tài liệu này?', confirmLabel: 'Xóa', tone: 'danger' })) return
    setLoading(true)
    setEmployeeError(null)
    try {
      const response = await apiRequest(`/api/employees/${detailEmployee.id}/delete-document`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, doc_type: type }),
      })
      const updatedEmp = await response.json()
      setDetailEmployee(employeeWithDerivedUsername(updatedEmp))
      setMessage(`Xóa tài liệu thành công.`)
      await loadEmployees()
    } catch (error) {
      const errMsg = (error as Error).message
      setEmployeeError(errMsg)
      setMessage(`Xóa tài liệu thất bại: ${errMsg}`)
    } finally {
      setLoading(false)
    }
  }

  async function openDocument(url: string, download = false) {
    try {
      const response = await apiRequest(url)
      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      if (download) {
        const link = document.createElement('a')
        link.href = objectUrl
        link.download = url.split('/').pop() || 'document'
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
        return
      }
      setPreviewUrl(objectUrl)
    } catch (error) {
      const errMsg = (error as Error).message
      setEmployeeError(errMsg)
      setMessage(`Không thể mở tài liệu: ${errMsg}`)
    }
  }

  async function saveEmployeeDetail() {
    if (!detailEmployee) return
    setLoading(true)
    setEmployeeError(null)
    try {
      const accountPassword = detailEmployeePassword.trim()
      const shouldSaveLoginAccount = Boolean(detailEmployee.account_role || accountPassword)
      await apiRequest(`/api/employees/${detailEmployee.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          machine_employee_id: detailEmployee.machine_employee_id,
          full_name: detailEmployee.full_name,
          notion_name: detailEmployee.notion_name,
          department_code: detailEmployee.department_code,
          department_name: detailEmployee.department_name,
          department_id: detailEmployee.department_id,
          annual_leave_quota: Number(detailEmployee.annual_leave_quota),
          is_active: detailEmployee.is_active,
          status: detailEmployee.status,
          employee_code: detailEmployee.employee_code || null,
          position: detailEmployee.position || null,
          contract_salary: Number(String(detailEmployee.contract_salary).replace(/\D/g, '') || 0),
          meal_allowance: Number(detailEmployee.meal_allowance || 0),
          phone_allowance: Number(detailEmployee.phone_allowance || 0),
          trans_allowance: Number(detailEmployee.trans_allowance || 0),
          other_allowance: Number(detailEmployee.other_allowance || 0),
          bonus_coefficient: Number(detailEmployee.bonus_coefficient || 0),
          employee_type: detailEmployee.employee_type,
          employee_type_effective_date: detailEmployee.employee_type !== detailEmployeeOriginalType
            ? detailEmployeeTypeEffectiveDate || null
            : null,
          dependents_count: Number(detailEmployee.dependents_count),
          account_number: detailEmployee.account_number || null,
          bank_name: detailEmployee.bank_name || null,
          tax_code: detailEmployee.tax_code || null,
          phone_number: detailEmployee.phone_number || null,
          company_phone_number: detailEmployee.company_phone_number || null,
          social_insurance_number: detailEmployee.social_insurance_number || null,
          pvi_insurance: detailEmployee.pvi_insurance || null,
          health_insurance_number: detailEmployee.health_insurance_number || null,
          company_email: detailEmployee.company_email || null,
          personal_email: detailEmployee.personal_email || null,
          notes: detailEmployee.notes || null,
          username: shouldSaveLoginAccount ? detailEmployee.username || null : null,
          password: accountPassword || null,
          start_date: detailEmployee.start_date || null,
          contract_type: detailEmployee.contract_type || null,
          contract_sign_date: detailEmployee.contract_sign_date || null,
          contract_start_date: isFixedTermEmployeeContract(detailEmployee.contract_type)
            ? detailEmployee.contract_start_date || null
            : null,
          contract_end_date: isFixedTermEmployeeContract(detailEmployee.contract_type)
            ? detailEmployee.contract_end_date || null
            : null,
          resignation_period: detailEmployee.resignation_period || null,
          last_working_date: detailEmployee.last_working_date || null,
          last_pay_date: detailEmployee.last_pay_date || null,
        }),
      })
      await Promise.all([loadEmployees(), loadSalaryData()])
      setMessage('Cập nhật nhân viên thành công.')
      setDetailEmployeePassword('')
      setDetailEmployee(null)
    } catch (error) {
      const errMsg = (error as Error).message
      setEmployeeError(errMsg)
      setMessage(`Cập nhật thất bại: ${errMsg}`)
    } finally {
      setLoading(false)
    }
  }

  async function deleteEmployee(employee: Employee) {
    const confirmed = await confirm({ title: 'Xóa hồ sơ nhân viên', message: `Bạn có chắc chắn muốn xóa hồ sơ ${employee.full_name} (${employee.machine_employee_id})?`, confirmLabel: 'Xóa', tone: 'danger' })
    if (!confirmed) {
      return
    }

    setLoading(true)
    try {
      await apiRequest(`/api/employees/${employee.id}`, { method: 'DELETE' })
      if (editingEmployeeId === employee.id) {
        setEditingEmployeeId(null)
      }
      await loadEmployees()
      setMessage(`Đã xóa nhân viên ${employee.full_name}.`)
    } catch (error) {
      setMessage(`Xóa nhân viên thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  const salarySummaries = useMemo(() => {
    // ─ Tổng hợp toàn bộ (Chính thức + Thử việc) ─
    let transfer = 0   // Σ(Lương NET + Hoàn thuế PIT − Đoàn phí − Khấu trừ khác)
    let ins     = 0   // Σ(BH_NLĐ_10.5% + BH_DN_21.5%)
    let pit     = 0   // Σ(PIT chính thức biểu lũy tiến + PIT thử việc 10%)
    let actual  = 0   // Σ(Lương_HĐLĐ / 26 * Ngày_công_thực)

    for (const emp of salaryEmployees) {
      // TRAINEE belongs to Khối C and is stipend-only outside payroll.
      if (emp.employee_type === 'TRAINEE') continue
      const input  = salaryInputs.find(x => x.employee_id === emp.id)
      const edited = editedInputs[emp.id] || {}

      const workingDays = edited.actual_working_days !== undefined ? Number(edited.actual_working_days) : (input?.actual_working_days ?? 0)
      const mealFree    = edited.meal_allowance_free  !== undefined ? Number(edited.meal_allowance_free)  : (input?.meal_allowance_free  ?? 0)
      const mealTax     = edited.meal_allowance_tax   !== undefined ? Number(edited.meal_allowance_tax)   : (input?.meal_allowance_tax   ?? 0)
      const phoneFree   = edited.phone_allowance_free !== undefined ? Number(edited.phone_allowance_free) : (input?.phone_allowance_free ?? 0)
      const transTax    = edited.trans_allowance_tax  !== undefined ? Number(edited.trans_allowance_tax)  : (input?.trans_allowance_tax  ?? 0)
      const perfTax     = edited.perf_allowance_tax   !== undefined ? Number(edited.perf_allowance_tax)   : (input?.perf_allowance_tax   ?? 0)
      const otherInc    = edited.other_income         !== undefined ? Number(edited.other_income)         : (input?.other_income         ?? 0)
      const bonus       = edited.bonus                !== undefined ? Number(edited.bonus)                : (input?.bonus                ?? 0)
      const bonus14     = edited.bonus_14             !== undefined ? Number(edited.bonus_14)             : (input?.bonus_14             ?? 0)
      const salesBonus  = input?.sales_bonus ?? 0
      const advance     = edited.advance_payment      !== undefined ? Number(edited.advance_payment)      : (input?.advance_payment      ?? 0)
      const pitRefund   = edited.pit_refund           !== undefined ? Number(edited.pit_refund)           : (input?.pit_refund           ?? 0)
      const otherDed    = edited.other_deductions     !== undefined ? Number(edited.other_deductions)     : (input?.other_deductions     ?? 0)

      const res = cake_salary({
        type: emp.employee_type as any,
        contract_salary: emp.contract_salary,
        actual_working_days: workingDays,
        standard_working_days: calculatePeriodWorkingDays(salaryPeriod),
        meal_allowance_free: mealFree,
        meal_allowance_tax: mealTax,
        phone_allowance_free: phoneFree,
        trans_allowance_tax: transTax,
        perf_allowance_tax: perfTax,
        other_income: otherInc,
        bonus: bonus + salesBonus,
        bonus_14: bonus14,
        dependents_count: emp.dependents_count,
        other_deductions: otherDed,
        pit_refund: pitRefund,
        advance_payment: advance,
      }, salaryPolicy)

      // ─ Tổng thực chuyển = net_salary + hoàn thuế − khấu trừ khác − tạm ứng
      // Dùng final_transfer để phản ánh đúng số tiền thực ra ngân hàng
      transfer += Math.max(0, res.final_transfer)

      // ─ Tổng bảo hiểm (NLĐ chịu + DN chịu) — chỉ tính FULLTIME
      ins     += res.total_ins_emp + res.total_ins_comp

      // ─ Tổng thuế TNCN (cả chính thức lũy tiến + thử việc 10%)
      pit     += res.pit_tax

      // ─ Tổng lương thực tế (luôn tính, kể cả thử việc)
      actual  += res.actual_salary
    }

    return { transfer, ins, pit, actual }
  }, [salaryEmployees, salaryInputs, editedInputs, salaryPeriod, salaryPolicy])

  // Salary / Payroll Handlers
  async function loadSalaryPeriods() {
    if (!isBusinessAdminRole(currentUser?.role)) return
    try {
      const response = await apiRequest('/api/salary/periods')
      const payload = await response.json()
      const validApprovalStatuses = new Set<SalaryApprovalStatus>(['DRAFT', 'CONFIRMED', 'PENDING_APPROVAL', 'APPROVED'])
      const periods: SalaryPeriodItem[] = Array.isArray(payload)
        ? payload
          .filter((item) => typeof item?.period === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(item.period))
          .map((item) => ({
            period: String(item.period),
            is_published: Boolean(item.is_published),
            input_count: Number(item.input_count || 0),
            approval_status: validApprovalStatuses.has(item.approval_status as SalaryApprovalStatus)
              ? item.approval_status as SalaryApprovalStatus
              : (item.is_published ? 'APPROVED' : 'DRAFT'),
          }))
        : []
      setSalaryPeriods(periods)
      if (salaryPeriodTouchedRef.current) return
      const current = currentMonthPeriod()
      const currentExists = periods.some((item) => item.period === current)
      const publishedPeriods = periods.filter((item) => item.is_published).map((item) => item.period)
      const fallbackPool = publishedPeriods.length > 0 ? publishedPeriods : periods.map((item) => item.period)
      const fallback = closestMonthPeriod(fallbackPool, current)
      // Keep the current draft month selected when it already has payroll
      // inputs. Falling back to the latest published month made August open
      // on July data until the user switched months manually.
      setSalaryPeriod(currentExists ? current : (fallback || current))
    } catch (error) {
      setMessage(`Không tải được danh sách kỳ lương: ${(error as Error).message}`)
    }
  }

  function salaryApprovalFallback(period: string): SalaryApprovalState {
    const periodInfo = salaryPeriods.find((item) => item.period === period)
    // is_published describes salary input visibility, not the approval
    // workflow. A confirmed period can already contain published inputs while
    // it is still waiting for Director/IT approval, so approval_status must
    // always take precedence when it is available.
    const fallbackStatus: SalaryApprovalStatus = periodInfo?.approval_status
      ?? (periodInfo?.is_published ? 'APPROVED' : 'DRAFT')
    return {
      period,
      status: fallbackStatus,
      confirmed_by_user_id: null,
      confirmed_at: null,
      requested_by_user_id: null,
      requested_at: null,
      approved_by_user_id: null,
      approved_at: null,
    }
  }

  async function refreshSalaryApproval(
    period: string = salaryPeriod,
    shouldApply: () => boolean = () => true,
  ) {
    try {
      const approvalRes = await apiRequest(`/api/salary/approval?period=${period}`)
      const approvalData = await approvalRes.json() as SalaryApprovalState
      if (shouldApply()) {
        setSalaryApproval(approvalData)
        setIsSalaryConfirmed(approvalData.status !== 'DRAFT')
      }
      return approvalData
    } catch (approvalError) {
      // Approval workflow is supplementary metadata. A deployment with an
      // unapplied approval migration must never hide the core salary data.
      const fallback = salaryApprovalFallback(period)
      if (shouldApply()) {
        setSalaryApproval(fallback)
        setIsSalaryConfirmed(fallback.status !== 'DRAFT')
      }
      console.warn('Salary approval workflow is temporarily unavailable.', approvalError)
      return fallback
    }
  }

  async function loadSalaryData() {
    if (!isBusinessAdminRole(currentUser?.role)) return
    const requestedPeriod = salaryPeriod
    const requestId = ++salaryLoadSequenceRef.current
    const isCurrentRequest = () => requestId === salaryLoadSequenceRef.current
    setLoading(true)
    try {
      const [employeesData, inputData, policyResult, policyHistoryResult] = await Promise.all([
        apiRequest(`/api/salary/employees?period=${requestedPeriod}`).then(response => response.json()),
        apiRequest(`/api/salary/inputs?period=${requestedPeriod}`).then(response => response.json()),
        apiRequest(`/api/salary/policy?period=${requestedPeriod}`)
          .then(response => response.json())
          .catch(error => {
            console.warn(`Không tải được chính sách lương tháng ${requestedPeriod}.`, error)
            return null
          }),
        apiRequest('/api/salary/policies')
          .then(response => response.json())
          .catch(error => {
            console.warn('Không tải được lịch sử chính sách lương.', error)
            return null
          }),
      ])
      if (!isCurrentRequest()) return

      await refreshSalaryApproval(requestedPeriod, isCurrentRequest)
      if (!isCurrentRequest()) return

      setSalaryEmployees(employeesData)
      setSalaryInputs(inputData)
      if (policyResult?.policy) {
        setSalaryPolicy(policyResult.policy)
      }
      if (Array.isArray(policyHistoryResult)) {
        setSalaryPolicyHistory(policyHistoryResult)
      }
      
      setEditedInputs({})
      setEditingSalaryEmployeeId(null)
      setMessage(`Đã tải thông tin bảng lương tháng ${requestedPeriod}.`)
    } catch (error) {
      if (isCurrentRequest()) {
        // Never leave a previous month's rows visible below the newly selected
        // period label when either core payroll request fails.
        setSalaryEmployees([])
        setSalaryInputs([])
        setEditedInputs({})
        setMessage(`Không tải được thông tin bảng lương: ${(error as Error).message}`)
      }
    } finally {
      if (isCurrentRequest()) {
        setLoading(false)
      }
    }
  }

  function openOtherIncomeEvidence(employee: any, input: any) {
    setOtherIncomeEvidenceEmployeeId(Number(employee.id))
    setOtherIncomeEvidenceNote(String(input?.other_income_note || ''))
    setOtherIncomeEvidenceFile(null)
  }

  function closeOtherIncomeEvidence() {
    if (isSavingOtherIncomeEvidence) return
    setOtherIncomeEvidenceEmployeeId(null)
    setOtherIncomeEvidenceNote('')
    setOtherIncomeEvidenceFile(null)
  }

  async function refreshSalaryInputs() {
    const inputRes = await apiRequest(`/api/salary/inputs?period=${salaryPeriod}`)
    const inputData = await inputRes.json()
    setSalaryInputs(inputData)
    return inputData
  }

  async function saveOtherIncomeEvidence() {
    if (otherIncomeEvidenceEmployeeId === null) return
    const existingInput = salaryInputs.find((item) => Number(item.employee_id) === otherIncomeEvidenceEmployeeId)
    const editedInput = editedInputs[otherIncomeEvidenceEmployeeId] || {}
    const amount = Number(editedInput.other_income ?? existingInput?.other_income ?? 0)
    const note = otherIncomeEvidenceNote.trim()
    if (amount > 0 && !note) {
      setMessage('Vui lòng nhập lý do của khoản Thu nhập khác trước khi lưu.')
      return
    }
    if (otherIncomeEvidenceFile && otherIncomeEvidenceFile.size > 15 * 1024 * 1024) {
      setMessage('Chứng từ Thu nhập khác không được vượt quá 15 MB.')
      return
    }

    setIsSavingOtherIncomeEvidence(true)
    try {
      const form = new FormData()
      form.append('period', salaryPeriod)
      form.append('other_income', String(Math.max(0, Math.round(amount))))
      form.append('note', note)
      if (otherIncomeEvidenceFile) form.append('document', otherIncomeEvidenceFile)
      await apiRequest(`/api/salary/other-income-evidence/${otherIncomeEvidenceEmployeeId}`, {
        method: 'POST',
        body: form,
      })
      await refreshSalaryInputs()
      setEditedInputs((previous) => {
        const next = { ...previous }
        const employeeEdits = { ...(next[otherIncomeEvidenceEmployeeId] || {}) }
        delete employeeEdits.other_income
        if (Object.keys(employeeEdits).length > 0) next[otherIncomeEvidenceEmployeeId] = employeeEdits
        else delete next[otherIncomeEvidenceEmployeeId]
        return next
      })
      setMessage(`Đã lưu Thu nhập khác, lý do và chứng từ cho tháng ${salaryPeriod}.`)
      setOtherIncomeEvidenceEmployeeId(null)
      setOtherIncomeEvidenceNote('')
      setOtherIncomeEvidenceFile(null)
    } catch (error) {
      setMessage(`Không lưu được hồ sơ Thu nhập khác: ${(error as Error).message}`)
    } finally {
      setIsSavingOtherIncomeEvidence(false)
    }
  }

  async function openSalaryPolicyModal() {
    setSalaryPolicyForm(buildSalaryPolicyForm(salaryPeriod, salaryPolicy))
    setSalaryPolicyModalOpen(true)
    try {
      const response = await apiRequest('/api/salary/policies')
      setSalaryPolicyHistory(await response.json())
    } catch (error) {
      setMessage(`Không tải được lịch sử chính sách lương: ${(error as Error).message}`)
    }
  }

  function updateSalaryPolicyNumber(field: keyof SalaryPolicy, value: string) {
    const amount = Number(value)
    setSalaryPolicyForm((current) => ({
      ...current,
      [field]: Number.isFinite(amount) ? amount : 0,
    }))
  }

  function updateSalaryPolicyVnd(field: SalaryPolicyVndField, value: string) {
    const amount = parseSalaryPolicyVndInput(value)
    setSalaryPolicyForm((current) => ({
      ...current,
      // `undefined` is an intentional in-progress state: it lets users clear
      // a formatted value completely before entering a replacement amount.
      [field]: amount,
    } as SalaryPolicyForm))
  }

  function updateSalaryPolicyBracket(index: number, field: keyof SalaryTaxBracket, value: string) {
    const amount = parseSalaryPolicyVndInput(value)
    setSalaryPolicyForm((current) => ({
      ...current,
      pit_brackets: current.pit_brackets.map((item, itemIndex) => (
        itemIndex !== index
          ? item
          : {
            ...item,
            // `null` keeps the text box empty while editing. For up_to it also
            // remains the supported "Không giới hạn" value on the last tier.
            [field]: amount ?? null,
          } as SalaryTaxBracket
      )),
    }))
  }

  async function saveSalaryPolicy() {
    const hasBlankVndField = SALARY_POLICY_VND_FIELDS.some((field) => (
      !Number.isSafeInteger(salaryPolicyForm[field]) || Number(salaryPolicyForm[field]) < 0
    ))
    const hasBlankDeduction = salaryPolicyForm.pit_brackets.some((item) => (
      !Number.isSafeInteger(item.deduction) || Number(item.deduction) < 0
    ))
    if (hasBlankVndField || hasBlankDeduction) {
      setMessage('Vui lòng nhập đầy đủ số tiền VNĐ hợp lệ trước khi lưu chính sách.')
      return
    }
    setSavingSalaryPolicy(true)
    try {
      const payload = {
        ...salaryPolicyForm,
        name: salaryPolicyForm.name.trim(),
        legal_basis: salaryPolicyForm.legal_basis.trim() || null,
        note: salaryPolicyForm.note.trim() || null,
        pit_brackets: salaryPolicyForm.pit_brackets.map((item) => ({
          up_to: item.up_to === null ? null : Number(item.up_to),
          rate: Number(item.rate),
          deduction: Number(item.deduction),
        })),
      }
      delete (payload as any).id
      delete (payload as any).version_code
      delete (payload as any).created_at
      const response = await apiRequest('/api/salary/policies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const created = await response.json()
      setSalaryPolicy(created)
      setSalaryPolicyModalOpen(false)
      setMessage(`Đã tạo ${created.version_code} — áp dụng từ tháng ${String(created.effective_from).slice(0, 7)} cho các bảng lương chưa phát hành.`)
      await loadSalaryData()
    } catch (error) {
      setMessage(`Không thể lưu chính sách lương: ${(error as Error).message}`)
    } finally {
      setSavingSalaryPolicy(false)
    }
  }

  async function downloadOtherIncomeEvidence() {
    if (otherIncomeEvidenceEmployeeId === null) return
    try {
      const response = await apiRequest(`/api/salary/other-income-evidence/${otherIncomeEvidenceEmployeeId}/file?period=${salaryPeriod}`)
      const blob = await response.blob()
      const existingInput = salaryInputs.find((item) => Number(item.employee_id) === otherIncomeEvidenceEmployeeId)
      const filename = extractFilename(response.headers.get('Content-Disposition'), existingInput?.other_income_document_name || `chung-tu-thu-nhap-khac-${salaryPeriod}`)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      setMessage(`Không tải được chứng từ: ${(error as Error).message}`)
    }
  }

  async function deleteOtherIncomeEvidence() {
    if (otherIncomeEvidenceEmployeeId === null || isSalaryLocked) return
    const accepted = await confirm({
      title: 'Xóa chứng từ Thu nhập khác',
      message: 'Chỉ xóa tệp đính kèm; số tiền và lý do vẫn được giữ nguyên. Bạn có chắc chắn?',
      confirmLabel: 'Xóa chứng từ',
      tone: 'danger',
    })
    if (!accepted) return
    try {
      await apiRequest(`/api/salary/other-income-evidence/${otherIncomeEvidenceEmployeeId}/file?period=${salaryPeriod}`, { method: 'DELETE' })
      await refreshSalaryInputs()
      setMessage('Đã xóa chứng từ Thu nhập khác.')
    } catch (error) {
      setMessage(`Không xóa được chứng từ: ${(error as Error).message}`)
    }
  }

  async function saveMonthlyInputs() {
    const pendingOtherIncomeEmployee = salaryEmployees.find((employee) =>
      employee.employee_type !== 'TRAINEE'
      && Object.prototype.hasOwnProperty.call(editedInputs[employee.id] || {}, 'other_income'),
    )
    if (pendingOtherIncomeEmployee) {
      const existingInput = salaryInputs.find((item) => Number(item.employee_id) === Number(pendingOtherIncomeEmployee.id))
      openOtherIncomeEvidence(pendingOtherIncomeEmployee, existingInput)
      setMessage('Hãy nhập lý do và kiểm tra chứng từ cho khoản Thu nhập khác trước khi lưu các thay đổi còn lại.')
      return
    }
    setLoading(true)
    try {
      const payload: any[] = []
      const undoEntries: Array<{ employeeId: number; previousInput: any | null }> = []
      for (const emp of salaryEmployees) {
        if (emp.employee_type === 'TRAINEE') continue
        const existingInput = salaryInputs.find(x => x.employee_id === emp.id)
        const edited = editedInputs[emp.id] || {}

        // Keep exactly one pre-save snapshot for the people the user changed.
        // It is used by the explicit undo button below; untouched rows are
        // never included in an undo operation.
        if (editedInputs[emp.id] !== undefined) {
          undoEntries.push({ employeeId: emp.id, previousInput: existingInput?.id > 0 ? { ...existingInput } : null })
        }
        
        if (editedInputs[emp.id] !== undefined || (existingInput && existingInput.id > 0)) {
          payload.push({
            employee_id: emp.id,
            salary_period: salaryPeriod,
            actual_working_days: edited.actual_working_days !== undefined ? Number(edited.actual_working_days) : (existingInput?.actual_working_days ?? 26.0),
            meal_allowance_free: edited.meal_allowance_free !== undefined ? Number(edited.meal_allowance_free) : (existingInput?.meal_allowance_free ?? 1200000),
            meal_allowance_tax: edited.meal_allowance_tax !== undefined ? Number(edited.meal_allowance_tax) : (existingInput?.meal_allowance_tax ?? 0),
            phone_allowance_free: edited.phone_allowance_free !== undefined ? Number(edited.phone_allowance_free) : (existingInput?.phone_allowance_free ?? 2000000),
            trans_allowance_tax: edited.trans_allowance_tax !== undefined ? Number(edited.trans_allowance_tax) : (existingInput?.trans_allowance_tax ?? 2000000),
            perf_allowance_tax: edited.perf_allowance_tax !== undefined ? Number(edited.perf_allowance_tax) : (existingInput?.perf_allowance_tax ?? 0),
            other_income: edited.other_income !== undefined ? Number(edited.other_income) : (existingInput?.other_income ?? 0),
            bonus: edited.bonus !== undefined ? Number(edited.bonus) : (existingInput?.bonus ?? 0),
            bonus_14: edited.bonus_14 !== undefined ? Number(edited.bonus_14) : (existingInput?.bonus_14 ?? 0),
            advance_payment: edited.advance_payment !== undefined ? Number(edited.advance_payment) : (existingInput?.advance_payment ?? 0),
            pit_refund: edited.pit_refund !== undefined ? Number(edited.pit_refund) : (existingInput?.pit_refund ?? 0),
            other_deductions: edited.other_deductions !== undefined ? Number(edited.other_deductions) : (existingInput?.other_deductions ?? 0),
          })
        }
      }
      
      if (payload.length === 0) {
        setMessage('Không có thay đổi biến động tháng nào cần lưu.')
        setLoading(false)
        return
      }

      const response = await apiRequest('/api/salary/inputs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const result = await response.json()
      setMessage(`Đã lưu thành công biến động tháng cho ${result.length} nhân sự.`)
      setEditedInputs({})

      if (undoEntries.length > 0) {
        setLastSalaryUndo({ salaryPeriod, entries: undoEntries })
      }
      
      const inputRes = await apiRequest(`/api/salary/inputs?period=${salaryPeriod}`)
      const inputData = await inputRes.json()
      setSalaryInputs(inputData)
    } catch (error) {
      setMessage(`Lưu biến động tháng thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function undoLastSavedSalaryInputs() {
    if (!lastSalaryUndo || lastSalaryUndo.salaryPeriod !== salaryPeriod) {
      setMessage('Không có lần lưu nào trong tháng hiện tại để hoàn tác.')
      return
    }
    if (isSalaryLocked) {
      setMessage('Bảng lương đang khóa thủ công; hãy mở khóa trước khi hoàn tác.')
      return
    }
    const accepted = await confirm({
      title: 'Hoàn tác lần lưu bảng lương gần nhất',
      message: `Khôi phục ${lastSalaryUndo.entries.length} nhân sự về dữ liệu trước lần lưu gần nhất của tháng ${salaryPeriod}?`,
      confirmLabel: 'Hoàn tác lần lưu',
      tone: 'danger',
    })
    if (!accepted) return

    setLoading(true)
    try {
      // Read again before restoring so a row that did not exist before the
      // saved change can be removed safely by its current database id.
      const currentRes = await apiRequest(`/api/salary/inputs?period=${salaryPeriod}`)
      const currentInputs = await currentRes.json()
      const restorePayload = lastSalaryUndo.entries
        .filter(entry => entry.previousInput)
        .map(entry => salaryInputRestorePayload(entry.previousInput, entry.employeeId, salaryPeriod))

      if (restorePayload.length > 0) {
        await apiRequest('/api/salary/inputs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(restorePayload),
        })
      }

      for (const entry of lastSalaryUndo.entries.filter(item => !item.previousInput)) {
        const createdInput = currentInputs.find((item: any) => item.employee_id === entry.employeeId && item.id > 0)
        if (createdInput) await apiRequest(`/api/salary/inputs/${createdInput.id}`, { method: 'DELETE' })
      }

      const refreshedRes = await apiRequest(`/api/salary/inputs?period=${salaryPeriod}`)
      setSalaryInputs(await refreshedRes.json())
      setEditedInputs({})
      setLastSalaryUndo(null)
      setMessage(`Đã hoàn tác lần lưu gần nhất của tháng ${salaryPeriod}.`)
    } catch (error) {
      setMessage(`Hoàn tác bảng lương thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  function startEditSalaryEmployee(emp: any) {
    setEditingSalaryEmployeeId(emp.id)
    setEditSalaryEmployeeForm({
      employee_code: emp.employee_code ?? '',
      fullname: emp.fullname ?? '',
      position: emp.position ?? '',
      contract_salary: emp.contract_salary ?? 0,
      employee_type: (emp.employee_type || 'FULLTIME') as EmployeeType,
      dependents_count: emp.dependents_count ?? 0,
      account_number: emp.account_number ?? '',
      bank_name: emp.bank_name ?? '',
    })
  }

  async function saveSalaryEmployeeInline(employeeId: number) {
    setLoading(true)
    try {
      await apiRequest(`/api/salary/employees/${employeeId}?period=${salaryPeriod}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_code: editSalaryEmployeeForm.employee_code,
          fullname: editSalaryEmployeeForm.fullname,
          position: editSalaryEmployeeForm.position,
          contract_salary: Number(String(editSalaryEmployeeForm.contract_salary).replace(/\D/g, '') || 0),
          employee_type: editSalaryEmployeeForm.employee_type,
          dependents_count: Number(editSalaryEmployeeForm.dependents_count),
          account_number: editSalaryEmployeeForm.account_number,
          bank_name: editSalaryEmployeeForm.bank_name,
        }),
      })
      setEditingSalaryEmployeeId(null)
      const empRes = await apiRequest(`/api/salary/employees?period=${salaryPeriod}`)
      const empData = await empRes.json()
      setSalaryEmployees(empData)
      setMessage(`Đã cập nhật cấu hình lương gốc cho nhân sự #${employeeId}.`)
    } catch (error) {
      setMessage(`Cập nhật lương gốc thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function exportSalaryReportTable() {
    const response = await apiRequest(`/api/salary/export?period=${salaryPeriod}`)
    const blob = await response.blob()
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = `salary_table_${salaryPeriod}.xlsx`
    link.click()
    URL.revokeObjectURL(href)
    setMessage(`Đã gửi yêu cầu tải bảng tính lương tháng ${salaryPeriod}.`)
  }

  /**
   * XUẤT FILE EXCEL PAYMENT CHI TRẢ LƯƠNG
   * Tạo file Payment Excel theo cấu trúc Payment_External.xlsx để Kế toán trưởng
   * phê duyệt chuyển khoản qua Ngân hàng.
   *
   * Cấu trúc:
   * - Row 1: Header (Txn Reference | Amount (VND) | Beneficiary Name | Account Number | Remarks | Ben Bank | Province | Branch | Validation)
   * - Row N: Data (blank | final_transfer | fullname_no_accent | account_number | Salary MM.YYYY | bank_name | blank | blank | OK)
   */
  function exportPaymentExcel() {
    // Lấy [MM/YYYY] từ salaryPeriod (e.g. '2026-05' → '05.2026')
    const [pYear, pMonth] = salaryPeriod.split('-')
    const periodLabel = `${pMonth}.${pYear}` // e.g. 05.2026
    const remarks = `Salary ${periodLabel}`

    // Hàm loại bỏ dấu tiếng Việt cho tên người thụ hưởng
    function removeVietnameseAccents(str: string): string {
      if (!str) return ''
      return str
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/đ/g, 'd')
        .replace(/Đ/g, 'D')
        .trim()
        .toUpperCase()
    }

    // Defaults giống như trong SalaryDataGrid
    const stdDays = calculatePeriodWorkingDays(salaryPeriod)
    const INPUT_DEFAULTS = {
      actual_working_days: stdDays,
      meal_allowance_free: 1200000,
      meal_allowance_tax: 0,
      phone_allowance_free: 2000000,
      trans_allowance_tax: 2000000,
      perf_allowance_tax: 0,
      other_income: 0,
      bonus: 0,
      bonus_14: 0,
      sales_bonus: 0,
      advance_payment: 0,
      pit_refund: 0,
      other_deductions: 0,
    }

    // Build danh sách rows
    const dataRows: (string | number | null)[][] = []

    for (const emp of salaryEmployees) {
      // Khối C chỉ theo dõi thực tập sinh, không xuất chuyển khoản lương.
      if (emp.employee_type === 'TRAINEE') continue
      // Lấy input gốc từ DB (nếu có)
      const dbInput = salaryInputs.find((inp: any) => inp.employee_id === emp.id) || {}
      // Merge với các chỉnh sửa chưa lưu (editedInputs)
      const editOverrides = editedInputs[emp.id] || {}
      const mergedInput = { ...INPUT_DEFAULTS, ...dbInput, ...editOverrides }

      // Tính lương theo cùng thuật toán như SalaryDataGrid
      const result = cake_salary({
        type: emp.employee_type as EmployeeType,
        contract_salary: Number(emp.contract_salary) || 0,
        actual_working_days: mergedInput.actual_working_days,
        standard_working_days: stdDays,
        meal_allowance_free: mergedInput.meal_allowance_free,
        meal_allowance_tax: mergedInput.meal_allowance_tax,
        phone_allowance_free: mergedInput.phone_allowance_free,
        trans_allowance_tax: mergedInput.trans_allowance_tax,
        perf_allowance_tax: mergedInput.perf_allowance_tax,
        other_income: mergedInput.other_income,
        bonus: mergedInput.bonus + (mergedInput.sales_bonus ?? 0),
        bonus_14: mergedInput.bonus_14,
        dependents_count: emp.dependents_count,
        other_deductions: mergedInput.other_deductions,
        pit_refund: mergedInput.pit_refund,
        advance_payment: mergedInput.advance_payment,
      }, salaryPolicy)

      const finalTransfer = result.final_transfer
      // Bỏ qua nhân viên có final_transfer = 0 (không cần chuyển khoản)
      if (finalTransfer <= 0) continue

      const beneficiaryName = removeVietnameseAccents(
        (dbInput as any).fullname || emp.fullname || emp.full_name || ''
      )
      const accountNumber = String(
        (dbInput as any).account_number || emp.account_number || ''
      ).trim()
      const benBank = String(
        (dbInput as any).bank_name || emp.bank_name || ''
      ).trim()

      // Row: [Txn Ref | Amount | Beneficiary Name | Account Number | Remarks | Ben Bank | Province | Branch | Validation]
      // Col A = blank (Txn Reference — để trống, ngân hàng tự sinh)
      dataRows.push([
        null,          // A: Txn Reference (để trống)
        finalTransfer, // B: Amount (VND)
        beneficiaryName, // C: Beneficiary Name
        accountNumber,   // D: Account Number
        remarks,         // E: Remarks
        benBank,         // F: Ben Bank
        null,            // G: Province
        null,            // H: Branch
        'OK',            // I: Validation (hard-coded OK)
      ])
    }

    if (dataRows.length === 0) {
      setMessage('Không có nhân viên nào có lương cần chuyển khoản trong tháng này.')
      return
    }

    // Tạo worksheet
    const headerRow = [
      'Txn Reference\nSố tham chiếu',
      'Amount (VND)\nSố tiền chuyển',
      'Beneficiary Name\nTên người nhận',
      'Account Number\nTài khoản nhận',
      'Remarks\nNội dung',
      'Ben Bank\nNgân hàng chuyển',
      'Province\nĐịa bàn',
      'Branch\nChi nhánh',
      'Validation\nKiểm tra',
    ]

    const wsData = [headerRow, ...dataRows]
    const ws = XLSX.utils.aoa_to_sheet(wsData)

    // Định dạng cột B (Amount) là số nguyên
    const range = XLSX.utils.decode_range(ws['!ref'] || 'A1')
    for (let R = 1; R <= range.e.r; R++) {
      const cellAddr = XLSX.utils.encode_cell({ r: R, c: 1 }) // Col B
      if (ws[cellAddr] && typeof ws[cellAddr].v === 'number') {
        ws[cellAddr].t = 'n'
        ws[cellAddr].z = '#,##0'
      }
    }

    // Set độ rộng cột
    ws['!cols'] = [
      { wch: 18 }, // A: Txn Reference
      { wch: 18 }, // B: Amount
      { wch: 35 }, // C: Beneficiary Name
      { wch: 22 }, // D: Account Number
      { wch: 20 }, // E: Remarks
      { wch: 35 }, // F: Ben Bank
      { wch: 12 }, // G: Province
      { wch: 12 }, // H: Branch
      { wch: 15 }, // I: Validation
    ]

    // Tạo workbook và tải về
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet 1')

    const filename = `Payment_Salary_${salaryPeriod}.xlsx`
    XLSX.writeFile(wb, filename)

    setMessage(`Đã xuất file Payment chuyển khoản lương tháng ${salaryPeriod} — ${dataRows.length} nhân viên (${filename}).`)
  }


  async function loadTimesheets() {
    if (!['ADMIN', 'DIRECTOR', 'HR_ADMIN', 'IT_ADMIN'].includes(currentUser?.role || '')) return
    setLoading(true)
    try {

      const gridResponse = await apiRequest(`/api/timesheets/grid?period_start=${periodStart}&period_end=${periodEnd}`)
      const gridPayload = (await gridResponse.json()) as TimesheetGridResponse

      setTimesheetIsLocked(gridPayload.is_locked || false)

      setTimesheetDayColumns(gridPayload.day_columns)
      setTimesheetGridRows(gridPayload.rows)
      setTimesheetPage(1)

      setMessage(`Đã tải ${gridPayload.rows.length} dòng lưới timesheet theo kỳ.`)
    } catch (error) {
      setMessage(`Không tải được timesheet: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function deleteTimesheetPeriod() {
    if (timesheetIsLocked) {
      setMessage('Không thể xóa bảng công vì tháng này đã bị khóa.')
      return
    }

    if (!await confirm({ title: 'Xóa bảng công', message: 'Bạn có chắc chắn muốn xóa toàn bộ bảng công của tháng này? Hành động này sẽ xóa dữ liệu quẹt thẻ và các chỉnh sửa thủ công của tháng này, không thể hoàn tác.', confirmLabel: 'Xóa bảng công', tone: 'danger' })) {
      return
    }

    setLoading(true)
    try {
      const response = await apiRequest(`/api/timesheets/period?period_start=${periodStart}&period_end=${periodEnd}`, {
        method: 'DELETE'
      })
      const result = await response.json()
      setMessage(result.message || 'Đã xóa bảng công thành công.')
      loadTimesheets()
    } catch (error) {
      setMessage(`Xóa bảng công thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function toggleLockTimesheet() {
    const action = timesheetIsLocked ? "Mở khóa" : "Khóa"
    if (!await confirm({ title: `${action} bảng công`, message: `Bạn có chắc chắn muốn ${action.toLowerCase()} bảng công này không?`, confirmLabel: action, tone: timesheetIsLocked ? 'primary' : 'danger' })) {
      return
    }

    setLoading(true)
    try {
      const lockRes = await apiRequest('/api/timesheets/lock-period', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          period_start: periodStart,
          period_end: periodEnd,
          is_locked: !timesheetIsLocked
        })
      });
      if (!lockRes.ok) {
        const errData = await lockRes.json()
        throw new Error(errData.detail || `Lỗi khi ${action.toLowerCase()} bảng công`)
      }

      setTimesheetIsLocked(!timesheetIsLocked)
      setMessage(`Đã ${action.toLowerCase()} bảng công thành công!`)
    } catch (error) {
      setMessage(`${action} bảng công thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function syncTimesheetToSalary() {
    if (!timesheetGridRows || timesheetGridRows.length === 0) {
      setMessage('Không có dữ liệu bảng công để xác nhận.')
      return
    }

    const d = new Date(periodEnd)
    const derivedSalaryPeriod = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`

    if (!await confirm({ title: 'Chốt bảng công', message: `Bạn có chắc chắn muốn chốt bảng công và đồng bộ số ngày công sang Bảng lương tháng ${derivedSalaryPeriod} không?`, confirmLabel: 'Chốt và đồng bộ' })) {
      return
    }

    setLoading(true)
    try {
      const traineeEmployeeIds = new Set(
        [...salaryEmployees, ...employees]
          .filter((employee: any) => employee.employee_type === 'TRAINEE')
          .map((employee: any) => Number(employee.id)),
      )
      const payload = timesheetGridRows
        .filter((row: any) => !traineeEmployeeIds.has(Number(row.employee_id)))
        .map((row: any) => ({
        employee_id: Number(row.employee_id),
        salary_period: derivedSalaryPeriod,
        actual_working_days: Number(
          row.total_payroll_days ?? (Number(row.total_work_days || 0) + Number(row.paid_leave_days || 0)),
        ),
        }))

      const res = await apiRequest('/api/salary/inputs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.detail || 'Lỗi khi đồng bộ lương')
      }

      setMessage(`Đã chốt công và đồng bộ thành công ${payload.length} nhân viên sang Bảng lương tháng ${derivedSalaryPeriod}!`)
    } catch (error) {
      setMessage(`Đồng bộ thất bại: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function loadDashboardKpi() {
    if (!isBusinessAdminRole(currentUser?.role)) return
    setLoading(true)
    try {
      const response = await apiRequest(`/api/dashboard/kpi?period_start=${periodStart}&period_end=${periodEnd}`)
      const payload = (await response.json()) as DashboardKpi
      setDashboardKpi(payload)
      setMessage('Đã tải dữ liệu Dashboard KPI.')
    } catch (error) {
      setMessage(`Không tải được Dashboard KPI: ${(error as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  async function loadOverrideHistory(options?: { silent?: boolean }) {
    if (!['ADMIN', 'DIRECTOR', 'HR_ADMIN', 'IT_ADMIN'].includes(currentUser?.role || '')) return
    const silent = Boolean(options?.silent)
    if (!silent) {
      setLoading(true)
    }
    try {
      const limit = Math.max(1, Math.min(1000, Number(overrideHistoryLimit) || 200))
      const employeeQuery = overrideHistoryEmployeeId.trim()
        ? `&employee_id=${encodeURIComponent(overrideHistoryEmployeeId.trim())}`
        : ''
      const response = await apiRequest(
        `/api/attendance/override/history?period_start=${periodStart}&period_end=${periodEnd}&limit=${limit}${employeeQuery}`
      )
      const payload = (await response.json()) as OverrideLog[]
      setOverrideLogs(payload)
      if (!silent) {
        setMessage(`Đã tải ${payload.length} bản ghi audit override.`)
      }
    } catch (error) {
      setMessage(`Không tải được lịch sử override: ${(error as Error).message}`)
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }
  useEffect(() => {
    if (!isBusinessAdminRole(currentUser?.role)) return
    void loadSalaryPeriods()
  }, [token, currentUser?.role])

  useEffect(() => {
    if (activeTab !== 'dashboard') {
      return
    }
    void loadDashboardKpi()
    void loadSalaryData()
  }, [activeTab, periodStart, periodEnd, salaryPeriod])

  useEffect(() => {
    if (activeTab !== 'dashboard' || !autoRefreshKpi) {
      return
    }
    const sec = Math.max(10, Number(autoRefreshSeconds) || 30)
    const timer = window.setInterval(() => {
      void loadDashboardKpi()
      void loadSalaryData()
    }, sec * 1000)
    return () => window.clearInterval(timer)
  }, [activeTab, autoRefreshKpi, autoRefreshSeconds])

  useEffect(() => {
    if (activeTab !== 'timesheets') {
      if (timesheetDefaultPeriodResolved) setTimesheetDefaultPeriodResolved(false)
      return
    }
    if (timesheetDefaultPeriodResolved) return

    let cancelled = false
    const resolveDefaultTimesheetPeriod = async () => {
      const currentRange = timesheetRangeForPeriod(currentMonthPeriod())
      const previousRange = timesheetRangeForPeriod(shiftMonthPeriod(currentRange.period, -1))
      let nextRange = previousRange

      try {
        const response = await apiRequest(
          `/api/timesheets/grid?period_start=${currentRange.start}&period_end=${currentRange.end}`,
        )
        const payload = (await response.json()) as TimesheetGridResponse
        if (payload.is_locked) nextRange = currentRange
      } catch {
        // Nếu chưa đọc được trạng thái kỳ hiện tại, kỳ trước vẫn là lựa chọn an toàn.
      }

      if (cancelled) return
      setPeriodStart(nextRange.start)
      setPeriodEnd(nextRange.end)
      setTimesheetDefaultPeriodResolved(true)
    }

    void resolveDefaultTimesheetPeriod()
    return () => {
      cancelled = true
    }
  }, [activeTab, timesheetDefaultPeriodResolved])

  useEffect(() => {
    if (activeTab !== 'timesheets' || !timesheetDefaultPeriodResolved) return
    void loadTimesheets()
  }, [activeTab, periodStart, periodEnd, timesheetDefaultPeriodResolved])

  useEffect(() => {
    if (activeTab !== 'timesheets' || timesheetNotificationEmployeeId === null) return
    const targetIndex = filteredTimesheetGridRows.findIndex((row) => row.employee_id === timesheetNotificationEmployeeId)
    if (targetIndex < 0) return
    const targetPage = Math.floor(targetIndex / TIMESHEET_PAGE_SIZE) + 1
    if (timesheetPage !== targetPage) {
      setTimesheetPage(targetPage)
      return
    }
    const timer = window.setTimeout(() => {
      document.getElementById(`timesheet-employee-${timesheetNotificationEmployeeId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 180)
    return () => window.clearTimeout(timer)
  }, [activeTab, timesheetNotificationEmployeeId, filteredTimesheetGridRows, timesheetPage])

  useEffect(() => {
    if (activeTab !== 'employees' && activeTab !== 'import' && activeTab !== 'timesheets') {
      return
    }
    void loadEmployees()
  }, [activeTab, salaryPeriod])

  useEffect(() => {
    if (!isBusinessAdminRole(currentUser?.role) || activeTab !== 'employees' || employeeNotificationId === null) return
    const employee = employees.find((item) => item.id === employeeNotificationId)
    if (!employee) return
    setDetailEmployeePassword('')
    setDetailEmployeeOriginalType((employee.employee_type || 'FULLTIME') as EmployeeType)
    setDetailEmployeeTypeEffectiveDate(new Date().toISOString().slice(0, 10))
    setDetailEmployee(employeeWithDerivedUsername(employee))
    setEmployeeNotificationId(null)
  }, [activeTab, currentUser?.role, employeeNotificationId, employees])

  useEffect(() => {
    if (activeTab !== 'salary') {
      return
    }
    void loadSalaryData()
  }, [activeTab, salaryPeriod])

  // App-wide realtime refresh: successful write requests publish one batched
  // data-change event. Refresh only the affected shared stores; the browser
  // page itself is never reloaded.
  useEffect(() => {
    if (!token || !lastDataChange) return
    const path = lastDataChange.path

    if (/\/api\/(?:(?:hr\/)?employees|salary-decisions)(?:\/|$)/.test(path)) {
      void loadEmployees()
      if (isBusinessAdminRole(currentUser?.role)) void loadSalaryData()
      return
    }
    if (/\/api\/salary(?:\/|$)/.test(path)) {
      if (isBusinessAdminRole(currentUser?.role)) {
        void loadSalaryData()
        void loadSalaryPeriods()
      }
      return
    }
    if (/\/api\/(?:departments|hr\/departments)(?:\/|$)/.test(path)) {
      void Promise.all([loadDepartments(), loadEmployees()])
      return
    }
    if (/\/api\/(?:timesheets|attendance|import|holidays|time-off)(?:\/|$)/.test(path)) {
      if (activeTab === 'timesheets') {
        void loadTimesheets()
        void loadOverrideHistory({ silent: true })
      }
      if (activeTab === 'dashboard') void loadDashboardKpi()
      return
    }
    if (/\/api\/commission(?:\/|$)/.test(path)) {
      if (isBusinessAdminRole(currentUser?.role) && activeTab === 'salary') void loadSalaryData()
      return
    }
    if (/\/api\/onboarding\/admin\/submissions(?:\/|$)/.test(path)) {
      void loadEmployees()
      return
    }
    if (/\/api\/offboarding\/admin\/submissions(?:\/|$)/.test(path)) {
      void Promise.all([loadDepartments(), loadEmployees()])
      if (isBusinessAdminRole(currentUser?.role)) void loadSalaryData()
    }
  }, [lastDataChange])

  function formatGridNumber(value: number) {
    if (Number.isInteger(value)) {
      return String(value)
    }
    return value.toFixed(1)
  }

  function formatCurrency(value: number) {
    if (value === null || value === undefined || isNaN(value)) {
      return '0'
    }
    return formatVnd(value)
  }



  async function exportTimesheet() {
    const response = await apiRequest(`/api/export/timesheet?period_start=${periodStart}&period_end=${periodEnd}`)
    const blob = await response.blob()
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = `timesheet_${periodStart}_${periodEnd}.xlsx`
    link.click()
    URL.revokeObjectURL(href)
    setMessage('Đã gửi yêu cầu export file Excel.')
  }

  if (currentPath === '/onboarding') {
    return <OnboardingPublic apiBase={apiBase} />
  }

  if (currentPath === '/offboarding') {
    return <OffboardingPublic apiBase={apiBase} />
  }

  if (!token) {
    return (
      <div className="sealink-login-shell w-screen h-screen overflow-hidden font-sans text-slate-700" style={{ fontFamily: 'var(--font-sans)' }}>
        <div className="sealink-login-visual">
          <div className="sealink-login-visual-copy">
            <h1>SEALINK INTERNATIONAL</h1>
            <p>Global Logistics &amp; Payroll Network</p>
          </div>
          <Login3DGlobe />
        </div>

        <div className="sealink-login-panel">
          <div className="sealink-login-background" aria-hidden="true">
            <span className="sealink-login-grid" />
            <span className="sealink-login-orbit sealink-login-orbit-one" />
            <span className="sealink-login-orbit sealink-login-orbit-two" />
            <span className="sealink-login-glow" />
          </div>
          <div className="sealink-login-card">
            <div className="sealink-login-heading">
              <p>SEALINK PORTAL</p>
              <h1>Đăng nhập</h1>
              <span>Hệ thống nhân sự và tiền lương</span>
            </div>

            <form onSubmit={handleLogin} className="space-y-5 login-form">
              {loginError && (
                <div className="bg-rose-50 border border-rose-200 text-rose-800 text-sm px-4 py-3.5 rounded-2xl animate-[fadeIn_0.2s_ease-out]">
                  {loginError}
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-wider text-[#475569] block px-1" style={{ fontFamily: 'var(--font-sans)' }}>Tên đăng nhập</label>
                <input
                  type="text"
                  name="username"
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  placeholder="Mã nhân viên hoặc email"
                  autoComplete="username"
                  required
                  className="w-full bg-slate-50 border border-slate-200 focus:border-[#163b66] focus:ring-4 focus:ring-[#163b66]/10 text-slate-800 rounded-2xl px-4 py-3.5 text-sm transition-all outline-none"
                  style={{ fontFamily: 'var(--font-sans)' }}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-wider text-[#475569] block px-1" style={{ fontFamily: 'var(--font-sans)' }}>Mật khẩu</label>
                <div className="sealink-login-password relative">
                  <input
                    type={showLoginPassword ? 'text' : 'password'}
                    name="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="Nhập mật khẩu truy cập"
                    autoComplete="current-password"
                    required
                    className="w-full bg-slate-50 border border-slate-200 focus:border-[#163b66] focus:ring-4 focus:ring-[#163b66]/10 text-slate-800 rounded-2xl px-4 py-3.5 pr-12 text-sm transition-all outline-none"
                    style={{ fontFamily: 'var(--font-sans)' }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowLoginPassword((visible) => !visible)}
                    className="sealink-login-password-toggle grid h-8 w-8 place-items-center border-0 bg-transparent p-0 text-slate-500 transition-colors hover:text-[#163b66] focus:outline-none focus:ring-0"
                    aria-label={showLoginPassword ? 'Ẩn mật khẩu' : 'Hiển thị mật khẩu'}
                    title={showLoginPassword ? 'Ẩn mật khẩu' : 'Hiển thị mật khẩu'}
                  >
                    {showLoginPassword ? (
                      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-none stroke-current" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="m3 3 18 18" />
                        <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
                        <path d="M9.9 4.2A10.7 10.7 0 0 1 12 4c5 0 8.3 4.2 9.4 6.1a1.8 1.8 0 0 1 0 1.8 15.7 15.7 0 0 1-3 3.8" />
                        <path d="M6.2 6.2A15.5 15.5 0 0 0 2.6 10a1.8 1.8 0 0 0 0 1.8C3.7 13.8 7 18 12 18c1.1 0 2.1-.2 3-.5" />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-none stroke-current" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M2.6 12.1a1.8 1.8 0 0 1 0-1.8C3.7 8.2 7 4 12 4s8.3 4.2 9.4 6.3a1.8 1.8 0 0 1 0 1.8C20.3 13.2 17 17.4 12 17.4S3.7 13.2 2.6 12.1Z" />
                        <circle cx="12" cy="10.7" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              <label className="sealink-login-remember">
                <input
                  type="checkbox"
                  checked={rememberLogin}
                  onChange={(event) => {
                    const checked = event.target.checked
                    setRememberLogin(checked)
                    if (!checked) {
                      localStorage.removeItem(REMEMBER_LOGIN_PREFERENCE_KEY)
                      localStorage.removeItem(REMEMBER_LOGIN_USERNAME_KEY)
                    }
                  }}
                />
                <span>Ghi nhớ đăng nhập trên thiết bị này</span>
              </label>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-[#163b66] hover:bg-[#102b49] text-white font-bold py-3.5 px-4 rounded-2xl shadow-[0_12px_24px_-10px_rgba(22,59,102,0.4)] hover:shadow-[0_16px_32px_-10px_rgba(22,59,102,0.6)] transform hover:-translate-y-0.5 active:translate-y-0 transition-all duration-200 flex items-center justify-center gap-2 mt-6 cursor-pointer"
                style={{ fontFamily: 'var(--font-sans)' }}
              >
                {loading ? (
                  <>
                    <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>Đang xác thực...</span>
                  </>
                ) : (
                  <span>Đăng nhập hệ thống</span>
                )}
              </button>
            </form>

            <div className="pt-6 text-center border-t border-slate-100 space-y-1">
              <span className="text-[11px] text-slate-400 uppercase tracking-widest font-semibold block" style={{ fontFamily: 'var(--font-sans)' }}>Phát triển bởi Sealink IT Team</span>
              <span className="text-[11px] text-slate-400 block" style={{ fontFamily: 'var(--font-sans)' }}>Hệ thống phân quyền và bảo mật cao</span>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <Suspense fallback={<LoadingState label="Đang tải giao diện…" />}>
    <EnterpriseShell
      tabs={dynamicTabs}
      activeTab={activeTab}
      onTabChange={handleTabChange}
      apiBase={apiBase}
      loading={loading}
      message={message}
      currentUser={currentUser}
      onLogout={handleLogout}
      apiRequest={apiRequest}
      onNotificationNavigate={handleNotificationNavigate}
      notificationNotice={notificationNotice}
      onDismissNotificationNotice={() => setNotificationNotice(null)}
      headerControls={
        isBusinessAdminRole(currentUser?.role) && activeTab === 'salary' ? (
          <div className="flex items-end gap-2">
            <MonthYearSelect
              id="salary-period-select"
              value={salaryPeriod}
              minYear={salaryPeriodYearBounds.min}
              maxYear={salaryPeriodYearBounds.max}
              onChange={(period) => {
                salaryPeriodTouchedRef.current = true
                setSalaryPeriod(period)
                setIsSalaryConfirmed(false)
                setIsSalaryLocked(false)
                setLastSalaryUndo(null)
              }}
              yearLabel="Năm lương"
              monthLabel="Tháng lương"
            />
          </div>
        ) : undefined
      }
    >
      <div
        className={`panel${activeTab === 'employees' ? ' employee-directory-page-panel' : ''}${activeTab === 'timesheets' ? ' timesheet-page-panel' : ''}`}
        style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}
      >
        {(isBusinessAdminRole(currentUser?.role) || currentUser?.role === 'HR_ADMIN') &&
          (activeTab === 'employees' || activeTab === 'onboarding' || activeTab === 'offboarding') && (
            <section className="mb-6 flex flex-col gap-4 rounded-[20px] border border-slate-200 bg-white p-4 shadow-sm lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-600">Không gian Nhân sự</p>
                <h2 className="mt-1 text-lg font-semibold text-slate-900">Vòng đời nhân sự</h2>
                <p className="mt-1 text-sm text-slate-600">Quản lý hồ sơ, tiếp nhận nhân viên mới và xử lý quy trình nghỉ việc trong cùng một không gian.</p>
              </div>
              <div
                className="app-segmented-tabs hr-lifecycle-tabs min-w-0"
                role="tablist"
                aria-label="Chức năng Nhân sự"
                style={{ marginTop: 0 }}
              >
                <button
                  type="button"
                  className="app-segmented-tab"
                  role="tab"
                  aria-selected={activeTab === 'employees'}
                  onClick={() => handleTabChange('employees')}
                >
                  <AppIcon name="users" size={16} />
                  Hồ sơ nhân sự
                </button>
                <button
                  type="button"
                  className="app-segmented-tab"
                  role="tab"
                  aria-selected={activeTab === 'onboarding'}
                  onClick={() => handleTabChange('onboarding')}
                >
                  <AppIcon name="document" size={16} />
                  Onboarding nhân viên mới
                </button>
                <button
                  type="button"
                  className="app-segmented-tab"
                  role="tab"
                  aria-selected={activeTab === 'offboarding'}
                  onClick={() => handleTabChange('offboarding')}
                >
                  <AppIcon name="leave" size={16} />
                  Offboarding / Nghỉ việc
                </button>
              </div>
            </section>
          )}
        {isBusinessAdminRole(currentUser?.role) && activeTab === 'dashboard' && (
          <>
            {/* 3 KPI Cards Admin Dashboard as Pie Chart */}
            <SalaryPieChart
              slices={[
                {
                  label: 'Tổng quỹ lương thực chi',
                  value: salarySummaries.transfer,
                  color: '#163B66',
                  formula: 'Σ(Lương NET + Hoàn thuế PIT - Đoàn phí)',
                  description: 'Tổng thực nhận của toàn bộ nhân viên tháng này.'
                },
                {
                  label: 'Tổng nghĩa vụ thuế TNCN',
                  value: salarySummaries.pit,
                  color: '#f43f5e',
                  formula: 'Σ(PIT_Chính_thức[Biểu 7 bậc] + PIT_Thử_việc[10%])',
                  description: 'Tổng tiền thuế thu nhập cá nhân trích nộp tháng này.'
                },
                {
                  label: 'Tổng trích nộp BH bắt buộc',
                  value: salarySummaries.ins,
                  color: '#0ea5e9',
                  formula: 'Σ(Bảo_hiểm_NLĐ_10.5% + Bảo_hiểm_DN_21.5%)',
                  description: 'Tổng bảo hiểm trích nộp (NLĐ chịu + DN chịu).'
                }
              ]}
            />

            <section className="grid-two dashboard-overview-grid">
              <div className="card dashboard-kpi-filter">
                <h2>Bộ lọc KPI theo tháng công</h2>
              <label>
                Period Start
                <BrandedDateInput value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
              </label>
              <label>
                Period End
                <BrandedDateInput value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
              </label>
              <label>
                Auto refresh KPI
                <select
                  value={autoRefreshKpi ? 'on' : 'off'}
                  onChange={(e) => setAutoRefreshKpi(e.target.value === 'on')}
                >
                  <option value="off">Tắt</option>
                  <option value="on">Bật</option>
                </select>
              </label>
              <label>
                Chu kỳ refresh (giây)
                <input
                  type="number"
                  min={10}
                  value={autoRefreshSeconds}
                  onChange={(e) => setAutoRefreshSeconds(e.target.value)}
                />
              </label>
            </div>

            <div className="card dashboard-symbol-summary">
              <h2>Tổng hợp ký hiệu công</h2>
              {dashboardKpi ? (
                <div className="kpi-symbols">
                  {Object.entries(dashboardKpi.symbol_counts).map(([key, value]) => (
                    <div key={key} className="kpi-pill">
                      <span>{key}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">Chưa có dữ liệu KPI cho kỳ đã chọn.</p>
              )}
            </div>

            {dashboardKpi && (
              <>
                <div className="card full-width kpi-grid dashboard-kpi-panel">
                  <article className="kpi-card">
                    <h3>Tổng nhân viên</h3>
                    <p>{dashboardKpi.total_employees}</p>
                  </article>
                  <article className="kpi-card">
                    <h3>Nhân viên active</h3>
                    <p>{dashboardKpi.active_employees}</p>
                  </article>
                  <article className="kpi-card">
                    <h3>Công đi làm (X)</h3>
                    <p>{dashboardKpi.present_days}</p>
                  </article>
                  <article className="kpi-card">
                    <h3>Vắng (V)</h3>
                    <p>{dashboardKpi.absent_days}</p>
                  </article>
                  <article className="kpi-card">
                    <h3>Công tác (CT)</h3>
                    <p>{dashboardKpi.business_trip_days}</p>
                  </article>
                  <article className="kpi-card">
                    <h3>Nghỉ phép (P)</h3>
                    <p>{dashboardKpi.paid_leave_days}</p>
                  </article>
                  <article className="kpi-card">
                    <h3>Đi muộn (phút)</h3>
                    <p>{dashboardKpi.total_late_minutes}</p>
                  </article>
                  <article className="kpi-card">
                    <h3>Về sớm (phút)</h3>
                    <p>{dashboardKpi.total_early_minutes}</p>
                  </article>
                  <article className="kpi-card">
                    <h3>Bất thường</h3>
                    <p>{dashboardKpi.abnormal_days}</p>
                  </article>
                </div>

                <div className="card full-width dashboard-trend-summary">
                  <div>
                    <h2>Xu hướng theo ngày</h2>
                    <p className="muted">{dashboardKpi.trend.length} ngày có dữ liệu trong kỳ đang chọn.</p>
                  </div>
                  <button type="button" className="dashboard-trend-open" onClick={() => setDashboardTrendOpen(true)}>
                    Xem chi tiết
                  </button>
                </div>
              </>
            )}
          </section>
          </>
        )}

        {currentUser?.role === 'HR_ADMIN' && activeTab === 'dashboard' && (
          <HrDashboard apiRequest={apiRequest} />
        )}

        {currentUser?.role === 'USER' && activeTab === 'personal-dashboard' && (
          <PersonalDashboard apiRequest={apiRequest} />
        )}

        {activeTab === 'my-account' && (
          <PersonalAccount apiRequest={apiRequest} embedded />
        )}

        {(
          (isBusinessAdminRole(currentUser?.role) && activeTab === 'dashboard')
          || (currentUser?.role === 'HR_ADMIN' && activeTab === 'dashboard')
          || (currentUser?.role === 'USER' && activeTab === 'personal-dashboard')
        ) && (
          <TimeOffDashboardForm
            apiRequest={apiRequest}
            onOpenWorkspace={() => {
              if (isBusinessAdminRole(currentUser?.role)) navigateTo('/admin/time-off')
              else if (currentUser?.role === 'HR_ADMIN') navigateTo('/hr/time-off')
              else navigateTo('/user/time-off')
            }}
          />
        )}

        {activeTab === 'time-off' && (
          <TimeOffManagement
            apiRequest={apiRequest}
            userRole={currentUser?.role || 'USER'}
            focusRequestId={timeOffNotificationRequestId}
            focusKey={notificationNotice?.resource_type === 'TIME_OFF_REQUEST' ? notificationNotice.id : null}
            onNavigate={navigateTo}
          />
        )}

        {activeTab === 'timesheets' && isTimesheetUploadOpen && (
          <section className="import-layout">
            <form ref={importToolbarFormRef} className="card import-workspace" onSubmit={handleImportPreview}>
              <div className="import-intro flex items-center justify-between">
                <h2>Upload + Preview</h2>
              </div>

              <div className="sl-toolbar-wrapper">

              <div className="sl-fixed-toolbar-row">
                
                {/* Nhóm bên trái: Các ô input cấu hình (Luôn nằm trên 1 hàng) */}
                <div className="sl-inputs-left-side">
                  
                  <div className="sl-date-field-group">
                    <div className="sl-input-wrapper">
                      <span className="sl-prefix">Từ:</span>
                      <BrandedDateInput value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
                    </div>
                    <span className="sl-range-tilde">~</span>
                    <div className="sl-input-wrapper">
                      <span className="sl-prefix">Đến:</span>
                      <BrandedDateInput value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
                    </div>
                  </div>

                  <div className="sl-vertical-line"></div>

                  <div className="sl-upload-item">
                    <span className="sl-input-label">Máy công:</span>
                    <label className="sl-custom-upload-btn">
                      <input ref={fileInputRef} type="file" onChange={onImportFileChange} className="sl-hidden-file" />
                      <span className="sl-tag-status">{importFile && <AppIcon name="check" size={13} />}{importFile ? 'Đã chọn' : 'Chọn tệp'}</span>
                    </label>
                  </div>

                  <div className="sl-vertical-line"></div>

                  <div className="sl-upload-item">
                    <span className="sl-input-label">Notion:</span>
                    <label className="sl-custom-upload-btn">
                      <input ref={notionFileInputRef} type="file" accept=".csv,text/csv" onChange={onNotionFileChange} className="sl-hidden-file" />
                      <span className="sl-tag-status">{notionFile && <AppIcon name="check" size={13} />}{notionFile ? 'Đã chọn' : 'Chọn CSV'}</span>
                    </label>
                    {notionFile && (
                      <button type="button" onClick={clearNotionFile} className="sl-btn-delete-csv">Bỏ CSV</button>
                    )}
                  </div>

                  <div className="sl-vertical-line"></div>

                  <div className="sl-userid-wrapper">
                    <span className="sl-prefix">BY:</span>
                  </div>

                </div>

                {/* Nhóm bên phải: 3 Nút hành động (Ép cứng nằm ngang, cấm co rúm) */}
                <div className="sl-buttons-right-side">
                  <button type="submit" disabled={loading} className={`sl-btn-action sl-color-blue ${loading ? 'loading-shimmer' : ''}`}>
                    1. Đọc file vân tay
                  </button>
                  <button type="button" onClick={() => void handleAttendanceJsonParse()} disabled={loading || !importFile} className={`sl-btn-action sl-color-slate ${loading ? 'loading-shimmer' : ''}`}>
                    2. Khớp đơn Notion
                  </button>
                  <button type="button" onClick={() => isShowingEmployeeBlockPreview ? void handleCommitFromBlocks() : handleSaveData()} disabled={loading || (!isShowingEmployeeBlockPreview && importPreview.length === 0)} className={`sl-btn-action sl-color-emerald ${loading ? 'loading-shimmer' : ''}`}>
                    3. Xác nhận & Lưu
                  </button>
                </div>

              </div>

              </div>

              <div className="import-preview-box">
                <div className="import-preview-heading">
                  <div>
                    <h3>{activeImportTableTitle}</h3>
                    <p className="muted">{activeImportTableDescription}</p>
                  </div>
                  <div className="import-preview-actions">
                    <p className="muted">
                      {isShowingEmployeeBlockPreview
                        ? `${visibleEmployeeBlocks.length}/${filteredEmployeeBlocks.length}/${rawCheckinEmployeeBlocks.length} nhân viên đang hiển thị từ sheet ${selectedImportSheet || '-'}.`
                        : isShowingParsedImportPreview
                          ? `${visibleImportTableRows.length}/${importPreview.length} dòng sau bóc tách.`
                          : `${visibleImportTableRows.length}/${selectedSheetInspection?.data_row_count ?? activeImportTableRows.length} dòng ${isShowingFallbackSampleRows ? 'dữ liệu mẫu' : 'dữ liệu thô'} từ sheet ${selectedImportSheet || '-'}.`}
                    </p>
                    <button
                      type="button"
                      className="ghost import-preview-toggle"
                      onClick={() => setIsImportPreviewDetailsOpen((open) => !open)}
                      aria-expanded={isImportPreviewDetailsOpen}
                    >
                      {isImportPreviewDetailsOpen ? 'Ẩn chi tiết' : 'Xem chi tiết'}
                    </button>
                  </div>
                </div>
                {importInspectStatusText && <div className="import-loading-banner">{importInspectStatusText}</div>}
                {isImportPreviewDetailsOpen && (
                  <>
                {isShowingEmployeeBlockPreview ? (
                  <EmployeeBlockPreview
                    visibleBlocks={visibleEmployeeBlocks}
                    filteredBlockCount={filteredEmployeeBlocks.length}
                    totalBlockCount={rawCheckinEmployeeBlocks.length}
                    searchValue={importTableSearch}
                    pageSize={employeeBlockPageSize}
                    pageSizeNumber={employeeBlockPageSizeNumber}
                    filters={employeeBlockFilters}
                    onSearchChange={(value) => {
                      setImportTableSearch(value)
                      setVisibleEmployeeBlockCount(Math.max(5, Number(employeeBlockPageSize) || 5))
                    }}
                    onPageSizeChange={changeEmployeeBlockPageSize}
                    onFilterChange={updateEmployeeBlockFilter}
                    onResetFilters={resetImportTableFilters}
                    onShowMore={showMoreEmployeeBlocks}
                    employees={employees}
                  />
                ) : activeImportTableColumns.length > 0 && (
                  <div className="import-filter-panel">
                    <label className="import-filter-search">
                      Tìm trong bảng dữ liệu
                      <input
                        value={importTableSearch}
                        onChange={(e) => setImportTableSearch(e.target.value)}
                        placeholder="Nhập từ khóa để lọc theo nội dung hiển thị"
                      />
                    </label>
                    <div className="import-column-filter-box">
                      <div className="import-column-filter-header">
                        <p className="muted">Lọc cột hiển thị. Mặc định hệ thống đang hiện toàn bộ thông tin.</p>
                        {(importTableSearch.trim() || activeImportSelectedColumnKeys.length > 0 || activeImportColumnFilterEntries.length > 0) && (
                          <button type="button" className="ghost import-filter-reset" onClick={resetImportTableFilters}>
                            Bỏ toàn bộ lọc
                          </button>
                        )}
                      </div>
                      <label className="import-column-select-field">
                        Chọn cột cần hiển thị
                        <select
                          value={activeImportSelectedColumnKeys[0] ?? ''}
                          onChange={(e) => selectImportTableColumn(e.target.value)}
                        >
                          <option value="">Tất cả cột</option>
                          {activeImportTableColumns.map((column) => (
                            <option key={`import-column-option-${column.key}`} value={column.key}>
                              {column.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    {advancedImportFilterColumns.length > 0 && (
                      <div className="import-column-criteria-box">
                        <div className="import-column-filter-header">
                          <p className="muted">
                            Chọn giá trị cần lọc theo từng cột. Nếu chưa chọn gì thì bảng vẫn hiển thị toàn bộ dữ liệu.
                          </p>
                        </div>
                        <div className="import-column-criteria-grid">
                          {advancedImportFilterColumns.map((column) => (
                            <label key={`import-column-filter-${column.key}`} className="import-column-filter-field">
                              {column.label}
                              <select
                                value={importColumnFilters[column.key] ?? ''}
                                onChange={(e) => updateImportColumnFilter(column.key, e.target.value)}
                              >
                                <option value="">Tất cả giá trị</option>
                                {(importColumnFilterOptions[column.key] ?? []).map((value) => (
                                  <option key={`import-filter-value-${column.key}-${value}`} value={value}>{value}</option>
                                ))}
                              </select>
                            </label>
                          ))}
                        </div>
                        {activeImportSelectedColumnKeys.length === 0 && (
                          <p className="muted import-column-criteria-note">
                            Đang hiển thị bộ cột gợi ý để lọc nhanh. Nếu cần lọc theo cột khác, hãy chọn cột đó trong danh sách phía trên.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}
                {!isShowingEmployeeBlockPreview && (
                  <div className="table-wrap import-table-wrap">
                  <table className="preview-data-table">
                    <thead>
                      <tr>
                        {visibleImportTableColumns.map((column, columnIndex) => (
                          <th
                            key={`preview-head-${column.key}`}
                            className={getImportStickyColumnClass(columnIndex)}
                          >
                            {column.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {visibleImportTableRows.length > 0 ? (
                        visibleImportTableRows.map((row, rowIndex) => (
                          <tr key={`preview-row-${rowIndex}`} className="transition-colors duration-150 hover:bg-slate-50/80">
                            {visibleImportTableColumns.map((column, columnIndex) => (
                              <td
                                key={`preview-cell-${rowIndex}-${column.key}`}
                                className={getImportStickyColumnClass(columnIndex)}
                              >
                                  {renderImportCellValue(row[column.key])}
                              </td>
                            ))}
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={Math.max(visibleImportTableColumns.length, 1)}>
                            {importFile
                              ? importTableSearch.trim() || activeImportSelectedColumnKeys.length > 0 || activeImportColumnFilterEntries.length > 0
                                ? 'Không có dữ liệu phù hợp với bộ lọc hiện tại.'
                                : 'Chưa có dữ liệu để hiển thị. Tải file xong, chọn sheet/header nếu cần rồi bấm Preview khi muốn bóc tách.'
                              : 'Chưa có file upload để hiển thị dữ liệu.'}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                  </div>
                )}
                  </>
                )}
              </div>
            </form>

          </section>
        )}

        {(isBusinessAdminRole(currentUser?.role) || currentUser?.role === 'HR_ADMIN') && activeTab === 'departments' && (
          <DepartmentTab
            apiRequest={apiRequest}
            token={token}
            departmentApiPath={currentUser?.role === 'HR_ADMIN' ? '/api/hr/departments' : '/api/departments'}
            employeeApiPath={currentUser?.role === 'HR_ADMIN' ? '/api/hr/employees' : '/api/employees'}
            departmentUpdateMethod={currentUser?.role === 'HR_ADMIN' ? 'PATCH' : 'PUT'}
            allowBonusConfig={currentUser?.role !== 'HR_ADMIN'}
            allowDelete={currentUser?.role !== 'HR_ADMIN'}
            organizationRefreshKey={employees
              .map((employee) => [
                employee.id,
                employee.company_email,
                employee.phone_number,
                employee.company_phone_number,
              ].join(':'))
              .join('|')}
            initialView={currentPath.endsWith('/departments/chart') ? 'chart' : 'list'}
            onViewChange={(view) => {
              const routePrefix = currentUser?.role === 'HR_ADMIN' ? '/hr/departments' : '/admin/departments'
              navigateTo(view === 'chart' ? `${routePrefix}/chart` : routePrefix)
            }}
            onOpenEmployee={isBusinessAdminRole(currentUser?.role) ? async (employeeId) => {
              try {
                let employee = employees.find((item) => item.id === employeeId)
                if (!employee) {
                  const response = await apiRequest(`/api/employees/${employeeId}`)
                  employee = (await response.json()) as Employee
                }
                setDetailEmployeePassword('')
                setDetailEmployeeOriginalType((employee.employee_type || 'FULLTIME') as EmployeeType)
                setDetailEmployeeTypeEffectiveDate(new Date().toISOString().slice(0, 10))
                setDetailEmployee(employeeWithDerivedUsername(employee))
              } catch (error) {
                setMessage(`Không thể mở hồ sơ nhân viên: ${(error as Error).message}`)
              }
            } : undefined}
          />
        )}

        {currentUser?.role === 'HR_ADMIN' && activeTab === 'employees' && (
          <HrEmployees
            apiRequest={apiRequest}
            onMessage={setMessage}
            onConfirm={confirm}
            focusEmployeeId={employeeNotificationId}
            focusKey={notificationNotice?.id || null}
          />
        )}

        {isBusinessAdminRole(currentUser?.role) && activeTab === 'employees' && (
          <section className="grid gap-6">
            <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_60px_-42px_rgba(15,23,42,0.28)]">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div className="max-w-3xl space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Employee Directory</p>
                  <h2 className="text-2xl font-bold tracking-[-0.03em] text-slate-900">Quản lý hồ sơ nhân sự và mapping Notion</h2>
                  <p className="text-sm leading-6 text-slate-500">
                    Bảng này dùng để map `Tên Notion` với `Mã máy chấm công`, từ đó luồng export sẽ điền ký hiệu nghỉ phép `P` đúng nhân sự khi upload file Leave Request.
                  </p>
                </div>

                {employeeError && (
                  <div style={{
                    background: '#fee2e2',
                    border: '1px solid #fca5a5',
                    color: '#b91c1c',
                    padding: '12px 16px',
                    borderRadius: '16px',
                    fontSize: '13px',
                    fontWeight: 500,
                    marginBottom: '16px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    width: '100%'
                  }}>
                    <AppIcon name="warning" size={17} />
                    <span>{employeeError}</span>
                    <button
                      type="button" 
                      onClick={() => setEmployeeError(null)} 
                      className="app-close-button app-close-button--compact"
                      style={{ marginLeft: 'auto', border: 'none', background: 'transparent', color: '#b91c1c', cursor: 'pointer', fontWeight: 'bold', fontSize: '16px' }}
                    >
                      <AppIcon name="close" size={14} />
                    </button>
                  </div>
                )}

                <div className="flex flex-col gap-3 sm:flex-row">
                  <button
                    type="button"
                    onClick={loadEmployees}
                    disabled={loading}
                    className="inline-flex h-[44px] min-w-[180px] items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 whitespace-nowrap"
                  >
                    Làm mới danh sách
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEmployeeForm(EMPTY_EMPLOYEE_FORM)
                      setEmployeeError(null)
                      setIsEmployeeModalOpen(true)
                    }}
                    disabled={loading}
                    className="inline-flex h-[44px] min-w-[180px] items-center justify-center rounded-2xl bg-[#163B66] px-4 text-sm font-semibold text-white shadow-[0_18px_36px_-24px_rgba(22,59,102,0.85)] transition hover:bg-[#102B49] disabled:cursor-not-allowed disabled:opacity-60 whitespace-nowrap"
                  >
                    Thêm nhân viên mới
                  </button>
                </div>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-3">
                <div className="rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Tổng hồ sơ</p>
                  <p className="mt-3 text-3xl font-bold tracking-[-0.03em] text-slate-900">{employees.length}</p>
                  <p className="mt-2 text-sm text-slate-500">Toàn bộ nhân sự đã lưu trong hệ thống.</p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Đang hoạt động</p>
                  <p className="mt-3 text-3xl font-bold tracking-[-0.03em] text-slate-900">
                    {employees.filter((employee) => employee.is_active).length}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Nhân sự đang bật để dùng cho import, bảng công và export.</p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Đã map Notion</p>
                  <p className="mt-3 text-3xl font-bold tracking-[-0.03em] text-slate-900">
                    {employees.filter((employee) => Boolean(employee.notion_name?.trim())).length}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Sẵn sàng đối soát đơn nghỉ phép từ file CSV Notion.</p>
                </div>
              </div>
            </div>

            <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_60px_-42px_rgba(15,23,42,0.28)]" style={{ minWidth: 0, width: '100%', overflow: 'hidden' }}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div className="grid gap-2">
                  <h3 className="m-0 text-lg font-bold tracking-[-0.02em] text-slate-900">Bảng hồ sơ nhân viên</h3>
                  <p className="text-sm text-slate-500">Tìm kiếm tức thời trên toàn bộ hồ sơ rồi mới chia 10 người mỗi trang.</p>
                </div>

                <label className="block w-full max-w-md text-sm font-semibold text-slate-600">
                  Tìm kiếm nhanh
                  <input
                    className="mt-2 h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-900 outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                    value={employeeSearch}
                    onChange={(e) => {
                      setEmployeeSearch(e.target.value)
                      setEmployeeDirectoryPage(1)
                    }}
                    placeholder="Mã máy, mã NV, họ tên, Notion, email..."
                  />
                </label>
              </div>

              <div className="employee-directory-controls" aria-label="Bộ lọc hồ sơ nhân viên">
                <label>
                  Phòng ban
                  <select
                    value={employeeDepartmentFilter}
                    onChange={(event) => {
                      setEmployeeDepartmentFilter(event.target.value)
                      setEmployeeDirectoryPage(1)
                    }}
                  >
                    <option value="all">Tất cả phòng ban</option>
                    {employeeDepartmentOptions.map((department) => (
                      <option key={department} value={department}>{department}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Trạng thái
                  <select
                    value={employeeStatusFilter}
                    onChange={(event) => {
                      setEmployeeStatusFilter(event.target.value as EmployeeDirectoryStatusFilter)
                      setEmployeeDirectoryPage(1)
                    }}
                  >
                    <option value="all">Tất cả trạng thái</option>
                    <option value="active">Đang hoạt động</option>
                    <option value="inactive">Đã nghỉ việc</option>
                  </select>
                </label>
                <label>
                  Loại nhân viên
                  <select
                    value={employeeTypeFilter}
                    onChange={(event) => {
                      setEmployeeTypeFilter(event.target.value)
                      setEmployeeDirectoryPage(1)
                    }}
                  >
                    <option value="all">Tất cả loại nhân viên</option>
                    {Object.entries(EMPLOYEE_TYPE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="employee-directory-reset"
                  onClick={() => {
                    setEmployeeSearch('')
                    setEmployeeDepartmentFilter('all')
                    setEmployeeStatusFilter('all')
                    setEmployeeTypeFilter('all')
                    setEmployeeDirectoryPage(1)
                  }}
                >
                  Đặt lại
                </button>
              </div>
              <div className="employee-directory-result-summary" aria-live="polite">
                <span>Tìm thấy <strong>{filteredEmployeeDirectoryRows.length}</strong> / {employees.length} hồ sơ</span>
                <span>Trang {employeeDirectoryPagination.currentPage} / {employeeDirectoryPagination.totalPages} · {EMPLOYEE_DIRECTORY_PAGE_SIZE} người/trang</span>
              </div>

              <div
                className="employee-directory-table-wrap mt-6 w-full max-w-full rounded-[24px] border border-slate-200"
                style={{ width: '100%', maxWidth: '100%' }}
              >
                <table className="employee-directory-table min-w-full divide-y divide-slate-200 text-sm text-slate-700" style={{ minWidth: '2900px' }}>
                  <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 shadow-[0_1px_0_rgba(226,232,240,1)]">
                    <tr>
                      <th className="employee-directory-sticky employee-directory-sticky-1 px-4 py-3">Mã máy / Mã NV</th>
                      <th className="employee-directory-sticky employee-directory-sticky-2 px-4 py-3">Họ tên &amp; Chức vụ</th>
                      <th className="employee-directory-sticky employee-directory-sticky-3 px-4 py-3">Tài khoản</th>
                      <th className="employee-directory-sticky employee-directory-sticky-4 px-4 py-3">Tên Notion</th>
                      <th className="px-4 py-3">Phòng ban</th>
                      <th className="px-4 py-3 text-right">Lương HĐLĐ (VND)</th>
                      {/* Cột phụ cấp mặc định — nền vàng nhạt */}
                      <th className="px-3 py-3 text-right" style={{ background: '#fffbeb', color: '#92400e', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
                        CƠM (MIỄN)
                      </th>
                      <th className="px-3 py-3 text-right" style={{ background: '#fffbeb', color: '#92400e', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
                        CƠM (THUẾ)
                      </th>
                      <th className="px-3 py-3 text-right" style={{ background: '#fffbeb', color: '#92400e', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
                        ĐT (MIỄN)
                      </th>
                      <th className="px-3 py-3 text-right" style={{ background: '#fffbeb', color: '#92400e', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
                        XĂNG XE
                      </th>
                      <th className="px-3 py-3 text-right" style={{ background: '#fffbeb', color: '#d97706', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
                        KPI
                      </th>
                      <th className="px-3 py-3 text-right" style={{ background: '#fffbeb', color: '#92400e', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
                        TN KHÁC
                      </th>
                      <th className="px-3 py-3 text-right" style={{ background: '#fffbeb', color: '#b45309', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
                        THƯỞNG
                      </th>
                      <th className="px-3 py-3 text-right" style={{ background: '#fffbeb', color: '#92400e', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
                        LƯƠNG T14
                      </th>
                      <th className="px-4 py-3">Loại NV</th>
                      <th className="px-4 py-3 text-center">NTT</th>
                      <th className="px-4 py-3">Ngân hàng &amp; STK</th>
                      <th className="px-4 py-3">Ngày bắt đầu</th>
                      <th className="px-4 py-3">Trạng thái</th>
                      <th className="px-4 py-3 text-right">Tác vụ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 bg-white">
                    {employeeDirectoryPagination.rows.length === 0 && (
                      <tr>
                        <td colSpan={20} className="px-4 py-10 text-center text-sm text-slate-500">
                          {employees.length === 0
                            ? 'Chưa có hồ sơ nhân sự. Bấm "Thêm nhân viên mới" để tạo mapping đầu tiên.'
                            : 'Không có hồ sơ phù hợp với nội dung tìm kiếm và bộ lọc hiện tại.'}
                        </td>
                      </tr>
                    )}

                    {employeeDirectoryPagination.rows.map((emp) => (
                      <tr key={emp.id} className="align-top hover:bg-slate-50/80">
                        {/* Mã máy / Mã NV */}
                        <td className="employee-directory-sticky employee-directory-sticky-1 px-4 py-4">
                          {editingEmployeeId === emp.id ? (
                            <div className="space-y-2">
                              <input
                                className="h-9 w-full min-w-[110px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.machine_employee_id}
                                placeholder="Mã máy (E001)"
                                onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, machine_employee_id: e.target.value }))}
                              />
                              <input
                                className="h-9 w-full min-w-[110px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition bg-slate-100 cursor-not-allowed text-slate-500"
                                value={editEmployeeForm.employee_code}
                                placeholder="Mã NV (SL001)"
                                disabled
                              />
                            </div>
                          ) : (
                            <div className="space-y-1">
                              <span className="inline-flex rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-700">{emp.machine_employee_id}</span>
                              {emp.employee_code && <p className="text-xs text-slate-400">{emp.employee_code}</p>}
                            </div>
                          )}
                        </td>
                        {/* Họ tên & Chức vụ */}
                        <td className="employee-directory-sticky employee-directory-sticky-2 px-4 py-4">
                          {editingEmployeeId === emp.id ? (
                            <div className="space-y-2">
                              <input
                                className="h-9 w-full min-w-[200px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.full_name}
                                placeholder="Họ tên tiếng Việt"
                                onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, full_name: e.target.value }))}
                              />
                              <input
                                className="h-9 w-full min-w-[200px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.position}
                                placeholder="Chức vụ"
                                onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, position: e.target.value }))}
                              />
                            </div>
                          ) : (
                            <div className="space-y-1">
                              <p 
                                className="font-semibold text-[#163B66] underline cursor-pointer hover:text-blue-700 transition"
                                onClick={() => {
                                  setDetailEmployeePassword('')
                                  setDetailEmployeeOriginalType((emp.employee_type || 'FULLTIME') as EmployeeType)
                                  setDetailEmployeeTypeEffectiveDate(new Date().toISOString().slice(0, 10))
                                  setDetailEmployee(employeeWithDerivedUsername(emp))
                                }}
                              >
                                {emp.full_name}
                              </p>
                              <p className="text-xs text-slate-500">{emp.position ?? <span className="italic">Chưa có chức vụ</span>}</p>
                            </div>
                          )}
                        </td>
                        {/* Tài khoản */}
                        <td className="employee-directory-sticky employee-directory-sticky-3 px-4 py-4">
                          {editingEmployeeId === emp.id ? (
                            <div className="space-y-2">
                              <input
                                className="h-9 w-full min-w-[140px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.username}
                                placeholder="Tên đăng nhập"
                                onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, username: e.target.value }))}
                              />
                              <input
                                type="password"
                                className="h-9 w-full min-w-[140px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.password}
                                placeholder="Mật khẩu mới (để trống nếu giữ nguyên)"
                                onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, password: e.target.value }))}
                              />
                            </div>
                          ) : (
                            <div className="space-y-1">
                              {emp.username ? (
                                <p className="font-semibold text-slate-900 font-mono text-xs">{emp.username}</p>
                              ) : (
                                <span className="text-xs italic text-slate-400">Chưa cấp tài khoản</span>
                              )}
                              <span
                                className={`inline-flex rounded-full px-2 py-1 text-[11px] font-bold ${
                                  (emp.account_role || emp.access_role) === 'HR_ADMIN'
                                    ? 'bg-purple-50 text-purple-700'
                                    : (emp.account_role || emp.access_role) === 'IT_ADMIN'
                                      ? 'bg-sky-50 text-sky-700'
                                      : (emp.account_role || emp.access_role) === 'ADMIN'
                                        ? 'bg-orange-50 text-orange-800'
                                        : (emp.account_role || emp.access_role) === 'DIRECTOR'
                                          ? 'bg-cyan-50 text-cyan-800'
                                        : 'bg-slate-100 text-slate-600'
                                }`}
                                title={emp.access_role_reason || ''}
                              >
                                {!emp.account_role && 'Sẽ cấp: '}
                                {ACCESS_ROLE_LABELS[emp.account_role || emp.access_role || 'USER']}
                              </span>
                            </div>
                          )}
                        </td>
                        {/* Tên Notion */}
                        <td className="employee-directory-sticky employee-directory-sticky-4 px-4 py-4">
                          {editingEmployeeId === emp.id ? (
                            <input
                              className="h-9 w-full min-w-[180px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                              value={editEmployeeForm.notion_name}
                              placeholder="DOCS - ..."
                              onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, notion_name: e.target.value }))}
                            />
                          ) : emp.notion_name ? (
                            <span className="text-sm text-slate-700">{emp.notion_name}</span>
                          ) : (
                            <span className="text-sm italic text-amber-600">Chưa map Notion</span>
                          )}
                        </td>
                        {/* Phòng ban */}
                        <td className="px-4 py-4 space-y-2">
                          {editingEmployeeId === emp.id ? (
                            <>
                              <select
                                className="h-9 w-full min-w-[150px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.department_id ?? ''}
                                onChange={(e) => setEditEmployeeForm((prev) => ({ 
                                  ...prev, 
                                  department_id: e.target.value ? Number(e.target.value) : null,
                                  department_name: e.target.value ? e.target.options[e.target.selectedIndex].text : '' 
                                }))}
                              >
                                <option value="">-- Chọn phòng ban --</option>
                                {departments.map((d) => (
                                  <option key={d.id} value={d.id}>{d.name}</option>
                                ))}
                              </select>
                              
                              <select
                                className="h-9 w-full min-w-[150px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-amber-500 focus:ring-4 focus:ring-amber-500/10"
                                value={editEmployeeForm.bonus_coefficient}
                                onChange={(e) => setEditEmployeeForm((prev) => ({ 
                                  ...prev, 
                                  bonus_coefficient: e.target.value
                                }))}
                              >
                                <option value="0">-- Mức Bonus (Theo PB hiện tại) --</option>
                                {departments.map((d) => {
                                  const rulesText = d.current_bonus_rules?.length 
                                    ? d.current_bonus_rules.map((r: any) => `${Math.round(r.rate * 100)}%`).join(', ') 
                                    : 'Chưa cấu hình'
                                  return (
                                    <option key={d.id} value={d.id}>
                                      Bonus {d.name} ({rulesText})
                                    </option>
                                  )
                                })}
                              </select>
                            </>
                          ) : (
                            <div className="flex flex-col gap-1">
                              <span>{emp.department_name ?? '-'}</span>
                              {emp.bonus_coefficient && emp.bonus_coefficient > 0 && (
                                <span className="text-[11px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded w-fit">
                                  Bonus: PB ID {emp.bonus_coefficient}
                                </span>
                              )}
                            </div>
                          )}
                        </td>
                        {/* Lương HĐLĐ */}
                        <td className="px-4 py-4 text-right">
                          {editingEmployeeId === emp.id ? (
                            <VndInput
                              className="h-9 w-full min-w-[130px] rounded-xl border border-slate-200 px-3 text-sm text-right outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                              value={editEmployeeForm.contract_salary}
                              placeholder="15.000.000"
                              onValueChange={(value) => setEditEmployeeForm((prev) => ({ ...prev, contract_salary: String(value) }))}
                            />
                          ) : (
                            <span className={`font-semibold ${ emp.contract_salary > 0 ? 'text-[#163B66]' : 'text-slate-400 italic' }`}>
                              {emp.contract_salary > 0 ? formatVnd(emp.contract_salary) : 'Chưa cập nhật'}
                            </span>
                          )}
                        </td>
                        {/* Phụ cấp mặc định từ bảng lương */}
                        {(() => {
                          const inp = salaryInputs.find((x: any) => x.employee_id === emp.id)
                          const typeDefaults = getMonthlyAllowanceDefaults(emp.employee_type as EmployeeType)
                          const fmt = (v: number) => v > 0
                            ? formatVnd(v)
                            : <span className="text-slate-300 text-xs">—</span>
                          const cellCls = 'px-3 py-4 text-right text-xs tabular-nums'
                          const pillStyle: React.CSSProperties = {
                            display: 'inline-block',
                            background: '#fffbeb',
                            border: '1px solid #fde68a',
                            borderRadius: 6,
                            padding: '2px 7px',
                            fontWeight: 600,
                            color: '#92400e',
                            minWidth: 72,
                            textAlign: 'right',
                          }
                          const fields = [
                            { key: 'meal_allowance_free',  def: Number(typeDefaults.meal_allowance_free) },
                            { key: 'meal_allowance_tax',   def: 0 },
                            { key: 'phone_allowance_free', def: Number(typeDefaults.phone_allowance_free) },
                            { key: 'trans_allowance_tax',  def: Number(typeDefaults.trans_allowance_tax) },
                            { key: 'perf_allowance_tax',   def: Number(typeDefaults.perf_allowance_tax) },
                            { key: 'other_income',         def: 0 },
                            { key: 'bonus',                def: 0 },
                            { key: 'bonus_14',             def: 0 },
                          ]
                          return fields.map(({ key, def }) => {
                            if (editingEmployeeId === emp.id) {
                              const val = editEmployeeForm[key as keyof typeof editEmployeeForm] ?? String(def)
                              return (
                                <td key={key} className={cellCls}>
                                  <VndInput
                                    className="h-9 w-24 rounded-xl border border-slate-200 px-2 text-sm text-right outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                    value={typeof val === 'boolean' ? '' : val}
                                    onValueChange={(value) => setEditEmployeeForm((prev) => ({ ...prev, [key]: String(value) }))}
                                  />
                                </td>
                              )
                            } else {
                              const val = inp ? Number(inp[key]) : def
                              return (
                                <td key={key} className={cellCls}>
                                  <span style={pillStyle}>{fmt(val)}</span>
                                </td>
                              )
                            }
                          })
                        })()}
                        {/* Loại NV */}
                        <td className="px-4 py-4">
                          {editingEmployeeId === emp.id ? (
                            <select
                              className="h-9 w-full min-w-[120px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                              value={editEmployeeForm.employee_type}
                              onChange={(e) => setEditEmployeeForm((prev) => ({
                                ...prev,
                                employee_type: e.target.value,
                                ...getMonthlyAllowanceDefaults(e.target.value),
                              }))}
                            >
                              <option value="FULLTIME">Chính thức</option>
                              <option value="PROBATION">Thử việc</option>
                              <option value="INTERN">Học việc</option>
                              <option value="TRAINEE">Thực tập</option>
                            </select>
                          ) : (
                            <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${ emp.employee_type === 'FULLTIME' ? 'bg-blue-50 text-blue-700' : 'bg-amber-50 text-amber-700' }`}>
                              {getEmployeeTypeLabel(emp.employee_type)}
                            </span>
                          )}
                        </td>
                        {/* Người phụ thuộc */}
                        <td className="px-4 py-4 text-center">
                          {editingEmployeeId === emp.id ? (
                            <input
                              type="number"
                              min={0}
                              className="h-9 w-16 rounded-xl border border-slate-200 px-3 text-sm text-center outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                              value={editEmployeeForm.dependents_count}
                              onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, dependents_count: e.target.value }))}
                            />
                          ) : (
                            <span className="font-semibold text-slate-700">{emp.dependents_count}</span>
                          )}
                        </td>
                        {/* Ngân hàng & STK */}
                        <td className="px-4 py-4">
                          {editingEmployeeId === emp.id ? (
                            <div className="space-y-2">
                              <input
                                className="h-9 w-full min-w-[140px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.bank_name}
                                placeholder="Tên ngân hàng (VCB)"
                                onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, bank_name: e.target.value }))}
                              />
                              <input
                                className="h-9 w-full min-w-[140px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.account_number}
                                placeholder="Số tài khoản"
                                onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, account_number: e.target.value }))}
                              />
                            </div>
                          ) : (
                            <div className="space-y-1">
                              {emp.bank_name ? <p className="text-xs font-semibold text-slate-700">{emp.bank_name}</p> : null}
                              {emp.account_number ? <p className="text-xs text-slate-500 font-mono">{emp.account_number}</p> : <span className="text-xs italic text-slate-400">Chưa có STK</span>}
                            </div>
                          )}
                        </td>
                        {/* Ngày bắt đầu */}
                        <td className="px-4 py-4">
                          {editingEmployeeId === emp.id ? (
                            <div className="space-y-2">
                              <BrandedDateInput
                                className="h-9 w-full min-w-[130px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                value={editEmployeeForm.start_date}
                                onChange={(e) => setEditEmployeeForm((prev) => ({ ...prev, start_date: e.target.value }))}
                              />
                              {editEmployeeForm.status === 'RESIGNED' && (
                                <BrandedDateInput
                                  className="h-9 w-full min-w-[130px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                                  aria-label={`Ngày làm việc cuối của ${emp.full_name}`}
                                  value={editEmployeeForm.last_working_date}
                                  onChange={(e) => setEditEmployeeForm((prev) => ({
                                    ...prev,
                                    last_working_date: e.target.value,
                                    resignation_period: e.target.value ? e.target.value.slice(0, 7) : '',
                                  }))}
                                />
                              )}
                            </div>
                          ) : (
                            <div className="space-y-1 text-xs">
                              <p><span className="text-slate-400">Vào:</span> {emp.start_date ? emp.start_date.split('T')[0].split('-').reverse().join('/') : '-'}</p>
                              {emp.status === 'RESIGNED' && (emp.last_working_date || emp.resignation_period) && (
                                <p><span className="text-rose-600 font-semibold">Ngày làm cuối:</span> {emp.last_working_date ? emp.last_working_date.split('T')[0].split('-').reverse().join('/') : emp.resignation_period}</p>
                              )}
                              {emp.status === 'RESIGNED' && emp.last_pay_date && (
                                <p><span className="text-slate-500 font-semibold">Trả lương cuối:</span> {emp.last_pay_date.split('T')[0].split('-').reverse().join('/')}</p>
                              )}
                            </div>
                          )}
                        </td>
                        {/* Trạng thái */}
                        <td className="px-4 py-4">
                          {editingEmployeeId === emp.id ? (
                            <select
                              className="h-9 w-full min-w-[130px] rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10"
                              value={editEmployeeForm.status}
                              onChange={(e) => setEditEmployeeForm((prev) => ({ 
                                ...prev, 
                                status: e.target.value,
                                is_active: e.target.value === 'ACTIVE',
                                ...(e.target.value !== 'RESIGNED' ? { resignation_period: '', last_working_date: '', last_pay_date: '' } : {}),
                              }))}
                            >
                              <option value="ACTIVE">Đang hoạt động</option>
                              <option value="LOCKED">Tạm khóa</option>
                              <option value="RESIGNED">Đã nghỉ việc</option>
                            </select>
                          ) : (
                            <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${ 
                              emp.status === 'ACTIVE' 
                                ? 'bg-emerald-50 text-emerald-700' 
                                : emp.status === 'RESIGNED'
                                ? 'bg-rose-50 text-rose-700'
                                : 'bg-slate-100 text-slate-500' 
                            }`}>
                              {emp.status === 'ACTIVE' 
                                ? 'Đang hoạt động' 
                                : emp.status === 'RESIGNED' 
                                ? 'Đã nghỉ việc' 
                                : 'Tạm khóa'}
                            </span>
                          )}
                        </td>
                        {/* Tác vụ */}
                        <td className="px-4 py-4">
                          <div className="flex justify-end gap-2">
                            {editingEmployeeId === emp.id ? (
                              <>
                                <button
                                  type="button"
                                  onClick={() => saveEmployeeInline(emp.id)}
                                  className="inline-flex items-center justify-center rounded-2xl bg-[#163B66] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#102B49]"
                                >
                                  Lưu
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setEditingEmployeeId(null)}
                                  className="inline-flex items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                                >
                                  Hủy
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  type="button"
                                  onClick={() => startEditEmployee(emp)}
                                  className="inline-flex h-[36px] w-[80px] items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                                >
                                  Sửa
                                </button>
                                <button
                                  type="button"
                                  onClick={() => deleteEmployee(emp)}
                                  className="app-delete-button inline-flex h-[36px] w-[80px] items-center justify-center rounded-xl border border-rose-200 bg-rose-50 px-4 text-sm font-semibold text-rose-700 transition hover:bg-rose-100"
                                >
                                  Xóa
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <nav className="employee-directory-pagination" aria-label="Phân trang hồ sơ nhân viên">
                <span>
                  {filteredEmployeeDirectoryRows.length > 0
                    ? `Hiển thị ${employeeDirectoryPagination.startIndex + 1}–${Math.min(employeeDirectoryPagination.startIndex + EMPLOYEE_DIRECTORY_PAGE_SIZE, filteredEmployeeDirectoryRows.length)} trong ${filteredEmployeeDirectoryRows.length}`
                    : 'Không có kết quả'}
                </span>
                <div className="employee-directory-page-buttons">
                  <button
                    type="button"
                    onClick={() => setEmployeeDirectoryPage((page) => Math.max(1, page - 1))}
                    disabled={employeeDirectoryPagination.currentPage === 1}
                  >
                    Trước
                  </button>
                  {Array.from({ length: employeeDirectoryPagination.totalPages }, (_, index) => index + 1).map((page) => (
                    <button
                      key={page}
                      type="button"
                      className={page === employeeDirectoryPagination.currentPage ? 'is-active' : ''}
                      onClick={() => setEmployeeDirectoryPage(page)}
                      aria-current={page === employeeDirectoryPagination.currentPage ? 'page' : undefined}
                    >
                      {page}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setEmployeeDirectoryPage((page) => Math.min(employeeDirectoryPagination.totalPages, page + 1))}
                    disabled={employeeDirectoryPagination.currentPage === employeeDirectoryPagination.totalPages}
                  >
                    Sau
                  </button>
                </div>
              </nav>
            </div>
          </section>
        )}

        {activeTab === 'timesheets' && (
          <section className="grid-two">
            <div className="card">
              <div className="timesheet-query-header">
                <div className="timesheet-query-summary">
                  <h2>Tra cứu tháng công</h2>
                  <p>Tải file chấm công khi cần, dữ liệu chi tiết được thu gọn mặc định.</p>
                </div>
                <button
                  type="button"
                  className="timesheet-upload-toggle"
                  onClick={() => setIsTimesheetUploadOpen((open) => !open)}
                  aria-expanded={isTimesheetUploadOpen}
                >
                  {isTimesheetUploadOpen ? 'Ẩn upload' : 'Upload chấm công'}
                </button>
              </div>
              <label>
                Period Start
                <BrandedDateInput value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
              </label>
              <label>
                Period End
                <BrandedDateInput value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
              </label>
              <button type="button" onClick={loadTimesheets} disabled={loading}>Tải bảng công</button>
            </div>

            <HolidayConfigurator apiRequest={apiRequest} />

            <div className="card full-width">
              <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px', borderBottom: '1px solid #cbd5e1', paddingBottom: '12px', marginBottom: '16px' }}>
                <h2 style={{ margin: 0, fontSize: '18px', color: '#1e3a8a', fontWeight: 800 }}>Grid ngày công 23 → 22</h2>
                
                <div className="app-action-toolbar" style={{ flexDirection: 'row' }}>
                  <MonthYearSelect
                      id="timesheet-period"
                      value={`${new Date(periodEnd).getFullYear()}-${String(new Date(periodEnd).getMonth() + 1).padStart(2, '0')}`}
                      onChange={(val) => {
                        const [year, month] = val.split('-');
                        const endD = new Date(Number(year), Number(month) - 1, 22);
                        const startD = new Date(Number(year), Number(month) - 2, 23);
                        const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
                        setPeriodStart(fmt(startD));
                        setPeriodEnd(fmt(endD));
                      }}
                      compact
                      yearLabel="Năm công"
                      monthLabel="Tháng công"
                  />
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '13px', color: '#475569', fontWeight: 600 }}>Từ ngày:</span>
                    <BrandedDateInput
                      containerClassName="branded-date-inline"
                      value={periodStart} 
                      onChange={(e) => setPeriodStart(e.target.value)} 
                      style={{ height: '32px', padding: '0 8px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', outline: 'none' }}
                    />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '13px', color: '#475569', fontWeight: 600 }}>Đến ngày:</span>
                    <BrandedDateInput
                      containerClassName="branded-date-inline"
                      value={periodEnd} 
                      onChange={(e) => setPeriodEnd(e.target.value)} 
                      style={{ height: '32px', padding: '0 8px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', outline: 'none' }}
                    />
                  </div>
                  {(() => {
                    const s = new Date(periodStart);
                    const e = new Date(periodEnd);
                    if (!isNaN(s.getTime()) && !isNaN(e.getTime())) {
                      let workingDays = 0;
                      let cur = new Date(s);
                      while (cur <= e) {
                        if (cur.getDay() !== 0 && cur.getDay() !== 6) { // Exclude Saturdays (6) and Sundays (0)
                          workingDays++;
                        }
                        cur.setDate(cur.getDate() + 1);
                      }
                      return (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '32px', padding: '0 16px', borderRadius: '6px', backgroundColor: '#f1f5f9', border: '1px solid #cbd5e1', color: '#0f172a', fontSize: '13px', fontWeight: 700, whiteSpace: 'nowrap' }}>
                            {workingDays > 0 ? `${workingDays} ngày công` : '0 ngày công'}
                          </div>
                          {/* Nút Khóa / Mở khóa bảng công (Icon only) - Style như bên bảng lương */}
                          <button
                            type="button"
                            onClick={toggleLockTimesheet}
                            disabled={loading || timesheetGridRows.length === 0}
                            title={timesheetIsLocked ? 'Bảng công đang khóa. Nhấp để mở khóa.' : 'Nhấp để khóa bảng công'}
                            aria-label={timesheetIsLocked ? 'Mở khóa bảng công' : 'Khóa bảng công'}
                            className={`icon-only-control timesheet-lock-control ${timesheetIsLocked ? 'is-locked' : 'is-unlocked'}`}
                          >
                            <AppIcon name={timesheetIsLocked ? 'lock' : 'unlock'} size={19} />
                          </button>
                        </div>
                      );
                    }
                    return null;
                  })()}
                  <button
                    type="button"
                    className="app-action-button"
                    onClick={loadTimesheets}
                    disabled={loading}
                    style={{
                      height: '32px',
                      padding: '0 16px',
                      borderRadius: '6px',
                      border: 'none',
                      background: 'linear-gradient(135deg, #1e3a8a, #172554)',
                      color: '#fff',
                      fontSize: '13px',
                      fontWeight: 700,
                      cursor: 'pointer',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {loading ? 'Đang tải...' : 'Xem công'}
                  </button>
                  {isBusinessAdminRole(currentUser?.role) && <button
                    type="button"
                    className="app-action-button"
                    onClick={syncTimesheetToSalary}
                    disabled={loading || timesheetGridRows.length === 0}
                    style={{
                      height: '32px',
                      padding: '0 16px',
                      borderRadius: '6px',
                      border: 'none',
                      background: 'linear-gradient(135deg, #10b981, #059669)',
                      color: '#fff',
                      fontSize: '13px',
                      fontWeight: 700,
                      cursor: 'pointer',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '6px'
                    }}
                    title="Chốt dữ liệu và đồng bộ số ngày công sang Bảng lương"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    Chốt bảng công
                  </button>}
                  <button
                    type="button"
                    className="app-action-button timesheet-history-open"
                    onClick={() => {
                      setOverrideLogs([])
                      setOverrideHistoryOpen(true)
                      void loadOverrideHistory({ silent: true })
                    }}
                  >
                    <AppIcon name="history" size={15} />
                    Lịch sử Override
                  </button>
                  <button
                    type="button"
                    className="app-action-button app-download-button"
                    onClick={exportTimesheet}
                    disabled={loading || timesheetGridRows.length === 0}
                    style={{
                      height: '32px',
                      padding: '0 16px',
                      borderRadius: '6px',
                      border: '1px solid #1d4ed8',
                      background: '#fff',
                      color: '#1d4ed8',
                      fontSize: '13px',
                      fontWeight: 700,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '6px'
                    }}
                    title="Xuất bảng công ra file Excel"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Xuất Excel
                  </button>
                  <button
                    type="button"
                    className="app-action-button app-action-button--danger app-delete-button"
                    onClick={deleteTimesheetPeriod}
                    disabled={loading || timesheetIsLocked}
                    style={{
                      height: '32px',
                      padding: '0 16px',
                      borderRadius: '6px',
                      border: '1px solid #ef4444',
                      background: '#fff',
                      color: '#ef4444',
                      fontSize: '13px',
                      fontWeight: 700,
                      cursor: timesheetIsLocked ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '6px',
                      opacity: timesheetIsLocked ? 0.6 : 1
                    }}
                    title={timesheetIsLocked ? "Bảng công đã bị khóa, không thể xóa" : "Xóa trắng toàn bộ bảng công của tháng này"}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                    Xóa bảng công
                  </button>
                </div>
              </div>
              <div className="timesheet-grid-controls" aria-label="Tìm kiếm và lọc bảng công">
                <label className="timesheet-grid-control timesheet-grid-search">
                  <span>Tìm kiếm toàn bộ bảng công</span>
                  <input
                    type="search"
                    value={timesheetEmployeeFilter}
                    onChange={(event) => {
                      setTimesheetEmployeeFilter(event.target.value)
                      setTimesheetPage(1)
                    }}
                    placeholder="Tên, ID máy, phòng ban, ký hiệu công..."
                    aria-label="Tìm kiếm toàn bộ bảng công"
                  />
                </label>
                <label className="timesheet-grid-control">
                  <span>Phòng ban</span>
                  <select
                    value={timesheetDepartmentFilter}
                    onChange={(event) => {
                      setTimesheetDepartmentFilter(event.target.value)
                      setTimesheetPage(1)
                    }}
                    aria-label="Lọc bảng công theo phòng ban"
                  >
                    <option value="all">Tất cả phòng ban</option>
                    {timesheetDepartmentOptions.map((department) => (
                      <option key={department} value={department}>{department}</option>
                    ))}
                  </select>
                </label>
                <label className="timesheet-grid-control">
                  <span>Bất thường</span>
                  <select
                    value={timesheetAbnormalFilter}
                    onChange={(event) => {
                      setTimesheetAbnormalFilter(event.target.value as TimesheetAbnormalFilter)
                      setTimesheetPage(1)
                    }}
                    aria-label="Lọc bảng công theo trạng thái bất thường"
                  >
                    <option value="all">Tất cả trạng thái</option>
                    <option value="abnormal">Có bất thường</option>
                    <option value="normal">Không bất thường</option>
                  </select>
                </label>
                <label className="timesheet-grid-control">
                  <span>Ký hiệu công</span>
                  <select
                    value={timesheetSymbolFilter}
                    onChange={(event) => {
                      setTimesheetSymbolFilter(event.target.value)
                      setTimesheetPage(1)
                    }}
                    aria-label="Lọc bảng công theo ký hiệu công"
                  >
                    <option value="all">Tất cả ký hiệu</option>
                    <option value="X">X — Đi làm</option>
                    <option value="P">P — Nghỉ phép</option>
                    <option value="Ro">Ro — Vắng</option>
                    <option value="CT">CT — Công tác</option>
                    <option value="X/P">X/P</option>
                    <option value="P/X">P/X</option>
                    <option value="P/Ro">P/Ro</option>
                    <option value="Ro/P">Ro/P</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="timesheet-grid-reset"
                  onClick={() => {
                    setTimesheetEmployeeFilter('')
                    setTimesheetDepartmentFilter('all')
                    setTimesheetAbnormalFilter('all')
                    setTimesheetSymbolFilter('all')
                    setTimesheetPage(1)
                  }}
                  disabled={
                    !timesheetEmployeeFilter
                    && timesheetDepartmentFilter === 'all'
                    && timesheetAbnormalFilter === 'all'
                    && timesheetSymbolFilter === 'all'
                  }
                >
                  Đặt lại
                </button>
              </div>
              <div className="timesheet-grid-result-summary" aria-live="polite">
                <span>
                  Tìm thấy <strong>{filteredTimesheetGridRows.length}</strong> / {timesheetGridRows.length} nhân viên
                </span>
                <span>Trang {timesheetPagination.currentPage} / {timesheetPagination.totalPages} · 10 người/trang</span>
              </div>
              <div className="timesheet-legend" aria-label="Giải thích ký hiệu bảng công">
                <div className="timesheet-legend-item symbol-work">
                  <span className="timesheet-legend-chip">X</span>
                  <span>Đi làm đủ ngày</span>
                </div>
                <div className="timesheet-legend-item symbol-paid-leave">
                  <span className="timesheet-legend-chip">P</span>
                  <span>Nghỉ phép cả ngày</span>
                </div>
                <div className="timesheet-legend-item symbol-absent">
                  <span className="timesheet-legend-chip">Ro</span>
                  <span>Vắng không lý do</span>
                </div>
                <div className="timesheet-legend-item symbol-business-trip">
                  <span className="timesheet-legend-chip">CT</span>
                  <span>Công tác</span>
                </div>
                <div className="timesheet-legend-item symbol-half-work-leave">
                  <span className="timesheet-legend-chip">X/P</span>
                  <span>Sáng làm, chiều nghỉ phép</span>
                </div>
                <div className="timesheet-legend-item symbol-half-leave-work">
                  <span className="timesheet-legend-chip">P/X</span>
                  <span>Sáng nghỉ phép, chiều làm</span>
                </div>
                <div className="timesheet-legend-item symbol-half-leave-absent">
                  <span className="timesheet-legend-chip">P/Ro</span>
                  <span>Sáng nghỉ phép, chiều vắng</span>
                </div>
                <div className="timesheet-legend-item symbol-half-absent-leave">
                  <span className="timesheet-legend-chip">Ro/P</span>
                  <span>Sáng vắng, chiều nghỉ phép</span>
                </div>
              </div>
              <div
                className="table-wrap timesheet-grid-scroll"
                role="region"
                aria-label="Bảng công chi tiết"
                tabIndex={0}
              >
                <table className="timesheet-grid-table">
                  <thead>
                    <tr>
                      <th rowSpan={2} className="sticky-col sticky-index">ID</th>
                      <th rowSpan={2} className="sticky-col sticky-name">Họ Và Tên</th>
                      <th rowSpan={2} className="sticky-col sticky-flag">Bất thường</th>
                      <th rowSpan={2} className="timesheet-total-header" title="Công tính lương: công thực tế + phép hưởng lương + WFH">Ngày công</th>
                      <th rowSpan={2} className="timesheet-total-header" title="Công thực tế có dữ liệu chấm công">Ngày công TT</th>
                      {timesheetDayColumns.map((column) => (
                        <th key={`${column.key}-weekday`} className={`timesheet-weekday-header ${column.is_weekend ? 'is-weekend' : ''}`}>
                          {column.weekday_label}
                        </th>
                      ))}
                      <th rowSpan={2} className="timesheet-summary-header">Nghỉ không lương</th>
                      <th rowSpan={2} className="timesheet-summary-header">Nghỉ hưởng lương</th>
                      <th rowSpan={2} className="timesheet-summary-header">Phép còn lại tháng trước</th>
                      <th rowSpan={2} className="timesheet-summary-header">Phép tháng này</th>
                      <th rowSpan={2} className="timesheet-summary-header">Phép còn lại</th>
                    </tr>
                    <tr>
                      {timesheetDayColumns.map((column) => (
                        <th key={`${column.key}-day`} className={`timesheet-day-header ${column.is_weekend ? 'is-weekend' : ''}`}>
                          {column.day_number}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {timesheetPagination.rows.length === 0 && (
                      <tr>
                        <td colSpan={timesheetDayColumns.length + 10} className="timesheet-grid-empty">
                          Không có nhân viên phù hợp với nội dung tìm kiếm và bộ lọc hiện tại.
                        </td>
                      </tr>
                    )}
                    {timesheetPagination.rows.map((row, idx) => {
                      return (
                        <tr
                          key={`grid-${row.employee_id}`}
                          id={`timesheet-employee-${row.employee_id}`}
                          className={`scroll-mt-28 transition-colors duration-150 hover:bg-slate-50/80 ${timesheetNotificationEmployeeId === row.employee_id ? 'bg-amber-100 ring-2 ring-inset ring-amber-400' : ''}`}
                        >
                          <td className="sticky-col sticky-index">{timesheetPagination.startIndex + idx + 1}</td>
                          <td className="sticky-col sticky-name timesheet-name-cell">
                            <strong>{row.full_name}</strong>
                            <span className="timesheet-name-meta">
                              {row.machine_employee_id}
                              {row.department_name ? ` • ${row.department_name}` : ''}
                            </span>
                          </td>
                          <td className="sticky-col sticky-flag">{row.abnormal_days > 0 ? `Có (${row.abnormal_days})` : 'Không'}</td>
                          <td className="timesheet-total-cell timesheet-payroll-total" title="Ngày công dùng để tính lương">
                            {formatGridNumber(row.total_payroll_days)}
                          </td>
                          <td className="timesheet-total-cell" title="Ngày công thực tế có chấm công">
                            {formatGridNumber(row.total_work_days)}
                          </td>
                          {timesheetDayColumns.map((column) => (
                              <TimesheetCell
                                key={`${row.employee_id}-${column.key}`}
                                row={row}
                                column={column}
                                loadTimesheets={loadTimesheets}
                                setMessage={setMessage}
                                setLoading={setLoading}
                                apiRequest={apiRequest}
                                loadOverrideHistory={loadOverrideHistory}
                                timesheetIsLocked={timesheetIsLocked}
                              />
                          ))}
                          <td className="timesheet-summary-cell">{formatGridNumber(row.unpaid_leave_days)}</td>
                          <td className="timesheet-summary-cell">{formatGridNumber(row.paid_leave_days)}</td>
                          <td className="timesheet-summary-cell">{formatGridNumber(row.previous_paid_leave_balance)}</td>
                          <td className="timesheet-summary-cell">{formatGridNumber(row.current_month_paid_leave_credit)}</td>
                          <td className="timesheet-summary-cell">{formatGridNumber(row.remaining_paid_leave_days)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <nav className="timesheet-grid-pagination" aria-label="Phân trang bảng công">
                <span className="timesheet-grid-page-range">
                  {filteredTimesheetGridRows.length > 0
                    ? `Hiển thị ${timesheetPagination.startIndex + 1}–${Math.min(timesheetPagination.startIndex + TIMESHEET_PAGE_SIZE, filteredTimesheetGridRows.length)} trong ${filteredTimesheetGridRows.length}`
                    : 'Không có kết quả'}
                </span>
                {timesheetPagination.totalPages > 1 ? (
                  <div className="timesheet-grid-page-buttons">
                    <button
                      type="button"
                      onClick={() => setTimesheetPage((page) => Math.max(1, page - 1))}
                      disabled={timesheetPagination.currentPage === 1}
                      aria-label="Trang bảng công trước"
                      title="Về trang trước"
                    >
                      Trước
                    </button>
                    {Array.from({ length: timesheetPagination.totalPages }, (_, index) => index + 1).map((page) => (
                      <button
                        key={page}
                        type="button"
                        className={page === timesheetPagination.currentPage ? 'is-active' : ''}
                        onClick={() => setTimesheetPage(page)}
                        aria-current={page === timesheetPagination.currentPage ? 'page' : undefined}
                        aria-label={`Trang bảng công ${page}`}
                      >
                        {page}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => setTimesheetPage((page) => Math.min(timesheetPagination.totalPages, page + 1))}
                      disabled={timesheetPagination.currentPage === timesheetPagination.totalPages}
                      aria-label="Trang bảng công sau"
                      title="Sang trang sau"
                    >
                      Sau
                    </button>
                  </div>
                ) : (
                  <span className="timesheet-grid-single-page">Chỉ có 1 trang · không cần chuyển trang</span>
                )}
              </nav>
              <p className="muted">Grid web đã đọc trực tiếp header ngày + T7/CN từ backend và hiển thị đủ các cột phép như form HR.</p>
            </div>

          </section>
        )}

        {activeTab === 'timesheets' && overrideHistoryOpen && createPortal(
          <div
            className="modal-backdrop override-history-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setOverrideHistoryOpen(false)
            }}
          >
            <section
              className="override-history-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="override-history-title"
            >
              <header className="override-history-modal-header">
                <div>
                  <p>NHẬT KÝ BẢNG CÔNG</p>
                  <h2 id="override-history-title">Lịch sử Override</h2>
                  <span>{periodStart} → {periodEnd} · {overrideLogs.length} bản ghi đang hiển thị</span>
                </div>
                <button
                  type="button"
                  className="app-close-button"
                  aria-label="Đóng lịch sử Override"
                  onClick={() => setOverrideHistoryOpen(false)}
                >
                  <AppIcon name="close" size={17} />
                </button>
              </header>

              <div className="override-history-modal-body">
                <div className="inline-actions history-actions override-history-actions">
                  <label className="override-history-filter">
                    Lọc theo mã nhân viên
                    <input
                      value={overrideHistoryEmployeeId}
                      onChange={(event) => setOverrideHistoryEmployeeId(event.target.value)}
                      placeholder="Để trống = tất cả"
                    />
                  </label>
                  <label>
                    Số bản ghi
                    <input
                      type="number"
                      min={1}
                      max={1000}
                      value={overrideHistoryLimit}
                      onChange={(event) => setOverrideHistoryLimit(event.target.value)}
                    />
                  </label>
                  <button
                    className="history-download-button app-download-button"
                    type="button"
                    onClick={() => void loadOverrideHistory()}
                    disabled={loading}
                    aria-label="Tải lịch sử chỉnh sửa"
                    title="Tải lịch sử chỉnh sửa"
                  >
                  </button>
                </div>

                <div className="table-wrap compact override-history-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Mã audit</th>
                        <th>Nhân viên</th>
                        <th>Thời điểm</th>
                        <th>Ngày công</th>
                        <th className="audit-column-before">Trước</th>
                        <th className="audit-column-after">Sau</th>
                        <th>Lý do</th>
                        <th>Người sửa</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overrideLogs.length === 0 && (
                        <tr>
                          <td colSpan={8} className="override-history-empty">
                            {loading ? 'Đang tải lịch sử chỉnh sửa...' : 'Không có bản ghi Override phù hợp.'}
                          </td>
                        </tr>
                      )}
                      {overrideLogs.map((log) => (
                        <tr key={log.audit_id}>
                          <td>{log.audit_id}</td>
                          <td>{`${log.employee_id} - ${log.employee_name}`}</td>
                          <td>{new Date(log.changed_at).toLocaleString()}</td>
                          <td>{log.work_date}</td>
                          <td className="audit-cell-before"><span className="audit-value audit-value-before">{log.old_symbol || '—'}</span></td>
                          <td className="audit-cell-after"><span className="audit-value audit-value-after">{log.new_symbol || '—'}</span></td>
                          <td>{log.reason}</td>
                          <td>{`${log.changed_by_user_id} - ${log.changed_by_name}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <footer className="override-history-modal-footer">
                <span>Dữ liệu audit được đọc trực tiếp từ backend.</span>
                <button type="button" onClick={() => setOverrideHistoryOpen(false)}>Đóng</button>
              </footer>
            </section>
          </div>,
          document.body,
        )}

        {activeTab === 'export' && (
          <section className="grid-two export-page-grid">
            <div className="card export-form-card">
              <h2>Export bảng công Excel theo mẫu HR</h2>
              <label>
                Period Start
                <BrandedDateInput value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
              </label>
              <label>
                Period End
                <BrandedDateInput value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
              </label>
              <button type="button" className="app-download-button" onClick={exportTimesheet}>Xuất file .xlsx theo tháng công</button>
            </div>
            <div className="card export-note-card">
              <h2>Ghi chú</h2>
              <p className="muted">
                Có 2 luồng export: từ tab này theo dữ liệu đã lưu trong hệ thống, hoặc từ tab Import để xuất trực tiếp ngay trên workbook vừa upload.
              </p>
            </div>
          </section>
        )}

        {isBusinessAdminRole(currentUser?.role) && activeTab === 'salary' && (
          <section className="flex flex-col gap-4" style={{ minWidth: 0 }}>
            {/* KPI Summary cards at top as Pie Chart */}
            <SalaryPieChart
              slices={[
                {
                  label: 'Tổng quỹ lương thực chi',
                  value: salarySummaries.transfer,
                  color: '#163B66',
                  formula: 'Σ(Lương NET + Hoàn thuế PIT - Đoàn phí)',
                  description: 'Số tiền thực ra ngân hàng toàn bộ nhân viên.'
                },
                {
                  label: 'Tổng nghĩa vụ thuế TNCN',
                  value: salarySummaries.pit,
                  color: '#f43f5e',
                  formula: 'Σ(PIT_Chính_thức[Biểu 7 bậc] + PIT_Thử_việc[10%])',
                  description: 'Tổng thuế TNCN trích nộp tháng này.'
                },
                {
                  label: 'Tổng trích nộp BH bắt buộc',
                  value: salarySummaries.ins,
                  color: '#0ea5e9',
                  formula: 'Σ(Bảo_hiểm_NLĐ_10.5% + Bảo_hiểm_DN_21.5%)',
                  description: 'Tổng phần NLĐ chịu + phần DN chịu.'
                },
                {
                  label: 'Tổng lương thực tế',
                  value: salarySummaries.actual,
                  color: '#10b981',
                  formula: 'Σ(Lương_HĐLĐ / Ngày_công_chuẩn * Ngày_công_tính_lương)',
                  description: 'Dùng cột Ngày công đã bao gồm nghỉ phép, WFH và các ngày được hưởng lương.'
                }
              ]}
            />
            
            <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_60px_-42px_rgba(15,23,42,0.28)]">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div className="max-w-3xl space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#163B66]">Payroll Calculation</p>
                  <h2 className="text-2xl font-bold tracking-[-0.03em] text-slate-900">Quản lý & Tính toán lương tự động</h2>
                  <p className="text-sm leading-6 text-slate-500">
                    Cấu hình mức lương hợp đồng gốc và cập nhật các khoản biến động theo tháng (ngày công tính lương gồm phép/WFH, phụ cấp, thưởng) để tự động xuất bảng lương Excel.
                  </p>
                </div>
              </div>
              
              <div className="app-segmented-tabs" role="tablist" aria-label="Các phần quản lý lương">
                <button
                  type="button"
                  id="salary-tab-grid"
                  onClick={() => {
                    setSalarySubTab('grid')
                    // Commission is ledger-driven and can be edited in the
                    // adjacent tab. Reload so the salary totals always use
                    // the newest wallet balance for the selected month.
                    void loadSalaryData()
                  }}
                  aria-selected={salarySubTab === 'grid'}
                  className={`app-segmented-tab border-b-2 px-6 py-3 text-sm font-semibold transition whitespace-nowrap ${
                    salarySubTab === 'grid'
                      ? 'border-[#163B66] text-[#163B66]'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  <AppIcon name="chart" size={16} /> Bảng tổng hợp (Admin Grid)
                </button>
                <button
                  type="button"
                  id="salary-tab-contract"
                  onClick={() => setSalarySubTab('contract')}
                  aria-selected={salarySubTab === 'contract'}
                  className={`app-segmented-tab border-b-2 px-6 py-3 text-sm font-semibold transition whitespace-nowrap ${
                    salarySubTab === 'contract'
                      ? 'border-[#163B66] text-[#163B66]'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  Lương hợp đồng gốc
                </button>
                <button
                  type="button"
                  id="salary-tab-commission"
                  onClick={() => setSalarySubTab('commission')}
                  aria-selected={salarySubTab === 'commission'}
                  className={`app-segmented-tab border-b-2 px-6 py-3 text-sm font-semibold transition whitespace-nowrap ${
                    salarySubTab === 'commission'
                      ? 'border-[#163B66] text-[#163B66]'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  Commission
                </button>
              </div>
            </div>

            {/* ══════════════════════════════════════════════════════ */}
            {/* SUBTAB: Bảng tổng hợp Admin Grid                       */}
            {/* ══════════════════════════════════════════════════════ */}
            {salarySubTab === 'grid' && (
              <div className="min-h-[250px] h-auto w-full animate-[fadeIn_0.25s_ease-out_forwards]" style={{ minWidth: 0, overflow: 'hidden' }}>
                {(currentUser?.role === 'DIRECTOR' || currentUser?.role === 'IT_ADMIN')
                  && salaryApproval?.period === salaryPeriod
                  && salaryApproval.status === 'PENDING_APPROVAL' && (
                    <div
                      id="salary-pending-approval-banner"
                      className="mb-4 flex flex-col gap-3 rounded-2xl border border-emerald-300 bg-emerald-50 px-5 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <p className="text-sm font-bold text-emerald-950">
                          Bảng lương tháng {salaryPeriod} đang chờ bạn phê duyệt
                        </p>
                        <p className="mt-1 text-sm text-emerald-800">
                          Phê duyệt sẽ tự động phát hành phiếu lương và gửi thông báo đến nhân viên.
                        </p>
                      </div>
                      <button
                        type="button"
                        id="salary-approve-request-button"
                        onClick={() => void approveSalaryPeriod()}
                        disabled={loading}
                        className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 text-sm font-bold text-white shadow-[0_8px_20px_rgba(5,150,105,0.24)] transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <AppIcon name="check" size={16} />
                        Phê duyệt bảng lương
                      </button>
                    </div>
                  )}
                <SalaryDataGrid
                  employees={salaryEmployees}
                  inputs={salaryInputs}
                  editedInputs={editedInputs}
                  salaryPeriod={salaryPeriod}
                  salaryPolicy={salaryPolicy}
                  focusEmployeeId={salaryNotificationEmployeeId}
                  focusKey={notificationNotice?.id || null}
                  isSalaryLocked={isSalaryLocked}
                  toolbarActions={(
                    <>
                      <button
                        type="button"
                        id="salary-reload-btn"
                        onClick={loadSalaryData}
                        disabled={loading}
                        className="app-action-button app-action-icon-button"
                        aria-label="Làm mới dữ liệu bảng lương"
                        title="Làm mới dữ liệu bảng lương"
                      >
                        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 7h-5V2" />
                          <path d="M4 17h5v5" />
                          <path d="M5.1 9A8 8 0 0 1 18.4 5.6L20 7" />
                          <path d="M18.9 15A8 8 0 0 1 5.6 18.4L4 17" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        id="salary-export-btn"
                        onClick={exportSalaryReportTable}
                        disabled={loading}
                        className="app-action-button app-download-button"
                      >
                        Tải Excel Báo cáo Lương
                      </button>
                      <button
                        type="button"
                        id="salary-export-payment-btn"
                        onClick={exportPaymentExcel}
                        disabled={loading || salaryEmployees.length === 0}
                        title="Xuất file Payment Excel cho Ngân hàng — theo mẫu Payment_External.xlsx"
                        className="app-action-button app-download-button inline-flex items-center gap-2"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                          <polyline points="7 10 12 15 17 10"/>
                          <line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        Xuất Payment Ngân Hàng
                      </button>
                      <button
                        type="button"
                        id="salary-policy-config-btn"
                        onClick={openSalaryPolicyModal}
                        disabled={loading}
                        title="Thiết lập mức lương tối thiểu, bảo hiểm và thuế theo ngày hiệu lực"
                        className="app-action-button inline-flex items-center gap-2"
                      >
                        <AppIcon name="settings" size={16} />
                        Chính sách lương
                      </button>
                    </>
                  )}
                  onToggleLock={() => {
                    const willLock = !isSalaryLocked
                    setIsSalaryLocked(willLock)
                    if (willLock) {
                      setEditedInputs({})
                    }
                    setMessage(willLock
                      ? `Đã khóa bảng lương tháng ${salaryPeriod} — không thể chỉnh sửa thêm.`
                      : `Đã mở khóa bảng lương tháng ${salaryPeriod}.`
                    )
                  }}
                  onCellChange={(empId, field, value) => {
                    setEditedInputs(prev => ({
                      ...prev,
                      [empId]: { ...(prev[empId] || {}), [field]: value },
                    }))
                  }}
                  onOpenOtherIncomeEvidence={openOtherIncomeEvidence}
                />
                {/* Save bar — hiện khi có chỉnh sửa */}
                {/* Control bar — luôn hiển thị để chứa nút Xác nhận */}
                <div
                  id="salary-approval-actions"
                  style={{
                    position: 'sticky', bottom: 0, zIndex: 30,
                    background: 'linear-gradient(135deg, #163b66 0%, #1d4ed8 100%)',
                    borderRadius: 14, padding: '10px 20px', marginTop: 8,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    gap: 12, boxShadow: '0 -4px 20px rgba(22,59,102,0.35)',
                  }}
                >
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#ffffff' }}>
                    {Object.keys(editedInputs).length > 0 ? (
                      <><AppIcon name="edit" size={15} /> Có <b style={{ color: '#fde68a' }}>{Object.keys(editedInputs).length}</b> nhân viên vừa chỉnh sửa — chưa lưu vào cơ sở dữ liệu</>
                    ) : (
                      <><AppIcon name="sparkle" size={15} /> Hệ thống sẵn sàng. Đã tải thông tin bảng lương tháng {salaryPeriod}.</>
                    )}
                  </span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {Object.keys(editedInputs).length > 0 && (
                      <>
                        <button
                          type="button"
                          onClick={() => setEditedInputs({})}
                          style={{
                            height: 34, padding: '0 14px', borderRadius: 8,
                            background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)',
                            color: '#ffffff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                          }}
                        >
                          <AppIcon name="undo" size={15} /> Hoàn tác thay đổi chưa lưu
                        </button>
                        <button
                          type="button"
                          onClick={saveMonthlyInputs}
                          disabled={loading || isSalaryLocked}
                          style={{
                            height: 34, padding: '0 18px', borderRadius: 8,
                            background: '#10b981', border: 'none',
                            color: '#ffffff', fontSize: 12, fontWeight: 700,
                            cursor: (loading || isSalaryLocked) ? 'not-allowed' : 'pointer',
                            boxShadow: '0 4px 12px rgba(16,185,129,0.4)',
                            opacity: isSalaryLocked ? 0.5 : 1,
                          }}
                        >
                          <AppIcon name="save" size={16} /> Lưu vào DB
                        </button>
                      </>
                    )}

                    <button
                      type="button"
                      className="salary-undo-last-button"
                      onClick={undoLastSavedSalaryInputs}
                      disabled={loading || isSalaryLocked || lastSalaryUndo?.salaryPeriod !== salaryPeriod}
                      title={lastSalaryUndo?.salaryPeriod === salaryPeriod
                        ? 'Khôi phục dữ liệu trước lần lưu gần nhất trong phiên làm việc này'
                        : 'Chưa có lần lưu nào trong phiên này để hoàn tác'}
                      style={{
                        height: 34, padding: '0 14px', borderRadius: 8,
                        background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)',
                        color: '#ffffff', fontSize: 12, fontWeight: 700,
                        cursor: (loading || isSalaryLocked || lastSalaryUndo?.salaryPeriod !== salaryPeriod) ? 'not-allowed' : 'pointer',
                        opacity: 1,
                      }}
                    >
                      <AppIcon name="undo" size={15} /> Hoàn tác lần lưu gần nhất
                    </button>

                    {currentUser?.role === 'ADMIN' && (
                      <>
                        <button
                          type="button"
                          className={`salary-confirm-button${salaryApproval?.status !== 'DRAFT' ? ' is-confirmed' : ''}`}
                          onClick={() => void confirmSalaryPeriod()}
                          disabled={loading || salaryApproval?.status !== 'DRAFT' || isSalaryLocked || Object.keys(editedInputs).length > 0}
                          title={salaryApproval?.status !== 'DRAFT'
                            ? 'Số liệu bảng lương đã được Kế toán trưởng xác nhận; phiếu lương chưa phát hành'
                            : Object.keys(editedInputs).length > 0
                              ? 'Hãy lưu các thay đổi vào DB trước khi xác nhận'
                              : 'Xác nhận số liệu bảng lương, chưa phát hành phiếu lương'}
                          style={{
                            height: 34, padding: '0 18px', borderRadius: 8,
                            background: salaryApproval?.status !== 'DRAFT' ? '#64748b' : '#f59e0b',
                            border: '1px solid rgba(255,255,255,0.45)',
                            color: '#ffffff', fontSize: 12, fontWeight: 700,
                            cursor: (loading || salaryApproval?.status !== 'DRAFT' || isSalaryLocked || Object.keys(editedInputs).length > 0) ? 'not-allowed' : 'pointer',
                            boxShadow: salaryApproval?.status === 'DRAFT' ? '0 4px 12px rgba(245,158,11,0.45)' : 'none',
                            opacity: salaryApproval?.status !== 'DRAFT' ? 0.75 : 1,
                            transition: 'all 0.2s ease', whiteSpace: 'nowrap',
                          }}
                        >
                          <AppIcon name="check" size={15} />
                          {salaryApproval?.status === 'DRAFT' ? 'Xác nhận bảng lương' : 'Đã xác nhận số liệu'}
                        </button>
                        <button
                          type="button"
                          onClick={() => void requestSalaryApproval()}
                          disabled={loading || salaryApproval?.status !== 'CONFIRMED'}
                          title={salaryApproval?.status === 'CONFIRMED'
                            ? 'Gửi yêu cầu tới hai Giám đốc và IT_ADMIN'
                            : salaryApproval?.status === 'PENDING_APPROVAL'
                              ? 'Yêu cầu đang chờ Giám đốc hoặc IT_ADMIN phê duyệt'
                              : salaryApproval?.status === 'APPROVED'
                                ? 'Bảng lương đã được phê duyệt và phát hành'
                                : 'Cần xác nhận số liệu trước khi gửi yêu cầu phê duyệt'}
                          style={{
                            height: 34, padding: '0 18px', borderRadius: 8,
                            background: salaryApproval?.status === 'CONFIRMED' ? '#10b981' : 'rgba(255,255,255,0.15)',
                            border: '1px solid rgba(255,255,255,0.45)', color: '#ffffff',
                            fontSize: 12, fontWeight: 700,
                            cursor: (loading || salaryApproval?.status !== 'CONFIRMED') ? 'not-allowed' : 'pointer',
                            opacity: salaryApproval?.status === 'CONFIRMED' ? 1 : 0.65,
                            boxShadow: salaryApproval?.status === 'CONFIRMED' ? '0 4px 12px rgba(16,185,129,0.4)' : 'none',
                            transition: 'all 0.2s ease', whiteSpace: 'nowrap',
                          }}
                        >
                          <AppIcon name="message" size={15} />
                          {salaryApproval?.status === 'PENDING_APPROVAL'
                            ? 'Đang chờ phê duyệt'
                            : salaryApproval?.status === 'APPROVED'
                              ? 'Đã được phê duyệt'
                              : 'Yêu cầu phê duyệt'}
                        </button>
                      </>
                    )}

                    {(currentUser?.role === 'DIRECTOR' || currentUser?.role === 'IT_ADMIN') && (
                      <button
                        id="salary-approve-publish-button"
                        type="button"
                        className={`salary-confirm-button${salaryApproval?.status === 'APPROVED' ? ' is-confirmed' : ''}`}
                        onClick={() => void approveSalaryPeriod()}
                        disabled={loading || salaryApproval?.status !== 'PENDING_APPROVAL'}
                        title={salaryApproval?.status === 'PENDING_APPROVAL'
                          ? 'Phê duyệt để tự động phát hành phiếu lương và thông báo nhân viên'
                          : salaryApproval?.status === 'APPROVED'
                            ? 'Bảng lương đã được phê duyệt và phát hành'
                            : 'Chưa có yêu cầu phê duyệt từ Kế toán trưởng'}
                        style={{
                          height: 34, padding: '0 18px', borderRadius: 8,
                          background: salaryApproval?.status === 'PENDING_APPROVAL' ? '#10b981' : '#64748b',
                          border: '1px solid rgba(255,255,255,0.45)', color: '#ffffff',
                          fontSize: 12, fontWeight: 700,
                          cursor: (loading || salaryApproval?.status !== 'PENDING_APPROVAL') ? 'not-allowed' : 'pointer',
                          opacity: 1,
                          boxShadow: salaryApproval?.status === 'PENDING_APPROVAL' ? '0 4px 12px rgba(16,185,129,0.4)' : 'none',
                          transition: 'all 0.2s ease', whiteSpace: 'nowrap',
                        }}
                      >
                        <AppIcon name="check" size={15} />
                        {salaryApproval?.status === 'APPROVED' ? 'Đã phê duyệt & phát hành' : 'Phê duyệt & phát hành'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}



            {salarySubTab === 'contract' && (
              <div className="min-h-[250px] h-auto w-full rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_60px_-42px_rgba(15,23,42,0.28)] animate-[fadeIn_0.3s_ease-out_forwards]">
                <h3 className="text-lg font-bold text-slate-900 mb-6">Cấu hình lương hợp đồng gốc</h3>
                <div className="min-h-[250px] h-auto w-full overflow-x-auto rounded-[24px] border border-slate-200">
                  <table className="min-w-full divide-y divide-slate-200 text-sm">
                    <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      <tr>
                        <th className="px-4 py-3 text-left">Mã NV</th>
                        <th className="px-4 py-3 text-left">Họ và tên</th>
                        <th className="px-4 py-3 text-left">Chức vụ</th>
                        <th className="px-4 py-3 text-right">Lương HĐLĐ (VND)</th>
                        <th className="px-4 py-3 text-center">Loại HĐ</th>
                        <th className="px-4 py-3 text-center">Người phụ thuộc</th>
                        <th className="px-4 py-3 text-left">Số tài khoản</th>
                        <th className="px-4 py-3 text-left">Ngân hàng</th>
                        <th className="px-4 py-3 text-right">Tác vụ</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 bg-white">
                      {salaryEmployees.map((emp) => {
                        const isEditing = editingSalaryEmployeeId === emp.id
                        return (
                          <tr key={emp.id} className="hover:bg-slate-50/50">
                            <td className="px-4 py-4">
                              {isEditing ? (
                                <input
                                  value={editSalaryEmployeeForm.employee_code}
                                  onChange={(e) => setEditSalaryEmployeeForm(prev => ({ ...prev, employee_code: e.target.value }))}
                                  className="h-9 w-24 rounded-lg border border-slate-200 px-2 text-slate-800 outline-none focus:border-[#163B66]"
                                />
                              ) : (
                                <span className="font-semibold text-slate-600">{emp.employee_code || emp.machine_employee_id}</span>
                              )}
                            </td>
                            <td className="px-4 py-4">
                              {isEditing ? (
                                <input
                                  value={editSalaryEmployeeForm.fullname}
                                  onChange={(e) => setEditSalaryEmployeeForm(prev => ({ ...prev, fullname: e.target.value }))}
                                  className="h-9 w-40 rounded-lg border border-slate-200 px-2 text-slate-800 outline-none focus:border-[#163B66]"
                                />
                              ) : (
                                <span className="font-semibold text-slate-900">{emp.fullname}</span>
                              )}
                            </td>
                            <td className="px-4 py-4">
                              {isEditing ? (
                                <input
                                  value={editSalaryEmployeeForm.position}
                                  onChange={(e) => setEditSalaryEmployeeForm(prev => ({ ...prev, position: e.target.value }))}
                                  className="h-9 w-32 rounded-lg border border-slate-200 px-2 text-slate-800 outline-none focus:border-[#163B66]"
                                />
                              ) : (
                                <span>{emp.position || '-'}</span>
                              )}
                            </td>
                            <td className="px-4 py-4 text-right font-semibold">
                              {isEditing ? (
                                <VndInput
                                  value={editSalaryEmployeeForm.contract_salary}
                                  onValueChange={(value) => setEditSalaryEmployeeForm(prev => ({ ...prev, contract_salary: value }))}
                                  className="h-9 w-28 rounded-lg border border-slate-200 px-2 text-right text-slate-800 outline-none focus:border-[#163B66]"
                                />
                              ) : (
                                formatCurrency(emp.contract_salary)
                              )}
                            </td>
                            <td className="px-4 py-4 text-center">
                              {isEditing ? (
                                <select
                                  value={editSalaryEmployeeForm.employee_type}
                                  onChange={(e) => setEditSalaryEmployeeForm(prev => ({ ...prev, employee_type: e.target.value as EmployeeType }))}
                                  className="h-9 rounded-lg border border-slate-200 px-2 text-slate-800 outline-none focus:border-[#163B66]"
                                >
                                  <option value="FULLTIME">Chính thức (FULLTIME)</option>
                                  <option value="PROBATION">Thử việc (PROBATION)</option>
                                  <option value="INTERN">Học việc (INTERN)</option>
                                  <option value="TRAINEE">Thực tập (TRAINEE)</option>
                                </select>
                              ) : (
                                <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${emp.employee_type === 'FULLTIME' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                                  {getEmployeeTypeLabel(emp.employee_type)}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-4 text-center">
                              {isEditing ? (
                                <input
                                  type="number"
                                  value={editSalaryEmployeeForm.dependents_count}
                                  onChange={(e) => setEditSalaryEmployeeForm(prev => ({ ...prev, dependents_count: parseInt(e.target.value, 10) || 0 }))}
                                  className="h-9 w-16 rounded-lg border border-slate-200 px-2 text-center text-slate-800 outline-none focus:border-[#163B66]"
                                />
                              ) : (
                                emp.dependents_count
                              )}
                            </td>
                            <td className="px-4 py-4">
                              {isEditing ? (
                                <input
                                  value={editSalaryEmployeeForm.account_number}
                                  onChange={(e) => setEditSalaryEmployeeForm(prev => ({ ...prev, account_number: e.target.value }))}
                                  className="h-9 w-32 rounded-lg border border-slate-200 px-2 text-slate-800 outline-none focus:border-[#163B66]"
                                />
                              ) : (
                                emp.account_number || '-'
                              )}
                            </td>
                            <td className="px-4 py-4">
                              {isEditing ? (
                                <input
                                  value={editSalaryEmployeeForm.bank_name}
                                  onChange={(e) => setEditSalaryEmployeeForm(prev => ({ ...prev, bank_name: e.target.value }))}
                                  className="h-9 w-36 rounded-lg border border-slate-200 px-2 text-slate-800 outline-none focus:border-[#163B66]"
                                />
                              ) : (
                                emp.bank_name || '-'
                              )}
                            </td>
                            <td className="px-4 py-4 text-right">
                              {isEditing ? (
                                <div className="flex justify-end gap-2">
                                  <button
                                    type="button"
                                    onClick={() => saveSalaryEmployeeInline(emp.id)}
                                    className="inline-flex h-8 items-center rounded-lg bg-[#163B66] px-3 text-xs font-semibold text-white transition hover:bg-[#102B49]"
                                  >
                                    Lưu
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setEditingSalaryEmployeeId(null)}
                                    className="inline-flex h-8 items-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
                                  >
                                    Hủy
                                  </button>
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => startEditSalaryEmployee(emp)}
                                  className="inline-flex h-8 items-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
                                >
                                  Sửa
                                </button>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {salarySubTab === 'commission' && (
              <div className="min-h-[250px] h-auto w-full rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_60px_-42px_rgba(15,23,42,0.28)] animate-[fadeIn_0.3s_ease-out_forwards]">
                <CommissionTab
                  apiBase={apiBase}
                  token={token}
                  notificationFocus={commissionNotificationFocus}
                  externalRefreshVersion={lastDataChange?.path.startsWith('/api/commission') ? lastDataChange.occurredAt : 0}
                />
              </div>
            )}

          </section>
        )}

      {dashboardTrendOpen && dashboardKpi && createPortal(
        <div className="modal-backdrop dashboard-trend-backdrop" onMouseDown={() => setDashboardTrendOpen(false)}>
          <section
            className="dashboard-trend-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="dashboard-trend-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="dashboard-trend-modal-header">
              <div>
                <h2 id="dashboard-trend-title">Xu hướng theo ngày</h2>
                <p>{periodStart} → {periodEnd} · {dashboardKpi.trend.length} ngày có dữ liệu</p>
              </div>
              <button type="button" className="app-close-button" aria-label="Đóng chi tiết xu hướng" onClick={() => setDashboardTrendOpen(false)}>
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </header>
            <div className="dashboard-trend-modal-body">
              <div className="table-wrap compact">
                <table>
                  <thead>
                    <tr>
                      <th>Ngày</th>
                      <th>Đi làm</th>
                      <th>Vắng</th>
                      <th>Bất thường</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboardKpi.trend.map((point) => (
                      <tr key={point.work_date}>
                        <td>{point.work_date}</td>
                        <td>{point.present_count}</td>
                        <td>{point.absent_count}</td>
                        <td>{point.abnormal_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <footer className="dashboard-trend-modal-footer">
              <button type="button" onClick={() => setDashboardTrendOpen(false)}>Đóng</button>
            </footer>
          </section>
        </div>,
        document.body,
      )}

      {detailEmployee && createPortal(
        <div className="modal-backdrop employee-detail-backdrop transition-opacity duration-300 animate-[modalBackdropIn_0.3s_ease-out_forwards]" onClick={() => setDetailEmployee(null)}>
          <div
            className="modal-card employee-detail-modal rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] max-w-2xl w-full transition-all duration-300 ease-out transform scale-95 opacity-0 animate-[modalPopIn_0.3s_ease-out_forwards]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-6 flex items-start justify-between gap-4 border-b border-slate-100 pb-4">
              <div>
                <h2 className="text-xl font-bold text-slate-900 tracking-tight">Chi tiết Nhân viên: {detailEmployee.full_name}</h2>
                <p className="text-sm text-slate-500 mt-1">Các thông tin cá nhân và hợp đồng</p>
              </div>
              <button
                type="button"
                onClick={() => setDetailEmployee(null)}
                className="app-close-button"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="px-1 space-y-6">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Thông tin nhận diện &amp; công việc</p>
                <div className="employee-detail-grid grid grid-cols-2 gap-4 text-sm">
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Tên nhân viên</span>
                    <input className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.full_name} onChange={(e) => setDetailEmployee({ ...detailEmployee, full_name: e.target.value })} placeholder="Tên trên báo cáo chấm công" />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Tên Notion</span>
                    <input className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.notion_name || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, notion_name: e.target.value })} placeholder="Có thể bổ sung sau" />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Mã máy chấm công</span>
                    <input className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.machine_employee_id} onChange={(e) => setDetailEmployee({ ...detailEmployee, machine_employee_id: e.target.value })} />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Mã nhân viên</span>
                    <input className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.employee_code || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, employee_code: e.target.value })} placeholder="Ví dụ: SL001" />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Phòng ban</span>
                    <select className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.department_id ?? ''} onChange={(e) => {
                      const departmentId = e.target.value ? Number(e.target.value) : null
                      const selectedDepartment = departments.find(item => item.id === departmentId)
                      setDetailEmployee({ ...detailEmployee, department_id: departmentId, department_name: selectedDepartment?.name || null })
                    }}>
                      <option value="">Chưa thiết lập</option>
                      {departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}
                    </select>
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Chức vụ</span>
                    <input className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.position || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, position: e.target.value })} placeholder="Có thể bổ sung sau" />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Ngày bắt đầu làm việc</span>
                    <BrandedDateInput className="mt-1" value={detailEmployee.start_date?.split('T')[0] || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, start_date: e.target.value })} />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Loại hợp đồng</span>
                    <select
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1"
                      value={detailEmployee.contract_type || ''}
                      onChange={(e) => setDetailEmployee({
                        ...detailEmployee,
                        contract_type: e.target.value || null,
                        contract_sign_date: e.target.value ? detailEmployee.contract_sign_date : null,
                        contract_start_date: isFixedTermEmployeeContract(e.target.value) ? detailEmployee.contract_start_date : null,
                        contract_end_date: isFixedTermEmployeeContract(e.target.value) ? detailEmployee.contract_end_date : null,
                      })}
                    >
                      <option value="">Chưa thiết lập</option>
                      {EMPLOYEE_CONTRACT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Ngày ký hợp đồng</span>
                    <BrandedDateInput disabled={!detailEmployee.contract_type} required={Boolean(detailEmployee.contract_type)} className="mt-1" value={detailEmployee.contract_sign_date || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, contract_sign_date: e.target.value || null })} />
                  </label>
                  {isFixedTermEmployeeContract(detailEmployee.contract_type) && (
                    <>
                      <label>
                        <span className="block text-xs font-semibold text-slate-400 uppercase">Hợp đồng từ ngày</span>
                        <BrandedDateInput className="mt-1" value={detailEmployee.contract_start_date || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, contract_start_date: e.target.value || null })} />
                      </label>
                      <label>
                        <span className="block text-xs font-semibold text-slate-400 uppercase">Hợp đồng đến ngày</span>
                        <BrandedDateInput min={detailEmployee.contract_start_date || undefined} className="mt-1" value={detailEmployee.contract_end_date || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, contract_end_date: e.target.value || null })} />
                      </label>
                    </>
                  )}
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Trạng thái</span>
                    <select className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.status} onChange={(e) => setDetailEmployee({
                      ...detailEmployee,
                      status: e.target.value,
                      is_active: e.target.value === 'ACTIVE',
                      ...(e.target.value !== 'RESIGNED' ? { resignation_period: null, last_working_date: null, last_pay_date: null } : {}),
                    })}>
                      <option value="ACTIVE">Đang hoạt động</option>
                      <option value="LOCKED">Tạm khóa</option>
                      <option value="RESIGNED">Đã nghỉ việc</option>
                    </select>
                  </label>
                  {detailEmployee.status === 'RESIGNED' && (
                    <>
                      <label>
                        <span className="block text-xs font-semibold text-slate-400 uppercase">Ngày làm việc cuối</span>
                        <BrandedDateInput className="mt-1" value={detailEmployee.last_working_date || ''} onChange={(e) => setDetailEmployee({
                          ...detailEmployee,
                          last_working_date: e.target.value || null,
                          resignation_period: e.target.value ? e.target.value.slice(0, 7) : null,
                        })} />
                      </label>
                      <label>
                        <span className="block text-xs font-semibold text-slate-400 uppercase">Ngày trả lương cuối</span>
                        <BrandedDateInput className="mt-1" value={detailEmployee.last_pay_date || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, last_pay_date: e.target.value || null })} />
                      </label>
                    </>
                  )}
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Loại nhân viên</span>
                    <select
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1"
                      value={detailEmployee.employee_type}
                      onChange={(e) => {
                        const nextType = e.target.value as EmployeeType
                        const allowances = getContractAllowanceDefaults(nextType)
                        setDetailEmployee({
                          ...detailEmployee,
                          employee_type: nextType,
                          meal_allowance: Number(allowances.meal_allowance),
                          phone_allowance: Number(allowances.phone_allowance),
                          trans_allowance: Number(allowances.trans_allowance),
                          other_allowance: Number(allowances.other_allowance),
                        })
                      }}
                    >
                      <option value="FULLTIME">Chính thức</option>
                      <option value="PROBATION">Thử việc</option>
                      <option value="INTERN">Học việc</option>
                      <option value="TRAINEE">Thực tập</option>
                    </select>
                  </label>
                  {detailEmployeeOriginalType && detailEmployee.employee_type !== detailEmployeeOriginalType && (
                    <label>
                      <span className="block text-xs font-semibold text-slate-400 uppercase">Ngày áp dụng thăng tiến</span>
                      <BrandedDateInput
                        required
                        className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1"
                        value={detailEmployeeTypeEffectiveDate}
                        onChange={(e) => setDetailEmployeeTypeEffectiveDate(e.target.value)}
                      />
                      <span className="mt-1 block text-[11px] text-slate-500">
                        {detailEmployeeOriginalType === 'INTERN' && detailEmployee.employee_type === 'PROBATION'
                          ? 'Học việc → Thử việc: giữ nguyên phụ cấp bằng 0.'
                          : 'Phụ cấp được áp dụng từ tháng lương chứa ngày này và các tháng sau.'}
                      </span>
                    </label>
                  )}
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Quota phép năm</span>
                    <input type="number" min={0} className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.annual_leave_quota} onChange={(e) => setDetailEmployee({ ...detailEmployee, annual_leave_quota: Number(e.target.value) })} />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Số người phụ thuộc</span>
                    <input type="number" min={0} className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.dependents_count} onChange={(e) => setDetailEmployee({ ...detailEmployee, dependents_count: Number(e.target.value) })} />
                  </label>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <p className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400"><AppIcon name="user" size={15} /> Thông tin cá nhân &amp; Liên hệ</p>
                <div className="employee-detail-grid grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Mã số thuế (MST)</span>
                    <input
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.tax_code || ''}
                      onChange={(e) => setDetailEmployee({ ...detailEmployee, tax_code: e.target.value })}
                      placeholder="Nhập MST..."
                    />
                  </div>
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Số điện thoại cá nhân</span>
                    <input
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.phone_number || ''}
                      onChange={(e) => setDetailEmployee({ ...detailEmployee, phone_number: e.target.value })}
                      placeholder="Nhập SĐT cá nhân..."
                    />
                  </div>
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Số điện thoại công ty</span>
                    <input
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.company_phone_number || ''}
                      onChange={(e) => setDetailEmployee({ ...detailEmployee, company_phone_number: e.target.value })}
                      placeholder="Nhập SĐT công ty..."
                    />
                  </div>
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Số BHXH</span>
                    <input
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.social_insurance_number || ''}
                      onChange={(e) => setDetailEmployee({ ...detailEmployee, social_insurance_number: e.target.value })}
                      placeholder="Nhập Số BHXH..."
                    />
                  </div>
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Bảo hiểm y tế (BHYT)</span>
                    <input
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.health_insurance_number || ''}
                      onChange={(e) => setDetailEmployee({ ...detailEmployee, health_insurance_number: e.target.value })}
                      placeholder="Nhập BHYT..."
                    />
                  </div>
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Bảo hiểm PVI</span>
                    <input
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.pvi_insurance || ''}
                      onChange={(e) => setDetailEmployee({ ...detailEmployee, pvi_insurance: e.target.value })}
                      placeholder="Nhập mã thẻ PVI..."
                    />
                  </div>
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Mail Công Ty</span>
                    <input
                      type="email"
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.company_email || ''}
                      onChange={(e) => {
                        const companyEmail = e.target.value
                        setDetailEmployee({
                          ...detailEmployee,
                          company_email: companyEmail,
                          username: usernameFromCompanyEmail(companyEmail),
                        })
                      }}
                      placeholder="nv.a@sealink.com"
                    />
                  </div>
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Mail Cá Nhân</span>
                    <input
                      type="email"
                      className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.personal_email || ''}
                      onChange={(e) => setDetailEmployee({ ...detailEmployee, personal_email: e.target.value })}
                      placeholder="ngvana@gmail.com"
                    />
                  </div>
                  <div className="col-span-2">
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Ghi chú</span>
                    <textarea
                      className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-[#163B66] focus:ring-4 focus:ring-[#163B66]/10 mt-1"
                      value={detailEmployee.notes || ''}
                      onChange={(e) => setDetailEmployee({ ...detailEmployee, notes: e.target.value })}
                      placeholder="Ghi chú khác..."
                      rows={2}
                    />
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Tài khoản đăng nhập (tùy chọn)</p>
                <p className="mb-4 text-xs text-slate-500">Nhân viên chưa có tài khoản có thể để trống. Khi tạo mới, nhập đồng thời tên đăng nhập và mật khẩu.</p>
                <div className="employee-detail-grid grid grid-cols-2 gap-4 text-sm">
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Tên đăng nhập</span>
                    <input className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.username || ''} readOnly placeholder="Tự động từ mail công ty" title="Tên đăng nhập được tạo tự động từ phần trước @ của mail công ty" />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Mật khẩu mới</span>
                    <EmployeePasswordField
                      value={detailEmployeePassword}
                      onChange={setDetailEmployeePassword}
                      onNotice={setMessage}
                      inputClassName="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1"
                      placeholder={detailEmployee.account_role ? 'Để trống nếu giữ nguyên' : 'Tối thiểu 12 ký tự'}
                    />
                  </label>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Cấu hình lương &amp; phụ cấp ban đầu</p>
                <div className="employee-detail-grid grid grid-cols-2 gap-4 text-sm">
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Lương hợp đồng</span>
                    <VndInput className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm text-right mt-1" value={detailEmployee.contract_salary} onValueChange={(value) => setDetailEmployee({ ...detailEmployee, contract_salary: value })} />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Hệ số bonus</span>
                    <input type="number" min={0} step="0.01" className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm text-right mt-1" value={detailEmployee.bonus_coefficient || 0} onChange={(e) => setDetailEmployee({ ...detailEmployee, bonus_coefficient: Number(e.target.value) })} />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Tiền cơm</span>
                    <VndInput className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm text-right mt-1" value={detailEmployee.meal_allowance} onValueChange={(value) => setDetailEmployee({ ...detailEmployee, meal_allowance: value })} />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Tiền điện thoại</span>
                    <VndInput className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm text-right mt-1" value={detailEmployee.phone_allowance} onValueChange={(value) => setDetailEmployee({ ...detailEmployee, phone_allowance: value })} />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Tiền xăng xe</span>
                    <VndInput className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm text-right mt-1" value={detailEmployee.trans_allowance} onValueChange={(value) => setDetailEmployee({ ...detailEmployee, trans_allowance: value })} />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Phụ cấp khác</span>
                    <VndInput className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm text-right mt-1" value={detailEmployee.other_allowance} onValueChange={(value) => setDetailEmployee({ ...detailEmployee, other_allowance: value })} />
                  </label>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <p className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400"><AppIcon name="document" size={15} /> Hồ sơ &amp; Tài liệu đính kèm</p>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase mb-2">CCCD / CMND</span>
                    <div className="flex flex-col gap-2 mb-2">
                      {(!detailEmployee.cccd_url || detailEmployee.cccd_url.length === 0) ? (
                        <span className="text-slate-500 italic text-xs">Chưa có dữ liệu</span>
                      ) : (
                        detailEmployee.cccd_url.map((url, idx) => (
                          <div key={idx} className="flex items-center justify-between bg-white border border-slate-200 rounded-xl p-2 px-3 shadow-sm hover:border-slate-300 transition-all">
                            <div className="flex items-center gap-2 overflow-hidden">
                              <svg className="w-4 h-4 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              <span className="text-xs font-medium text-slate-600 truncate max-w-[130px]" title={url.split('/').pop()}>
                                {url.split('/').pop()}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0 ml-2">
                              <span 
                              onClick={() => openDocument(url)} 
                                className="cursor-pointer p-1.5 rounded-lg hover:bg-slate-100 transition-colors flex items-center justify-center" 
                                title="Xem trước"
                              >
                                <svg className="w-4 h-4 text-slate-500 hover:text-blue-600 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                </svg>
                              </span>
                              <button
                                type="button"
                                onClick={() => openDocument(url, true)}
                                className="app-download-button p-1.5 rounded-lg transition-colors flex items-center justify-center"
                                title="Tải xuống"
                              >
                                <svg className="w-4 h-4 text-slate-500 hover:text-green-600 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                </svg>
                              </button>
                              <span 
                                onClick={() => deleteFile('cccd', url)} 
                                className="cursor-pointer p-1.5 rounded-lg hover:bg-slate-100 transition-colors flex items-center justify-center" 
                                title="Xóa"
                              >
                                <svg className="w-4 h-4 text-slate-500 hover:text-rose-600 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                              </span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                    <label
                      className="employee-document-upload cursor-pointer h-8 rounded-lg bg-white border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
                      aria-label="Tải lên CCCD mới"
                      title="Tải lên CCCD mới"
                    >
                      <AppIcon name="upload" size={16} />
                      <input 
                        type="file" 
                        multiple
                        className="hidden" 
                        accept="image/*,.pdf" 
                        onChange={(e) => {
                          if (e.target.files && e.target.files.length > 0) {
                            uploadFile('cccd', e.target.files);
                          }
                        }}
                      />
                    </label>
                  </div>
                  <div>
                    <span className="block text-xs font-semibold text-slate-400 uppercase mb-2">Chứng từ</span>
                    <div className="flex flex-col gap-2 mb-2">
                      {(!detailEmployee.contract_url || detailEmployee.contract_url.length === 0) ? (
                        <span className="text-slate-500 italic text-xs">Chưa có dữ liệu</span>
                      ) : (
                        detailEmployee.contract_url.map((url, idx) => (
                          <div key={idx} className="flex items-center justify-between bg-white border border-slate-200 rounded-xl p-2 px-3 shadow-sm hover:border-slate-300 transition-all">
                            <div className="flex items-center gap-2 overflow-hidden">
                              <svg className="w-4 h-4 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              <span className="text-xs font-medium text-slate-600 truncate max-w-[130px]" title={url.split('/').pop()}>
                                {url.split('/').pop()}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0 ml-2">
                              <span 
                              onClick={() => openDocument(url)} 
                                className="cursor-pointer p-1.5 rounded-lg hover:bg-slate-100 transition-colors flex items-center justify-center" 
                                title="Xem trước"
                              >
                                <svg className="w-4 h-4 text-slate-500 hover:text-blue-600 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                </svg>
                              </span>
                              <button
                                type="button"
                                onClick={() => openDocument(url, true)}
                                className="app-download-button p-1.5 rounded-lg transition-colors flex items-center justify-center"
                                title="Tải xuống"
                              >
                                <svg className="w-4 h-4 text-slate-500 hover:text-green-600 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                </svg>
                              </button>
                              <span 
                                onClick={() => deleteFile('contract', url)} 
                                className="cursor-pointer p-1.5 rounded-lg hover:bg-slate-100 transition-colors flex items-center justify-center" 
                                title="Xóa"
                              >
                                <svg className="w-4 h-4 text-slate-500 hover:text-rose-600 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                              </span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                    <label
                      className="employee-document-upload cursor-pointer h-8 rounded-lg bg-white border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
                      aria-label="Tải lên Chứng từ mới"
                      title="Tải lên Chứng từ mới"
                    >
                      <AppIcon name="upload" size={16} />
                      <input 
                        type="file" 
                        multiple
                        className="hidden" 
                        accept="image/jpeg,image/png,image/webp,application/pdf" 
                        onChange={(e) => {
                          if (e.target.files && e.target.files.length > 0) {
                            uploadFile('contract', e.target.files);
                          }
                        }}
                      />
                    </label>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <p className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400"><AppIcon name="bank" size={15} /> Thông tin ngân hàng</p>
                <div className="employee-detail-grid grid grid-cols-2 gap-4 text-sm">
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Tên ngân hàng</span>
                    <input className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.bank_name || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, bank_name: e.target.value })} placeholder="Có thể bổ sung sau" />
                  </label>
                  <label>
                    <span className="block text-xs font-semibold text-slate-400 uppercase">Số tài khoản</span>
                    <input className="h-9 w-full rounded-xl border border-slate-200 px-3 text-sm mt-1" value={detailEmployee.account_number || ''} onChange={(e) => setDetailEmployee({ ...detailEmployee, account_number: e.target.value })} placeholder="Có thể bổ sung sau" />
                  </label>
                </div>
              </div>
            </div>

            <SalaryDecisionsSection 
              apiBase={apiBase} 
              token={token} 
              employeeId={detailEmployee.id} 
              currentSalary={detailEmployee.contract_salary} 
              departmentId={detailEmployee.department_id}
            />

            <div className="mt-6 flex flex-row items-center justify-end gap-3 pt-4 border-t border-slate-100">
              <button
                type="button"
                className="employee-detail-footer-button inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-6 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                onClick={() => setDetailEmployee(null)}
              >
                Đóng
              </button>
              <button
                type="button"
                className={`employee-detail-footer-button sl-btn-action sl-color-blue ${loading ? 'loading-shimmer' : ''} inline-flex items-center justify-center rounded-xl px-6 text-sm font-semibold`}
                onClick={saveEmployeeDetail}
                disabled={loading}
              >
                Lưu thông tin
              </button>
            </div>
          </div>
        </div>,
        document.fullscreenElement || document.body,
      )}

      {isEmployeeModalOpen && (
        <div className="modal-backdrop employee-create-backdrop transition-opacity duration-300 animate-[modalBackdropIn_0.3s_ease-out_forwards]" onClick={() => setIsEmployeeModalOpen(false)}>
          <form
            className="modal-card employee-create-modal rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] max-w-2xl transition-all duration-300 ease-out transform scale-95 opacity-0 animate-[modalPopIn_0.3s_ease-out_forwards]"
            onClick={(event) => event.stopPropagation()}
            onSubmit={createEmployee}
          >
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">Add Employee</p>
                <h2>Thêm nhân viên mới</h2>
                <p className="text-sm text-slate-500">
                  Khai báo thông tin nhận diện, lương hợp đồng và thông tin ngân hàng để hệ thống tự động tính bảng lương.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsEmployeeModalOpen(false)}
                className="app-close-button"
              >
                <AppIcon name="close" size={17} />
              </button>
            </div>

            {employeeError && (
              <div style={{
                background: '#fee2e2',
                border: '1px solid #fca5a5',
                color: '#b91c1c',
                padding: '12px 16px',
                borderRadius: '16px',
                fontSize: '13px',
                fontWeight: 500,
                marginBottom: '20px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                width: '100%'
              }}>
                <AppIcon name="warning" size={17} />
                <span>{employeeError}</span>
                <button
                  type="button" 
                  onClick={() => setEmployeeError(null)} 
                  className="app-close-button app-close-button--compact"
                  style={{ marginLeft: 'auto', border: 'none', background: 'transparent', color: '#b91c1c', cursor: 'pointer', fontWeight: 'bold', fontSize: '16px' }}
                >
                  <AppIcon name="close" size={14} />
                </button>
              </div>
            )}

            {/* IDENTITY INFO */}
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Thông tin nhận diện</p>
            <div className="grid gap-4 md:grid-cols-2">
              <label>
                <span>ID máy chấm công <span className="text-rose-500">*</span></span>
                <input
                  value={employeeForm.machine_employee_id}
                  onChange={(e) => setEmployeeForm((prev) => ({ ...prev, machine_employee_id: e.target.value }))}
                  placeholder="Ví dụ: E001"
                  required
                />
                <span className="mt-1 block text-xs font-normal text-slate-500">Đây là ID duy nhất dùng để đối chiếu dữ liệu từ máy chấm công.</span>
              </label>
              <label>
                Phòng ban
                <select
                  value={employeeForm.department_id ?? ''}
                  onChange={(e) => setEmployeeForm((prev) => ({ 
                    ...prev, 
                    department_id: e.target.value ? Number(e.target.value) : null,
                    department_name: e.target.value ? e.target.options[e.target.selectedIndex].text : '' 
                  }))}
                >
                  <option value="">-- Chọn phòng ban --</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Mức Bonus áp dụng
                <select
                  value={employeeForm.bonus_coefficient}
                  onChange={(e) => setEmployeeForm((prev) => ({ 
                    ...prev, 
                    bonus_coefficient: e.target.value
                  }))}
                >
                  <option value="0">-- Mặc định theo phòng ban hiện tại --</option>
                  {departments.map((d) => {
                    const rulesText = d.current_bonus_rules?.length 
                      ? d.current_bonus_rules.map((r: any) => `${Math.round(r.rate * 100)}%`).join(', ') 
                      : 'Chưa cấu hình'
                    return (
                      <option key={d.id} value={d.id}>
                        {d.name} ({rulesText})
                      </option>
                    )
                  })}
                </select>
              </label>
              <label>
                Tên tiếng Việt
                <input
                  value={employeeForm.full_name}
                  onChange={(e) => setEmployeeForm((prev) => ({ ...prev, full_name: e.target.value }))}
                  placeholder="Ví dụ: Ngô Thị Anh Hôn"
                  required
                />
              </label>
              <label>
                Tên Notion
                <input
                  value={employeeForm.notion_name}
                  onChange={(e) => setEmployeeForm((prev) => ({ ...prev, notion_name: e.target.value }))}
                  placeholder="Ví dụ: DOCS - PARADO QUANG"
                />
              </label>
              <label>
                Ngày bắt đầu làm việc
                <BrandedDateInput
                  value={employeeForm.start_date}
                  onChange={(e) => setEmployeeForm((prev) => ({ ...prev, start_date: e.target.value }))}
                />
              </label>
            </div>

            {/* SALARY CONFIGURATION */}
            <div className="mt-5 rounded-2xl border border-[#163B66]/15 bg-[#163B66]/[0.03] p-5">
              <p className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#163B66]/70"><AppIcon name="settings" size={15} /> Cấu hình lương &amp; hợp đồng</p>
              <div className="grid gap-4 md:grid-cols-2">
                <label>
                  Mã nhân viên (theo HĐ)
                  <input
                    value="Tự động tạo (SLxxx)"
                    disabled
                    className="bg-slate-100/60 text-slate-400 cursor-not-allowed border border-slate-200"
                  />
                </label>
                <label>
                  Chức vụ
                  <input
                    value={employeeForm.position}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, position: e.target.value }))}
                    placeholder="Ví dụ: Kế toán"
                  />
                </label>
                <label>
                  Loại hợp đồng
                  <select
                    value={employeeForm.contract_type}
                    onChange={(e) => setEmployeeForm((prev) => ({
                      ...prev,
                      contract_type: e.target.value,
                      contract_start_date: isFixedTermEmployeeContract(e.target.value) ? prev.contract_start_date : '',
                      contract_end_date: isFixedTermEmployeeContract(e.target.value) ? prev.contract_end_date : '',
                    }))}
                  >
                    <option value="">-- Chọn loại hợp đồng --</option>
                    {EMPLOYEE_CONTRACT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label>
                  Loại nhân viên
                  <select
                    value={employeeForm.employee_type}
                    onChange={(e) => setEmployeeForm((prev) => ({
                      ...prev,
                      employee_type: e.target.value,
                      ...getContractAllowanceDefaults(e.target.value),
                    }))}
                  >
                    <option value="FULLTIME">Chính thức (full BH + thuế lũy tiến)</option>
                    <option value="PROBATION">Thử việc (không BH + khấu trừ 10%)</option>
                    <option value="INTERN">Học việc (không BH + khấu trừ 10%)</option>
                    <option value="TRAINEE">Thực tập (Khối C, không tính lương)</option>
                  </select>
                </label>
                <label>
                  Ngày ký hợp đồng
                  <BrandedDateInput
                    value={employeeForm.contract_sign_date}
                    disabled={!employeeForm.contract_type}
                    required={Boolean(employeeForm.contract_type)}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, contract_sign_date: e.target.value }))}
                  />
                </label>
                {isFixedTermEmployeeContract(employeeForm.contract_type) && (
                  <>
                    <label>
                      Hợp đồng từ ngày
                      <BrandedDateInput
                        value={employeeForm.contract_start_date}
                        required
                        onChange={(e) => setEmployeeForm((prev) => ({ ...prev, contract_start_date: e.target.value }))}
                      />
                    </label>
                    <label>
                      Hợp đồng đến ngày
                      <BrandedDateInput
                        value={employeeForm.contract_end_date}
                        min={employeeForm.contract_start_date || undefined}
                        required
                        onChange={(e) => setEmployeeForm((prev) => ({ ...prev, contract_end_date: e.target.value }))}
                      />
                    </label>
                  </>
                )}
                <label>
                  Lương theo HĐLĐ (VND)
                  <VndInput
                    value={employeeForm.contract_salary}
                    onValueChange={(value) => setEmployeeForm((prev) => ({ ...prev, contract_salary: String(value) }))}
                    placeholder="Ví dụ: 15000000"
                    style={{ textAlign: 'right' }}
                  />
                </label>
                <label>
                  Tiền cơm (VND/tháng)
                  <VndInput
                    value={employeeForm.meal_allowance}
                    onValueChange={(value) => setEmployeeForm((prev) => ({ ...prev, meal_allowance: String(value) }))}
                    placeholder="Ví dụ: 1200000"
                    style={{ textAlign: 'right' }}
                  />
                </label>
                <label>
                  Tiền điện thoại (VND/tháng)
                  <VndInput
                    value={employeeForm.phone_allowance}
                    onValueChange={(value) => setEmployeeForm((prev) => ({ ...prev, phone_allowance: String(value) }))}
                    placeholder="Ví dụ: 2000000"
                    style={{ textAlign: 'right' }}
                  />
                </label>
                <label>
                  Số người phụ thuộc (NTT)
                  <input
                    type="number"
                    min={0}
                    value={employeeForm.dependents_count}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, dependents_count: e.target.value }))}
                    placeholder="0"
                  />
                </label>
                <label>
                  Tiền xăng xe (VND/tháng)
                  <VndInput
                    value={employeeForm.trans_allowance}
                    onValueChange={(value) => setEmployeeForm((prev) => ({ ...prev, trans_allowance: String(value) }))}
                    placeholder="Ví dụ: 2000000"
                    style={{ textAlign: 'right' }}
                  />
                </label>
                <label>
                  Quota phép năm (ngày)
                  <input
                    type="number"
                    min={0}
                    value={employeeForm.annual_leave_quota}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, annual_leave_quota: e.target.value }))}
                  />
                </label>
                <label>
                  Phụ cấp khác (VND/tháng)
                  <VndInput
                    value={employeeForm.other_allowance}
                    onValueChange={(value) => setEmployeeForm((prev) => ({ ...prev, other_allowance: String(value) }))}
                    placeholder="Ví dụ: 0"
                    style={{ textAlign: 'right' }}
                  />
                </label>
              </div>
              <div className="mt-4 rounded-xl border border-sky-100 bg-sky-50 px-4 py-3 text-xs leading-5 text-sky-900">
                <strong>Quyền hệ thống dự kiến: {ACCESS_ROLE_LABELS[inferAccessRolePreview(employeeForm.department_name, employeeForm.position, employeeForm.full_name)]}</strong>
                <br />
                Quyền không chọn thủ công: Tôn Thất Trung Kiên và Tô Tố Vân nhận DIRECTOR; “Admin” trong nhánh IT &amp; ADMIN nhận HR_ADMIN; nhân viên IT dùng tài khoản quản trị chung admin_sealink; trường hợp khác nhận USER.
              </div>
            </div>

            {/* ACCOUNT LOGIN INFO */}
            <div className="mt-4 rounded-2xl border border-slate-200 bg-[#0ea5e9]/[0.02] p-5">
              <p className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#0284c7] font-bold"><AppIcon name="user" size={15} /> Thông tin tài khoản đăng nhập (không bắt buộc)</p>
              <p className="mb-4 text-xs text-slate-500">Có thể để trống và bổ sung tài khoản sau khi hoàn tất mapping nhân viên.</p>
              <div className="grid gap-4 md:grid-cols-2">
                <label>
                  Tên đăng nhập (Username)
                  <input
                    value={employeeForm.username}
                    readOnly
                    placeholder="Tự động từ mail công ty"
                    title="Tên đăng nhập được tạo tự động từ phần trước @ của mail công ty"
                  />
                </label>
                <label>
                  Mật khẩu (Password)
                  <EmployeePasswordField
                    value={employeeForm.password}
                    onChange={(value) => setEmployeeForm((prev) => ({ ...prev, password: value }))}
                    onNotice={setMessage}
                    placeholder="Để trống nếu chưa tạo tài khoản"
                  />
                </label>
              </div>
            </div>

            {/* BANK INFO */}
            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-5">
              <p className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400"><AppIcon name="bank" size={15} /> Thông tin ngân hàng</p>
              <div className="grid gap-4 md:grid-cols-2">
                <label>
                  Tên ngân hàng
                  <input
                    value={employeeForm.bank_name}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, bank_name: e.target.value }))}
                    placeholder="Ví dụ: Vietcombank"
                  />
                </label>
                <label>
                  Số tài khoản
                  <input
                    value={employeeForm.account_number}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, account_number: e.target.value }))}
                    placeholder="Ví dụ: 1234567890"
                  />
                </label>
              </div>
            </div>

            {/* PERSONAL INFO */}
            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-5">
              <p className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400"><AppIcon name="user" size={15} /> Thông tin cá nhân &amp; Liên hệ</p>
              <div className="grid gap-4 md:grid-cols-2">
                <label>
                  Mã số thuế (MST)
                  <input
                    value={employeeForm.tax_code}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, tax_code: e.target.value }))}
                    placeholder="Ví dụ: 0101234567"
                  />
                </label>
                <label>
                  Số điện thoại cá nhân
                  <input
                    value={employeeForm.phone_number}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, phone_number: e.target.value }))}
                    placeholder="Ví dụ: 0987654321"
                  />
                </label>
                <label>
                  Số điện thoại công ty
                  <input
                    value={employeeForm.company_phone_number}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, company_phone_number: e.target.value }))}
                    placeholder="Ví dụ: 0287 307 5768"
                  />
                </label>
                <label>
                  Số BHXH
                  <input
                    value={employeeForm.social_insurance_number}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, social_insurance_number: e.target.value }))}
                    placeholder="Ví dụ: 0123456789"
                  />
                </label>
                <label>
                  Bảo hiểm y tế (BHYT)
                  <input
                    value={employeeForm.health_insurance_number}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, health_insurance_number: e.target.value }))}
                    placeholder="Ví dụ: DN401..."
                  />
                </label>
                <label>
                  Bảo hiểm PVI
                  <input
                    value={employeeForm.pvi_insurance}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, pvi_insurance: e.target.value }))}
                    placeholder="Mã thẻ PVI"
                  />
                </label>
                <label>
                  Mail Công Ty
                  <input
                    type="email"
                    value={employeeForm.company_email}
                    onChange={(e) => {
                      const companyEmail = e.target.value
                      setEmployeeForm((prev) => ({
                        ...prev,
                        company_email: companyEmail,
                        username: usernameFromCompanyEmail(companyEmail),
                      }))
                    }}
                    placeholder="Ví dụ: nv.a@sealink.com"
                  />
                </label>
                <label>
                  Mail Cá Nhân
                  <input
                    type="email"
                    value={employeeForm.personal_email}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, personal_email: e.target.value }))}
                    placeholder="Ví dụ: ngvana@gmail.com"
                  />
                </label>
                <label className="md:col-span-2">
                  Ghi chú
                  <textarea
                    value={employeeForm.notes}
                    onChange={(e) => setEmployeeForm((prev) => ({ ...prev, notes: e.target.value }))}
                    placeholder="Các ghi chú khác về nhân sự..."
                    rows={2}
                    className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm outline-none transition focus:border-[#163B66] focus:ring-1 focus:ring-[#163B66]"
                  />
                </label>
              </div>
            </div>
            <div className="mt-6 flex flex-row items-center justify-end gap-3">
              <button
                type="button"
                className="inline-flex h-[44px] min-w-[120px] items-center justify-center rounded-xl border border-slate-200 bg-white px-6 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                onClick={() => {
                  setIsEmployeeModalOpen(false)
                  setEmployeeForm(EMPTY_EMPLOYEE_FORM)
                }}
              >
                Đóng
              </button>
              <button 
                type="submit" 
                disabled={loading}
                className="inline-flex h-[44px] min-w-[180px] items-center justify-center rounded-xl bg-[#163B66] px-6 text-sm font-semibold text-white shadow-[0_18px_36px_-24px_rgba(22,59,102,0.85)] transition hover:bg-[#102B49] disabled:cursor-not-allowed disabled:opacity-60 whitespace-nowrap"
              >
                Lưu hồ sơ nhân viên
              </button>
            </div>
          </form>
        </div>
      )}



        {activeTab === 'my-payslip' && (
          <section className="mobile-payslip-page space-y-6 max-w-4xl mx-auto animate-[fadeIn_0.3s_ease-out_forwards]">
            {/* Period selector */}
            <div className="mobile-payslip-toolbar rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-slate-900 tracking-tight">Chọn tháng thanh toán lương</h2>
                <p className="text-xs text-slate-500 mt-1">Chọn tháng cần xem chi tiết phiếu lương của bạn.</p>
              </div>
              <div className="mobile-payslip-toolbar__actions flex flex-wrap items-end gap-3">
                <MonthYearSelect
                  id="my-payslip-period"
                  value={myPayslipPeriod}
                  availablePeriods={myPayslipPeriodOptions}
                  onChange={(period) => {
                    setMyPayslipPeriod(period)
                    setPayslipPdfStatus(null)
                  }}
                  disabled={myPayslipPeriodOptions.length === 0}
                  emptyLabel="Chưa có phiếu lương"
                  yearLabel="Năm phiếu lương"
                  monthLabel="Tháng phiếu lương"
                />
                <button
                  type="button"
                  onClick={loadMyPayslip}
                  disabled={loading || !myPayslipPeriod}
                  className="bg-slate-900 hover:bg-slate-800 text-white text-sm font-bold px-4 py-2.5 rounded-xl transition cursor-pointer"
                >
                  Làm mới
                </button>
                <button
                  type="button"
                  onClick={downloadMyPayslipPdf}
                  disabled={!myPayslipData || isDownloadingPayslip}
                  className="app-download-button inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-50"
                  title={myPayslipData ? 'Tải phiếu lương đang hiển thị dưới dạng PDF' : 'Chọn tháng có phiếu lương đã phát hành để tải PDF'}
                >
                  {isDownloadingPayslip ? (
                    <>
                      <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle className="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" /><path className="opacity-75" d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /></svg>
                      Đang tạo PDF
                    </>
                  ) : (
                    <>
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></svg>
                      Tải PDF
                    </>
                  )}
                </button>
              </div>
            </div>

            {payslipPdfStatus && (
              <div
                role={payslipPdfStatus.tone === 'error' ? 'alert' : 'status'}
                className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-xs font-medium ${
                  payslipPdfStatus.tone === 'error'
                    ? 'border-rose-200 bg-rose-50 text-rose-700'
                    : payslipPdfStatus.tone === 'success'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-sky-200 bg-sky-50 text-sky-700'
                }`}
              >
                {payslipPdfStatus.tone === 'loading' && (
                  <svg className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle className="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" /><path className="opacity-75" d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /></svg>
                )}
                <span>{payslipPdfStatus.text}</span>
              </div>
            )}

            {myPayslipData ? (() => {
              const actualSalary = myPayslipData.calculations.actual_salary || 0;
              const mealAllowance = (myPayslipData.inputs.meal_allowance_free || 0) + (myPayslipData.inputs.meal_allowance_tax || 0);
              const phoneAllowance = myPayslipData.inputs.phone_allowance_free || 0;
              const transAllowance = myPayslipData.inputs.trans_allowance_tax || 0;
              const perfAllowance = myPayslipData.inputs.perf_allowance_tax || 0;
              const otherIncome = myPayslipData.inputs.other_income || 0;
              const bonus = myPayslipData.inputs.bonus || 0;
              const salesBonus = myPayslipData.inputs.sales_bonus || 0;
              const pitRefund = myPayslipData.inputs.pit_refund || 0;
              const commissionSummary = myPayslipData.commission_summary || {
                cycles: [], total_bonus_quarter: 0, current_period_bonus: salesBonus,
                remaining_bonus: 0, pending_jobs: [], pending_bonus_amount: 0,
                scheduled_job_payouts: [], scheduled_job_payout_total: 0,
              };
              const commissionCycles = commissionSummary.cycles || [];
              const pendingCommissionJobs = commissionSummary.pending_jobs || [];
              const scheduledCommissionPayouts = commissionSummary.scheduled_job_payouts || [];
              const formatRoundedCurrency = (value: number) => formatCurrency(Math.round(Number(value) || 0));

              const grossEarnings = actualSalary + mealAllowance + phoneAllowance + transAllowance + perfAllowance + otherIncome + bonus + salesBonus + pitRefund;

              const totalIns = myPayslipData.calculations.total_ins_emp || 0;
              const pitTax = myPayslipData.calculations.pit_tax || 0;
              const unionFee = myPayslipData.calculations.union_fee || 0;
              const advancePayment = myPayslipData.inputs.advance_payment || 0;
              const otherDeductions = myPayslipData.inputs.other_deductions || 0;

              const totalDeductions = totalIns + pitTax + unionFee + advancePayment + otherDeductions;
              const finalTransfer = myPayslipData.calculations.final_transfer || 0;

              const formatPeriod = (periodStr: string) => {
                if (!periodStr) return '';
                const parts = periodStr.split('-');
                if (parts.length < 2) return periodStr;
                return `Tháng ${parts[1]}/${parts[0]}`;
              };

              const getPayDate = (periodStr: string) => {
                if (!periodStr) return 'N/A';
                const parts = periodStr.split('-').map(Number);
                if (parts.length < 2) return 'N/A';
                let year = parts[0];
                let month = parts[1] + 1;
                if (month > 12) {
                  month = 1;
                  year += 1;
                }
                return `25/${month.toString().padStart(2, '0')}/${year}`;
              };

              const getMonthBounds = (period: string) => {
                if (!period) return { start: '?', end: '?' };
                try {
                  const [year, month] = period.split('-');
                  const currentYear = parseInt(year);
                  const currentMonth = parseInt(month);
                  let prevYear = currentYear;
                  let prevMonth = currentMonth - 1;
                  if (prevMonth === 0) { prevMonth = 12; prevYear--; }
                  const prevMonthStr = String(prevMonth).padStart(2, '0');
                  const currMonthStr = String(currentMonth).padStart(2, '0');
                  return { start: `23/${prevMonthStr}/${prevYear}`, end: `22/${currMonthStr}/${currentYear}` };
                } catch { return { start: '?', end: '?' }; }
              };

              const formatDateStr = (dateStr?: string) => {
                if (!dateStr) return '?';
                try {
                  const [y, m, d] = dateStr.split('-');
                  return `${d}/${m}/${y}`;
                } catch { return dateStr; }
              };

              const getDayBefore = (dateStr?: string) => {
                if (!dateStr) return '?';
                try {
                  const d = new Date(dateStr);
                  d.setDate(d.getDate() - 1);
                  const dd = String(d.getDate()).padStart(2, '0');
                  const mm = String(d.getMonth() + 1).padStart(2, '0');
                  return `${dd}/${mm}/${d.getFullYear()}`;
                } catch { return '?'; }
              };

              return (
                <div ref={myPayslipPdfRef} className="mobile-payslip-document rounded-[32px] border border-slate-200 bg-white p-8 sm:p-12 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.15)] space-y-8 relative overflow-hidden text-slate-800">
                  {/* Accent Top Border */}
                  <div className="absolute top-0 left-0 right-0 h-1.5 bg-slate-900"></div>

                  {/* Header: Company and Logo */}
                  <div className="flex flex-col sm:flex-row justify-between items-start gap-6 border-b border-slate-100 pb-8">
                    <div className="flex items-center gap-4">
                      <img src={logoSealink} alt="Sealink Logo" className="h-16 w-16 rounded-2xl border border-slate-150 p-1 object-contain" />
                      <div>
                        <h3 className="text-xl font-bold text-slate-950 tracking-tight">SEALINK INTERNATIONAL</h3>
                        <p className="text-[11px] text-slate-500 uppercase tracking-widest font-semibold mt-0.5">Tiền lương & Chế độ đãi ngộ</p>
                      </div>
                    </div>
                    <div className="sm:text-right space-y-1">
                      <span className="inline-block bg-slate-100 text-slate-800 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider">Phiếu Lương / Payslip</span>
                      <h2 className="text-2xl font-black text-slate-900 tracking-tight mt-2">{formatPeriod(myPayslipData.salary_period)}</h2>
                      <p className="text-xs text-slate-500">Ngày phát hành: {new Date().toLocaleDateString('vi-VN')}</p>
                    </div>
                  </div>

                  {/* Employee Summary & Net Pay widgets */}
                  <div className="flex flex-col lg:flex-row justify-between gap-8">
                    {/* Left Column: Info Grid */}
                    <div className="flex-1 space-y-4">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">TÓM TẮT NHÂN VIÊN / EMPLOYEE SUMMARY</h3>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
                        <div className="flex justify-between border-b border-slate-100 pb-1.5">
                          <span className="text-slate-500 font-medium">Họ và tên / Name:</span>
                          <strong className="text-slate-900 font-semibold">{myPayslipData.employee_name}</strong>
                        </div>
                        <div className="flex justify-between border-b border-slate-100 pb-1.5">
                          <span className="text-slate-500 font-medium">Mã nhân viên / ID:</span>
                          <strong className="text-slate-900 font-mono font-semibold">{myPayslipData.employee_code || 'N/A'}</strong>
                        </div>
                        <div className="flex justify-between border-b border-slate-100 pb-1.5">
                          <span className="text-slate-500 font-medium">Chức vụ / Designation:</span>
                          <strong className="text-slate-900 font-semibold">{myPayslipData.position || 'N/A'}</strong>
                        </div>
                        <div className="flex justify-between border-b border-slate-100 pb-1.5">
                          <span className="text-slate-500 font-medium">Ngày vào làm / Joining Date:</span>
                          <strong className="text-slate-900 font-semibold">{myPayslipData.start_date || 'N/A'}</strong>
                        </div>
                        <div className="flex justify-between border-b border-slate-100 pb-1.5">
                          <span className="text-slate-500 font-medium">Tháng thanh toán / Pay Month:</span>
                          <strong className="text-slate-900 font-semibold">{formatPeriod(myPayslipData.salary_period)}</strong>
                        </div>
                        <div className="flex justify-between border-b border-slate-100 pb-1.5">
                          <span className="text-slate-500 font-medium">Ngày chi trả / Pay Date:</span>
                          <strong className="text-slate-900 font-semibold">{getPayDate(myPayslipData.salary_period)}</strong>
                        </div>
                      </div>
                    </div>

                    {/* Right Column: Net Pay Box (Zoho Style) */}
                    <div className="w-full lg:w-[320px] rounded-2xl border border-emerald-100 bg-emerald-50/20 p-5 flex flex-col justify-between space-y-4 shadow-sm">
                      <div className="text-center rounded-xl bg-emerald-50 border border-emerald-100 py-4 px-3">
                        <p className="text-2xl font-black text-emerald-700 tracking-tight">
                          {formatCurrency(finalTransfer)}
                        </p>
                        <p className="text-xs text-emerald-600 font-medium mt-1">Thực nhận chuyển khoản / Net Pay</p>
                      </div>
                      <div className="divide-y divide-emerald-100/50 text-xs text-emerald-950 font-medium">
                        <div className="flex justify-between py-2">
                          <span>Số ngày công đi làm / Paid Days:</span>
                          <span className="font-bold">{myPayslipData.inputs.actual_working_days} ngày</span>
                        </div>
                        <div className="flex justify-between py-2">
                          <span>Ngày nghỉ không công / LOP Days:</span>
                          <span className="font-bold">{Math.max(0, calculatePeriodWorkingDays(myPayslipData.salary_period) - myPayslipData.inputs.actual_working_days)} ngày</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Bank Account Info Section */}
                  <div className="border-t border-b border-slate-100 py-3 text-xs text-slate-500 flex flex-col sm:flex-row justify-between gap-2">
                    <div>
                      <span className="font-medium text-slate-400">Tài khoản thanh toán / Bank Account:</span>
                      <strong className="ml-1 text-slate-700 font-mono">{myPayslipData.account_number || 'N/A'} ({myPayslipData.bank_name || 'N/A'})</strong>
                    </div>
                    <div>
                      <span className="font-medium text-slate-400">Chế độ hợp đồng / Contract Type:</span>
                      <strong className="ml-1 text-slate-700">{getEmployeeTypeLabel(myPayslipData.employee_type)}</strong>
                    </div>
                  </div>

                  {/* Commission quarter overview: informational only, derived from the wallet ledger. */}
                  <section className="rounded-2xl border border-sky-100 bg-sky-50/40 p-5 space-y-4">
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <h4 className="text-sm font-bold text-slate-900">Tổng hợp thưởng doanh số theo quý</h4>
                        <p className="mt-1 text-xs text-slate-500">Dữ liệu chỉ đọc từ ví thưởng commission; số tiền này không làm thay đổi công thức lương.</p>
                      </div>
                      {commissionCycles.length > 0 && (
                        <span className="w-fit rounded-full bg-white px-3 py-1 text-[11px] font-bold text-sky-800 ring-1 ring-sky-100">
                          {commissionCycles.map((cycle: any) => cycle.period_label).join(' · ')}
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      <div className="rounded-xl border border-slate-200 bg-white p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Tổng thưởng quý</p>
                        <p className="mt-1 whitespace-nowrap text-sm font-black tracking-tight text-slate-900 sm:text-base">{formatRoundedCurrency(commissionSummary.total_bonus_quarter || 0)}</p>
                      </div>
                      <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Nhận trong {formatPeriod(myPayslipData.salary_period)}</p>
                        <p className="mt-1 whitespace-nowrap text-sm font-black tracking-tight text-emerald-700 sm:text-base">{formatRoundedCurrency(commissionSummary.current_period_bonus || 0)}</p>
                      </div>
                      <div className="rounded-xl border border-amber-100 bg-amber-50/60 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">Còn lại sau tháng này</p>
                        <p className="mt-1 whitespace-nowrap text-sm font-black tracking-tight text-amber-700 sm:text-base">{formatRoundedCurrency(commissionSummary.remaining_bonus || 0)}</p>
                      </div>
                    </div>
                    {commissionCycles.length > 0 && (
                      <p className="text-[11px] text-slate-500">
                        Kế hoạch chi trả: {commissionCycles.map((cycle: any) => `${cycle.period_label} (${(cycle.payout_periods || []).map(formatPeriod).join(', ')})`).join(' · ')}.
                        “Còn lại” là phần dự kiến thuộc các tháng sau của cùng chu kỳ chi trả.
                      </p>
                    )}
                    {scheduledCommissionPayouts.length > 0 && (
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4">
                        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                          <div>
                            <h5 className="text-xs font-bold text-emerald-900">Khoản bonus bổ sung đã được kế toán lập lệnh</h5>
                            <p className="mt-0.5 text-[11px] text-emerald-700">Các khoản này được cộng trong tháng lương đang xem, ngoài phần bonus chuẩn của kỳ.</p>
                          </div>
                          <span className="text-xs font-black text-emerald-800">Tổng bổ sung: {formatRoundedCurrency(commissionSummary.scheduled_job_payout_total || 0)}</span>
                        </div>
                        <div className="mt-3 overflow-auto rounded-lg border border-emerald-100 bg-white">
                          <table className="min-w-full text-left text-xs">
                            <thead className="bg-emerald-50 text-[11px] uppercase tracking-wide text-emerald-800">
                              <tr><th className="px-3 py-2">JOB / kỳ nguồn</th><th className="px-3 py-2">Ghi chú kế toán</th><th className="px-3 py-2 text-right">Số tiền cộng thêm</th></tr>
                            </thead>
                            <tbody className="divide-y divide-emerald-50 text-slate-700">
                              {scheduledCommissionPayouts.map((item: any, index: number) => (
                                <tr key={`${item.job_no}-${item.source_period_label}-${index}`}>
                                  <td className="px-3 py-2"><b className="text-slate-900">{item.job_no}</b><span className="block text-[11px] text-slate-500">{item.source_period_label || 'Kỳ nguồn'}{item.customer ? ` · ${item.customer}` : ''}</span></td>
                                  <td className="max-w-[360px] px-3 py-2 text-slate-600">{item.note || 'Kế toán đã lập lệnh chi trả bonus theo JOB.'}</td>
                                  <td className="whitespace-nowrap px-3 py-2 text-right font-bold text-emerald-700">{formatRoundedCurrency(item.amount || 0)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    <div className="payslip-commission-pending-jobs overflow-hidden rounded-xl border border-slate-200 bg-white">
                      <div className="flex flex-col gap-1 border-b border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <h5 className="text-xs font-bold text-slate-800">JOB chưa đủ điều kiện nhận bonus</h5>
                          <p className="mt-0.5 text-[11px] text-slate-500">JOB có Payment Received = NO vẫn nằm trong tổng thưởng quý nhưng sẽ chờ khách hàng thanh toán.</p>
                        </div>
                        {pendingCommissionJobs.length > 0 && <span className="text-xs font-bold text-amber-700">Đang chờ: {formatRoundedCurrency(commissionSummary.pending_bonus_amount || 0)}</span>}
                      </div>
                      {pendingCommissionJobs.length > 0 ? (
                        <div className="payslip-commission-job-list max-h-44 overflow-auto">
                          <table className="min-w-full text-left text-xs">
                            <thead className="sticky top-0 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                              <tr><th className="px-4 py-2">Giai đoạn nguồn</th><th className="px-4 py-2">JOB</th><th className="px-4 py-2">Khách hàng</th><th className="px-4 py-2 text-right">Bonus đang chờ</th></tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 text-slate-700">
                              {pendingCommissionJobs.map((job: any, index: number) => (
                                <tr key={`${job.period_label}-${job.job_no}-${index}`}>
                                  <td className="px-4 py-2 font-medium">{job.period_label}</td>
                                  <td className="px-4 py-2 font-semibold text-slate-900">{job.job_no}</td>
                                  <td className="max-w-[180px] truncate px-4 py-2" title={job.customer || ''}>{job.customer || '—'}</td>
                                  <td className="px-4 py-2 text-right font-semibold text-amber-700">{formatRoundedCurrency(job.pending_bonus || 0)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="px-4 py-3 text-xs text-emerald-700">Không có JOB nào đang chờ Payment Received trong giai đoạn thưởng đang hiển thị.</p>
                      )}
                    </div>
                  </section>

                  {/* Earnings & Deductions Tables */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4">
                    {/* Left Table: Earnings */}
                    <div className="space-y-4 flex flex-col justify-between">
                      <div>
                        <div className="flex justify-between items-center border-b border-slate-200 pb-2">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">EARNINGS / THU NHẬP</h4>
                          <span className="text-xs font-bold uppercase tracking-wider text-slate-400">SỐ TIỀN / AMOUNT</span>
                        </div>
                        <div className="divide-y divide-slate-100 text-sm">
                          <div className="py-2.5 flex justify-between">
                            <div>
                              <span className="font-semibold text-slate-800">Lương thực tế theo ngày công</span>
                              <p className="text-[11px] text-slate-400 mt-0.5">Lương HĐ: {formatCurrency(myPayslipData.contract_salary)} | Công chuẩn: {calculatePeriodWorkingDays(myPayslipData.salary_period)}</p>
                              {myPayslipData.inputs?.is_mid_month_change && (() => {
                                let actual_salary_old = 0;
                                let actual_salary_new = 0;
                                const stdWorkingDays = calculatePeriodWorkingDays(myPayslipData.salary_period);
                                const ratio = Math.min(1.0, myPayslipData.inputs.actual_working_days / stdWorkingDays);
                                const total_days = (myPayslipData.inputs.prorated_days_old || 0) + (myPayslipData.inputs.prorated_days_new || 0);
                                if (total_days > 0) {
                                  const old_base = ((myPayslipData.inputs.prorated_old_salary || 0) * (myPayslipData.inputs.prorated_days_old || 0)) / total_days;
                                  actual_salary_old = Math.round(old_base * ratio);
                                  actual_salary_new = actualSalary - actual_salary_old;
                                }
                                return (
                                  <div className="mt-1 space-y-0.5">
                                    <p className="text-[11px] text-slate-500 italic">
                                      - Mức cũ: {myPayslipData.inputs.prorated_days_old} ngày (Từ {getMonthBounds(myPayslipData.salary_period).start} đến {getDayBefore(myPayslipData.inputs.mid_month_effective_date)}: {formatCurrency(myPayslipData.inputs.prorated_old_salary)}) - {formatCurrency(actual_salary_old)}
                                    </p>
                                    <p className="text-[11px] text-slate-500 italic">
                                      - Mức mới: {myPayslipData.inputs.prorated_days_new} ngày (Từ {formatDateStr(myPayslipData.inputs.mid_month_effective_date)} đến {getMonthBounds(myPayslipData.salary_period).end}: {formatCurrency(myPayslipData.inputs.prorated_new_salary)}) - {formatCurrency(actual_salary_new)}
                                    </p>
                                  </div>
                                );
                              })()}
                            </div>
                            <span className="font-semibold text-slate-900">{formatCurrency(actualSalary)}</span>
                          </div>
                          
                          {mealAllowance > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Phụ cấp ăn trưa</span>
                                <p className="text-[11px] text-slate-400 mt-0.5">Miễn thuế: {formatCurrency(myPayslipData.inputs.meal_allowance_free)} | Tính thuế: {formatCurrency(myPayslipData.inputs.meal_allowance_tax)}</p>
                              </div>
                              <span className="font-semibold text-slate-900">{formatCurrency(mealAllowance)}</span>
                            </div>
                          )}

                          {phoneAllowance > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Phụ cấp điện thoại</span>
                                <p className="text-[11px] text-slate-400 mt-0.5">Miễn thuế TNCN</p>
                              </div>
                              <span className="font-semibold text-slate-900">{formatCurrency(phoneAllowance)}</span>
                            </div>
                          )}

                          {transAllowance > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Phụ cấp xăng xe (Có tính thuế)</span>
                              </div>
                              <span className="font-semibold text-slate-900">{formatCurrency(transAllowance)}</span>
                            </div>
                          )}

                          {perfAllowance > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Phụ cấp hiệu suất công việc</span>
                              </div>
                              <span className="font-semibold text-slate-900">{formatCurrency(perfAllowance)}</span>
                            </div>
                          )}

                          {otherIncome > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Thu nhập bổ sung khác</span>
                                {myPayslipData.inputs.other_income_note && (
                                  <p className="mt-1 max-w-xl text-[11px] leading-4 text-slate-500">
                                    Lý do: {myPayslipData.inputs.other_income_note}
                                  </p>
                                )}
                              </div>
                              <span className="font-semibold text-slate-900">{formatCurrency(otherIncome)}</span>
                            </div>
                          )}

                          {bonus > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Tiền thưởng (Bonus)</span>
                              </div>
                              <span className="font-semibold text-emerald-600">+{formatCurrency(bonus)}</span>
                            </div>
                          )}

                          {salesBonus > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Tiền thưởng doanh số</span>
                              </div>
                              <span className="font-semibold text-slate-900">{formatCurrency(salesBonus)}</span>
                            </div>
                          )}

                          {pitRefund > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Quyết toán hoàn thuế PIT</span>
                              </div>
                              <span className="font-semibold text-emerald-600">+{formatCurrency(pitRefund)}</span>
                            </div>
                          )}
                        </div>
                      </div>
                      
                      <div className="flex justify-between items-center bg-slate-50/80 rounded-xl p-3 border border-slate-100 text-sm font-bold text-slate-800 mt-4">
                        <span>Tổng thu nhập / Gross Earnings</span>
                        <span>{formatCurrency(grossEarnings)}</span>
                      </div>
                    </div>

                    {/* Right Table: Deductions */}
                    <div className="space-y-4 flex flex-col justify-between">
                      <div>
                        <div className="flex justify-between items-center border-b border-slate-200 pb-2">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">DEDUCTIONS / KHẤU TRỪ</h4>
                          <span className="text-xs font-bold uppercase tracking-wider text-slate-400">SỐ TIỀN / AMOUNT</span>
                        </div>
                        <div className="divide-y divide-slate-100 text-sm">
                          {totalIns > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Bảo hiểm bắt buộc (10.5%)</span>
                                <p className="text-[11px] text-slate-400 mt-0.5">BHXH (8%): {formatCurrency(myPayslipData.calculations.social_emp)} | BHYT: {formatCurrency(myPayslipData.calculations.health_emp)} | BHTN: {formatCurrency(myPayslipData.calculations.unemp_emp)}</p>
                              </div>
                              <span className="font-semibold text-rose-600">-{formatCurrency(totalIns)}</span>
                            </div>
                          )}

                          {pitTax > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Thuế thu nhập cá nhân (PIT)</span>
                              </div>
                              <span className="font-semibold text-rose-600">-{formatCurrency(pitTax)}</span>
                            </div>
                          )}

                          {unionFee > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Đoàn phí Công đoàn (0.5%)</span>
                              </div>
                              <span className="font-semibold text-rose-600">-{formatCurrency(unionFee)}</span>
                            </div>
                          )}

                          {advancePayment > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Tạm ứng lương</span>
                              </div>
                              <span className="font-semibold text-rose-600">-{formatCurrency(advancePayment)}</span>
                            </div>
                          )}

                          {otherDeductions > 0 && (
                            <div className="py-2.5 flex justify-between">
                              <div>
                                <span className="font-semibold text-slate-800">Khấu trừ khác</span>
                              </div>
                              <span className="font-semibold text-rose-600">-{formatCurrency(otherDeductions)}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="flex justify-between items-center bg-slate-50/80 rounded-xl p-3 border border-slate-100 text-sm font-bold text-rose-600 mt-4">
                        <span>Tổng khấu trừ / Total Deductions</span>
                        <span>-{formatCurrency(totalDeductions)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Total Net Payable Banner (Zoho Style) */}
                  <div className="border-t border-slate-200 pt-6">
                    <div className="bg-[#F0FAED] text-emerald-950 border border-emerald-100 rounded-2xl p-5 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 shadow-sm">
                      <div>
                        <h4 className="text-sm font-bold uppercase tracking-wider text-emerald-800">TOTAL NET PAYABLE / THỰC NHẬN CHUYỂN KHOẢN</h4>
                        <p className="text-xs text-emerald-600 mt-1">Lương thực chuyển = Tổng thu nhập - Tổng khấu trừ</p>
                      </div>
                      <span className="text-3xl font-black tracking-tight text-emerald-900">
                        {formatCurrency(finalTransfer)}
                      </span>
                    </div>
                    
                    {/* Amount in words */}
                    <div className="mt-4 text-sm text-slate-600 flex justify-end">
                      <p className="italic font-medium">Bằng chữ / Amount In Words: <span className="font-semibold text-slate-800 not-italic">{numberToVietnameseWords(finalTransfer)}</span></p>
                    </div>
                  </div>

                  {/* Signature Notice Footer */}
                  <div className="pt-6 border-t border-slate-100 text-[11px] text-slate-400 flex flex-col sm:flex-row justify-between gap-4">
                    <p>Mọi thắc mắc về số liệu vui lòng liên hệ phòng Kế toán trước ngày 25 hàng tháng.</p>
                    <p className="sm:text-right font-semibold text-slate-500">-- Tài liệu được hệ thống tự động xuất, không yêu cầu chữ ký tay --</p>
                  </div>
                </div>
              );
            })() : (
              <div className="rounded-[28px] border border-slate-200 bg-white p-12 text-center shadow-sm">
                <svg viewBox="0 0 24 24" fill="none" className="mx-auto h-12 w-12 text-slate-300" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <h3 className="mt-4 text-sm font-bold text-slate-800">Phiếu lương chưa được phát hành</h3>
                <p className="mt-2 text-xs text-slate-500 max-w-sm mx-auto">
                  Phiếu lương tháng {myPayslipPeriod} đang được kế toán hoàn thiện hoặc chưa được ban giám đốc kích hoạt phát hành cho nhân viên.
                </p>
              </div>
            )}
          </section>
        )}

        {activeTab === 'my-held-bonuses' && (
          <section className="mobile-held-bonus-page mx-auto max-w-5xl space-y-6 animate-[fadeIn_0.3s_ease-out_forwards]">
            <div className="mobile-held-bonus-toolbar flex flex-col gap-4 rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-bold tracking-tight text-slate-900">JOB bonus đang giữ</h2>
                <p className="mt-1 text-xs text-slate-500">Theo dõi từng JOB có bonus chưa được chi trả và gửi yêu cầu để kế toán kiểm tra, xác minh thanh toán.</p>
              </div>
              <div className="mobile-held-bonus-toolbar__actions flex items-center gap-3">
                <span className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-700 ring-1 ring-amber-100">{visibleMyHeldBonusJobs.length} JOB đang giữ</span>
                <button type="button" onClick={loadMyHeldBonusJobs} disabled={loading} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-bold text-slate-800 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60">Làm mới</button>
              </div>
            </div>

            {heldBonusPeriods.length > 0 && (
              <div className="mobile-held-bonus-period rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-bold text-slate-900">Quý có JOB bonus đang giữ</p>
                  <p className="mt-1 text-xs text-slate-500">Chọn đúng kỳ nguồn để xem các JOB đang chờ chi trả của bạn.</p>
                </div>
                <select
                  value={selectedHeldBonusPeriodId ?? ''}
                  onChange={(event) => setSelectedHeldBonusPeriodId(Number(event.target.value))}
                  className="mt-3 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-bold text-slate-800 outline-none focus:border-sky-300 sm:mt-0 sm:w-[320px]"
                  aria-label="Chọn quý có JOB bonus đang giữ"
                >
                  {heldBonusPeriods.map((period) => <option key={period.id} value={period.id}>{period.label}</option>)}
                </select>
              </div>
            )}

            <div className="mobile-held-bonus-notice rounded-2xl border border-sky-100 bg-sky-50/60 px-5 py-4 text-xs leading-5 text-sky-900">
              <b>Quy trình:</b> gửi yêu cầu → kế toán xác minh khách hàng đã thanh toán → kế toán lập lệnh chi trả theo JOB. Gửi yêu cầu không tự động mở bonus và không thay đổi công thức tính thưởng.
            </div>

            {visibleMyHeldBonusJobs.length > 0 ? (
              <div className="grid gap-4">
                {visibleMyHeldBonusJobs.map((job: any) => {
                  const statusInfo: Record<string, { label: string; className: string }> = {
                    NONE: { label: 'Chưa gửi yêu cầu', className: 'bg-slate-100 text-slate-600' },
                    PENDING: { label: 'Chờ kế toán xác minh', className: 'bg-amber-50 text-amber-700' },
                    VERIFIED: { label: 'Đã xác minh · chờ lập lệnh', className: 'bg-sky-50 text-sky-700' },
                    COMMAND_CREATED: { label: 'Đã lập lệnh chi trả', className: 'bg-emerald-50 text-emerald-700' },
                    REJECTED: { label: 'Kế toán chưa xác minh', className: 'bg-rose-50 text-rose-700' },
                  }
                  const statusInfoForJob = statusInfo[job.request_status] || statusInfo.NONE
                  return (
                    <article
                      key={job.job_id}
                      id={`held-bonus-job-${job.job_id}`}
                      className={`mobile-held-bonus-card scroll-mt-28 rounded-2xl border bg-white p-5 shadow-sm transition ${
                        heldBonusNotificationJobId === Number(job.job_id)
                          ? 'border-amber-400 bg-amber-50/30 ring-4 ring-amber-200/70'
                          : 'border-slate-200'
                      }`}
                    >
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2"><h3 className="text-base font-black text-slate-900">{job.job_no}</h3><span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${statusInfoForJob.className}`}>{statusInfoForJob.label}</span></div>
                          <p className="mt-1 text-xs text-slate-500">{job.period_label} · {job.customer || 'Chưa có thông tin khách hàng'}</p>
                        </div>
                        <div className="mobile-held-bonus-total rounded-xl bg-amber-50 px-4 py-3 text-right ring-1 ring-amber-100"><p className="text-[11px] font-bold uppercase tracking-wide text-amber-700">Bonus đang giữ</p><p className="mt-1 text-lg font-black text-amber-800">{formatCurrency(job.total_held || 0)}</p></div>
                      </div>
                      <div className="mobile-held-bonus-metrics mt-4 grid gap-3 text-xs sm:grid-cols-3">
                        <div className="rounded-lg bg-slate-50 p-3"><p className="text-slate-400">Giữ tự động</p><b className="mt-1 block text-amber-700">{formatCurrency(job.payment_held || 0)}</b></div>
                        <div className="rounded-lg bg-slate-50 p-3"><p className="text-slate-400">Giữ thủ công</p><b className="mt-1 block text-rose-700">{formatCurrency(job.manual_held || 0)}</b></div>
                        <div className="rounded-lg bg-slate-50 p-3"><p className="text-slate-400">Payment Received</p><b className={`mt-1 block ${String(job.payment_received).toUpperCase() === 'YES' ? 'text-emerald-700' : 'text-amber-700'}`}>{job.payment_received || 'NO'}</b></div>
                      </div>
                      {job.accounting_note && <p className="mt-3 rounded-lg bg-sky-50 px-3 py-2 text-xs text-sky-800"><b>Phản hồi kế toán:</b> {job.accounting_note}</p>}
                      {job.request_note && job.request_status !== 'NONE' && <p className="mt-3 text-xs text-slate-500"><b>Ghi chú yêu cầu:</b> {job.request_note}</p>}
                      {job.can_request ? (
                        <div className="mobile-held-bonus-request mt-4 flex flex-col gap-2 sm:flex-row">
                          <input value={myHeldBonusNotes[job.job_id] || ''} onChange={(event) => setMyHeldBonusNotes((previous) => ({ ...previous, [job.job_id]: event.target.value }))} placeholder="Ghi chú cho kế toán (không bắt buộc)" className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none focus:border-sky-300" />
                          <button type="button" onClick={() => void requestAccountingForMyHeldBonus(job)} disabled={loading} className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60">Yêu cầu kế toán duyệt</button>
                        </div>
                      ) : job.manual_held > 0 && job.payment_held <= 0 ? <p className="mt-4 text-xs text-slate-500">JOB đang giữ thủ công; kế toán sẽ xử lý theo ghi chú nội bộ.</p> : null}
                    </article>
                  )
                })}
              </div>
            ) : (
              <div className="mobile-held-bonus-empty rounded-[28px] border border-emerald-100 bg-emerald-50/40 p-12 text-center shadow-sm"><p className="text-base font-bold text-emerald-800">{myHeldBonusJobs.length > 0 ? 'Quý đã chọn không có JOB đang giữ bonus' : 'Không có JOB nào đang giữ bonus'}</p><p className="mt-2 text-xs text-emerald-700">Khi có bonus chưa đủ điều kiện chi trả, JOB sẽ tự xuất hiện tại đây.</p></div>
            )}
          </section>
        )}

        {activeTab === 'my-attendance' && (
          <PersonalAttendanceGrid
            rows={myAttendanceData}
            period={myAttendancePeriod}
            onPeriodChange={setMyAttendancePeriod}
            onRefresh={() => void loadMyAttendance()}
          />
        )}

        {currentUser?.role === 'IT_ADMIN' && activeTab === 'it-backups' && (
          <ItOperations apiRequest={apiRequest} view="backups" />
        )}

        {currentUser?.role === 'IT_ADMIN' && activeTab === 'it-audit' && (
          <ItOperations apiRequest={apiRequest} view="audit" />
        )}

        {activeTab === 'my-attendance-details' && (
          <section className="space-y-6 max-w-5xl mx-auto animate-[fadeIn_0.3s_ease-out_forwards]">
            {/* Calendar period header */}
            <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-slate-900 tracking-tight">Nhật ký & Lịch công chi tiết</h2>
                <p className="text-xs text-slate-500 mt-1">Chu kỳ tính công mặc định từ ngày 23 tháng trước đến ngày 22 tháng này.</p>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <MonthYearSelect
                  id="my-attendance-detail-period"
                  value={myAttendancePeriod}
                  onChange={setMyAttendancePeriod}
                  yearLabel="Năm công"
                  monthLabel="Tháng công"
                />
                <button
                  type="button"
                  onClick={loadMyAttendance}
                  disabled={loading}
                  className="bg-slate-900 hover:bg-slate-800 text-white text-sm font-bold px-4 py-2.5 rounded-xl transition cursor-pointer"
                >
                  Làm mới
                </button>
              </div>
            </div>

            {myAttendanceData.length > 0 ? (
              <div className="rounded-[32px] border border-slate-200 bg-white p-6 sm:p-8 shadow-sm">
                {/* Weekday labels */}
                <div className="grid grid-cols-7 gap-2 mb-4 text-center text-xs font-bold uppercase tracking-wider text-slate-400">
                  <div>T2</div>
                  <div>T3</div>
                  <div>T4</div>
                  <div>T5</div>
                  <div>T6</div>
                  <div className="text-indigo-400">T7</div>
                  <div className="text-rose-400">CN</div>
                </div>

                {/* Day blocks grid */}
                <div className="grid grid-cols-7 gap-3">
                  {/* Spacer cells */}
                  {Array.from({ length: (() => {
                    if (myAttendanceData.length === 0) return 0
                    const startDay = new Date(myAttendanceData[0].work_date)
                    const dayOfWeek = startDay.getDay()
                    return dayOfWeek === 0 ? 6 : dayOfWeek - 1
                  })() }).map((_, index) => (
                    <div key={`empty-${index}`} className="aspect-square bg-slate-50/50 rounded-2xl border border-dashed border-slate-150"></div>
                  ))}

                  {/* Day blocks */}
                  {myAttendanceData.map((day) => {
                    const d = new Date(day.work_date)
                    const dayNum = d.getDate()
                    const isWeekend = d.getDay() === 0 || d.getDay() === 6
                    
                    return (
                      <div
                        key={day.work_date}
                        className={`aspect-square border rounded-2xl p-3 shadow-sm hover:shadow-md transition duration-205 flex flex-col justify-between ${
                          day.missing_flag
                            ? 'bg-rose-50/20 border-rose-100'
                            : isWeekend
                              ? 'bg-slate-50/70 border-slate-150'
                              : 'bg-white border-slate-100'
                        }`}
                      >
                        {/* Top: Day and Badge */}
                        <div className="flex justify-between items-center">
                          <span className={`text-sm font-bold ${
                            isWeekend ? 'text-slate-500' : 'text-slate-800'
                          }`}>
                            {dayNum}
                          </span>
                          <span>
                            {getTimesheetSymbolNode(day.final_symbol)}
                          </span>
                        </div>

                        {/* Mid: check-in & out */}
                        <div className="my-2 space-y-1">
                          {day.check_in ? (
                            <div className="flex items-center gap-1.5 text-[11px]">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                              <span className="text-slate-400">In:</span>
                              <strong className="text-slate-700 font-bold font-mono">{day.check_in.slice(0, 5)}</strong>
                            </div>
                          ) : !isWeekend && (
                            <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                              <span className="h-1.5 w-1.5 rounded-full bg-slate-300"></span>
                              <span>Không quẹt</span>
                            </div>
                          )}

                          {day.check_out ? (
                            <div className="flex items-center gap-1.5 text-[11px]">
                              <span className="h-1.5 w-1.5 rounded-full bg-blue-500"></span>
                              <span className="text-slate-400">Out:</span>
                              <strong className="text-slate-700 font-bold font-mono">{day.check_out.slice(0, 5)}</strong>
                            </div>
                          ) : day.check_in && !isWeekend && (
                            <div className="flex items-center gap-1.5 text-[11px] text-rose-450 font-medium">
                              <span className="h-1.5 w-1.5 rounded-full bg-rose-400 animate-pulse"></span>
                              <span>Thiếu Out</span>
                            </div>
                          )}
                        </div>

                        {/* Bot: info & popover trigger */}
                        <div className="flex justify-between items-center text-[11px]">
                          <div>
                            {day.late_minutes > 0 && (
                              <span className="text-amber-600 font-semibold block">Trễ {day.late_minutes}m</span>
                            )}
                            {day.early_minutes > 0 && (
                              <span className="text-rose-600 font-semibold block">Sớm {day.early_minutes}m</span>
                            )}
                          </div>

                          {day.raw_scans && day.raw_scans.length > 0 && (
                            <div className="relative group">
                              <button
                                type="button"
                                className="cursor-pointer text-slate-400 hover:text-slate-750 bg-slate-100 hover:bg-slate-200 px-1.5 py-0.5 rounded text-[11px] font-semibold transition"
                              >
                                •••
                              </button>
                              
                              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-30 w-48 bg-slate-950/95 backdrop-blur-md text-white text-[11px] rounded-xl p-3 shadow-xl pointer-events-none transition-all duration-300 border border-white/10">
                                <p className="font-bold border-b border-white/10 pb-1 mb-1.5 uppercase tracking-wider text-[11px] text-slate-400">Lịch sử quẹt thẻ trong ngày</p>
                                <div className="grid grid-cols-3 gap-1">
                                  {day.raw_scans.map((scan: string, idx: number) => (
                                    <span key={idx} className="bg-white/10 px-1 py-0.5 rounded text-center font-mono text-[11px]">{scan.slice(0, 5)}</span>
                                  ))}
                                </div>
                                {day.is_overridden && (
                                  <p className="mt-2 text-[11px] text-amber-300 leading-normal border-t border-white/10 pt-1">
                                    <AppIcon name="edit" size={13} /> Đã sửa bởi Admin: {day.override_reason}
                                  </p>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* Legend */}
                <div className="mt-6 pt-6 border-t border-slate-150 flex flex-wrap gap-4 text-xs text-slate-500">
                  <div className="flex items-center gap-1.5">
                    <span className="inline-flex items-center justify-center h-5 w-8 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">X</span>
                    <span>Công thường (Đầy đủ)</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="inline-flex items-center justify-center h-5 w-8 rounded text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">P</span>
                    <span>Nghỉ phép hưởng lương</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="inline-flex items-center justify-center h-5 w-8 rounded text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200">Ro</span>
                    <span>Vắng mặt (Không công)</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="inline-flex items-center justify-center h-5 w-8 rounded text-[11px] font-bold bg-purple-50 text-purple-700 border border-purple-200">CT</span>
                    <span>Công tác bên ngoài</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-rose-400 animate-pulse"></span>
                    <span>Thiếu check-out (Lỗi quẹt thẻ)</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-[28px] border border-slate-200 bg-white p-12 text-center shadow-sm">
                <svg viewBox="0 0 24 24" fill="none" className="mx-auto h-12 w-12 text-slate-300" stroke="currentColor" strokeWidth="1.5">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                <h3 className="mt-4 text-sm font-bold text-slate-800">Không tìm thấy lịch chấm công</h3>
                <p className="mt-2 text-xs text-slate-500 max-w-sm mx-auto">
                  Chưa có dữ liệu chấm công cho nhân sự trong tháng {myAttendancePeriod}. Vui lòng thử tải lại hoặc liên hệ quản trị viên để hoàn tất import.
                </p>
              </div>
            )}
          </section>
        )}
        {/* THU NHẬP KHÁC: LÝ DO VÀ CHỨNG TỪ RIÊNG THEO NHÂN VIÊN/THÁNG */}
        {otherIncomeEvidenceEmployeeId !== null && createPortal(
          <div
            className="other-income-evidence-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) closeOtherIncomeEvidence()
            }}
          >
            <section className="other-income-evidence-modal" role="dialog" aria-modal="true" aria-labelledby="other-income-evidence-title">
              <header className="other-income-evidence-modal__header">
                <div className="other-income-evidence-modal__heading">
                  <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Hồ sơ Thu nhập khác</p>
                  <h3 id="other-income-evidence-title" className="mt-1 text-xl font-bold text-slate-950">
                    {otherIncomeEvidenceEmployee?.fullname || 'Nhân viên'} · Tháng {salaryPeriod.slice(5, 7)}/{salaryPeriod.slice(0, 4)}
                  </h3>
                  <p className="mt-2 text-sm text-slate-500">
                    Khoản này được tính vào lương tháng và hoàn toàn không tham gia công thức commission.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeOtherIncomeEvidence}
                  className="other-income-evidence-modal__close app-close-button"
                  aria-label="Đóng"
                >
                  <AppIcon name="close" size={17} />
                </button>
              </header>

              <div className="other-income-evidence-modal__body space-y-5 px-6 py-5">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="other-income-evidence-summary other-income-evidence-summary--amount rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-700">Số tiền TN KHÁC</p>
                    <p className="mt-2 text-2xl font-bold text-emerald-800">{formatCurrency(otherIncomeEvidenceAmount)}</p>
                    <p className="mt-1 text-xs text-emerald-700">Nhập hoặc sửa số này tại cột TN KHÁC trong bảng lương.</p>
                  </div>
                  <div className="other-income-evidence-summary rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Chứng từ hiện tại</p>
                    <p className="mt-2 truncate text-sm font-semibold text-slate-800">
                      {otherIncomeEvidenceInput?.other_income_document_name || 'Chưa có tệp đính kèm'}
                    </p>
                    {otherIncomeEvidenceInput?.other_income_document_uploaded_at && (
                      <p className="mt-1 text-xs text-slate-500">
                        Tải lên: {new Date(otherIncomeEvidenceInput.other_income_document_uploaded_at).toLocaleString('vi-VN')}
                      </p>
                    )}
                  </div>
                </div>

                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-slate-800">
                    Lý do / nguồn của khoản thu nhập {otherIncomeEvidenceAmount > 0 && <span className="text-rose-600">*</span>}
                  </span>
                  <textarea
                    value={otherIncomeEvidenceNote}
                    onChange={(event) => setOtherIncomeEvidenceNote(event.target.value)}
                    disabled={isSalaryLocked}
                    maxLength={2000}
                    rows={4}
                    placeholder="Ví dụ: Hỗ trợ dự án ABC theo quyết định ngày 02/08/2026..."
                    className="w-full resize-y rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-4 focus:ring-slate-100 disabled:bg-slate-100"
                  />
                  <span className="mt-1 block text-right text-xs text-slate-400">{otherIncomeEvidenceNote.length}/2.000</span>
                </label>

                <label className="other-income-evidence-upload block rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 transition hover:border-slate-400">
                  <span className="block text-sm font-semibold text-slate-800">Tải chứng từ liên quan</span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">
                    PDF, Excel, Word, CSV hoặc ảnh; tối đa 15 MB. Tệp được lưu riêng và chỉ tài khoản quản trị lương được truy cập.
                  </span>
                  <input
                    type="file"
                    accept=".pdf,.xlsx,.xls,.csv,.doc,.docx,.png,.jpg,.jpeg"
                    disabled={isSalaryLocked}
                    onChange={(event) => setOtherIncomeEvidenceFile(event.target.files?.[0] || null)}
                    className="other-income-evidence-file-input mt-3 block w-full text-sm text-slate-600 file:mr-4 file:rounded-xl file:border-0 file:bg-slate-200 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-slate-800 hover:file:bg-slate-300"
                  />
                  {otherIncomeEvidenceFile && (
                    <span className="mt-2 block truncate text-xs font-medium text-slate-700">Tệp mới: {otherIncomeEvidenceFile.name}</span>
                  )}
                </label>
              </div>

              <footer className="other-income-evidence-modal__footer">
                <div className="flex flex-wrap gap-2">
                  {otherIncomeEvidenceInput?.other_income_document_name && (
                    <>
                      <button type="button" onClick={downloadOtherIncomeEvidence} className="app-download-button app-modal-button app-modal-button--secondary h-10 rounded-xl px-4 text-sm font-semibold transition">
                        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v12m0 0 4-4m-4 4-4-4M5 19h14" />
                        </svg>
                        Tải chứng từ
                      </button>
                      <button type="button" onClick={deleteOtherIncomeEvidence} disabled={isSalaryLocked || isSalaryConfirmed} className="app-delete-button h-10 rounded-xl border border-rose-200 bg-white px-4 text-sm font-semibold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50">
                        Xóa tệp
                      </button>
                    </>
                  )}
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={closeOtherIncomeEvidence} className="app-modal-button app-modal-button--secondary h-10 rounded-xl border border-slate-300 bg-white px-5 text-sm font-semibold text-slate-800 transition hover:bg-slate-100">
                    Hủy
                  </button>
                  <button
                    type="button"
                    onClick={saveOtherIncomeEvidence}
                    disabled={isSavingOtherIncomeEvidence || isSalaryLocked}
                    className="app-modal-button app-modal-button--primary h-10 rounded-xl bg-slate-800 px-5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 4h12l2 2v14H5V4Zm3 0v6h8V4M8 20v-6h8v6" />
                    </svg>
                    {isSavingOtherIncomeEvidence ? 'Đang lưu...' : 'Lưu hồ sơ'}
                  </button>
                </div>
              </footer>
            </section>
          </div>,
          document.body,
        )}

        {(isBusinessAdminRole(currentUser?.role) || currentUser?.role === 'HR_ADMIN') && activeTab === 'onboarding' && (
          <OnboardingAdmin apiRequest={apiRequest} onNotice={setMessage} />
        )}

        {(isBusinessAdminRole(currentUser?.role) || currentUser?.role === 'HR_ADMIN') && activeTab === 'offboarding' && (
          <OffboardingAdmin apiRequest={apiRequest} onNotice={setMessage} />
        )}

        {salaryPolicyModalOpen && createPortal(
          <div
            className="app-modal-overlay fixed inset-0 z-[140] flex items-center justify-center p-4"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !savingSalaryPolicy) setSalaryPolicyModalOpen(false)
            }}
          >
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="salary-policy-modal-title"
              className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white/95 shadow-2xl ring-1 ring-white/70"
            >
              <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-6 py-5">
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Thiết lập có phiên bản</p>
                  <h3 id="salary-policy-modal-title" className="mt-1 text-xl font-bold text-slate-950">Chính sách lương, bảo hiểm và thuế</h3>
                  <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
                    Mỗi lần lưu sẽ tạo một phiên bản mới. Phiếu lương đã phát hành giữ nguyên số liệu cũ; chỉ các tháng chưa phát hành từ ngày hiệu lực trở đi mới dùng chính sách này.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSalaryPolicyModalOpen(false)}
                  disabled={savingSalaryPolicy}
                  aria-label="Đóng cấu hình chính sách lương"
                  className="app-close-button"
                >
                  <AppIcon name="close" size={17} />
                </button>
              </header>

              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
                <div className="grid gap-4 md:grid-cols-12">
                  <label className="block md:col-span-5">
                    <span className="mb-1.5 block text-sm font-semibold text-slate-700">Tên phiên bản</span>
                    <input value={salaryPolicyForm.name} onChange={(event) => setSalaryPolicyForm((current) => ({ ...current, name: event.target.value }))} maxLength={180} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                  </label>
                  <div className="block md:col-span-3">
                    <MonthYearSelect
                      id="salary-policy-effective-period"
                      value={salaryPolicyForm.effective_from.slice(0, 7)}
                      onChange={(period) => setSalaryPolicyForm((current) => ({ ...current, effective_from: `${period}-01` }))}
                      yearLabel="Năm hiệu lực"
                      monthLabel="Tháng hiệu lực"
                    />
                  </div>
                  <label className="block md:col-span-2">
                    <span className="mb-1.5 block text-sm font-semibold text-slate-700">Vùng BHTN mặc định</span>
                    <select value={salaryPolicyForm.default_region} onChange={(event) => setSalaryPolicyForm((current) => ({ ...current, default_region: event.target.value }))} className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50">
                      <option value="I">Vùng I</option><option value="II">Vùng II</option><option value="III">Vùng III</option><option value="IV">Vùng IV</option>
                    </select>
                  </label>
                  <label className="block md:col-span-2">
                    <span className="mb-1.5 block text-sm font-semibold text-slate-700">Hệ số trần BHTN</span>
                    <input type="number" min="0" step="1" value={salaryPolicyForm.unemployment_cap_multiplier} onChange={(event) => updateSalaryPolicyNumber('unemployment_cap_multiplier', event.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                  </label>
                </div>

                <section className="mt-6 rounded-2xl border border-slate-200 p-4">
                  <h4 className="text-base font-bold text-slate-900">Mức lương làm căn cứ</h4>
                  <p className="mt-1 text-xs text-slate-500">Các mức này dùng cho trần đóng bảo hiểm và giới hạn BHTN theo vùng.</p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {([
                      ['common_minimum_wage', 'Lương tối thiểu chung'],
                      ['social_health_salary_cap', 'Trần lương đóng BHXH, BHYT'],
                      ['regional_minimum_wage_i', 'Lương tối thiểu vùng I'],
                      ['regional_minimum_wage_ii', 'Lương tối thiểu vùng II'],
                      ['regional_minimum_wage_iii', 'Lương tối thiểu vùng III'],
                      ['regional_minimum_wage_iv', 'Lương tối thiểu vùng IV'],
                    ] as Array<[SalaryPolicyVndField, string]>).map(([field, label]) => (
                      <label key={field} className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">{label} (VND)</span>
                        <VndInput value={salaryPolicyForm[field]} onValueChange={(value) => updateSalaryPolicyVnd(field, String(value))} onEmpty={() => updateSalaryPolicyVnd(field, '')} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm tabular-nums outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                      </label>
                    ))}
                  </div>
                </section>

                <section className="mt-4 rounded-2xl border border-slate-200 p-4">
                  <h4 className="text-base font-bold text-slate-900">Tỷ lệ bảo hiểm và công đoàn</h4>
                  <p className="mt-1 text-xs text-slate-500">Nhập theo phần trăm. Ví dụ 8 nghĩa là 8%.</p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {([
                      ['social_employee_rate', 'BHXH người lao động'],
                      ['health_employee_rate', 'BHYT người lao động'],
                      ['unemployment_employee_rate', 'BHTN người lao động'],
                      ['social_employer_rate', 'BHXH doanh nghiệp'],
                      ['health_employer_rate', 'BHYT doanh nghiệp'],
                      ['unemployment_employer_rate', 'BHTN doanh nghiệp'],
                      ['union_fund_employer_rate', 'KPCĐ doanh nghiệp'],
                      ['union_employee_rate', 'Đoàn phí người lao động'],
                    ] as Array<[keyof SalaryPolicy, string]>).map(([field, label]) => (
                      <label key={field} className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">{label} (%)</span>
                        <input type="number" min="0" max="100" step="0.1" value={Number(salaryPolicyForm[field] || 0) * 100} onChange={(event) => setSalaryPolicyForm((current) => ({ ...current, [field]: Math.max(0, Number(event.target.value || 0)) / 100 }))} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                      </label>
                    ))}
                    <label className="block">
                      <span className="mb-1.5 block text-xs font-semibold text-slate-600">Trần đoàn phí (VND)</span>
                      <VndInput value={salaryPolicyForm.union_employee_cap} onValueChange={(value) => updateSalaryPolicyVnd('union_employee_cap', String(value))} onEmpty={() => updateSalaryPolicyVnd('union_employee_cap', '')} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm tabular-nums outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                    </label>
                  </div>
                </section>

                <section className="mt-4 rounded-2xl border border-slate-200 p-4">
                  <h4 className="text-base font-bold text-slate-900">Giảm trừ và thuế TNCN</h4>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {([
                      ['personal_deduction', 'Giảm trừ bản thân (VND)'],
                      ['dependent_deduction', 'Giảm trừ người phụ thuộc (VND)'],
                      ['probation_withholding_threshold', 'Ngưỡng khấu trừ thử việc (VND)'],
                    ] as Array<[SalaryPolicyVndField, string]>).map(([field, label]) => (
                      <label key={field} className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">{label}</span>
                        <VndInput value={salaryPolicyForm[field]} onValueChange={(value) => updateSalaryPolicyVnd(field, String(value))} onEmpty={() => updateSalaryPolicyVnd(field, '')} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm tabular-nums outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                      </label>
                    ))}
                    <label className="block">
                      <span className="mb-1.5 block text-xs font-semibold text-slate-600">Khấu trừ thử việc (%)</span>
                      <input type="number" min="0" max="100" step="0.1" value={salaryPolicyForm.probation_withholding_rate * 100} onChange={(event) => setSalaryPolicyForm((current) => ({ ...current, probation_withholding_rate: Math.max(0, Number(event.target.value || 0)) / 100 }))} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                    </label>
                  </div>
                  <div className="mt-5 overflow-x-auto rounded-xl border border-slate-200">
                    <table className="min-w-[680px] w-full text-sm">
                      <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-3 py-2">Bậc</th><th className="px-3 py-2">Đến mức (VND)</th><th className="px-3 py-2">Thuế suất (%)</th><th className="px-3 py-2">Trừ nhanh (VND)</th></tr></thead>
                      <tbody>
                        {salaryPolicyForm.pit_brackets.map((bracket, index) => (
                          <tr key={index} className="border-t border-slate-100">
                            <td className="px-3 py-2 font-semibold text-slate-700">{index + 1}</td>
                            <td className="px-3 py-2"><VndInput placeholder={index === salaryPolicyForm.pit_brackets.length - 1 ? 'Không giới hạn' : ''} value={bracket.up_to} onValueChange={(value) => updateSalaryPolicyBracket(index, 'up_to', String(value))} onEmpty={() => updateSalaryPolicyBracket(index, 'up_to', '')} className="w-full rounded-lg border border-slate-300 px-2.5 py-2 tabular-nums outline-none focus:border-[#163b66]" /></td>
                            <td className="px-3 py-2"><input type="number" min="0" max="100" step="0.1" value={bracket.rate * 100} onChange={(event) => setSalaryPolicyForm((current) => ({ ...current, pit_brackets: current.pit_brackets.map((item, itemIndex) => itemIndex === index ? { ...item, rate: Math.max(0, Number(event.target.value || 0)) / 100 } : item) }))} className="w-full rounded-lg border border-slate-300 px-2.5 py-2 outline-none focus:border-[#163b66]" /></td>
                            <td className="px-3 py-2"><VndInput value={bracket.deduction} onValueChange={(value) => updateSalaryPolicyBracket(index, 'deduction', String(value))} onEmpty={() => updateSalaryPolicyBracket(index, 'deduction', '')} className="w-full rounded-lg border border-slate-300 px-2.5 py-2 tabular-nums outline-none focus:border-[#163b66]" /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="mt-4 grid gap-4 lg:grid-cols-2">
                  <label className="block rounded-2xl border border-slate-200 p-4">
                    <span className="mb-1.5 block text-sm font-semibold text-slate-700">Căn cứ / văn bản áp dụng</span>
                    <input value={salaryPolicyForm.legal_basis} onChange={(event) => setSalaryPolicyForm((current) => ({ ...current, legal_basis: event.target.value }))} maxLength={500} placeholder="Ví dụ: Nghị định, quyết định hoặc thông báo nội bộ..." className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                  </label>
                  <label className="block rounded-2xl border border-slate-200 p-4">
                    <span className="mb-1.5 block text-sm font-semibold text-slate-700">Ghi chú thay đổi</span>
                    <textarea value={salaryPolicyForm.note} onChange={(event) => setSalaryPolicyForm((current) => ({ ...current, note: event.target.value }))} maxLength={2000} rows={2} placeholder="Nêu lý do thay đổi để kế toán đối chiếu về sau..." className="w-full resize-y rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none transition focus:border-[#163b66] focus:ring-4 focus:ring-blue-50" />
                  </label>
                </section>

                <section className="mt-5 rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
                  <h4 className="text-sm font-bold text-slate-900">Lịch sử phiên bản</h4>
                  <div className="mt-3 max-h-36 overflow-y-auto pr-1">
                    {salaryPolicyHistory.length === 0 ? <p className="text-sm text-slate-500">Đang tải lịch sử...</p> : salaryPolicyHistory.map((item) => (
                      <div key={item.id || item.version_code} className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-100 py-2 text-sm last:border-b-0">
                        <span className="font-semibold text-slate-800">{item.version_code || 'Chưa có mã'} · {item.name || 'Chính sách lương'}</span>
                        <span className="text-slate-600">Hiệu lực: {item.effective_from ? new Date(`${item.effective_from}T00:00:00`).toLocaleDateString('vi-VN') : '—'}</span>
                      </div>
                    ))}
                  </div>
                </section>
              </div>

              <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
                <p className="text-xs leading-5 text-slate-500">Không ảnh hưởng công thức bonus/commission. Khi cần thay đổi, luôn tạo phiên bản mới thay vì sửa lịch sử.</p>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setSalaryPolicyModalOpen(false)} disabled={savingSalaryPolicy} className="h-10 rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:opacity-50">Hủy</button>
                  <button type="button" onClick={saveSalaryPolicy} disabled={savingSalaryPolicy || !salaryPolicyForm.name.trim() || !salaryPolicyForm.effective_from} className="h-10 rounded-xl bg-[#163b66] px-5 text-sm font-semibold text-white transition hover:bg-[#0f2a4a] disabled:cursor-not-allowed disabled:opacity-50">{savingSalaryPolicy ? 'Đang lưu...' : 'Lưu phiên bản mới'}</button>
                </div>
              </footer>
            </section>
          </div>,
          document.body,
        )}

        {/* IMAGE PREVIEW MODAL */}
        {previewUrl && (
          <div className="app-modal-overlay fixed inset-0 z-[100] flex items-center justify-center p-4 animate-[fadeIn_0.2s_ease-out_forwards]" onClick={() => setPreviewUrl(null)}>
            <div className="relative max-w-5xl w-full flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                aria-label="Đóng xem trước tài liệu"
                className="app-close-button fixed top-4 right-4 z-[110]"
                onClick={() => setPreviewUrl(null)}
                title="Đóng"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              {previewUrl.toLowerCase().endsWith('.pdf') ? (
                <iframe src={previewUrl} className="w-full h-[80vh] bg-white rounded-xl shadow-2xl" title="PDF Preview" />
              ) : (
                <img src={previewUrl} alt="Preview" className="max-w-full max-h-[85vh] object-contain rounded-xl shadow-2xl" />
              )}
            </div>
          </div>
        )}
      </div>

    </EnterpriseShell>
    </Suspense>
  )
}

export default App
