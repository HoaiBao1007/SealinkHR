import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { DateTimeRangePicker, defaultTimeOffRange, snapDateTimeToHalfHour } from './DateTimeRangePicker'
import { BUSINESS_TRAVEL_REQUEST, LEAVE_REQUEST, TimeOffRequestIntent, type LeaveBalance } from './TimeOffRequestIntent'
import { TimeOffAttachmentUpload, type TimeOffAttachment } from './TimeOffAttachmentUpload'
import { AppIcon } from '../../shared/ui/AppIcon'
import './time-off-management.css'

type ApiRequest = (path: string, init?: RequestInit) => Promise<Response>

type ApproverOption = {
  user_id: number
  employee_id: number | null
  full_name: string
  source: string
  is_default: boolean
}

type Bootstrap = {
  employee: {
    id: number
    full_name: string
    employee_code: string
    department_id: number | null
    department_name: string | null
  } | null
  manager: {
    user_id: number
    employee_id: number | null
    full_name: string
    source: string
  } | null
  approver_options: ApproverOption[]
  can_submit: boolean
  pending_approval_count: number
  handover_candidates: Array<{ id: number; full_name: string; department_name?: string | null }>
  departments: Array<{ id: number; name: string }>
  request_types: Array<{ value: string; label: string }>
  leave_balance: LeaveBalance | null
}

type ApprovalAction = {
  id: number
  action: string
  from_status: string
  to_status: string
  comment?: string | null
  actor_name?: string | null
  created_at: string
}

type TimeOffRequest = {
  id: number
  employee: { id: number | null; full_name: string; employee_code?: string | null }
  department: { id: number | null; name?: string | null }
  manager: { employee_id: number | null; user_id: number | null; full_name?: string | null }
  request_type?: string | null
  request_type_label?: string | null
  start_date: string
  end_date: string
  start_at: string
  end_at: string
  total_days: number
  day_part: string
  day_part_label?: string | null
  reason?: string | null
  handover_employee?: { id: number; full_name: string } | null
  handover_notes?: string | null
  business_travel_location?: string | null
  business_travel_policy_acknowledged?: boolean | null
  attachments?: TimeOffAttachment[]
  manager_comment?: string | null
  status: 'PENDING_MANAGER' | 'APPROVED' | 'REJECTED' | 'MORE_INFO_REQUIRED' | string
  status_label: string
  submitted_at: string
  updated_at: string
  approved_at?: string | null
  is_own: boolean
  is_assigned_approver: boolean
  can_act: boolean
  can_edit: boolean
  can_edit_schedule: boolean
  actions?: ApprovalAction[]
}

type RequestFormState = {
  request_type: string
  approver_user_id: string
  start_at: string
  end_at: string
  reason: string
  handover_employee_id: string
  handover_notes: string
  business_travel_location: string
  business_travel_policy_acknowledged: boolean
}

type ViewKey = 'calendar' | 'new' | 'mine' | 'pending'

type Props = {
  apiRequest: ApiRequest
  userRole: string
  focusRequestId?: number | null
  focusKey?: number | null
  onNavigate?: (path: string) => void
}

const STATUS_OPTIONS = [
  { value: '', label: 'Tất cả được phép xem' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'PENDING_MANAGER', label: 'Under Review' },
  { value: 'MORE_INFO_REQUIRED', label: 'More Information Required' },
  { value: 'REJECTED', label: 'Rejected' },
]

const STATUS_LABELS: Record<string, string> = {
  PENDING_MANAGER: 'Under Review',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  MORE_INFO_REQUIRED: 'More Information Required',
}

const ACTION_LABELS: Record<string, string> = {
  SUBMIT: 'Đã gửi yêu cầu',
  EDIT: 'Đã chỉnh sửa yêu cầu',
  RESUBMIT: 'Đã bổ sung và gửi lại',
  APPROVE: 'Đã phê duyệt',
  REJECT: 'Đã từ chối',
  REQUEST_INFO: 'Yêu cầu bổ sung thông tin',
  IT_ADMIN_UPDATE_SCHEDULE: 'IT Admin đã chỉnh thời gian nghỉ',
}

function isoDate(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const twoDigits = (part: number) => String(part).padStart(2, '0')
  return `${twoDigits(date.getHours())}:${twoDigits(date.getMinutes())} ${twoDigits(date.getDate())}/${twoDigits(date.getMonth() + 1)}/${date.getFullYear()}`
}

function monthTitle(month: Date) {
  return `Tháng ${month.getMonth() + 1}, ${month.getFullYear()}`
}

function calendarWeeks(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const mondayOffset = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(first.getDate() - mondayOffset)
  return Array.from({ length: 6 }, (_, weekIndex) => (
    Array.from({ length: 7 }, (_, dayIndex) => {
      const day = new Date(start)
      day.setDate(start.getDate() + weekIndex * 7 + dayIndex)
      return day
    })
  ))
}

function eventsForCalendarDay(events: TimeOffRequest[], day: string) {
  return events
    .filter((item) => item.start_date <= day && item.end_date >= day)
    .sort((a, b) => a.employee.full_name.localeCompare(b.employee.full_name, 'vi-VN') || a.id - b.id)
}

type CalendarEventGroup = {
  key: string
  employeeName: string
  primary: TimeOffRequest
  items: TimeOffRequest[]
}

function groupCalendarEventsByEmployee(events: TimeOffRequest[]) {
  const grouped = new Map<string, TimeOffRequest[]>()
  events.forEach((item) => {
    const employeeKey = item.employee.id != null ? `employee-${item.employee.id}` : `name-${item.employee.full_name}`
    grouped.set(employeeKey, [...(grouped.get(employeeKey) || []), item])
  })
  return Array.from(grouped.entries()).map(([key, items]): CalendarEventGroup => ({
    key,
    employeeName: items[0]?.employee.full_name || 'Nhân viên',
    primary: [...items].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime() || b.id - a.id)[0],
    items,
  }))
}

function formatCalendarDay(value: string) {
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

function emptyForm(defaultApproverUserId?: number | null): RequestFormState {
  const range = defaultTimeOffRange()
  return {
    request_type: LEAVE_REQUEST,
    approver_user_id: defaultApproverUserId ? String(defaultApproverUserId) : '',
    start_at: range.startAt,
    end_at: range.endAt,
    reason: '',
    handover_employee_id: '',
    handover_notes: '',
    business_travel_location: '',
    business_travel_policy_acknowledged: false,
  }
}

async function responseJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || 'Không thể xử lý yêu cầu.')
  return payload as T
}

function managerSourceLabel(source?: string) {
  if (source === 'PARENT_MANAGER') return 'Manager cấp trên'
  if (source === 'OTHER_DEPARTMENT_MANAGER') return 'Manager phòng ban khác'
  if (source === 'FALLBACK_APPROVER') return 'Người duyệt dự phòng'
  return 'Manager phòng ban'
}

export function TimeOffManagement({ apiRequest, userRole, focusRequestId, focusKey, onNavigate }: Props) {
  const [view, setView] = useState<ViewKey>('calendar')
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1))
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [calendarEvents, setCalendarEvents] = useState<TimeOffRequest[]>([])
  const [myRequests, setMyRequests] = useState<TimeOffRequest[]>([])
  const [pendingRequests, setPendingRequests] = useState<TimeOffRequest[]>([])
  const [selectedRequest, setSelectedRequest] = useState<TimeOffRequest | null>(null)
  const [selectedCalendarDay, setSelectedCalendarDay] = useState<{ date: string; items: TimeOffRequest[] } | null>(null)
  const [form, setForm] = useState<RequestFormState>(emptyForm)
  const [editingRequestId, setEditingRequestId] = useState<number | null>(null)
  const [scheduleDraft, setScheduleDraft] = useState<{ startAt: string; endAt: string } | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [employeeFilter, setEmployeeFilter] = useState('')
  const [actionMode, setActionMode] = useState<'REJECT' | 'REQUEST_INFO' | null>(null)
  const [actionComment, setActionComment] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<TimeOffAttachment[]>([])

  const weeks = useMemo(() => calendarWeeks(month), [month])
  const calendarStart = isoDate(weeks[0][0])
  const calendarEnd = isoDate(weeks[5][6])
  const today = isoDate(new Date())

  const visibleCalendarEvents = useMemo(() => {
    const query = employeeFilter.trim().toLocaleLowerCase('vi-VN')
    if (!query) return calendarEvents
    return calendarEvents.filter((item) => item.employee.full_name.toLocaleLowerCase('vi-VN').includes(query))
  }, [calendarEvents, employeeFilter])

  async function loadCalendar() {
    const params = new URLSearchParams({ start_date: calendarStart, end_date: calendarEnd })
    if (statusFilter) params.set('status', statusFilter)
    if (departmentFilter) params.set('department_id', departmentFilter)
    const payload = await responseJson<{ events: TimeOffRequest[] }>(
      await apiRequest(`/api/time-off/calendar?${params.toString()}`),
    )
    setCalendarEvents(payload.events || [])
  }

  async function loadWorkspace(showLoading = false) {
    if (showLoading) setLoading(true)
    setError(null)
    try {
      const [bootstrapData, mineData, pendingData] = await Promise.all([
        responseJson<Bootstrap>(await apiRequest('/api/time-off/bootstrap')),
        apiRequest('/api/time-off/requests/mine').then((response) => response.ok ? response.json() : []),
        responseJson<TimeOffRequest[]>(await apiRequest('/api/time-off/requests/pending')),
      ])
      setBootstrap(bootstrapData)
      setForm((current) => ({
        ...current,
        approver_user_id: current.approver_user_id || String(bootstrapData.manager?.user_id || ''),
      }))
      setMyRequests(Array.isArray(mineData) ? mineData : [])
      setPendingRequests(pendingData || [])
      await loadCalendar()
    } catch (requestError) {
      setError((requestError as Error).message)
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  async function openRequest(requestId: number) {
    setError(null)
    try {
      const detail = await responseJson<TimeOffRequest>(await apiRequest(`/api/time-off/requests/${requestId}`))
      setSelectedRequest(detail)
      setActionMode(null)
      setActionComment('')
      setScheduleDraft(null)
    } catch (requestError) {
      setError((requestError as Error).message)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadWorkspace(true), 0)
    return () => window.clearTimeout(timer)
    // The API request wrapper is stable for one authenticated App session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!bootstrap) return
    const timer = window.setTimeout(() => {
      void loadCalendar().catch((requestError) => setError((requestError as Error).message))
    }, 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calendarStart, calendarEnd, statusFilter, departmentFilter])

  useEffect(() => {
    if (!focusRequestId) return
    const timer = window.setTimeout(() => void openRequest(focusRequestId), 0)
    return () => window.clearTimeout(timer)
    // focusKey lets the same notification target reopen after a prior close.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequestId, focusKey])

  async function submitRequest(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    if (!form.start_at || !form.end_at || form.end_at <= form.start_at) {
      setError('Thời gian kết thúc phải sau thời gian bắt đầu.')
      return
    }
    if (form.request_type === BUSINESS_TRAVEL_REQUEST && (!form.business_travel_policy_acknowledged || attachments.length === 0)) {
      setError(!form.business_travel_policy_acknowledged
        ? 'Bạn cần xác nhận đã xem qua quy định công tác trước khi gửi yêu cầu.'
        : 'Vui lòng upload quyết định của BGĐ trước khi gửi yêu cầu công tác.')
      return
    }
    setSaving(true)
    try {
      const payload = {
        ...form,
        approver_user_id: form.approver_user_id ? Number(form.approver_user_id) : null,
        handover_employee_id: form.handover_employee_id ? Number(form.handover_employee_id) : null,
        handover_notes: form.handover_notes.trim() || null,
        attachment_ids: attachments.filter((attachment) => attachment.is_staged).map((attachment) => attachment.id),
      }
      const path = editingRequestId
        ? `/api/time-off/requests/${editingRequestId}`
        : '/api/time-off/requests'
      const method = editingRequestId ? 'PUT' : 'POST'
      const result = await responseJson<TimeOffRequest>(await apiRequest(path, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }))
      setNotice(editingRequestId ? 'Đã lưu thay đổi và gửi lại yêu cầu cho Manager.' : 'Đã gửi yêu cầu nghỉ cho Manager.')
      setForm(emptyForm(bootstrap?.manager?.user_id))
      setAttachments([])
      setEditingRequestId(null)
      setView('mine')
      await loadWorkspace()
      await openRequest(result.id)
    } catch (requestError) {
      setError((requestError as Error).message)
    } finally {
      setSaving(false)
    }
  }

  function editRequest(request: TimeOffRequest) {
    setEditingRequestId(request.id)
    setForm({
      request_type: [LEAVE_REQUEST, 'WORK_FROM_HOME_REQUEST', BUSINESS_TRAVEL_REQUEST].includes(request.request_type || '')
        ? request.request_type!
        : LEAVE_REQUEST,
      approver_user_id: request.manager.user_id ? String(request.manager.user_id) : String(bootstrap?.manager?.user_id || ''),
      start_at: snapDateTimeToHalfHour(request.start_at.slice(0, 16)),
      end_at: snapDateTimeToHalfHour(request.end_at.slice(0, 16)),
      reason: request.reason || '',
      handover_employee_id: request.handover_employee?.id ? String(request.handover_employee.id) : '',
      handover_notes: request.handover_notes || '',
      business_travel_location: request.business_travel_location || '',
      business_travel_policy_acknowledged: Boolean(request.business_travel_policy_acknowledged),
    })
    setAttachments(request.attachments || [])
    setScheduleDraft(null)
    setSelectedRequest(null)
    setView('new')
  }

  function beginScheduleEdit(request: TimeOffRequest) {
    setActionMode(null)
    setActionComment('')
    setScheduleDraft({
      startAt: snapDateTimeToHalfHour(request.start_at.slice(0, 16)),
      endAt: snapDateTimeToHalfHour(request.end_at.slice(0, 16)),
    })
  }

  async function saveScheduleEdit() {
    if (!selectedRequest || !scheduleDraft) return
    if (!scheduleDraft.startAt || !scheduleDraft.endAt || scheduleDraft.endAt <= scheduleDraft.startAt) {
      setError('Thời gian kết thúc phải sau thời gian bắt đầu.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const detail = await responseJson<TimeOffRequest>(await apiRequest(
        `/api/time-off/requests/${selectedRequest.id}/schedule`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ start_at: scheduleDraft.startAt, end_at: scheduleDraft.endAt }),
        },
      ))
      setSelectedRequest(detail)
      setScheduleDraft(null)
      setNotice('Đã cập nhật ngày và giờ nghỉ của nhân viên.')
      await loadWorkspace()
    } catch (requestError) {
      setError((requestError as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function downloadAttachment(attachment: TimeOffAttachment) {
    if (!selectedRequest) return
    setError(null)
    try {
      const response = await apiRequest(`/api/time-off/requests/${selectedRequest.id}/attachments/${attachment.id}/download`)
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string }
        throw new Error(payload.detail || 'Không thể tải file đính kèm.')
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = attachment.file_name
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (downloadError) {
      setError((downloadError as Error).message)
    }
  }

  async function applyAction(action: 'APPROVE' | 'REJECT' | 'REQUEST_INFO') {
    if (!selectedRequest) return
    if ((action === 'REJECT' || action === 'REQUEST_INFO') && !actionComment.trim()) {
      setError('Vui lòng nhập lý do hoặc nội dung cần bổ sung.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const detail = await responseJson<TimeOffRequest>(await apiRequest(
        `/api/time-off/requests/${selectedRequest.id}/actions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, comment: actionComment.trim() || null }),
        },
      ))
      setSelectedRequest(detail)
      setActionMode(null)
      setActionComment('')
      setNotice(action === 'APPROVE' ? 'Đã phê duyệt yêu cầu.' : action === 'REJECT' ? 'Đã từ chối yêu cầu.' : 'Đã yêu cầu nhân viên bổ sung thông tin.')
      await loadWorkspace()
    } catch (requestError) {
      setError((requestError as Error).message)
    } finally {
      setSaving(false)
    }
  }

  function changeMonth(offset: number) {
    setMonth((current) => new Date(current.getFullYear(), current.getMonth() + offset, 1))
  }

  const viewTabs: Array<{ key: ViewKey; label: string; count?: number }> = [
    { key: 'calendar', label: 'Time Off Calendar' },
    { key: 'new', label: editingRequestId ? 'Chỉnh sửa đơn' : 'Request Form' },
    { key: 'mine', label: 'My Requests', count: myRequests.length },
    { key: 'pending', label: 'Pending My Approval', count: pendingRequests.length },
  ]

  return (
    <section className="time-off-shell">
      <header className="time-off-hero">
        <div>
          <span className="time-off-eyebrow">People operations · In-app workflow</span>
          <h2>Time Off Management</h2>
          <p>Gửi đơn nghỉ, làm việc tại nhà hoặc công tác; phê duyệt theo cơ cấu phòng ban trong một workspace thống nhất.</p>
        </div>
        <button type="button" className="time-off-primary" onClick={() => { setEditingRequestId(null); setForm(emptyForm(bootstrap?.manager?.user_id)); setView('new') }} disabled={!bootstrap?.can_submit}>
          <AppIcon name="plus" size={16} /> Tạo yêu cầu
        </button>
      </header>

      <nav className="time-off-view-tabs" aria-label="Time Off views">
        {viewTabs.map((tab) => (
          <button key={tab.key} type="button" className={view === tab.key ? 'is-active' : ''} onClick={() => setView(tab.key)}>
            {tab.label}
            {typeof tab.count === 'number' && tab.count > 0 && <span>{tab.count}</span>}
          </button>
        ))}
      </nav>

      {error && <div className="time-off-alert is-error"><AppIcon name="warning" size={16} />{error}<button type="button" className="app-close-button app-close-button--compact" onClick={() => setError(null)} aria-label="Đóng thông báo lỗi"><AppIcon name="close" size={14} /></button></div>}
      {notice && <div className="time-off-alert is-success"><AppIcon name="check" size={16} />{notice}<button type="button" className="app-close-button app-close-button--compact" onClick={() => setNotice(null)} aria-label="Đóng thông báo"><AppIcon name="close" size={14} /></button></div>}

      {loading ? (
        <div className="time-off-loading"><span /><p>Đang tải Time Off workspace…</p></div>
      ) : view === 'calendar' ? (
        <div className="time-off-calendar-card">
          <div className="time-off-calendar-toolbar">
            <div className="time-off-month-nav">
              <button type="button" onClick={() => changeMonth(-1)} aria-label="Tháng trước">‹</button>
              <button type="button" onClick={() => setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}>Today</button>
              <button type="button" onClick={() => changeMonth(1)} aria-label="Tháng sau">›</button>
              <h3>{monthTitle(month)}</h3>
            </div>
            <div className="time-off-filters">
              <label>
                <span>Trạng thái</span>
                <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                <span>Phòng ban</span>
                <select value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)}>
                  <option value="">Tất cả phòng ban</option>
                  {bootstrap?.departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                </select>
              </label>
              <label className="time-off-search-filter">
                <span>Nhân viên</span>
                <input value={employeeFilter} onChange={(event) => setEmployeeFilter(event.target.value)} placeholder="Tìm theo tên…" />
              </label>
            </div>
          </div>

          <div className="time-off-calendar-privacy">
            <span>◉</span>
            Calendar chung hiển thị đơn Approved và đơn đang chờ Manager duyệt; lý do nghỉ luôn được ẩn trên lịch chung. Chỉ Manager được backend gán mới có quyền duyệt đơn.
          </div>

          <div className="time-off-weekdays">
            {['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'].map((day) => <span key={day}>{day}</span>)}
          </div>
          <div className="time-off-calendar-grid">
            {weeks.map((week, weekIndex) => {
              return (
                <div className="time-off-calendar-week" key={weekIndex}>
                  {week.map((day) => {
                    const value = isoDate(day)
                    const outside = day.getMonth() !== month.getMonth()
                    const dayEvents = eventsForCalendarDay(visibleCalendarEvents, value)
                    const eventGroups = groupCalendarEventsByEmployee(dayEvents)
                    const visibleEventGroups = eventGroups.slice(0, 2)
                    const hiddenGroupCount = eventGroups.length - visibleEventGroups.length
                    return (
                      <div
                        key={value}
                        className={`time-off-day-cell${outside ? ' is-outside' : ''}${value === today ? ' is-today' : ''}`}
                      >
                        <span>{day.getDate()}</span>
                        <div className="time-off-day-events">
                          {visibleEventGroups.map((group) => (
                            <button
                              type="button"
                              key={`${group.key}-${value}`}
                              className={`time-off-event status-${group.primary.status.toLowerCase()}`}
                              onClick={() => group.items.length === 1 ? void openRequest(group.primary.id) : setSelectedCalendarDay({ date: value, items: group.items })}
                              title={group.items.length === 1
                                ? `${group.employeeName} · ${group.primary.department.name || 'Chưa có phòng ban'} · ${formatDateTime(group.primary.start_at)} → ${formatDateTime(group.primary.end_at)} · ${group.primary.status_label}`
                                : `${group.employeeName} · ${group.items.length} đơn nghỉ trong ngày · Nhấn để xem chi tiết`}
                            >
                              <span className="time-off-event-dot" />
                              <strong className="time-off-event-name">{group.employeeName}</strong>
                              {group.items.length > 1 && <span className="time-off-event-count" aria-label={`${group.items.length} đơn nghỉ`}>{group.items.length}</span>}
                            </button>
                          ))}
                          {hiddenGroupCount > 0 && (
                            <button
                              type="button"
                              className="time-off-day-more"
                              onClick={() => setSelectedCalendarDay({ date: value, items: dayEvents })}
                            >
                              +{hiddenGroupCount} Xem thêm
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
          {visibleCalendarEvents.length === 0 && <div className="time-off-calendar-empty">Không có yêu cầu phù hợp với bộ lọc trong khoảng lịch này.</div>}
        </div>
      ) : view === 'new' ? (
        <div className="time-off-form-layout">
          <form className="time-off-request-form" onSubmit={submitRequest}>
            <div className="time-off-section-heading">
              <div><span>01</span><h3>{editingRequestId ? 'Chỉnh sửa yêu cầu' : 'Thông tin người gửi'}</h3></div>
              <p>Nhân viên và phòng ban lấy từ tài khoản đăng nhập; Manager mặc định có thể đổi trong danh sách hợp lệ.</p>
            </div>
            <div className="time-off-identity-grid">
              <div><span>Nhân viên</span><strong>{bootstrap?.employee?.full_name || 'Chưa liên kết hồ sơ'}</strong></div>
              <div><span>Mã nhân viên</span><strong>{bootstrap?.employee?.employee_code || '—'}</strong></div>
              <div><span>Phòng ban</span><strong>{bootstrap?.employee?.department_name || 'Chưa cấu hình'}</strong></div>
              <div className="time-off-manager-choice"><span>Manager duyệt</span><select value={form.approver_user_id} onChange={(event) => setForm({ ...form, approver_user_id: event.target.value })} required><option value="">Chưa xác định</option>{(bootstrap?.approver_options || []).map((option) => <option key={option.user_id} value={option.user_id}>{option.full_name}{option.is_default ? ' · Mặc định' : ''} · {managerSourceLabel(option.source)}</option>)}</select><small>Backend xác thực danh sách người duyệt.</small></div>
            </div>

            <div className="time-off-section-heading">
              <div><span>02</span><h3>Chi tiết yêu cầu</h3></div>
              <p>Chọn loại yêu cầu, sau đó nhập thời gian và thông tin cần thiết.</p>
            </div>
            <div className="time-off-field-grid time-off-range-grid">
              <TimeOffRequestIntent
                value={form.request_type}
                leaveBalance={bootstrap?.leave_balance}
                onChange={(requestType) => setForm((current) => ({
                  ...current,
                  request_type: requestType,
                  business_travel_location: requestType === BUSINESS_TRAVEL_REQUEST ? current.business_travel_location : '',
                  business_travel_policy_acknowledged: requestType === BUSINESS_TRAVEL_REQUEST ? current.business_travel_policy_acknowledged : false,
                }))}
              />
              <DateTimeRangePicker
                startAt={form.start_at}
                endAt={form.end_at}
                onChange={({ startAt, endAt }) => setForm({ ...form, start_at: startAt, end_at: endAt })}
              />
            </div>

            <div className="time-off-section-heading">
              <div><span>03</span><h3>Nội dung & bàn giao</h3></div>
              <p>Nội dung này chỉ hiển thị cho bạn và người có quyền duyệt đơn.</p>
            </div>
            <div className="time-off-field-grid">
              {form.request_type === BUSINESS_TRAVEL_REQUEST && (
                <label><span>Địa điểm công tác *</span><input value={form.business_travel_location} maxLength={255} onChange={(event) => setForm({ ...form, business_travel_location: event.target.value })} placeholder="Ví dụ: Hà Nội, Hải Phòng, Singapore…" required /></label>
              )}
              <label className="is-wide"><span>{form.request_type === BUSINESS_TRAVEL_REQUEST ? 'Lý do đi công tác *' : 'Lý do yêu cầu *'}</span><textarea value={form.reason} rows={2} maxLength={255} onChange={(event) => setForm({ ...form, reason: event.target.value })} placeholder={form.request_type === BUSINESS_TRAVEL_REQUEST ? 'Mô tả mục đích công tác…' : 'Mô tả ngắn gọn nội dung yêu cầu…'} required /></label>
              {form.request_type === BUSINESS_TRAVEL_REQUEST && (
                <label className="time-off-travel-policy"><input type="checkbox" checked={form.business_travel_policy_acknowledged} onChange={(event) => setForm({ ...form, business_travel_policy_acknowledged: event.target.checked })} required /><span>Tôi đã xem qua và đồng ý tuân thủ quy định công tác của công ty.</span></label>
              )}
              <TimeOffAttachmentUpload
                apiRequest={apiRequest}
                requestType={form.request_type}
                attachments={attachments}
                onChange={setAttachments}
                disabled={saving}
              />
              <details className="time-off-handover-details">
                <summary><span>Bàn giao công việc</span><small>{form.handover_employee_id || form.handover_notes ? 'Đã có thông tin' : 'Không bắt buộc'}</small></summary>
                <div>
                  <label><span>Người bàn giao</span><select value={form.handover_employee_id} onChange={(event) => setForm({ ...form, handover_employee_id: event.target.value })}><option value="">Chưa chọn</option>{bootstrap?.handover_candidates.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}{employee.department_name ? ` · ${employee.department_name}` : ''}</option>)}</select></label>
                  <label><span>Ghi chú bàn giao</span><textarea value={form.handover_notes} rows={2} maxLength={2000} onChange={(event) => setForm({ ...form, handover_notes: event.target.value })} placeholder="Công việc, deadline và tài liệu cần bàn giao…" /></label>
                </div>
              </details>
            </div>
            {bootstrap && !bootstrap.can_submit && <div className="time-off-config-warning">Hồ sơ chưa có phòng ban/Manager có tài khoản. Admin cần hoàn tất cấu hình Department & Manager trước khi gửi.</div>}
            <div className="time-off-form-actions">
              {editingRequestId && <button type="button" className="time-off-secondary" onClick={() => { setEditingRequestId(null); setForm(emptyForm(bootstrap?.manager?.user_id)) }}>Hủy chỉnh sửa</button>}
              <button type="submit" className="time-off-primary" disabled={saving || !bootstrap?.can_submit || (form.request_type === BUSINESS_TRAVEL_REQUEST && (!form.business_travel_policy_acknowledged || attachments.length === 0))}>{saving ? 'Đang gửi…' : editingRequestId ? 'Lưu và gửi lại Manager' : 'Gửi yêu cầu'}</button>
            </div>
          </form>
          <section className="time-off-form-aside" aria-labelledby="time-off-approval-workflow-title">
            <div className="time-off-form-aside-heading">
              <div className="time-off-aside-icon" aria-hidden="true"><AppIcon name="arrow-right" size={19} /></div>
              <div>
                <p>QUY TRÌNH</p>
                <h3 id="time-off-approval-workflow-title">Luồng phê duyệt</h3>
              </div>
            </div>
            <ol>
              <li><span>1</span><div><strong>Submit</strong><p>Backend xác nhận danh tính và kiểm tra trùng thời gian.</p></div></li>
              <li><span>2</span><div><strong>Manager review</strong><p>Đơn vào đúng “Pending My Approval” và tạo thông báo.</p></div></li>
              <li><span>3</span><div><strong>In-app result</strong><p>Kết quả được gửi vào tài khoản nhân viên trên website.</p></div></li>
            </ol>
            {userRole === 'HR_ADMIN' || userRole === 'ADMIN' || userRole === 'DIRECTOR' || userRole === 'IT_ADMIN' ? (
              <button className="time-off-aside-link" type="button" onClick={() => onNavigate?.(userRole === 'HR_ADMIN' ? '/hr/departments' : '/admin/departments')}>Mở cấu hình Department &amp; Manager <AppIcon name="arrow-right" size={15} /></button>
            ) : null}
          </section>
        </div>
      ) : (
        <div className="time-off-list-card">
          <div className="time-off-list-heading">
            <div><h3>{view === 'mine' ? 'My Requests' : 'Pending My Approval'}</h3><p>{view === 'mine' ? 'Toàn bộ yêu cầu nghỉ của bạn và trạng thái hiện tại.' : 'Chỉ các đơn được backend gán trực tiếp cho tài khoản của bạn.'}</p></div>
            {view === 'mine' && <button type="button" className="time-off-primary" onClick={() => setView('new')}><AppIcon name="plus" size={16} /> Tạo yêu cầu</button>}
          </div>
          <div className="time-off-request-list">
            {(view === 'mine' ? myRequests : pendingRequests).map((request) => (
              <button type="button" key={request.id} className="time-off-request-row" onClick={() => void openRequest(request.id)}>
                <span className={`time-off-status-mark status-${request.status.toLowerCase()}`} />
                <div className="time-off-request-main"><strong>{view === 'mine' ? request.request_type_label || 'Yêu cầu nghỉ' : request.employee.full_name}</strong><span>{formatDateTime(request.start_at)} → {formatDateTime(request.end_at)} · {request.total_days} ngày công</span></div>
                <div className="time-off-request-department"><span>{request.department.name || 'Chưa có phòng ban'}</span><small>{view === 'mine' ? `Manager: ${request.manager.full_name || '—'}` : request.request_type_label}</small></div>
                <span className={`time-off-status status-${request.status.toLowerCase()}`}>{STATUS_LABELS[request.status] || request.status_label}</span>
                <span className="time-off-row-arrow">›</span>
              </button>
            ))}
            {(view === 'mine' ? myRequests : pendingRequests).length === 0 && (
              <div className="time-off-empty-state"><div><AppIcon name="check" size={22} /></div><h4>{view === 'mine' ? 'Bạn chưa có yêu cầu nghỉ' : 'Không có đơn chờ duyệt'}</h4><p>{view === 'mine' ? 'Tạo yêu cầu mới để bắt đầu quy trình.' : 'Các yêu cầu mới sẽ xuất hiện tại đây.'}</p></div>
            )}
          </div>
        </div>
      )}

      {selectedCalendarDay && createPortal(
        <div className="ui-modal-backdrop time-off-day-events-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedCalendarDay(null) }}>
          <section className="time-off-day-events-modal" role="dialog" aria-modal="true" aria-label="Danh sách nhân viên nghỉ trong ngày" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span>TIME OFF CALENDAR</span><h3>Ngày {formatCalendarDay(selectedCalendarDay.date)}</h3><p>{selectedCalendarDay.items.length} đơn nghỉ trong ngày này.</p></div>
              <button type="button" className="app-close-button" onClick={() => setSelectedCalendarDay(null)} aria-label="Đóng"><AppIcon name="close" size={17} /></button>
            </header>
            <div className="time-off-day-events-list">
              {selectedCalendarDay.items.map((item) => (
                <button type="button" key={item.id} className="time-off-day-event-row" onClick={() => { setSelectedCalendarDay(null); void openRequest(item.id) }}>
                  <span className={`time-off-status-mark status-${item.status.toLowerCase()}`} />
                  <span><strong>{item.employee.full_name}</strong><small>{item.department.name || 'Chưa có phòng ban'} · {formatDateTime(item.start_at)} → {formatDateTime(item.end_at)}</small></span>
                  <em className={`time-off-status status-${item.status.toLowerCase()}`}>{STATUS_LABELS[item.status] || item.status_label}</em>
                </button>
              ))}
            </div>
            <footer><button type="button" className="time-off-secondary" onClick={() => setSelectedCalendarDay(null)}>Đóng</button></footer>
          </section>
        </div>,
        document.body,
      )}

      {selectedRequest && createPortal(
        <div className="ui-modal-backdrop time-off-detail-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedRequest(null) }}>
          <section className="time-off-detail-modal" role="dialog" aria-label="Time Off request detail" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span>TIME OFF REQUEST · #{selectedRequest.id}</span><h3>{selectedRequest.employee.full_name}</h3><p>{selectedRequest.department.name || 'Chưa có phòng ban'} · {selectedRequest.employee.employee_code || '—'}</p></div>
              <button type="button" className="app-close-button" onClick={() => setSelectedRequest(null)} aria-label="Đóng"><AppIcon name="close" size={17} /></button>
            </header>
            <div className="time-off-detail-body">
              <div className="time-off-detail-status-row">
                <span className={`time-off-status status-${selectedRequest.status.toLowerCase()}`}>{STATUS_LABELS[selectedRequest.status] || selectedRequest.status_label}</span>
                <small>Cập nhật {formatDateTime(selectedRequest.updated_at)}</small>
              </div>
              <dl className="time-off-detail-grid">
                <div><dt>Thời gian</dt><dd>{formatDateTime(selectedRequest.start_at)} → {formatDateTime(selectedRequest.end_at)}</dd></div>
                <div><dt>Quy đổi</dt><dd>{selectedRequest.total_days} ngày công</dd></div>
                <div><dt>Loại yêu cầu</dt><dd>{selectedRequest.request_type_label || 'Thông tin riêng tư'}</dd></div>
                <div><dt>{selectedRequest.status === 'APPROVED' ? 'Manager đã duyệt' : 'Manager'}</dt><dd>{selectedRequest.manager.full_name || '—'}</dd></div>
              </dl>
              {scheduleDraft && (
                <section className="time-off-schedule-editor">
                  <div><span>IT ADMIN · Chỉnh thời gian nghỉ</span><p>Ngày, giờ và số ngày công sẽ được tính lại tự động. Thay đổi được ghi vào audit log.</p></div>
                  <DateTimeRangePicker
                    startAt={scheduleDraft.startAt}
                    endAt={scheduleDraft.endAt}
                    onChange={({ startAt, endAt }) => setScheduleDraft({ startAt, endAt })}
                    compact
                    disabled={saving}
                  />
                </section>
              )}
              {selectedRequest.business_travel_location && <section className="time-off-business-travel-box"><span>Địa điểm công tác</span><strong>{selectedRequest.business_travel_location}</strong><small>Đã xác nhận quy định công tác</small></section>}
              {selectedRequest.reason ? <section className="time-off-private-box"><span>{selectedRequest.request_type === BUSINESS_TRAVEL_REQUEST ? 'Lý do đi công tác' : 'Lý do yêu cầu'} · Chỉ người có quyền</span><p>{selectedRequest.reason}</p></section> : <section className="time-off-private-box is-locked"><span>Riêng tư</span><p>Lý do yêu cầu và dữ liệu bàn giao không hiển thị trên Calendar chung.</p></section>}
              {selectedRequest.attachments && selectedRequest.attachments.length > 0 && (
                <section className="time-off-detail-attachments">
                  <span>File đính kèm</span>
                  {selectedRequest.attachments.map((attachment) => (
                    <button key={attachment.id} type="button" className="app-download-button" onClick={() => void downloadAttachment(attachment)}>▧ {attachment.file_name}</button>
                  ))}
                </section>
              )}
              {selectedRequest.handover_employee || selectedRequest.handover_notes ? <section className="time-off-handover-box"><span>Bàn giao cho</span><strong>{selectedRequest.handover_employee?.full_name || 'Chưa chọn'}</strong><p>{selectedRequest.handover_notes || 'Không có ghi chú bàn giao.'}</p></section> : null}
              {selectedRequest.manager_comment && <section className="time-off-manager-comment"><span>Phản hồi từ Manager</span><p>{selectedRequest.manager_comment}</p></section>}

              {selectedRequest.actions && selectedRequest.actions.length > 0 && (
                <section className="time-off-timeline"><h4>Lịch sử xử lý</h4>{selectedRequest.actions.map((action) => <div key={action.id}><span /><div><strong>{ACTION_LABELS[action.action] || action.action}</strong><small>{action.actor_name || 'Hệ thống'} · {formatDateTime(action.created_at)}</small>{action.comment && <p>{action.comment}</p>}</div></div>)}</section>
              )}
            </div>
            <footer>
              {selectedRequest.can_edit && <button type="button" className="time-off-primary" onClick={() => editRequest(selectedRequest)}>{selectedRequest.status === 'PENDING_MANAGER' ? 'Chỉnh sửa yêu cầu' : 'Bổ sung thông tin'}</button>}
              {selectedRequest.can_edit_schedule && !scheduleDraft && <button type="button" className="time-off-secondary" disabled={saving} onClick={() => beginScheduleEdit(selectedRequest)}>Chỉnh thời gian nghỉ</button>}
              {selectedRequest.can_act && !actionMode && !scheduleDraft && <>
                <button type="button" className="time-off-approve" disabled={saving} onClick={() => void applyAction('APPROVE')}>Approve</button>
                <button type="button" className="time-off-more-info" disabled={saving} onClick={() => setActionMode('REQUEST_INFO')}>Yêu cầu bổ sung</button>
                <button type="button" className="time-off-reject" disabled={saving} onClick={() => setActionMode('REJECT')}>Reject</button>
              </>}
              {scheduleDraft && <div className="time-off-schedule-actions"><button type="button" className="time-off-secondary" disabled={saving} onClick={() => setScheduleDraft(null)}>Hủy</button><button type="button" className="time-off-primary" disabled={saving} onClick={() => void saveScheduleEdit()}>{saving ? 'Đang lưu…' : 'Lưu thời gian nghỉ'}</button></div>}
              {actionMode && <div className="time-off-action-compose"><label>{actionMode === 'REJECT' ? 'Lý do từ chối *' : 'Thông tin cần bổ sung *'}<textarea value={actionComment} autoFocus onChange={(event) => setActionComment(event.target.value)} /></label><div><button type="button" className="time-off-secondary" onClick={() => { setActionMode(null); setActionComment('') }}>Hủy</button><button type="button" className={actionMode === 'REJECT' ? 'time-off-reject' : 'time-off-more-info'} disabled={saving} onClick={() => void applyAction(actionMode)}>{saving ? 'Đang xử lý…' : 'Xác nhận'}</button></div></div>}
              {!selectedRequest.can_act && !selectedRequest.can_edit && !selectedRequest.can_edit_schedule && <button type="button" className="time-off-secondary" onClick={() => setSelectedRequest(null)}>Đóng</button>}
            </footer>
          </section>
        </div>,
        document.body,
      )}
    </section>
  )
}
