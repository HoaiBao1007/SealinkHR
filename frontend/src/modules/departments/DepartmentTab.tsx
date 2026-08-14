import { useState, useEffect, useMemo, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useConfirmDialog } from '../../shared/ui/ConfirmDialog'
import { OrganizationChart } from './OrganizationChart'

function DepartmentModalPortal({ children }: { children: ReactNode }) {
  return createPortal(
    <div className="department-modal-backdrop">
      {children}
    </div>,
    document.body,
  )
}

type EmployeeMinimal = {
  id: number
  full_name: string
  notion_name: string | null
  position: string | null
}

type Department = {
  id: number
  name: string
  manager_id: number | null
  parent_id: number | null
  sort_order: number
  manager: EmployeeMinimal | null
  employees: EmployeeMinimal[]
}

type Employee = {
  id: number
  full_name: string
  notion_name: string | null
  department_id: number | null
}

type OrganizationUnit = {
  id: number
  code: string
  name: string
  unit_type: string
  parent_id: number | null
  linked_department_id: number | null
  color: string | null
  sort_order: number
}

type DepartmentTreeNode = {
  department: Department
  unit: OrganizationUnit | null
  children: DepartmentTreeNode[]
  directEmployeeCount: number
  branchEmployeeCount: number
}

type ApiRequest = (path: string, init?: RequestInit) => Promise<Response>

type BonusRule = { min: number, max: number, rate: number }

const FIXED_NON_SALES_BONUS_RULES: BonusRule[] = [
  { min: 0, max: 999, rate: 0.20 },
]

function isSalesBonusDepartment(name?: string | null) {
  const normalized = String(name || '')
    .toUpperCase()
    .replace(/[_-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return normalized === 'SALE LOCAL' || normalized === 'SALE OVERSEA'
}

export function DepartmentTab({
  apiRequest,
  token,
  onOpenEmployee,
  organizationRefreshKey,
  initialView = 'list',
  onViewChange,
  departmentApiPath = '/api/departments',
  employeeApiPath = '/api/employees',
  departmentUpdateMethod = 'PUT',
  allowBonusConfig = true,
  allowDelete = true,
}: {
  apiRequest: ApiRequest
  token: string
  onOpenEmployee?: (employeeId: number) => void
  organizationRefreshKey?: string
  initialView?: 'list' | 'chart'
  onViewChange?: (view: 'list' | 'chart') => void
  departmentApiPath?: string
  employeeApiPath?: string
  departmentUpdateMethod?: 'PUT' | 'PATCH'
  allowBonusConfig?: boolean
  allowDelete?: boolean
}) {
  const confirm = useConfirmDialog()
  const [departments, setDepartments] = useState<Department[]>([])
  const [allEmployees, setAllEmployees] = useState<Employee[]>([])
  const [organizationUnits, setOrganizationUnits] = useState<OrganizationUnit[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'list' | 'chart'>(initialView)

  // Modals state
  const [showEmployeeListModal, setShowEmployeeListModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [showManageEmployeesModal, setShowManageEmployeesModal] = useState(false)
  const [showBonusConfigModal, setShowBonusConfigModal] = useState(false)
  const [currentDept, setCurrentDept] = useState<Department | null>(null)
  
  // Edit Form state
  const [deptName, setDeptName] = useState('')
  const [managerId, setManagerId] = useState<number | ''>('')
  
  // Manage Employees state
  const [selectedEmployeeIds, setSelectedEmployeeIds] = useState<number[]>([])
  
  // Bonus Config state
  const [bonusPeriod, setBonusPeriod] = useState('')
  const [endPeriod, setEndPeriod] = useState('')
  const [isCustomPeriod, setIsCustomPeriod] = useState(false)
  const [bonusRules, setBonusRules] = useState<BonusRule[]>([])
  
  const [collapsedBranchIds, setCollapsedBranchIds] = useState<number[]>([])
  const usesProgressiveBonus = currentDept ? isSalesBonusDepartment(currentDept.name) : true

  const loadData = async () => {
    try {
      setError(null)
      const [departmentResponse, employeeResponse, organizationResponse] = await Promise.all([
        apiRequest(departmentApiPath),
        apiRequest(employeeApiPath),
        apiRequest('/api/organization/chart'),
      ])
      if (!departmentResponse.ok) {
        const detail = await departmentResponse.json().catch(() => null)
        throw new Error(detail?.detail || 'Không thể tải danh sách phòng ban.')
      }
      if (!employeeResponse.ok) {
        const detail = await employeeResponse.json().catch(() => null)
        throw new Error(detail?.detail || 'Không thể tải danh sách nhân viên.')
      }

      const departmentRows = await departmentResponse.json()
      const employeeRows = await employeeResponse.json() as Employee[]
      const normalizedDepartments = departmentRows.map((department: any) => ({
        ...department,
        manager: department.manager
          ?? employeeRows.find((employee) => employee.id === department.manager_id)
          ?? null,
        employees: Array.isArray(department.employees)
          ? department.employees
          : employeeRows.filter((employee) => employee.department_id === department.id),
      }))
      setDepartments(normalizedDepartments)
      setAllEmployees(employeeRows)
      if (organizationResponse.ok) {
        const organizationPayload = await organizationResponse.json()
        setOrganizationUnits(Array.isArray(organizationPayload?.units) ? organizationPayload.units : [])
      } else {
        setOrganizationUnits([])
      }
    } catch (err: any) {
      setError(err.message)
    }
  }

  useEffect(() => {
    setLoading(true)
    void loadData().finally(() => setLoading(false))
  }, [token, departmentApiPath, employeeApiPath, organizationRefreshKey])

  useEffect(() => {
    setViewMode(initialView)
  }, [initialView])

  const changeViewMode = (view: 'list' | 'chart') => {
    setViewMode(view)
    onViewChange?.(view)
  }

  const handleSaveDepartment = async () => {
    if (!deptName.trim()) return
    try {
      const payload = {
        name: deptName,
        manager_id: managerId === '' ? null : Number(managerId),
        parent_id: currentDept?.parent_id ?? null,
        sort_order: currentDept?.sort_order ?? departments.length,
      }
      
      let url = departmentApiPath
      let method = 'POST'
      if (currentDept && currentDept.id) {
        url = `${departmentApiPath}/${currentDept.id}`
        method = departmentUpdateMethod
      }

      const res = await apiRequest(url, {
        method,
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      })

      if (!res.ok) {
        const errorData = await res.json()
        throw new Error(errorData.detail || 'Failed to save department')
      }

      await loadData()
      setShowEditModal(false)
      setCurrentDept(null)
    } catch (err: any) {
      alert(err.message)
    }
  }

  const handleSaveEmployees = async () => {
    if (!currentDept) return
    try {
      const res = await apiRequest(`${departmentApiPath}/${currentDept.id}/employees`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ employee_ids: selectedEmployeeIds })
      })

      if (!res.ok) throw new Error('Failed to assign employees')
      await loadData()
      setShowManageEmployeesModal(false)
    } catch (err: any) {
      alert(err.message)
    }
  }

  const openEditModal = (dept?: Department) => {
    if (dept) {
      setCurrentDept(dept)
      setDeptName(dept.name)
      setManagerId(dept.manager_id || '')
    } else {
      setCurrentDept(null)
      setDeptName('')
      setManagerId('')
    }
    setShowEditModal(true)
  }

  const openManageEmployeesModal = (dept: Department) => {
    setCurrentDept(dept)
    setSelectedEmployeeIds(dept.employees.map(e => e.id))
    setShowManageEmployeesModal(true)
  }

  const openEmployeeListModal = (dept: Department) => {
    setCurrentDept(dept)
    setShowEmployeeListModal(true)
  }

  const fetchBonusConfig = async (deptId: number, period: string) => {
    try {
      const res = await apiRequest(`/api/departments/${deptId}/bonus-config?period=${period}`)
      if (!res.ok) throw new Error('Không thể tải cấu hình bonus')
      const data = await res.json()
      setBonusRules(data.rules)
      if (data.end_period) {
        setIsCustomPeriod(true)
        setEndPeriod(data.end_period)
      } else {
        setIsCustomPeriod(false)
        setEndPeriod('')
      }
    } catch (err: any) {
      alert(err.message)
    }
  }

  const openBonusConfigModal = (dept: Department) => {
    setCurrentDept(dept)
    const today = new Date()
    const currentMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
    setBonusPeriod(currentMonth)
    setIsCustomPeriod(false)
    setEndPeriod('')
    fetchBonusConfig(dept.id, currentMonth)
    setShowBonusConfigModal(true)
  }

  const handleSaveBonusConfig = async () => {
    if (!currentDept) return
    try {
      const res = await apiRequest(`/api/departments/${currentDept.id}/bonus-config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          period: bonusPeriod,
          end_period: isCustomPeriod && endPeriod ? endPeriod : null,
          rules: usesProgressiveBonus ? bonusRules : FIXED_NON_SALES_BONUS_RULES
        })
      })
      if (!res.ok) throw new Error('Không thể lưu cấu hình bonus')
      alert('Đã lưu cấu hình bonus thành công cho tháng ' + bonusPeriod)
      setShowBonusConfigModal(false)
    } catch (err: any) {
      alert(err.message)
    }
  }

  const handleDelete = async (deptId: number) => {
    if (!await confirm({ title: 'Xóa phòng ban', message: 'Bạn có chắc chắn muốn xóa phòng ban này?', confirmLabel: 'Xóa', tone: 'danger' })) return
    try {
      const res = await apiRequest(`/api/departments/${deptId}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error('Failed to delete department')
      await loadData()
    } catch (err: any) {
      alert(err.message)
    }
  }

  const departmentTree = useMemo(() => {
    const departmentsById = new Map(departments.map((department) => [department.id, department]))
    const unitsById = new Map(organizationUnits.map((unit) => [unit.id, unit]))
    const unitByDepartmentId = new Map(
      organizationUnits
        .filter((unit) => unit.linked_department_id != null)
        .map((unit) => [unit.linked_department_id as number, unit]),
    )

    const findOrganizationParentDepartmentId = (unit: OrganizationUnit | undefined) => {
      const visited = new Set<number>()
      let parentUnitId = unit?.parent_id ?? null
      while (parentUnitId != null && !visited.has(parentUnitId)) {
        visited.add(parentUnitId)
        const parentUnit = unitsById.get(parentUnitId)
        if (!parentUnit) return null
        if (
          parentUnit.linked_department_id != null
          && departmentsById.has(parentUnit.linked_department_id)
        ) {
          return parentUnit.linked_department_id
        }
        parentUnitId = parentUnit.parent_id
      }
      return null
    }

    const parentByDepartmentId = new Map<number, number | null>()
    departments.forEach((department) => {
      const organizationParentId = findOrganizationParentDepartmentId(
        unitByDepartmentId.get(department.id),
      )
      const fallbackParentId =
        department.parent_id != null && departmentsById.has(department.parent_id)
          ? department.parent_id
          : null
      const parentId = organizationParentId ?? fallbackParentId
      parentByDepartmentId.set(
        department.id,
        parentId !== department.id ? parentId : null,
      )
    })

    const childrenByDepartmentId = new Map<number, Department[]>()
    const rootDepartments: Department[] = []
    departments.forEach((department) => {
      const parentId = parentByDepartmentId.get(department.id) ?? null
      if (parentId == null) {
        rootDepartments.push(department)
        return
      }
      const children = childrenByDepartmentId.get(parentId) ?? []
      children.push(department)
      childrenByDepartmentId.set(parentId, children)
    })

    const sortDepartments = (rows: Department[]) => rows.sort((left, right) => {
      const leftUnit = unitByDepartmentId.get(left.id)
      const rightUnit = unitByDepartmentId.get(right.id)
      return (
        (leftUnit?.sort_order ?? left.sort_order ?? 9999)
        - (rightUnit?.sort_order ?? right.sort_order ?? 9999)
        || left.name.localeCompare(right.name, 'vi')
      )
    })

    const buildNode = (department: Department, path: Set<number>): DepartmentTreeNode => {
      const nextPath = new Set(path)
      nextPath.add(department.id)
      const children = sortDepartments(childrenByDepartmentId.get(department.id) ?? [])
        .filter((child) => !nextPath.has(child.id))
        .map((child) => buildNode(child, nextPath))
      const directEmployeeCount = department.employees.length
      return {
        department,
        unit: unitByDepartmentId.get(department.id) ?? null,
        children,
        directEmployeeCount,
        branchEmployeeCount:
          directEmployeeCount
          + children.reduce((total, child) => total + child.branchEmployeeCount, 0),
      }
    }

    return sortDepartments(rootDepartments).map((department) => buildNode(department, new Set()))
  }, [departments, organizationUnits])

  const treeDepartmentCount = departments.length
  const treeEmployeeCount = departments.reduce(
    (total, department) => total + department.employees.length,
    0,
  )

  const toggleBranch = (departmentId: number) => {
    setCollapsedBranchIds((current) => (
      current.includes(departmentId)
        ? current.filter((id) => id !== departmentId)
        : [...current, departmentId]
    ))
  }

  const renderDepartmentNode = (node: DepartmentTreeNode, level = 0): ReactNode => {
    const { department, unit, children } = node
    const isBranchCollapsed = collapsedBranchIds.includes(department.id)
    const accentColor = unit?.color || (level === 0 ? '#1d4f7d' : '#64748b')
    const levelLabel = level === 0 ? 'Phòng ban chính' : level === 1 ? 'Nhóm trực thuộc' : `Nhánh cấp ${level + 1}`
    const compactActionClass = 'department-action-button'

    return (
      <div key={department.id} className={level > 0 ? 'relative ml-5 border-l border-slate-200 pl-5 sm:ml-8 sm:pl-7' : ''}>
        {level > 0 && (
          <span className="absolute -left-px top-8 h-px w-5 bg-slate-200 sm:w-7" aria-hidden="true" />
        )}
        <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:border-slate-300 hover:shadow-md">
          <div className="grid gap-3 p-3 sm:p-4 xl:grid-cols-[minmax(280px,360px)_minmax(500px,1fr)_auto] xl:items-center">
            <div className="flex min-w-0 items-start gap-3">
              {children.length > 0 ? (
                <button
                  type="button"
                  onClick={() => toggleBranch(department.id)}
                  className="department-tree-toggle mt-0.5"
                  aria-label={isBranchCollapsed ? `Mở nhánh ${department.name}` : `Thu gọn nhánh ${department.name}`}
                  aria-expanded={!isBranchCollapsed}
                >
                  <svg className={`h-4 w-4 transition-transform ${isBranchCollapsed ? '' : 'rotate-90'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              ) : (
                <span className="mt-1 h-7 w-2 shrink-0 rounded-full" style={{ backgroundColor: accentColor }} aria-hidden="true" />
              )}

              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-bold text-slate-900">{department.name}</h3>
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                    {levelLabel}
                  </span>
                  {!unit && (
                    <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-bold text-amber-700 ring-1 ring-amber-200">
                      Chưa gắn sơ đồ
                    </span>
                  )}
                </div>
                {unit && unit.name !== department.name && (
                  <p className="mt-1 text-xs font-medium text-slate-500">Trên sơ đồ: {unit.name}</p>
                )}
              </div>
            </div>

            <dl className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-[120px_120px_minmax(230px,1fr)]">
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Nhân sự trực tiếp</dt>
                <dd className="mt-0.5 text-sm font-bold text-slate-800">{node.directEmployeeCount}</dd>
              </div>
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Toàn nhánh</dt>
                <dd className="mt-0.5 text-sm font-bold text-slate-800">{node.branchEmployeeCount}</dd>
              </div>
              <div className="col-span-2 min-w-0 rounded-xl bg-slate-50 px-3 py-2 sm:col-span-1">
                <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Quản lý</dt>
                <dd className="mt-0.5 whitespace-normal break-words text-sm font-bold leading-5 text-slate-800" title={department.manager?.full_name || 'Chưa thiết lập'}>
                  {department.manager?.full_name || 'Chưa thiết lập'}
                </dd>
              </div>
            </dl>

            <div className="flex flex-wrap items-center gap-1.5 xl:max-w-[360px] xl:justify-end">
              <button
                type="button"
                onClick={() => openEmployeeListModal(department)}
                className={compactActionClass}
                title="Xem danh sách nhân sự"
              >
                <span aria-hidden="true">👥</span>
                <span>Xem nhân sự</span>
              </button>
              <button
                type="button"
                onClick={() => openEditModal(department)}
                className={compactActionClass}
                title="Chỉnh sửa thông tin phòng ban"
              >
                <span aria-hidden="true">✎</span>
                <span>Chỉnh sửa</span>
              </button>
              <button
                type="button"
                onClick={() => openManageEmployeesModal(department)}
                className={compactActionClass}
                title="Gán hoặc bỏ nhân sự khỏi phòng ban"
              >
                <span aria-hidden="true">⚙</span>
                <span>Nhân sự</span>
              </button>
              {allowBonusConfig && (
                <button
                  type="button"
                  onClick={() => openBonusConfigModal(department)}
                  className={compactActionClass}
                  title="Mở cấu hình Bonus"
                >
                  <span aria-hidden="true">%</span>
                  <span>Bonus</span>
                </button>
              )}
              {allowDelete && (
                <button
                  type="button"
                  onClick={() => handleDelete(department.id)}
                  className={`${compactActionClass} department-action-danger`}
                  title="Xóa phòng ban"
                  aria-label={`Xóa phòng ban ${department.name}`}
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </article>

        {!isBranchCollapsed && children.length > 0 && (
          <div className="mt-3 space-y-3">
            {children.map((child) => renderDepartmentNode(child, level + 1))}
          </div>
        )}
      </div>
    )
  }

  if (loading && viewMode === 'list') return <div className="p-8 text-center">Đang tải...</div>

  return (
    <div className="space-y-6">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: '#0f172a' }}>Quản lý Phòng ban</h2>
          <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>Cơ cấu tổ chức và phân bổ nhân sự</p>
        </div>
        {viewMode === 'list' && (
          <button 
            onClick={() => openEditModal()}
            className="add-dept-btn"
          >
            + Thêm phòng ban
          </button>
        )}
      </div>

      <div
        role="tablist"
        aria-label="Chế độ xem phòng ban"
        className="grid grid-cols-2 gap-2 rounded-2xl border border-slate-200 bg-slate-100 p-1.5"
      >
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'list'}
          onClick={() => changeViewMode('list')}
          className={`min-h-11 rounded-xl px-4 text-sm font-bold transition ${
            viewMode === 'list'
              ? 'border border-slate-200 bg-white text-slate-900 shadow-sm'
              : 'border border-transparent bg-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          Danh sách phòng ban
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'chart'}
          onClick={() => changeViewMode('chart')}
          className={`min-h-11 rounded-xl px-4 text-sm font-bold transition ${
            viewMode === 'chart'
              ? 'border border-slate-200 bg-white text-slate-900 shadow-sm'
              : 'border border-transparent bg-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          Sơ đồ tổ chức
        </button>
      </div>

      {viewMode === 'chart' ? (
        <OrganizationChart
          apiRequest={apiRequest}
          token={token}
          onOpenEmployee={onOpenEmployee}
          refreshKey={organizationRefreshKey}
        />
      ) : (
        <>
      {error && <div className="rounded-xl bg-red-50 p-4 text-red-600 border border-red-200">{error}</div>}

      <section className="overflow-hidden rounded-[24px] border border-slate-200 bg-slate-50 shadow-sm">
        <header className="border-b border-slate-200 bg-slate-900 px-5 py-4 text-white sm:px-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-slate-300">Cơ cấu phòng ban</p>
              <h3 className="mt-1 text-lg font-bold">SEALINK INTERNATIONAL</h3>
              <p className="mt-1 text-xs text-slate-300">Thứ tự và nhánh trực thuộc được đồng bộ từ Sơ đồ tổ chức.</p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-white/10 px-3 py-1.5 font-semibold">{treeDepartmentCount} phòng ban</span>
              <span className="rounded-full bg-white/10 px-3 py-1.5 font-semibold">{treeEmployeeCount} nhân sự</span>
            </div>
          </div>
        </header>

        <div className="space-y-4 p-4 sm:p-6">
          {departmentTree.length > 0 ? (
            departmentTree.map((node) => renderDepartmentNode(node))
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
              <p className="text-sm font-semibold text-slate-700">Chưa có phòng ban nào.</p>
              <p className="mt-1 text-xs text-slate-500">Hãy thêm phòng ban để bắt đầu xây dựng cơ cấu tổ chức.</p>
            </div>
          )}
        </div>
      </section>

      {/* Employee List Modal */}
      {showEmployeeListModal && currentDept && (
        <DepartmentModalPortal>
          <div className="department-modal-surface flex max-h-[82vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
              <div className="min-w-0">
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">Danh sách nhân sự</p>
                <h3 className="mt-1 truncate text-lg font-bold text-slate-900">{currentDept.name}</h3>
                <p className="mt-1 text-sm text-slate-500">
                  {currentDept.employees.length} nhân sự trực tiếp · Quản lý: {currentDept.manager?.full_name || 'Chưa thiết lập'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowEmployeeListModal(false)}
                className="department-modal-icon-button app-close-button"
                aria-label="Đóng danh sách nhân sự"
                title="Đóng"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </header>

            <div className="flex-1 overflow-y-auto bg-slate-50/70 p-4 sm:p-5">
              {currentDept.employees.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center">
                  <p className="text-sm font-semibold text-slate-700">Phòng ban này chưa có nhân sự.</p>
                  <p className="mt-1 text-xs text-slate-500">Chọn “Quản lý nhân sự” để thêm nhân viên vào phòng ban.</p>
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {currentDept.employees.map((employee) => (
                    <button
                      key={employee.id}
                      type="button"
                      onClick={() => {
                        setShowEmployeeListModal(false)
                        onOpenEmployee?.(employee.id)
                      }}
                      className="department-employee-card"
                      disabled={!onOpenEmployee}
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-600">
                        {employee.full_name.trim().charAt(0).toUpperCase() || 'NV'}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold text-slate-800">{employee.full_name}</span>
                        <span className="block truncate text-xs text-slate-500">
                          {[employee.position, employee.notion_name].filter(Boolean).join(' · ') || 'Chưa bổ sung chức vụ'}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <footer className="flex flex-wrap justify-end gap-2 border-t border-slate-200 px-5 py-3">
              <button
                type="button"
                onClick={() => setShowEmployeeListModal(false)}
                className="department-modal-button"
              >
                Đóng
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowEmployeeListModal(false)
                  openManageEmployeesModal(currentDept)
                }}
                className="department-modal-button department-modal-button-primary"
              >
                Quản lý nhân sự
              </button>
            </footer>
          </div>
        </DepartmentModalPortal>
      )}

      {/* Edit Modal */}
      {showEditModal && (
        <DepartmentModalPortal>
          <div className="department-modal-surface w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-slate-900 mb-4">
              {currentDept ? 'Chỉnh sửa phòng ban' : 'Thêm phòng ban mới'}
            </h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Tên phòng ban</label>
                <input 
                  type="text" 
                  value={deptName}
                  onChange={e => setDeptName(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  placeholder="VD: Phòng Marketing"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Trưởng phòng (Manager)</label>
                <select 
                  value={managerId}
                  onChange={e => setManagerId(e.target.value ? Number(e.target.value) : '')}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                >
                  <option value="">-- Chọn trưởng phòng --</option>
                  {allEmployees.map(emp => (
                    <option key={emp.id} value={emp.id}>{emp.full_name} {emp.notion_name ? `(${emp.notion_name})` : ''}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button 
                onClick={() => setShowEditModal(false)}
                className="department-modal-button"
              >
                Hủy
              </button>
              <button 
                onClick={handleSaveDepartment}
                className="department-modal-button department-modal-button-primary"
              >
                Lưu thay đổi
              </button>
            </div>
          </div>
        </DepartmentModalPortal>
      )}

      {/* Manage Employees Modal */}
      {showManageEmployeesModal && currentDept && (
        <DepartmentModalPortal>
          <div className="department-modal-surface w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl max-h-[85vh] flex flex-col">
            <h3 className="text-lg font-bold text-slate-900 mb-1">Quản lý nhân sự</h3>
            <p className="text-sm text-slate-500 mb-4">Gán nhân sự vào phòng: <span className="font-semibold text-slate-800">{currentDept.name}</span></p>
            
            <div className="flex-1 overflow-y-auto border border-slate-200 rounded-xl p-1 bg-slate-50">
              <div className="grid gap-1">
                {allEmployees.map(emp => {
                  const isSelected = selectedEmployeeIds.includes(emp.id)
                  return (
                    <div 
                      key={emp.id} 
                      onClick={() => {
                        if (isSelected) {
                          setSelectedEmployeeIds(prev => prev.filter(id => id !== emp.id))
                        } else {
                          setSelectedEmployeeIds(prev => [...prev, emp.id])
                        }
                      }}
                      className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${
                        isSelected ? 'bg-blue-50 border border-blue-200/60' : 'bg-white border border-transparent hover:bg-slate-100'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`flex h-5 w-5 items-center justify-center rounded border ${isSelected ? 'border-blue-600 bg-blue-600' : 'border-slate-300 bg-white'}`}>
                          {isSelected && <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                        </div>
                        <div>
                          <p className={`text-sm font-medium ${isSelected ? 'text-blue-900' : 'text-slate-700'}`}>{emp.full_name}</p>
                          {emp.notion_name && <p className="text-xs text-slate-500">{emp.notion_name}</p>}
                        </div>
                      </div>
                      {!isSelected && emp.department_id && emp.department_id !== currentDept.id && (
                         <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full font-medium">Đang ở phòng khác</span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="mt-6 flex justify-between items-center">
              <p className="text-sm text-slate-600">Đã chọn: <strong className="text-slate-900">{selectedEmployeeIds.length}</strong> nhân sự</p>
              <div className="flex gap-3">
                <button 
                  onClick={() => setShowManageEmployeesModal(false)}
                  className="department-modal-button"
                >
                  Hủy
                </button>
                <button 
                  onClick={handleSaveEmployees}
                  className="department-modal-button department-modal-button-primary"
                >
                  Lưu thay đổi
                </button>
              </div>
            </div>
          </div>
        </DepartmentModalPortal>
      )}

      {/* Bonus Config Modal */}
      {allowBonusConfig && showBonusConfigModal && currentDept && (
        <DepartmentModalPortal>
          <div className="department-modal-surface w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl max-h-[90vh] flex flex-col">
            <h3 className="text-lg font-bold text-slate-900 mb-1">Cấu hình Bonus</h3>
            <p className="text-sm text-slate-500 mb-4">Phòng ban: <span className="font-semibold text-slate-800">{currentDept.name}</span></p>

            <div className="mb-4">
              <style>{`
                .custom-checkbox-label {
                  display: flex !important;
                  align-items: center !important;
                  gap: 8px !important;
                  cursor: pointer !important;
                  margin-bottom: 8px !important;
                  margin-top: 0 !important;
                  width: fit-content !important;
                }
                .custom-checkbox-input {
                  height: 16px !important;
                  width: 16px !important;
                  min-width: 16px !important;
                  padding: 0 !important;
                  margin: 0 !important;
                  border: 1px solid #cbd5e1 !important;
                  border-radius: 4px !important;
                  cursor: pointer !important;
                  box-sizing: border-box !important;
                  display: inline-block !important;
                  appearance: checkbox !important;
                  -webkit-appearance: checkbox !important;
                }
              `}</style>
              <label className="custom-checkbox-label">
                <input 
                  type="checkbox" 
                  className="custom-checkbox-input rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  checked={isCustomPeriod}
                  onChange={e => setIsCustomPeriod(e.target.checked)}
                />
                <span className="text-sm font-semibold text-slate-700">Áp dụng thời gian tùy chỉnh</span>
              </label>

              <div className="flex items-center gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">{isCustomPeriod ? "Từ tháng (YYYY-MM)" : "Tháng áp dụng (YYYY-MM)"}</label>
                  <input 
                    type="month" 
                    value={bonusPeriod}
                    onChange={e => {
                      if (e.target.value) {
                        setBonusPeriod(e.target.value)
                        fetchBonusConfig(currentDept.id, e.target.value)
                      }
                    }}
                    className="w-full min-w-[150px] rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                {isCustomPeriod && (
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Đến tháng (YYYY-MM)</label>
                    <input 
                      type="month" 
                      value={endPeriod}
                      onChange={e => setEndPeriod(e.target.value)}
                      className="w-full min-w-[150px] rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                )}
              </div>
              <p className="text-[11px] text-slate-400 mt-2">
                Lưu ý: Thay đổi cấu hình chỉ áp dụng cho tháng đã chọn và các tháng tiếp theo. Các tháng trước đó sẽ được giữ nguyên.
                {isCustomPeriod && " Nếu cấu hình hết hạn, hệ thống sẽ tự động dùng mức cấu hình trước đó."}
              </p>
            </div>

            <div className="flex-1 overflow-y-auto border border-slate-200 rounded-xl p-3 bg-slate-50">
              <div className="flex justify-between items-center mb-2 pb-2 border-b border-slate-200">
                <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                  {usesProgressiveBonus ? 'Bảng mốc Level & % Bonus' : 'Mức Bonus cố định'}
                </span>
                {usesProgressiveBonus && (
                  <button 
                    type="button"
                    onClick={() => {
                      setBonusRules(prev => [...prev, { min: 0, max: 0, rate: 0 }])
                    }}
                    className="text-xs font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-2 py-1 rounded"
                  >
                    + Thêm dòng
                  </button>
                )}
              </div>

              {!usesProgressiveBonus && (
                <p className="mb-3 text-xs text-slate-600">
                  Nhân viên không thuộc SALE luôn nhận 20% của 95% tổng Profit, không tăng theo mức Profit.
                </p>
              )}

              {bonusRules.length === 0 ? (
                <div className="text-center py-6 text-slate-400 text-sm">Chưa có cấu hình mốc. Nhấn + Thêm dòng để tạo.</div>
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-12 gap-2 text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                    <div className="col-span-3">Từ hệ số (Min)</div>
                    <div className="col-span-3">Đến hệ số (Max)</div>
                    <div className="col-span-4">Tỉ lệ Bonus (%)</div>
                    <div className="col-span-2 text-center">Xóa</div>
                  </div>
                  {bonusRules.map((rule, index) => (
                    <div key={index} className="grid grid-cols-12 gap-2 items-center">
                      <div className="col-span-3">
                        <input 
                          type="number" 
                          step="0.01"
                          required
                          disabled={!usesProgressiveBonus}
                          value={rule.min}
                          onChange={e => {
                            const val = parseFloat(e.target.value)
                            setBonusRules(prev => {
                              const next = [...prev]
                              next[index].min = isNaN(val) ? 0 : val
                              return next
                            })
                          }}
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs text-slate-800 outline-none focus:border-blue-500 disabled:bg-slate-100 disabled:text-slate-500"
                        />
                      </div>
                      <div className="col-span-3">
                        <input 
                          type="number" 
                          step="0.01"
                          required
                          disabled={!usesProgressiveBonus}
                          value={rule.max}
                          onChange={e => {
                            const val = parseFloat(e.target.value)
                            setBonusRules(prev => {
                              const next = [...prev]
                              next[index].max = isNaN(val) ? 0 : val
                              return next
                            })
                          }}
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs text-slate-800 outline-none focus:border-blue-500 disabled:bg-slate-100 disabled:text-slate-500"
                        />
                      </div>
                      <div className="col-span-4 flex items-center gap-1.5">
                        <input 
                          type="number" 
                          step="0.1"
                          required
                          disabled={!usesProgressiveBonus}
                          value={Math.round(rule.rate * 100)}
                          onChange={e => {
                            const val = parseFloat(e.target.value)
                            setBonusRules(prev => {
                              const next = [...prev]
                              next[index].rate = isNaN(val) ? 0 : (val / 100)
                              return next
                            })
                          }}
                          className="w-20 rounded-lg border border-slate-300 px-2 py-1.5 text-xs text-slate-800 outline-none focus:border-blue-500 disabled:bg-slate-100 disabled:text-slate-500"
                        />
                        <span className="text-xs text-slate-500">%</span>
                      </div>
                      <div className="col-span-2 text-center">
                        {usesProgressiveBonus && (
                          <button 
                            type="button"
                            onClick={() => {
                              setBonusRules(prev => prev.filter((_, idx) => idx !== index))
                            }}
                            className="p-1.5 text-slate-400 hover:text-rose-600 rounded transition"
                          >
                            <svg className="w-4 h-4 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button 
                onClick={() => setShowBonusConfigModal(false)}
                className="department-modal-button"
              >
                Hủy
              </button>
              <button 
                onClick={handleSaveBonusConfig}
                className="department-modal-button department-modal-button-primary"
              >
                Lưu thay đổi
              </button>
            </div>
          </div>
        </DepartmentModalPortal>
      )}
        </>
      )}
    </div>
  )
}
