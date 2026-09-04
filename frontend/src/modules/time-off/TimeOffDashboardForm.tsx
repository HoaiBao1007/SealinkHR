import { useEffect, useState, type FormEvent } from 'react'
import { DateTimeRangePicker, defaultTimeOffRange } from './DateTimeRangePicker'
import { BUSINESS_TRAVEL_REQUEST, LEAVE_REQUEST, TimeOffRequestIntent, type LeaveBalance } from './TimeOffRequestIntent'
import { TimeOffAttachmentUpload, type TimeOffAttachment } from './TimeOffAttachmentUpload'
import { AppIcon } from '../../shared/ui/AppIcon'
import './time-off-dashboard-form.css'

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
    department_name: string | null
  } | null
  manager: {
    user_id: number
    full_name: string
    source: string
  } | null
  approver_options: ApproverOption[]
  can_submit: boolean
  handover_candidates: Array<{
    id: number
    full_name: string
    department_name?: string | null
  }>
  request_types: Array<{ value: string; label: string }>
  leave_balance: LeaveBalance | null
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

type SubmittedRequest = {
  id: number
  status: string
}

type Props = {
  apiRequest: ApiRequest
  onOpenWorkspace: () => void
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
  if (!response.ok) {
    const detail = (payload as { detail?: string }).detail
    throw new Error(detail || 'Không thể xử lý yêu cầu nghỉ.')
  }
  return payload as T
}

function managerSourceLabel(source?: string) {
  if (source === 'PARENT_MANAGER') return 'Manager cấp trên'
  if (source === 'OTHER_DEPARTMENT_MANAGER') return 'Manager phòng ban khác'
  if (source === 'FALLBACK_APPROVER') return 'Người duyệt dự phòng'
  return 'Manager phòng ban'
}

export function TimeOffDashboardForm({ apiRequest, onOpenWorkspace }: Props) {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [form, setForm] = useState<RequestFormState>(emptyForm)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<TimeOffAttachment[]>([])

  useEffect(() => {
    let active = true
    const timer = window.setTimeout(async () => {
      try {
        const payload = await responseJson<Bootstrap>(await apiRequest('/api/time-off/bootstrap'))
        if (active) {
          setBootstrap(payload)
          setForm((current) => ({
            ...current,
            approver_user_id: current.approver_user_id || String(payload.manager?.user_id || ''),
          }))
        }
      } catch (requestError) {
        if (active) setError((requestError as Error).message)
      } finally {
        if (active) setLoading(false)
      }
    }, 0)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
    // The authenticated request wrapper is stable for one mounted App session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSuccess(null)

    if (!form.start_at || !form.end_at || form.end_at <= form.start_at) {
      setError('Thời gian kết thúc phải sau thời gian bắt đầu.')
      return
    }
    if (!form.approver_user_id) {
      setError('Vui lòng chọn Manager nhận yêu cầu.')
      return
    }
    if (form.request_type === BUSINESS_TRAVEL_REQUEST && (!form.business_travel_policy_acknowledged || attachments.length === 0)) {
      setError(!form.business_travel_policy_acknowledged
        ? 'Bạn cần xác nhận đã xem qua quy định công tác trước khi gửi yêu cầu.'
        : 'Vui lòng upload quyết định của BGĐ trước khi gửi yêu cầu công tác.')
      return
    }

    setSubmitting(true)
    try {
      const selectedApprover = bootstrap?.approver_options.find(
        (option) => String(option.user_id) === form.approver_user_id,
      )
      const request = await responseJson<SubmittedRequest>(await apiRequest('/api/time-off/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          approver_user_id: Number(form.approver_user_id),
          reason: form.reason.trim(),
          handover_employee_id: form.handover_employee_id
            ? Number(form.handover_employee_id)
            : null,
          handover_notes: form.handover_notes.trim() || null,
          attachment_ids: attachments.filter((attachment) => attachment.is_staged).map((attachment) => attachment.id),
        }),
      }))
      setSuccess(`Đơn #${request.id} đã được gửi đến ${selectedApprover?.full_name || 'Manager'} và thông báo đã được tạo trong tài khoản người duyệt.`)
      setForm(emptyForm(bootstrap?.manager?.user_id))
      setAttachments([])
    } catch (requestError) {
      setError((requestError as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="time-off-dashboard-card" aria-labelledby="time-off-dashboard-title">
      <header className="time-off-dashboard-header">
        <div className="time-off-dashboard-heading">
          <span className="time-off-dashboard-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" focusable="false">
              <path d="M7 3v3m10-3v3M4.5 9.5h15M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" />
              <path d="m9 14 2 2 4-4" />
            </svg>
          </span>
          <div>
            <span className="time-off-dashboard-eyebrow">TIME OFF</span>
            <h2 id="time-off-dashboard-title">Gửi yêu cầu</h2>
            <p>Gửi đơn nghỉ, làm việc tại nhà hoặc công tác. Thông tin nhân viên được lấy từ tài khoản đăng nhập.</p>
          </div>
        </div>
        <button type="button" className="time-off-dashboard-link" onClick={onOpenWorkspace}>
          Xem lịch & đơn của tôi
          <AppIcon name="arrow-right" size={15} />
        </button>
      </header>

      {loading ? (
        <div className="time-off-dashboard-loading" role="status">Đang tải thông tin nhân viên…</div>
      ) : (
        <form className="time-off-dashboard-form" onSubmit={submitRequest}>
          <div className="time-off-dashboard-identity" aria-label="Thông tin tự động từ tài khoản">
            <div>
              <span>Nhân viên</span>
              <strong>{bootstrap?.employee?.full_name || 'Chưa liên kết hồ sơ'}</strong>
              <small>{bootstrap?.employee?.employee_code || 'Chưa có mã nhân viên'}</small>
            </div>
            <div>
              <span>Phòng ban</span>
              <strong>{bootstrap?.employee?.department_name || 'Chưa cấu hình'}</strong>
              <small>Đọc từ hồ sơ nhân viên</small>
            </div>
            <div>
              <span>Gửi đến Manager</span>
              <select
                className="time-off-dashboard-manager-select"
                value={form.approver_user_id}
                onChange={(event) => setForm((current) => ({ ...current, approver_user_id: event.target.value }))}
                aria-label="Chọn Manager nhận yêu cầu"
                required
              >
                <option value="">Chưa xác định</option>
                {(bootstrap?.approver_options || []).map((option) => (
                  <option key={option.user_id} value={option.user_id}>
                    {option.full_name}{option.is_default ? ' · Mặc định' : ''} · {managerSourceLabel(option.source)}
                  </option>
                ))}
              </select>
              <small>Danh sách được backend giới hạn theo các Manager đã cấu hình.</small>
            </div>
          </div>

          <div className="time-off-dashboard-fields">
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
              onChange={({ startAt, endAt }) => setForm((current) => ({
                ...current,
                start_at: startAt,
                end_at: endAt,
              }))}
              compact
            />
            {form.request_type === BUSINESS_TRAVEL_REQUEST && (
              <label>
                <span>Địa điểm công tác *</span>
                <input
                  value={form.business_travel_location}
                  maxLength={255}
                  onChange={(event) => setForm((current) => ({ ...current, business_travel_location: event.target.value }))}
                  placeholder="Ví dụ: Hà Nội, Hải Phòng, Singapore…"
                  required
                />
              </label>
            )}
            <label className="is-flexible">
              <span>{form.request_type === BUSINESS_TRAVEL_REQUEST ? 'Lý do đi công tác *' : 'Lý do yêu cầu *'}</span>
              <textarea
                value={form.reason}
                maxLength={255}
                onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))}
                placeholder={form.request_type === BUSINESS_TRAVEL_REQUEST ? 'Mô tả mục đích công tác…' : 'Mô tả ngắn gọn nội dung yêu cầu…'}
                rows={2}
                required
              />
            </label>
            {form.request_type === BUSINESS_TRAVEL_REQUEST && (
              <label className="time-off-travel-policy">
                <input
                  type="checkbox"
                  checked={form.business_travel_policy_acknowledged}
                  onChange={(event) => setForm((current) => ({ ...current, business_travel_policy_acknowledged: event.target.checked }))}
                  required
                />
                <span>Tôi đã xem qua và đồng ý tuân thủ quy định công tác của công ty.</span>
              </label>
            )}
            <TimeOffAttachmentUpload
              apiRequest={apiRequest}
              requestType={form.request_type}
              attachments={attachments}
              onChange={setAttachments}
              disabled={submitting}
            />
            <details className="time-off-dashboard-handover">
              <summary>
                <span>Bàn giao công việc</span>
                <small>{form.handover_employee_id || form.handover_notes ? 'Đã có thông tin' : 'Không bắt buộc'}</small>
              </summary>
              <div>
                <label>
                  <span>Người bàn giao</span>
                  <select
                    value={form.handover_employee_id}
                    onChange={(event) => setForm((current) => ({ ...current, handover_employee_id: event.target.value }))}
                  >
                    <option value="">Chưa chọn</option>
                    {(bootstrap?.handover_candidates || []).map((employee) => (
                      <option key={employee.id} value={employee.id}>
                        {employee.full_name}{employee.department_name ? ` · ${employee.department_name}` : ''}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Ghi chú bàn giao</span>
                  <textarea
                    value={form.handover_notes}
                    maxLength={2000}
                    rows={2}
                    onChange={(event) => setForm((current) => ({ ...current, handover_notes: event.target.value }))}
                    placeholder="Công việc, deadline hoặc tài liệu cần bàn giao…"
                  />
                </label>
              </div>
            </details>
          </div>

          {bootstrap && !bootstrap.can_submit && (
            <div className="time-off-dashboard-warning" role="alert">
              Tài khoản chưa có hồ sơ nhân viên, phòng ban hoặc Manager hợp lệ. Admin cần hoàn tất mapping trước khi gửi đơn.
            </div>
          )}
          {error && <div className="time-off-dashboard-message is-error" role="alert">{error}</div>}
          {success && <div className="time-off-dashboard-message is-success" role="status">{success}</div>}

          <footer className="time-off-dashboard-actions">
            <p>
              Khi gửi, backend sẽ kiểm tra trùng lịch, hạn mức phép (với Leave Request), tạo trạng thái <strong>PENDING_MANAGER</strong> và thông báo cho đúng Manager.
            </p>
            <button type="submit" disabled={submitting || !bootstrap?.can_submit || (form.request_type === BUSINESS_TRAVEL_REQUEST && (!form.business_travel_policy_acknowledged || attachments.length === 0))}>
              {submitting ? 'Đang gửi…' : 'Gửi yêu cầu đến Manager'}
            </button>
          </footer>
        </form>
      )}
    </section>
  )
}
