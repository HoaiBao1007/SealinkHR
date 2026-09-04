import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import { EMPLOYEE_CONTRACT_OPTIONS, isFixedTermEmployeeContract } from '../../shared/employeeContract'
import { BrandedDateInput } from '../../shared/ui/BrandedDateInput'
import { AppIcon } from '../../shared/ui/AppIcon'
import { MonthYearSelect } from '../../shared/ui/MonthYearSelect'

type ApiRequest = (path: string, init?: RequestInit) => Promise<Response>

const cardStyle: CSSProperties = {
  border: '1px solid #dbe5f0',
  borderRadius: 22,
  background: 'linear-gradient(180deg, #ffffff 0%, #fbfdff 100%)',
  padding: 22,
  boxShadow: '0 16px 42px -32px rgba(15, 23, 42, .38)',
}

const buttonStyle: CSSProperties = {
  minHeight: 36,
  border: '1px solid #d4deea',
  borderRadius: 10,
  background: 'linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%)',
  color: '#172033',
  fontWeight: 700,
  padding: '7px 13px',
  cursor: 'pointer',
  boxShadow: '0 5px 14px -10px rgba(15, 23, 42, .45)',
  transition: 'transform .18s ease, border-color .18s ease, background .18s ease, box-shadow .18s ease',
}

const inputStyle: CSSProperties = {
  width: '100%',
  minHeight: 42,
  border: '1px solid #d6e0eb',
  borderRadius: 12,
  background: '#fbfdff',
  padding: '9px 12px',
  color: '#172033',
  boxShadow: 'inset 0 1px 2px rgba(15, 23, 42, .025)',
}

function Metric({ label, value, tone = '#163b66' }: { label: string; value: string | number; tone?: string }) {
  return (
    <article className="role-metric-card" style={cardStyle}>
      <p style={{ margin: 0, color: '#64748b', fontSize: 12, fontWeight: 700, textTransform: 'uppercase' }}>{label}</p>
      <p style={{ margin: '8px 0 0', color: tone, fontSize: 28, fontWeight: 800 }}>{value}</p>
    </article>
  )
}

export function HrDashboard({ apiRequest }: { apiRequest: ApiRequest }) {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void apiRequest('/api/role-dashboard/hr')
      .then((response) => response.json())
      .then(setData)
      .catch((reason) => setError(String(reason?.message || reason)))
  }, [apiRequest])

  if (error) return <div className="status-message error">{error}</div>
  if (!data) return <div className="status-message">Đang tải tổng quan nhân sự…</div>
  return (
    <section className="role-portal-stack">
      <div className="role-portal-intro">
        <h2 style={{ margin: 0 }}>Dashboard Admin vận hành</h2>
        <p style={{ color: '#64748b' }}>Tổng quan nhân sự và chấm công. Không hiển thị lương, phụ cấp hoặc bonus.</p>
      </div>
      <div className="role-metric-grid">
        <Metric label="Nhân viên hoạt động" value={data.employees.active} />
        <Metric label="Nhân viên ngừng hoạt động" value={data.employees.inactive} tone="#b45309" />
        <Metric label="Chưa gán phòng ban" value={data.employees.without_department} tone="#dc2626" />
        <Metric label="Bảng công chờ duyệt" value={data.attendance.draft} tone="#7c3aed" />
        <Metric label="Ngày bất thường" value={data.attendance.abnormal_days} tone="#be123c" />
        <Metric label="Tổng phút đi muộn" value={data.attendance.late_minutes} tone="#c2410c" />
      </div>
    </section>
  )
}

export function PersonalDashboard({ apiRequest }: { apiRequest: ApiRequest }) {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    void apiRequest('/api/role-dashboard/personal')
      .then((response) => response.json())
      .then(setData)
      .catch((reason) => setError(String(reason?.message || reason)))
  }, [apiRequest])
  if (error) return <div className="status-message error">{error}</div>
  if (!data) return <div className="status-message">Đang tải thông tin cá nhân…</div>
  if (!data.linked) return <div className="status-message error">{data.message}</div>
  return (
    <section className="role-portal-stack">
      <div style={cardStyle}>
        <p style={{ margin: 0, color: '#64748b', fontSize: 12, fontWeight: 700 }}>HỒ SƠ CÁ NHÂN</p>
        <h2 style={{ margin: '7px 0' }}>{data.employee.full_name}</h2>
        <p style={{ margin: 0, color: '#475569' }}>
          {[data.employee.employee_code, data.employee.department_name, data.employee.position].filter(Boolean).join(' · ') || 'Chưa cập nhật thông tin đơn vị'}
        </p>
      </div>
      <div className="role-metric-grid">
        <Metric label="Phiếu lương đã phát hành" value={data.published_payslip_count} />
        <Metric label="Tháng phiếu lương gần nhất" value={data.latest_payslip_period || 'Chưa có'} />
        <Metric label="Ngày công kỳ gần nhất" value={data.latest_attendance?.work_days ?? 'Chưa có'} tone="#047857" />
        <Metric label="Phút đi muộn kỳ gần nhất" value={data.latest_attendance?.late_minutes ?? 'Chưa có'} tone="#b45309" />
      </div>
    </section>
  )
}

type PersonalAccountData = {
  employee_id: number
  employee_code: string | null
  machine_employee_id: string
  full_name: string
  notion_name: string | null
  department_name: string | null
  position: string | null
  company_email: string | null
  company_phone_number: string | null
  personal_email: string | null
  phone_number: string | null
  username: string
  role: string
}

export function PersonalAccount({ apiRequest, embedded = false }: { apiRequest: ApiRequest; embedded?: boolean }) {
  const [data, setData] = useState<PersonalAccountData | null>(null)
  const [form, setForm] = useState({ personal_email: '', phone_number: '', username: '', current_password: '', new_password: '', confirm_password: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiRequest('/api/user/my-account')
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail || 'Không thể tải thông tin tài khoản.')
      setData(payload)
      setForm((previous) => ({
        ...previous,
        personal_email: payload.personal_email || '',
        phone_number: payload.phone_number || '',
        username: payload.username || '',
        current_password: '',
        new_password: '',
        confirm_password: '',
      }))
    } catch (reason: any) {
      setError(reason?.message || String(reason))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [apiRequest])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    if (form.new_password && form.new_password !== form.confirm_password) {
      setError('Mật khẩu mới và xác nhận mật khẩu chưa trùng khớp.')
      return
    }
    setSaving(true)
    try {
      const body: Record<string, string | null> = {
        personal_email: form.personal_email.trim() || null,
        phone_number: form.phone_number.trim() || null,
        username: form.username.trim(),
      }
      if (form.new_password) {
        body.current_password = form.current_password
        body.new_password = form.new_password
      } else if (data && form.username.trim() !== data.username) {
        body.current_password = form.current_password
      }
      const response = await apiRequest('/api/user/my-account', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail || 'Không thể cập nhật tài khoản.')
      setData(payload)
      setForm((previous) => ({ ...previous, current_password: '', new_password: '', confirm_password: '', username: payload.username }))
      setMessage('Đã cập nhật thông tin tài khoản thành công.')
    } catch (reason: any) {
      setError(reason?.message || String(reason))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="status-message">Đang tải thông tin tài khoản…</div>
  if (!data) return <div className="status-message error">{error || 'Không tìm thấy thông tin tài khoản.'}</div>

  return (
    <section className="personal-account-shell" style={{ maxWidth: embedded ? undefined : 1040, margin: embedded ? undefined : '0 auto' }}>
      {!embedded && (
        <div style={cardStyle}>
          <p style={{ margin: 0, color: '#64748b', fontSize: 12, fontWeight: 800 }}>TÀI KHOẢN CỦA TÔI</p>
          <h2 style={{ margin: '7px 0' }}>{data.full_name}</h2>
          <p style={{ margin: 0, color: '#475569' }}>{[data.employee_code, data.department_name, data.position].filter(Boolean).join(' · ') || 'Chưa cập nhật đơn vị'}</p>
        </div>
      )}

      {error && <div className="status-message error">{error}</div>}
      {message && <div className="status-message success">{message}</div>}

      <form className="personal-account-form" onSubmit={submit} style={{ ...cardStyle, display: 'grid', gap: 20 }}>
        {embedded && (
          <div>
            <p style={{ margin: 0, color: '#64748b', fontSize: 12, fontWeight: 800 }}>TÀI KHOẢN CỦA TÔI</p>
            <h2 style={{ margin: '7px 0 0' }}>Thông tin đăng nhập và bảo mật</h2>
          </div>
        )}
        <div>
          <h3 style={{ margin: '0 0 12px' }}>Thông tin hồ sơ chỉ đọc</h3>
          <div className="personal-account-field-grid personal-account-field-grid--readonly">
            <label>Mã nhân viên<input style={{ ...inputStyle, marginTop: 6, background: '#f8fafc' }} value={data.employee_code || ''} readOnly /></label>
            <label>Mã máy chấm công<input style={{ ...inputStyle, marginTop: 6, background: '#f8fafc' }} value={data.machine_employee_id || ''} readOnly /></label>
            <label>Email công ty<input style={{ ...inputStyle, marginTop: 6, background: '#f8fafc' }} value={data.company_email || ''} readOnly /></label>
            <label>SĐT công ty<input style={{ ...inputStyle, marginTop: 6, background: '#f8fafc' }} value={data.company_phone_number || ''} readOnly /></label>
            <label>Vai trò hệ thống<input style={{ ...inputStyle, marginTop: 6, background: '#f8fafc' }} value={data.role} readOnly /></label>
          </div>
        </div>

        <div>
          <h3 style={{ margin: '0 0 12px' }}>Thông tin được phép chỉnh sửa</h3>
          <div className="personal-account-field-grid">
            <label>Email cá nhân<input type="email" style={{ ...inputStyle, marginTop: 6 }} value={form.personal_email} onChange={(event) => setForm((previous) => ({ ...previous, personal_email: event.target.value }))} placeholder="email@example.com" /></label>
            <label>Số điện thoại cá nhân<input style={{ ...inputStyle, marginTop: 6 }} value={form.phone_number} onChange={(event) => setForm((previous) => ({ ...previous, phone_number: event.target.value }))} placeholder="Nhập số điện thoại" /></label>
            <label>Tên đăng nhập<input style={{ ...inputStyle, marginTop: 6 }} value={form.username} onChange={(event) => setForm((previous) => ({ ...previous, username: event.target.value }))} required /></label>
          </div>
        </div>

        <div>
          <h3 style={{ margin: '0 0 5px' }}>Bảo mật đăng nhập</h3>
          <p style={{ margin: '0 0 12px', color: '#64748b', fontSize: 12 }}>Nhập mật khẩu hiện tại khi đổi tên đăng nhập hoặc mật khẩu. Để trống mật khẩu mới nếu không muốn đổi.</p>
          <div className="personal-account-field-grid">
            <label>Mật khẩu hiện tại<input type="password" autoComplete="current-password" style={{ ...inputStyle, marginTop: 6 }} value={form.current_password} onChange={(event) => setForm((previous) => ({ ...previous, current_password: event.target.value }))} /></label>
            <label>Mật khẩu mới<input type="password" autoComplete="new-password" minLength={8} style={{ ...inputStyle, marginTop: 6 }} value={form.new_password} onChange={(event) => setForm((previous) => ({ ...previous, new_password: event.target.value }))} /></label>
            <label>Xác nhận mật khẩu mới<input type="password" autoComplete="new-password" minLength={8} style={{ ...inputStyle, marginTop: 6 }} value={form.confirm_password} onChange={(event) => setForm((previous) => ({ ...previous, confirm_password: event.target.value }))} /></label>
          </div>
        </div>

        <div className="personal-account-actions"><button className="portal-action-button" type="submit" style={buttonStyle} disabled={saving}>{saving ? 'Đang lưu…' : 'Lưu thay đổi'}</button></div>
      </form>
    </section>
  )
}

type HrEmployee = {
  id: number
  machine_employee_id: string
  full_name: string
  notion_name: string | null
  department_id: number | null
  department_name: string | null
  employee_code: string | null
  position: string | null
  employee_type: string
  annual_leave_quota: number
  start_date: string | null
  contract_type: string | null
  contract_sign_date: string | null
  contract_start_date: string | null
  contract_end_date: string | null
  tax_code: string | null
  is_active: boolean
  company_email: string | null
  personal_email: string | null
  phone_number: string | null
  company_phone_number: string | null
  social_insurance_number: string | null
  health_insurance_number: string | null
  pvi_insurance: string | null
  account_number: string | null
  bank_name: string | null
  notes: string | null
  cccd_url: string[]
  contract_url: string[]
  username: string | null
  account_role: string | null
  access_role: string
  access_role_reason: string
}

const accessRoleMeta: Record<string, { label: string; color: string; background: string }> = {
  ADMIN: { label: 'Kế toán trưởng · ADMIN', color: '#7c2d12', background: '#ffedd5' },
  DIRECTOR: { label: 'GIÁM ĐỐC · DIRECTOR', color: '#075985', background: '#e0f2fe' },
  HR_ADMIN: { label: 'Admin vận hành · HR_ADMIN', color: '#7c3aed', background: '#f3e8ff' },
  IT_ADMIN: { label: 'Quản trị hệ thống cấp cao · IT_ADMIN', color: '#0369a1', background: '#e0f2fe' },
  USER: { label: 'Nhân viên · USER', color: '#475569', background: '#f1f5f9' },
}

function AccessRoleBadge({ role, pending = false }: { role: string; pending?: boolean }) {
  const meta = accessRoleMeta[role] || accessRoleMeta.USER
  return (
    <span style={{
      display: 'inline-flex',
      borderRadius: 999,
      padding: '4px 8px',
      fontSize: 11,
      fontWeight: 800,
      color: meta.color,
      background: meta.background,
      border: `1px solid ${meta.color}22`,
    }}>
      {pending ? `Sẽ cấp: ${meta.label}` : meta.label}
    </span>
  )
}

const emptyEmployee = {
  machine_employee_id: '',
  full_name: '',
  notion_name: '',
  department_id: '',
  employee_code: '',
  position: '',
  employee_type: 'FULLTIME',
  annual_leave_quota: '12',
  start_date: '',
  contract_type: '',
  contract_sign_date: '',
  contract_start_date: '',
  contract_end_date: '',
  tax_code: '',
  company_email: '',
  personal_email: '',
  phone_number: '',
  company_phone_number: '',
  social_insurance_number: '',
  health_insurance_number: '',
  pvi_insurance: '',
  account_number: '',
  bank_name: '',
  notes: '',
  username: '',
  password: '',
}

export function HrEmployees({
  apiRequest,
  onMessage,
  onConfirm,
  focusEmployeeId,
  focusKey,
}: {
  apiRequest: ApiRequest
  onMessage: (message: string) => void
  onConfirm: (options: { title: string; message: string; confirmLabel?: string; tone?: 'primary' | 'danger' }) => Promise<boolean>
  focusEmployeeId?: number | null
  focusKey?: number | null
}) {
  const [employees, setEmployees] = useState<HrEmployee[]>([])
  const [departments, setDepartments] = useState<any[]>([])
  const [search, setSearch] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<any>(emptyEmployee)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [pendingDocuments, setPendingDocuments] = useState<{ cccd: File[]; contract: File[] }>({ cccd: [], contract: [] })
  const [existingDocuments, setExistingDocuments] = useState<{ cccd: string[]; contract: string[] }>({ cccd: [], contract: [] })

  const load = async () => {
    const [employeeResponse, departmentResponse] = await Promise.all([
      apiRequest(`/api/hr/employees${search.trim() ? `?q=${encodeURIComponent(search.trim())}` : ''}`),
      apiRequest('/api/hr/departments'),
    ])
    setEmployees(await employeeResponse.json())
    setDepartments(await departmentResponse.json())
  }
  useEffect(() => { void load() }, [])

  const openCreate = () => {
    setEditingId(null)
    setForm({ ...emptyEmployee })
    setFormError('')
    setPendingDocuments({ cccd: [], contract: [] })
    setExistingDocuments({ cccd: [], contract: [] })
    setShowForm(true)
  }
  const openEdit = (employee: HrEmployee) => {
    setEditingId(employee.id)
    setForm({
      machine_employee_id: employee.machine_employee_id,
      full_name: employee.full_name,
      notion_name: employee.notion_name || '',
      department_id: employee.department_id ?? '',
      employee_code: employee.employee_code || '',
      position: employee.position || '',
      employee_type: employee.employee_type,
      annual_leave_quota: String(employee.annual_leave_quota ?? 12),
      start_date: employee.start_date || '',
      contract_type: employee.contract_type || '',
      contract_sign_date: employee.contract_sign_date || '',
      contract_start_date: employee.contract_start_date || '',
      contract_end_date: employee.contract_end_date || '',
      tax_code: employee.tax_code || '',
      company_email: employee.company_email || '',
      personal_email: employee.personal_email || '',
      phone_number: employee.phone_number || '',
      company_phone_number: employee.company_phone_number || '',
      social_insurance_number: employee.social_insurance_number || '',
      health_insurance_number: employee.health_insurance_number || '',
      pvi_insurance: employee.pvi_insurance || '',
      account_number: employee.account_number || '',
      bank_name: employee.bank_name || '',
      notes: employee.notes || '',
      username: employee.username || '',
      password: '',
    })
    setFormError('')
    setPendingDocuments({ cccd: [], contract: [] })
    setExistingDocuments({ cccd: employee.cccd_url || [], contract: employee.contract_url || [] })
    setShowForm(true)
  }
  useEffect(() => {
    if (!focusEmployeeId || employees.length === 0) return
    const employee = employees.find((item) => item.id === focusEmployeeId)
    if (!employee) {
      onMessage('Hồ sơ được nhắc trong thông báo không còn tồn tại hoặc không thuộc phạm vi truy cập.')
      return
    }
    openEdit(employee)
    window.setTimeout(() => {
      document.getElementById(`hr-employee-${employee.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 100)
  }, [focusEmployeeId, focusKey, employees])
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    const payload = {
      ...form,
      department_id: form.department_id === '' ? null : Number(form.department_id),
      annual_leave_quota: form.annual_leave_quota === '' ? 12 : Number(form.annual_leave_quota),
      start_date: form.start_date || null,
      contract_type: form.contract_type || null,
      contract_sign_date: form.contract_sign_date || null,
      contract_start_date: isFixedTermEmployeeContract(form.contract_type) ? form.contract_start_date || null : null,
      contract_end_date: isFixedTermEmployeeContract(form.contract_type) ? form.contract_end_date || null : null,
      password: form.password || undefined,
    }
    try {
      const response = await apiRequest(editingId ? `/api/hr/employees/${editingId}` : '/api/hr/employees', {
        method: editingId ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) {
        const result = await response.json().catch(() => null)
        throw new Error(result?.detail || 'Không thể lưu hồ sơ nhân viên.')
      }
      const savedEmployee = await response.json()
      const uploadFailures: string[] = []
      for (const docType of ['cccd', 'contract'] as const) {
        if (pendingDocuments[docType].length === 0) continue
        const documentForm = new FormData()
        pendingDocuments[docType].forEach((file) => documentForm.append('files', file))
        try {
          await apiRequest(`/api/hr/employees/${savedEmployee.id}/upload-${docType}`, {
            method: 'POST',
            body: documentForm,
          })
        } catch (reason: any) {
          uploadFailures.push(`${docType.toUpperCase()}: ${reason?.message || String(reason)}`)
        }
      }
      setShowForm(false)
      onMessage(uploadFailures.length > 0
        ? `${editingId ? 'Đã cập nhật' : 'Đã tạo'} hồ sơ nhưng có tệp chưa tải lên: ${uploadFailures.join('; ')}`
        : editingId ? 'Đã cập nhật hồ sơ nhân viên và tài liệu.' : 'Đã tạo hồ sơ nhân viên và tài liệu. Phần lương, phụ cấp và bonus chờ Kế toán trưởng thiết lập.')
      await load()
    } catch (reason: any) {
      setFormError(reason?.message || String(reason))
    } finally {
      setSaving(false)
    }
  }
  const stageDocuments = (docType: 'cccd' | 'contract', files: FileList | null) => {
    if (!files) return
    const accepted = Array.from(files).filter((file) => file.size > 0 && file.size <= 10 * 1024 * 1024)
    setPendingDocuments((previous) => ({
      ...previous,
      [docType]: [...previous[docType], ...accepted].slice(0, 10),
    }))
    if (accepted.length !== files.length) {
      setFormError('Một số tệp không hợp lệ hoặc vượt quá giới hạn 10 MB.')
    }
  }
  const openHrDocument = async (url: string, download = false) => {
    try {
      const response = await apiRequest(url)
      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.target = download ? '_self' : '_blank'
      anchor.rel = 'noopener noreferrer'
      if (download) anchor.download = url.split('/').pop() || 'document'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
    } catch (reason: any) {
      setFormError(reason?.message || String(reason))
    }
  }
  const deleteHrDocument = async (docType: 'cccd' | 'contract', url: string) => {
    if (!editingId) return
    const accepted = await onConfirm({
      title: 'Xóa tài liệu',
      message: 'Bạn có chắc chắn muốn xóa tài liệu này khỏi hồ sơ nhân viên?',
      confirmLabel: 'Xóa tài liệu',
      tone: 'danger',
    })
    if (!accepted) return
    setSaving(true)
    setFormError('')
    try {
      const response = await apiRequest(`/api/hr/employees/${editingId}/delete-document`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, doc_type: docType }),
      })
      const employee = await response.json()
      setExistingDocuments({ cccd: employee.cccd_url || [], contract: employee.contract_url || [] })
    } catch (reason: any) {
      setFormError(reason?.message || String(reason))
    } finally {
      setSaving(false)
    }
  }
  const deactivate = async (employee: HrEmployee) => {
    const accepted = await onConfirm({
      title: 'Ngừng hoạt động hồ sơ',
      message: `Ngừng hoạt động hồ sơ ${employee.full_name}? Dữ liệu lịch sử vẫn được giữ nguyên.`,
      confirmLabel: 'Ngừng hoạt động',
      tone: 'danger',
    })
    if (!accepted) return
    await apiRequest(`/api/hr/employees/${employee.id}/deactivate`, { method: 'POST' })
    onMessage('Đã ngừng hoạt động hồ sơ; không xóa lịch sử.')
    await load()
  }

  return (
    <section style={{ display: 'grid', gap: 16 }}>
      <div style={{ ...cardStyle, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'end', justifyContent: 'space-between' }}>
        <label style={{ flex: '1 1 320px' }}>Tìm nhân viên
          <input style={inputStyle} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tên, mã máy, mã nhân viên, tên Notion…" />
        </label>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={buttonStyle} onClick={() => void load()}>Tìm</button>
          <button style={buttonStyle} onClick={openCreate}>+ Thêm nhân viên</button>
        </div>
      </div>
      <div style={{ ...cardStyle, padding: 14, background: '#f8fafc', fontSize: 13, color: '#475569' }}>
        <strong style={{ color: '#0f172a' }}>Cấp tài khoản:</strong> mở “Sửa” tại đúng hồ sơ, nhập tên đăng nhập và mật khẩu tối thiểu 12 ký tự.
        Quyền được xác định tự động: Tôn Thất Trung Kiên và Tô Tố Vân nhận DIRECTOR; chức vụ Admin trong nhánh IT &amp; ADMIN nhận HR_ADMIN; nhân viên IT dùng tài khoản quản trị chung admin_sealink; các tài khoản cá nhân khác nhận USER.
      </div>
      {showForm && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={() => { if (!saving) setShowForm(false) }}
        >
          <form
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="hr-employee-dialog-title"
            onSubmit={submit}
            onMouseDown={(event) => event.stopPropagation()}
            style={{ width: 'min(760px, 100%)', maxWidth: 760 }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 24 }}>
              <div>
                <p style={{ margin: '0 0 8px', color: '#526979', fontSize: 11, fontWeight: 800, letterSpacing: '.2em', textTransform: 'uppercase' }}>
                  {editingId ? 'Edit Employee' : 'Add Employee'}
                </p>
                <h2 id="hr-employee-dialog-title" style={{ margin: 0 }}>{editingId ? 'Chỉnh sửa hồ sơ nhân viên' : 'Thêm nhân viên mới'}</h2>
                <p style={{ margin: '8px 0 0', color: '#64748b', fontSize: 13 }}>
                  Khai báo hồ sơ nhân sự, tài khoản và thông tin liên hệ. Dữ liệu tài chính được phân quyền riêng.
                </p>
              </div>
              <button
                type="button"
                className="app-close-button"
                aria-label="Đóng biểu mẫu"
                disabled={saving}
                onClick={() => setShowForm(false)}
              >
                <AppIcon name="close" size={17} />
              </button>
            </div>

            {formError && (
              <div className="status-message error" style={{ marginBottom: 18 }}>
                {formError}
              </div>
            )}

            <p style={{ margin: '0 0 12px', color: '#64748b', fontSize: 11, fontWeight: 800, letterSpacing: '.18em', textTransform: 'uppercase' }}>
              Thông tin nhận diện
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(250px,1fr))', gap: 16 }}>
              <label><span>ID máy chấm công <span style={{ color: '#e11d48' }}>*</span></span>
                <input style={inputStyle} value={form.machine_employee_id} required placeholder="Ví dụ: E001" onChange={(e) => setForm((previous: any) => ({ ...previous, machine_employee_id: e.target.value }))} />
              </label>
              <label><span>Tên tiếng Việt <span style={{ color: '#e11d48' }}>*</span></span>
                <input style={inputStyle} value={form.full_name} required placeholder="Họ và tên nhân viên" onChange={(e) => setForm((previous: any) => ({ ...previous, full_name: e.target.value }))} />
              </label>
              <label>Tên Notion
                <input style={inputStyle} value={form.notion_name} placeholder="Tên dùng để đối soát dữ liệu" onChange={(e) => setForm((previous: any) => ({ ...previous, notion_name: e.target.value }))} />
              </label>
              <label>Phòng ban
                <select style={inputStyle} value={form.department_id} onChange={(e) => setForm((previous: any) => ({ ...previous, department_id: e.target.value }))}>
                  <option value="">-- Chọn phòng ban --</option>
                  {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                </select>
              </label>
              <label>Mã nhân viên
                <input style={inputStyle} value={form.employee_code} placeholder="Có thể bổ sung sau" onChange={(e) => setForm((previous: any) => ({ ...previous, employee_code: e.target.value }))} />
              </label>
              <label>Chức vụ
                <input style={inputStyle} value={form.position} placeholder="Ví dụ: Chuyên viên HR" onChange={(e) => setForm((previous: any) => ({ ...previous, position: e.target.value }))} />
              </label>
              <label>Ngày bắt đầu làm việc
                <BrandedDateInput style={inputStyle} value={form.start_date} onChange={(e) => setForm((previous: any) => ({ ...previous, start_date: e.target.value }))} />
              </label>
              <label>Loại nhân viên
                <select style={inputStyle} value={form.employee_type} onChange={(e) => setForm((previous: any) => ({ ...previous, employee_type: e.target.value }))}>
                  <option value="FULLTIME">Chính thức</option>
                  <option value="PROBATION">Thử việc</option>
                  <option value="INTERN">Học việc</option>
                  <option value="TRAINEE">Thực tập</option>
                </select>
              </label>
              <label>Quota phép năm (ngày)
                <input style={inputStyle} type="number" min={0} step="0.5" value={form.annual_leave_quota} onChange={(e) => setForm((previous: any) => ({ ...previous, annual_leave_quota: e.target.value }))} />
              </label>
            </div>

            <div style={{ marginTop: 20, border: '1px solid #cbd5e1', borderRadius: 18, background: '#f8fafc', padding: 18 }}>
              <p style={{ margin: '0 0 14px', color: '#475569', fontSize: 11, fontWeight: 800, letterSpacing: '.18em', textTransform: 'uppercase' }}>Thông tin hợp đồng</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(250px,1fr))', gap: 16 }}>
                <label>Loại hợp đồng
                  <select
                    style={inputStyle}
                    value={form.contract_type}
                    onChange={(e) => setForm((previous: any) => ({
                      ...previous,
                      contract_type: e.target.value,
                      contract_sign_date: e.target.value ? previous.contract_sign_date : '',
                      contract_start_date: isFixedTermEmployeeContract(e.target.value) ? previous.contract_start_date : '',
                      contract_end_date: isFixedTermEmployeeContract(e.target.value) ? previous.contract_end_date : '',
                    }))}
                  >
                    <option value="">-- Chọn loại hợp đồng --</option>
                    {EMPLOYEE_CONTRACT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label>Ngày ký hợp đồng
                  <BrandedDateInput style={inputStyle} disabled={!form.contract_type} required={Boolean(form.contract_type)} value={form.contract_sign_date} onChange={(e) => setForm((previous: any) => ({ ...previous, contract_sign_date: e.target.value }))} />
                </label>
                {isFixedTermEmployeeContract(form.contract_type) && (
                  <>
                    <label>Hợp đồng từ ngày
                      <BrandedDateInput style={inputStyle} required value={form.contract_start_date} onChange={(e) => setForm((previous: any) => ({ ...previous, contract_start_date: e.target.value }))} />
                    </label>
                    <label>Hợp đồng đến ngày
                      <BrandedDateInput style={inputStyle} required min={form.contract_start_date || undefined} value={form.contract_end_date} onChange={(e) => setForm((previous: any) => ({ ...previous, contract_end_date: e.target.value }))} />
                    </label>
                  </>
                )}
              </div>
              <p style={{ margin: '12px 0 0', color: '#64748b', fontSize: 12 }}>
                Hợp đồng lần 1 và lần 2 bắt buộc nhập đủ thời gian từ ngày đến ngày. Các loại còn lại chỉ cần ngày ký hợp đồng.
              </p>
            </div>

            <div style={{ marginTop: 20, border: '1px solid #bae6fd', borderRadius: 18, background: '#f0f9ff', padding: 18 }}>
              <p style={{ margin: '0 0 4px', color: '#0369a1', fontSize: 11, fontWeight: 800, letterSpacing: '.18em', textTransform: 'uppercase' }}>Thông tin tài khoản đăng nhập</p>
              <p style={{ margin: '0 0 14px', color: '#64748b', fontSize: 12 }}>Có thể để trống và cấp tài khoản sau. Khi tạo mới tài khoản, mật khẩu phải có ít nhất 12 ký tự.</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(250px,1fr))', gap: 16 }}>
                <label>Tên đăng nhập
                  <input style={inputStyle} autoComplete="off" value={form.username} placeholder="Để trống nếu chưa cấp" onChange={(e) => setForm((previous: any) => ({ ...previous, username: e.target.value }))} />
                </label>
                <label>{editingId ? 'Mật khẩu mới' : 'Mật khẩu'}
                  <input style={inputStyle} type="password" autoComplete="new-password" minLength={12} value={form.password} placeholder="Để trống nếu chưa cấp hoặc không đổi" onChange={(e) => setForm((previous: any) => ({ ...previous, password: e.target.value }))} />
                </label>
              </div>
            </div>

            <div style={{ marginTop: 16, border: '1px solid #e2e8f0', borderRadius: 18, background: '#f8fafc', padding: 18 }}>
              <p style={{ margin: '0 0 14px', color: '#64748b', fontSize: 11, fontWeight: 800, letterSpacing: '.18em', textTransform: 'uppercase' }}>Thông tin ngân hàng</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(250px,1fr))', gap: 16 }}>
                <label>Tên ngân hàng
                  <input style={inputStyle} value={form.bank_name} placeholder="Ví dụ: Vietcombank" onChange={(e) => setForm((previous: any) => ({ ...previous, bank_name: e.target.value }))} />
                </label>
                <label>Số tài khoản
                  <input style={inputStyle} value={form.account_number} placeholder="Số tài khoản nhận lương" onChange={(e) => setForm((previous: any) => ({ ...previous, account_number: e.target.value }))} />
                </label>
              </div>
            </div>

            <div style={{ marginTop: 16, border: '1px solid #e2e8f0', borderRadius: 18, background: '#f8fafc', padding: 18 }}>
              <p style={{ margin: '0 0 14px', color: '#64748b', fontSize: 11, fontWeight: 800, letterSpacing: '.18em', textTransform: 'uppercase' }}>Thông tin cá nhân &amp; liên hệ</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(250px,1fr))', gap: 16 }}>
                <label>Email công ty
                  <input style={inputStyle} type="email" value={form.company_email} placeholder="nhanvien@sealink.com" onChange={(e) => setForm((previous: any) => ({ ...previous, company_email: e.target.value }))} />
                </label>
                <label>Email cá nhân
                  <input style={inputStyle} type="email" value={form.personal_email} placeholder="email@example.com" onChange={(e) => setForm((previous: any) => ({ ...previous, personal_email: e.target.value }))} />
                </label>
                <label>SĐT cá nhân
                  <input style={inputStyle} value={form.phone_number} onChange={(e) => setForm((previous: any) => ({ ...previous, phone_number: e.target.value }))} />
                </label>
                <label>SĐT công ty
                  <input style={inputStyle} value={form.company_phone_number} onChange={(e) => setForm((previous: any) => ({ ...previous, company_phone_number: e.target.value }))} />
                </label>
                <label>Mã số thuế
                  <input style={inputStyle} value={form.tax_code} onChange={(e) => setForm((previous: any) => ({ ...previous, tax_code: e.target.value }))} />
                </label>
                <label>Số BHXH
                  <input style={inputStyle} value={form.social_insurance_number} onChange={(e) => setForm((previous: any) => ({ ...previous, social_insurance_number: e.target.value }))} />
                </label>
                <label>Số BHYT
                  <input style={inputStyle} value={form.health_insurance_number} onChange={(e) => setForm((previous: any) => ({ ...previous, health_insurance_number: e.target.value }))} />
                </label>
                <label>Bảo hiểm PVI
                  <input style={inputStyle} value={form.pvi_insurance} onChange={(e) => setForm((previous: any) => ({ ...previous, pvi_insurance: e.target.value }))} />
                </label>
                <label style={{ gridColumn: '1 / -1' }}>Ghi chú
                  <textarea style={{ ...inputStyle, minHeight: 76, resize: 'vertical' }} rows={3} value={form.notes} onChange={(e) => setForm((previous: any) => ({ ...previous, notes: e.target.value }))} />
                </label>
              </div>
            </div>

            <div style={{ marginTop: 16, border: '1px solid #dbe5f0', borderRadius: 18, background: '#f8fafc', padding: 18 }}>
              <p style={{ margin: '0 0 14px', color: '#475569', fontSize: 11, fontWeight: 800, letterSpacing: '.18em', textTransform: 'uppercase' }}>Hồ sơ &amp; tài liệu đính kèm</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(270px,1fr))', gap: 16 }}>
                {(['cccd', 'contract'] as const).map((docType) => (
                  <section key={docType} style={{ border: '1px solid #e2e8f0', borderRadius: 14, background: '#fff', padding: 14 }}>
                    <strong style={{ display: 'block', marginBottom: 10, color: '#334155', fontSize: 12 }}>{docType === 'cccd' ? 'CCCD / CMND' : 'Hồ sơ hợp đồng'}</strong>
                    <div style={{ display: 'grid', gap: 8 }}>
                      {existingDocuments[docType].map((url) => (
                        <div key={url} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 8, alignItems: 'center', border: '1px solid #e2e8f0', borderRadius: 10, padding: '8px 10px' }}>
                          <span title={url.split('/').pop()} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#475569', fontSize: 11 }}>{url.split('/').pop()}</span>
                          <div style={{ display: 'flex', gap: 4 }}>
                            <button type="button" className="ghost" style={{ minHeight: 36, padding: '6px 10px', fontSize: 11 }} onClick={() => void openHrDocument(url)}>Xem</button>
                            <button type="button" className="ghost app-download-button" style={{ minHeight: 36, padding: '6px 10px', fontSize: 11 }} onClick={() => void openHrDocument(url, true)}>Tải</button>
                            <button type="button" className="ghost app-delete-button" style={{ minHeight: 36, padding: '6px 10px', color: '#b42318', fontSize: 11 }} disabled={saving} onClick={() => void deleteHrDocument(docType, url)}>Xóa</button>
                          </div>
                        </div>
                      ))}
                      {pendingDocuments[docType].map((file, index) => (
                        <div key={`${file.name}-${file.lastModified}-${index}`} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 8, alignItems: 'center', border: '1px solid #bae6fd', borderRadius: 10, background: '#f0f9ff', padding: '8px 10px' }}>
                          <span title={file.name} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#0369a1', fontSize: 11 }}>{file.name} · mới</span>
                          <button type="button" className="ghost" style={{ minHeight: 36, padding: '6px 10px', color: '#b42318', fontSize: 11 }} onClick={() => setPendingDocuments((previous) => ({ ...previous, [docType]: previous[docType].filter((_, itemIndex) => itemIndex !== index) }))}>Bỏ</button>
                        </div>
                      ))}
                      {existingDocuments[docType].length === 0 && pendingDocuments[docType].length === 0 && <span style={{ color: '#526979', fontSize: 11 }}>Chưa có tài liệu.</span>}
                    </div>
                    <label style={{ ...buttonStyle, display: 'inline-flex', alignItems: 'center', marginTop: 12, fontSize: 11 }}>
                      + {docType === 'cccd' ? 'Tải CCCD mới' : 'Tải hồ sơ hợp đồng'}
                      <input type="file" multiple accept="image/jpeg,image/png,image/webp,application/pdf" style={{ display: 'none' }} onChange={(event) => { stageDocuments(docType, event.target.files); event.target.value = '' }} />
                    </label>
                  </section>
                ))}
              </div>
              <p style={{ margin: '10px 0 0', color: '#64748b', fontSize: 11 }}>Chấp nhận JPG, PNG, WEBP hoặc PDF; tối đa 10 MB mỗi tệp. Tệp mới được tải lên khi lưu hồ sơ.</p>
            </div>

            <div style={{ marginTop: 16, border: '1px solid #fed7aa', borderRadius: 14, background: '#fff7ed', padding: '12px 14px', color: '#9a3412', fontSize: 12, lineHeight: 1.55 }}>
              <strong>Giới hạn quyền admin_HR:</strong> form này không hiển thị và không gửi lương hợp đồng, phụ cấp, hệ số bonus hoặc cấu hình bonus. Các dữ liệu đó chỉ do Kế toán trưởng hoặc IT_ADMIN có quyền nghiệp vụ quản lý.
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 22, paddingTop: 16, borderTop: '1px solid #e2e8f0' }}>
              <button type="button" className="ghost" disabled={saving} onClick={() => setShowForm(false)}>Đóng</button>
              <button type="submit" disabled={saving}>{saving ? 'Đang lưu…' : 'Lưu hồ sơ nhân viên'}</button>
            </div>
          </form>
        </div>
      )}
      <div style={{ ...cardStyle, overflow: 'hidden', padding: 0 }}>
        <div style={{ maxHeight: 570, overflow: 'auto' }}>
          <table style={{ width: '100%', minWidth: 1050, borderCollapse: 'collapse' }}>
            <thead><tr>{['Mã máy / Mã NV', 'Họ tên', 'Tên Notion', 'Phòng ban', 'Chức vụ', 'Loại NV', 'Tài khoản', 'Quyền hệ thống', 'Trạng thái', 'Thao tác'].map((value) => <th key={value}>{value}</th>)}</tr></thead>
            <tbody>
              {employees.map((employee) => (
                <tr
                  key={employee.id}
                  id={`hr-employee-${employee.id}`}
                  style={focusEmployeeId === employee.id ? { background: '#fef3c7', outline: '2px solid #f59e0b' } : undefined}
                >
                  <td>{employee.machine_employee_id}<br /><small>{employee.employee_code || '—'}</small></td>
                  <td><strong>{employee.full_name}</strong></td>
                  <td>{employee.notion_name || '—'}</td>
                  <td>{employee.department_name || 'Chưa gán'}</td>
                  <td>{employee.position || '—'}</td>
                  <td>{employee.employee_type}</td>
                  <td>{employee.username || 'Chưa cấp'}</td>
                  <td title={employee.access_role_reason}>
                    <AccessRoleBadge role={employee.account_role || employee.access_role} pending={!employee.account_role} />
                  </td>
                  <td>{employee.is_active ? 'Đang hoạt động' : 'Ngừng hoạt động'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button style={buttonStyle} onClick={() => openEdit(employee)}>Sửa</button>
                      {employee.is_active && <button style={buttonStyle} onClick={() => void deactivate(employee)}>Ngừng</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

export function ItOperations({ apiRequest, view }: { apiRequest: ApiRequest; view: 'backups' | 'audit' }) {
  const [data, setData] = useState<any>(null)
  const [running, setRunning] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [restoreCandidate, setRestoreCandidate] = useState<any>(null)
  const [restoreConfirmation, setRestoreConfirmation] = useState('')
  const [restoring, setRestoring] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const load = async () => {
    if (view === 'backups') {
      const response = await apiRequest('/api/it/backups')
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail || 'Không thể tải danh sách backup.')
      setData(payload)
      return
    }
    const [auditResponse, overrideResponse] = await Promise.all([
      apiRequest('/api/it/audit?limit=300'),
      apiRequest('/api/it/attendance-overrides?limit=300'),
    ])
    const [auditPayload, overridePayload] = await Promise.all([
      auditResponse.json(),
      overrideResponse.json(),
    ])
    if (!auditResponse.ok) throw new Error(auditPayload?.detail || 'Không thể tải nhật ký hệ thống.')
    if (!overrideResponse.ok) throw new Error(overridePayload?.detail || 'Không thể tải lịch sử chỉnh sửa bảng công.')
    setData({
      events: auditPayload,
      attendanceOverrides: overridePayload,
    })
  }
  const refreshAudit = async () => {
    setRefreshing(true)
    setError('')
    try {
      await load()
    } catch (reason: any) {
      setError(String(reason?.message || reason))
    } finally {
      setRefreshing(false)
    }
  }
  useEffect(() => {
    setData(null)
    setError('')
    void refreshAudit()
    if (view !== 'audit') return undefined
    const intervalId = window.setInterval(() => { void refreshAudit() }, 15000)
    const onFocus = () => { void refreshAudit() }
    window.addEventListener('focus', onFocus)
    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener('focus', onFocus)
    }
  }, [view])
  const run = async () => {
    setRunning(true)
    setError('')
    setMessage('')
    try {
      const response = await apiRequest('/api/it/backups/run', { method: 'POST' })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail || 'Không thể tạo backup.')
      await load()
      setMessage(`Đã tạo backup ${payload?.name || ''}.`)
    } catch (reason: any) {
      setError(String(reason?.message || reason))
    } finally {
      setRunning(false)
    }
  }
  const downloadBackup = async (item: any) => {
    setError('')
    setMessage('')
    try {
      const response = await apiRequest(`/api/it/backups/${encodeURIComponent(item.name)}/download`)
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail || 'Không thể tải bản backup.')
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = item.name
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage(`Đã tải ${item.name}.`)
    } catch (reason: any) {
      setError(String(reason?.message || reason))
    }
  }
  const openRestore = (item: any) => {
    setError('')
    setMessage('')
    setRestoreConfirmation('')
    setRestoreCandidate(item)
  }
  const closeRestore = () => {
    if (restoring) return
    setRestoreCandidate(null)
    setRestoreConfirmation('')
  }
  const restore = async () => {
    if (!restoreCandidate) return
    const expected = `RESTORE ${restoreCandidate.name}`
    if (restoreConfirmation.trim() !== expected) {
      setError(`Nhập chính xác “${expected}” để xác nhận khôi phục.`)
      return
    }
    setRestoring(true)
    setError('')
    try {
      const response = await apiRequest(`/api/it/backups/${encodeURIComponent(restoreCandidate.name)}/restore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation: restoreConfirmation.trim() }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail || 'Không thể khôi phục database.')
      setRestoreCandidate(null)
      setRestoreConfirmation('')
      setMessage(`Đã khôi phục từ ${restoreCandidate.name}. Bản hiện tại trước khi khôi phục đã được lưu: ${payload?.recovery_point?.name || 'backup an toàn'}.`)
      await load()
    } catch (reason: any) {
      setError(String(reason?.message || reason))
    } finally {
      setRestoring(false)
    }
  }
  if (!data) return <div className={`status-message${error ? ' error' : ''}`}>{error || 'Đang tải dữ liệu IT…'}</div>
  if (view === 'backups') {
    return (
      <section style={{ display: 'grid', gap: 16 }}>
        {error && <div className="status-message error">{error}</div>}
        <div className="it-section-header" style={cardStyle}>
          <div>
            <h2 style={{ margin: 0 }}>Backup cơ sở dữ liệu</h2>
            <p style={{ color: '#64748b' }}>Tự động 23:30 mỗi ngày · giữ 30 bản · kiểm tra SHA-256.</p>
          </div>
          <button className="app-action-button" style={buttonStyle} disabled={running} onClick={() => void run()}>{running ? 'Đang backup…' : 'Backup ngay'}</button>
        </div>
        <div style={cardStyle}>
          <p><strong>Trạng thái:</strong> {data.capability.ready ? 'Sẵn sàng' : 'Chưa sẵn sàng'}</p>
          <p><strong>Công cụ:</strong> {data.capability.tool || 'Chưa tìm thấy'}</p>
          <p><strong>Thư mục:</strong> {data.capability.backup_directory}</p>
          <p className="backup-restore-scope">Phạm vi backup hiện tại: dữ liệu MySQL. Các tệp đính kèm cần được sao lưu riêng cùng thư mục <code>backend/uploads</code>.</p>
          <p className="backup-restore-notice"><strong>Khôi phục:</strong> {data.capability.restore_ready ? 'Sẵn sàng — bắt buộc kiểm SHA-256, xác nhận và tạo backup an toàn trước khi thực hiện.' : 'Chưa sẵn sàng — không tìm thấy công cụ mysql.'}</p>
          {message && <div className="status-message success">{message}</div>}
          <div style={{ maxHeight: 420, overflow: 'auto' }}>
            <table className="backup-history-table" style={{ width: '100%', minWidth: 920 }}><thead><tr><th>Tệp</th><th>Thời điểm</th><th>Kích thước</th><th>SHA-256</th><th>Thao tác</th></tr></thead>
              <tbody>{data.backups.map((item: any) => <tr key={item.name}><td>{item.name}</td><td>{new Date(item.created_at).toLocaleString('vi-VN')}</td><td>{Math.round(item.size_bytes / 1024)} KB</td><td><code>{item.sha256?.slice(0, 16)}…</code></td><td><div className="backup-row-actions"><button type="button" className="app-download-button" onClick={() => void downloadBackup(item)}>Tải xuống</button><button type="button" className="backup-restore-trigger" disabled={!data.capability.restore_ready} onClick={() => openRestore(item)}>Restore</button></div></td></tr>)}</tbody>
            </table>
          </div>
        </div>
        {restoreCandidate && (
          <div className="modal-backdrop backup-restore-backdrop" role="presentation" onMouseDown={closeRestore}>
            <section className="modal-card backup-restore-dialog" role="dialog" aria-modal="true" aria-labelledby="backup-restore-title" onMouseDown={(event) => event.stopPropagation()}>
              <div className="backup-restore-dialog-header">
                <div><p>KHÔI PHỤC DỮ LIỆU</p><h2 id="backup-restore-title">Khôi phục từ bản backup</h2></div>
                <button type="button" className="app-close-button" onClick={closeRestore} disabled={restoring} aria-label="Đóng"><AppIcon name="close" size={17} /></button>
              </div>
              <div className="backup-restore-warning">
                <strong>Thao tác này sẽ thay thế dữ liệu database hiện tại.</strong>
                <span>Hệ thống sẽ kiểm SHA-256 và tạo một bản backup an toàn của trạng thái hiện tại trước khi khôi phục.</span>
              </div>
              <dl className="backup-restore-summary"><div><dt>Bản sẽ dùng</dt><dd>{restoreCandidate.name}</dd></div><div><dt>Thời điểm</dt><dd>{new Date(restoreCandidate.created_at).toLocaleString('vi-VN')}</dd></div></dl>
              <label className="backup-restore-confirmation"><span>Nhập <code>RESTORE {restoreCandidate.name}</code> để xác nhận</span><input autoFocus value={restoreConfirmation} onChange={(event) => setRestoreConfirmation(event.target.value)} disabled={restoring} /></label>
              <div className="backup-restore-dialog-actions"><button type="button" className="ghost" onClick={closeRestore} disabled={restoring}>Hủy</button><button type="button" className="backup-restore-danger" onClick={() => void restore()} disabled={restoring || restoreConfirmation.trim() !== `RESTORE ${restoreCandidate.name}`}>{restoring ? 'Đang khôi phục…' : 'Khôi phục dữ liệu'}</button></div>
            </section>
          </div>
        )}
      </section>
    )
  }
  return (
    <section style={{ display: 'grid', gap: 16 }}>
      {error && <div className="status-message error">{error}</div>}
      <div style={cardStyle}>
      <div className="it-section-header" style={{ marginBottom: 14 }}>
        <div>
          <h2 style={{ margin: 0 }}>Nhật ký hệ thống · chỉ đọc</h2>
          <p style={{ margin: '5px 0 0', color: '#64748b', fontSize: 12 }}>Tự đồng bộ mỗi 15 giây và khi bạn quay lại cửa sổ.</p>
        </div>
        <button type="button" className="app-action-button" style={buttonStyle} disabled={refreshing} onClick={() => void refreshAudit()}>{refreshing ? 'Đang tải…' : 'Làm mới'}</button>
      </div>
      <div style={{ maxHeight: 430, overflow: 'auto' }}>
        <table style={{ width: '100%', minWidth: 1080 }}><thead><tr><th>Thời điểm</th><th>Tài khoản</th><th>Vai trò</th><th>Hành động</th><th>Đối tượng</th><th>Địa chỉ máy / IP</th><th>Trạng thái</th><th>Nội dung</th></tr></thead>
          <tbody>{data.events.map((item: any) => <tr key={item.id}><td>{new Date(item.occurred_at).toLocaleString('vi-VN')}</td><td>{item.actor_username}</td><td>{item.actor_role}</td><td>{item.action}</td><td>{item.resource_type} {item.resource_id || ''}</td><td>{item.device_address || 'Chưa định danh'}<br /><small>{item.source_ip || '—'}</small></td><td>{item.status}</td><td>{item.summary}</td></tr>)}</tbody>
        </table>
      </div>
      </div>
      <div style={cardStyle}>
        <h2 style={{ marginTop: 0 }}>Lịch sử chỉnh sửa bảng công · chỉ đọc</h2>
        <div style={{ maxHeight: 430, overflow: 'auto' }}>
          <table style={{ width: '100%', minWidth: 980 }}>
            <thead><tr><th>Thời điểm</th><th>Nhân viên</th><th>Ngày công</th><th className="audit-column-before">Trước</th><th className="audit-column-after">Sau</th><th>Giờ vào/ra mới</th><th>Người sửa</th><th>Địa chỉ máy / IP</th><th>Lý do</th></tr></thead>
            <tbody>{data.attendanceOverrides.map((item: any) => (
              <tr key={item.id}>
                <td>{new Date(item.changed_at).toLocaleString('vi-VN')}</td>
                <td>{item.employee_name}</td>
                <td>{item.work_date}</td>
                <td className="audit-cell-before"><span className="audit-value audit-value-before">{item.old_symbol || '—'}</span></td>
                <td className="audit-cell-after"><span className="audit-value audit-value-after">{item.new_symbol || '—'}</span></td>
                <td>{item.new_check_in || '—'} / {item.new_check_out || '—'}</td>
                <td>{item.changed_by_name}</td>
                <td>{item.device_address || 'Chưa định danh'}<br /><small>{item.source_ip || '—'}</small></td>
                <td>{item.reason}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

export function PersonalAttendanceGrid({ rows, period, onPeriodChange, onRefresh }: { rows: any[]; period: string; onPeriodChange: (value: string) => void; onRefresh: () => void }) {
  const orderedRows = useMemo(
    () => [...rows].sort((left, right) => String(left.work_date).localeCompare(String(right.work_date))),
    [rows],
  )
  const symbolNode = (row: any) => {
    const symbol = String(row.final_symbol || row.attendance_symbol || '').trim()
    const normalized = symbol.toUpperCase()
    if (!symbol || normalized === 'T7' || normalized === 'CN') return null
    const colors = normalized === 'X'
      ? { color: '#047857', border: '#6ee7b7', background: '#ecfdf5' }
      : normalized.includes('P')
        ? { color: '#b45309', border: '#fcd34d', background: '#fffbeb' }
        : normalized === 'CT'
          ? { color: '#1d4ed8', border: '#93c5fd', background: '#eff6ff' }
          : { color: '#be123c', border: '#fda4af', background: '#fff1f2' }
    return (
      <span style={{
        display: 'inline-flex',
        minWidth: 28,
        height: 28,
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 999,
        border: `1px solid ${colors.border}`,
        background: colors.background,
        color: colors.color,
        fontSize: 12,
        fontWeight: 800,
      }}>
        {symbol}
      </span>
    )
  }
  return (
    <section style={{ display: 'grid', gap: 16 }}>
      <div style={{ ...cardStyle, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'end', justifyContent: 'space-between' }}>
        <div><h2 style={{ margin: 0 }}>Chấm công của tôi</h2><p style={{ color: '#64748b', marginBottom: 0 }}>Chỉ hiển thị ngày và ký hiệu chấm công trong tháng đã chọn.</p></div>
        <div className="app-action-toolbar">
          <MonthYearSelect
            id="personal-attendance-period"
            value={period}
            onChange={onPeriodChange}
            compact
            yearLabel="Năm công"
            monthLabel="Tháng công"
          />
          <button className="app-action-button" style={buttonStyle} onClick={onRefresh}>Làm mới</button>
        </div>
      </div>
      <div style={{ ...cardStyle, padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto', maxWidth: '100%' }}>
          <table style={{ width: 'max-content', minWidth: '100%', borderCollapse: 'separate', borderSpacing: 0 }}>
            <thead>
              <tr>
                <th style={{ position: 'sticky', left: 0, zIndex: 3, minWidth: 150, background: '#f8fafc' }}>Tháng</th>
                {orderedRows.map((row) => {
                  const value = new Date(`${row.work_date}T00:00:00`)
                  const weekend = value.getDay() === 0 || value.getDay() === 6
                  return (
                    <th key={`weekday-${row.work_date}`} style={{ minWidth: 56, textAlign: 'center', color: weekend ? '#1d4ed8' : '#475569', background: weekend ? '#dbeafe' : '#f1f5f9' }}>
                      {value.toLocaleDateString('vi-VN', { weekday: 'short' }).replace('Th ', 'T')}
                    </th>
                  )
                })}
              </tr>
              <tr>
                <th style={{ position: 'sticky', left: 0, zIndex: 3, minWidth: 150, background: '#f8fafc' }}>{period}</th>
                {orderedRows.map((row) => {
                  const value = new Date(`${row.work_date}T00:00:00`)
                  const weekend = value.getDay() === 0 || value.getDay() === 6
                  return <th key={`date-${row.work_date}`} style={{ minWidth: 56, textAlign: 'center', background: weekend ? '#dbeafe' : '#e2e8f0' }}>{value.getDate()}</th>
                })}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ position: 'sticky', left: 0, zIndex: 2, minWidth: 150, background: '#fff', fontWeight: 800 }}>Ký hiệu</td>
                {orderedRows.map((row) => {
                  const value = new Date(`${row.work_date}T00:00:00`)
                  const weekend = value.getDay() === 0 || value.getDay() === 6
                  return (
                    <td key={row.work_date} style={{ minWidth: 56, height: 56, padding: 8, textAlign: 'center', background: weekend ? '#e8f3df' : '#fff' }}>
                      {weekend ? null : symbolNode(row)}
                    </td>
                  )
                })}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ ...cardStyle, padding: 20 }}>
        <div style={{ marginBottom: 18 }}>
          <h3 style={{ margin: 0, fontSize: 18, color: '#0f172a' }}>Nhật ký &amp; Lịch công chi tiết</h3>
          <p style={{ margin: '6px 0 0', color: '#64748b', fontSize: 13 }}>
            Chu kỳ tính công mặc định từ ngày 23 tháng trước đến ngày 22 tháng này. Di chuột vào nút ba chấm để xem toàn bộ mốc quẹt thẻ trong ngày.
          </p>
        </div>

        {orderedRows.length > 0 ? (
          <div style={{ overflowX: 'auto', paddingBottom: 6 }}>
            <div style={{ minWidth: 930 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(112px, 1fr))', gap: 10, marginBottom: 10 }}>
                {['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'].map((weekday) => (
                  <div key={weekday} style={{ textAlign: 'center', color: weekday === 'T7' ? '#6366f1' : weekday === 'CN' ? '#f43f5e' : '#475569', fontSize: 12, fontWeight: 800 }}>
                    {weekday}
                  </div>
                ))}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(112px, 1fr))', gap: 10 }}>
                {Array.from({ length: (() => {
                  const firstDate = new Date(`${orderedRows[0].work_date}T00:00:00`)
                  return firstDate.getDay() === 0 ? 6 : firstDate.getDay() - 1
                })() }).map((_, index) => (
                  <div key={`calendar-empty-${index}`} style={{ minHeight: 148, border: '1px dashed #cbd5e1', borderRadius: 16, background: '#f8fafc' }} />
                ))}

                {orderedRows.map((row) => {
                  const workDate = new Date(`${row.work_date}T00:00:00`)
                  const weekend = workDate.getDay() === 0 || workDate.getDay() === 6
                  const rawScans = Array.isArray(row.raw_scans) ? row.raw_scans : []
                  return (
                    <article
                      key={`calendar-${row.work_date}`}
                      style={{
                        position: 'relative',
                        minHeight: 148,
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        border: weekend ? '1px solid #334155' : '1px solid #dbe7f3',
                        borderRadius: 16,
                        background: weekend ? '#f8fafc' : '#ffffff',
                        padding: 12,
                        boxShadow: weekend ? 'none' : '0 5px 16px rgba(15, 23, 42, 0.06)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <strong style={{ fontSize: 18, color: '#0f172a' }}>{workDate.getDate()}</strong>
                        {weekend ? (
                          <span style={{ border: '1px solid #e2e8f0', borderRadius: 999, padding: '3px 8px', color: workDate.getDay() === 6 ? '#4f46e5' : '#e11d48', fontSize: 11, fontWeight: 700 }}>
                            {workDate.getDay() === 6 ? 'T7' : 'CN'}
                          </span>
                        ) : symbolNode(row)}
                      </div>

                      {!weekend && (
                        <div style={{ display: 'grid', gap: 6, marginTop: 12, fontSize: 11 }}>
                          {row.check_in ? <div><span style={{ color: '#10b981' }}>●</span> <span style={{ color: '#64748b' }}>In:</span> <b style={{ marginLeft: 4 }}>{String(row.check_in).slice(0, 5)}</b></div> : <div style={{ color: '#526979' }}>● Không quẹt</div>}
                          {row.check_out ? <div><span style={{ color: '#3b82f6' }}>●</span> <span style={{ color: '#64748b' }}>Out:</span> <b style={{ marginLeft: 4 }}>{String(row.check_out).slice(0, 5)}</b></div> : null}
                        </div>
                      )}

                      {!weekend && (
                        <div style={{ display: 'flex', alignItems: 'end', justifyContent: 'space-between', gap: 8, marginTop: 12 }}>
                          <div style={{ fontSize: 11, lineHeight: 1.5 }}>
                            {Number(row.late_minutes || 0) > 0 && <div style={{ color: '#ea580c' }}>Trễ {Number(row.late_minutes)}m</div>}
                            {Number(row.early_minutes || 0) > 0 && <div style={{ color: '#e11d48' }}>Sớm {Number(row.early_minutes)}m</div>}
                          </div>
                          {rawScans.length > 0 && (
                            <div className="group" style={{ position: 'relative' }}>
                              <button type="button" aria-label={`Xem lịch sử quẹt thẻ ngày ${workDate.toLocaleDateString('vi-VN')}`} style={{ width: 38, height: 30, border: '1px solid #cbd5e1', borderRadius: 10, background: '#f1f5f9', color: '#475569', cursor: 'pointer', fontWeight: 900 }}>•••</button>
                              <div className="hidden group-hover:block group-focus-within:block" style={{ position: 'absolute', zIndex: 20, bottom: 38, left: '50%', width: 210, transform: 'translateX(-50%)', border: '1px solid #bfdbfe', borderRadius: 12, background: '#e8f0ff', padding: 10, boxShadow: '0 14px 34px rgba(15, 23, 42, 0.22)' }}>
                                <p style={{ margin: '0 0 8px', color: '#64748b', fontSize: 11, fontWeight: 800, textTransform: 'uppercase' }}>Lịch sử quẹt thẻ trong ngày</p>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 5 }}>
                                  {rawScans.map((scan: unknown, index: number) => <span key={`${row.work_date}-${index}`} style={{ borderRadius: 5, background: '#ffffff', padding: '4px 5px', textAlign: 'center', color: '#334155', fontSize: 11 }}>{String(scan).slice(0, 5)}</span>)}
                                </div>
                                {row.override_reason && <p style={{ margin: '8px 0 0', color: '#b45309', fontSize: 11 }}>Đã điều chỉnh: {row.override_reason}</p>}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </article>
                  )
                })}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ padding: 36, textAlign: 'center', color: '#64748b' }}>Chưa có dữ liệu chấm công trong tháng đã chọn.</div>
        )}
      </div>
    </section>
  )
}
