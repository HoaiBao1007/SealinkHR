import { useEffect, useMemo, useRef, useState } from 'react'
import { AppIcon } from '../../shared/ui/AppIcon'
import type { OnboardingField, OnboardingFormConfig } from './OnboardingPublic'
import './onboarding.css'

type ApiRequest = (path: string, init?: RequestInit) => Promise<Response>
type Department = { id: number; name: string; code?: string | null }
type Attachment = { id: number; original_name: string; size_bytes: number; download_url: string }
type Submission = {
  id: number; public_id: string; status: string; full_name: string; email: string; application_type: string
  review_note?: string | null; employee_id?: number | null; submitted_at: string; answers: Record<string, unknown>
  fields: OnboardingField[]; attachments: Attachment[]
}
type Props = { apiRequest: ApiRequest; onNotice: (message: string) => void }
type ConfigResponse = { published: OnboardingFormConfig; draft: OnboardingFormConfig; public_path: string }

const statuses = ['NEW', 'NEEDS_INFO', 'REJECTED', 'INTERN', 'TRAINEE', 'PROBATION', 'OFFICIAL', 'PART_TIME', 'DONE']
const statusLabels: Record<string, string> = { NEW: 'Mới', NEEDS_INFO: 'Cần bổ sung', REJECTED: 'Từ chối', INTERN: 'Thực tập', TRAINEE: 'Học việc', PROBATION: 'Thử việc', OFFICIAL: 'Chính thức', PART_TIME: 'Part-time', DONE: 'Hoàn tất' }
const fieldTypes = ['text', 'textarea', 'email', 'phone', 'date', 'select', 'multiselect', 'number', 'file']

async function responseJson<T>(response: Response): Promise<T> {
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || 'Yêu cầu không thành công.')
  return data
}

function optionsText(field: OnboardingField) { return (field.options || []).map((option) => `${option.value}|${option.label}`).join('\n') }
function optionsFromText(value: string) { return value.split('\n').map((line) => line.trim()).filter(Boolean).map((line) => { const [rawValue, ...labelParts] = line.split('|'); const label = labelParts.join('|').trim() || rawValue.trim(); return { value: rawValue.trim(), label } }) }
function conditionValuesText(field: OnboardingField) { return (field.visible_when?.values || []).join(', ') }
function conditionValuesFromText(value: string) { return value.split(',').map((item) => item.trim()).filter(Boolean) }

export function OnboardingAdmin({ apiRequest, onNotice }: Props) {
  const [view, setView] = useState<'builder' | 'review'>('review')
  const [config, setConfig] = useState<ConfigResponse | null>(null)
  const [draft, setDraft] = useState<OnboardingFormConfig | null>(null)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [approval, setApproval] = useState({ machine_employee_id: '', employee_code: '', department_id: '', start_date: '' })
  const [approvalError, setApprovalError] = useState('')
  const machineEmployeeIdRef = useRef<HTMLInputElement>(null)
  const publicUrl = `${window.location.origin}/onboarding`

  const selected = submissions.find((item) => item.id === selectedId) || null
  const filtered = useMemo(() => filter ? submissions.filter((item) => item.status === filter) : submissions, [filter, submissions])
  const approvalErrorTargetsMachineId = Boolean(
    approvalError && (!approval.machine_employee_id.trim() || approvalError.toLocaleLowerCase('vi').includes('mã chấm công')),
  )

  async function load() {
    setBusy(true)
    try {
      const [configuration, submissionRows, departmentRows] = await Promise.all([
        apiRequest('/api/onboarding/admin/config').then(responseJson<ConfigResponse>),
        apiRequest('/api/onboarding/admin/submissions').then(responseJson<Submission[]>),
        apiRequest('/api/hr/departments').then(responseJson<Department[]>),
      ])
      setConfig(configuration)
      setDraft(structuredClone(configuration.draft))
      setSubmissions(submissionRows)
      if (!selectedId && submissionRows[0]) setSelectedId(submissionRows[0].id)
      setDepartments(departmentRows)
    } catch (reason) { onNotice((reason as Error).message) }
    finally { setBusy(false) }
  }

  useEffect(() => { void load() }, [])

  function updateField(index: number, patch: Partial<OnboardingField>) {
    setDraft((current) => current ? { ...current, fields: current.fields.map((field, fieldIndex) => fieldIndex === index ? { ...field, ...patch } : field) } : current)
  }
  function moveField(index: number, offset: number) {
    setDraft((current) => {
      if (!current) return current
      const next = [...current.fields]
      const target = index + offset
      if (target < 0 || target >= next.length) return current
      ;[next[index], next[target]] = [next[target], next[index]]
      return { ...current, fields: next }
    })
  }

  async function saveDraft() {
    if (!draft) return
    setBusy(true)
    try {
      const saved = await apiRequest('/api/onboarding/admin/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: draft.title, description: draft.description, success_message: draft.success_message, fields: draft.fields }) }).then(responseJson<OnboardingFormConfig>)
      setDraft(saved)
      onNotice('Đã lưu bản nháp biểu mẫu onboarding.')
    } catch (reason) { onNotice((reason as Error).message) }
    finally { setBusy(false) }
  }

  async function publish() {
    if (!draft) return
    setBusy(true)
    try {
      const value = await apiRequest('/api/onboarding/admin/config/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: draft.title,
          description: draft.description,
          success_message: draft.success_message,
          fields: draft.fields,
        }),
      }).then(responseJson<{ published: OnboardingFormConfig; draft: OnboardingFormConfig }>)
      setConfig((current) => current ? { ...current, ...value } : null)
      setDraft(structuredClone(value.draft))
      onNotice(`Đã phát hành biểu mẫu onboarding phiên bản ${value.published.version_number}.`)
    } catch (reason) { onNotice((reason as Error).message) }
    finally { setBusy(false) }
  }

  async function reviewAction(action: 'request-changes' | 'reject') {
    if (!selected || note.trim().length < 3) { onNotice('Vui lòng nhập lý do tối thiểu 3 ký tự.'); return }
    setBusy(true)
    try {
      await apiRequest(`/api/onboarding/admin/submissions/${selected.id}/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note }) }).then(responseJson<Submission>)
      setNote(''); await load(); onNotice(action === 'reject' ? 'Đã từ chối hồ sơ.' : 'Đã ghi nhận yêu cầu bổ sung.')
    } catch (reason) { onNotice((reason as Error).message) }
    finally { setBusy(false) }
  }

  async function approve() {
    if (!selected) return
    const machineEmployeeId = approval.machine_employee_id.trim()
    if (!machineEmployeeId) {
      const message = 'Cần nhập mã máy chấm công trước khi phê duyệt.'
      setApprovalError(message)
      onNotice(message)
      machineEmployeeIdRef.current?.focus()
      machineEmployeeIdRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
    setApprovalError('')
    setBusy(true)
    try {
      await apiRequest(`/api/onboarding/admin/submissions/${selected.id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ machine_employee_id: machineEmployeeId, employee_code: approval.employee_code.trim() || null, department_id: approval.department_id ? Number(approval.department_id) : null, start_date: approval.start_date || null }) }).then(responseJson<Submission>)
      await load(); onNotice('Đã phê duyệt và tạo nhân viên chính thức trong database HR.')
    } catch (reason) {
      const message = (reason as Error).message
      setApprovalError(message)
      onNotice(message)
    }
    finally { setBusy(false) }
  }

  async function updateStatus(status: string) {
    if (!selected) return
    try {
      await apiRequest(`/api/onboarding/admin/submissions/${selected.id}/status`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, note: note || null }) }).then(responseJson<Submission>)
      await load(); onNotice('Đã cập nhật trạng thái onboarding.')
    } catch (reason) { onNotice((reason as Error).message) }
  }

  async function downloadAttachment(attachment: Attachment) {
    try {
      const response = await apiRequest(attachment.download_url)
      if (!response.ok) throw new Error('Không thể tải tệp.')
      const href = URL.createObjectURL(await response.blob())
      const link = document.createElement('a'); link.href = href; link.download = attachment.original_name; link.click(); URL.revokeObjectURL(href)
    } catch (reason) { onNotice((reason as Error).message) }
  }

  return <div className="onboarding-admin">
    <section className="onboarding-admin-card onboarding-admin-hero"><div><h2>Onboarding nhân viên mới</h2><p>Biểu mẫu công khai cố định, dữ liệu tạm độc lập và chỉ tạo nhân sự sau phê duyệt.</p></div><div className="onboarding-link-box"><code>{publicUrl}</code><button className="onboarding-icon-button" title="Sao chép link" onClick={() => { void navigator.clipboard.writeText(publicUrl); onNotice('Đã sao chép link onboarding.') }}><AppIcon name="copy" size={17} /></button></div></section>
    <div className="onboarding-admin-tabs" role="tablist"><button className={view === 'review' ? 'is-active' : ''} onClick={() => setView('review')}>Hồ sơ chờ duyệt ({submissions.filter((item) => item.status === 'NEW').length})</button><button className={view === 'builder' ? 'is-active' : ''} onClick={() => setView('builder')}>Thiết kế biểu mẫu</button></div>

    {view === 'builder' && draft && <section className="onboarding-admin-card">
      <div className="onboarding-config-grid"><label className="onboarding-field"><span className="onboarding-field-label">Tiêu đề</span><input className="onboarding-input" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label className="onboarding-field"><span className="onboarding-field-label">Thông báo sau khi gửi</span><input className="onboarding-input" value={draft.success_message} onChange={(event) => setDraft({ ...draft, success_message: event.target.value })} /></label><label className="onboarding-field is-wide"><span className="onboarding-field-label">Mô tả</span><textarea className="onboarding-textarea" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label></div>
      <div className="onboarding-builder-list">{draft.fields.map((field, index) => <div className="onboarding-builder-row" key={`${field.key}-${index}`}>
        <label className="onboarding-field onboarding-builder-display-label"><span className="onboarding-field-label">Nhãn hiển thị</span><input className="onboarding-input" value={field.label} onChange={(event) => updateField(index, { label: event.target.value })} /></label>
        <label className="onboarding-field"><span className="onboarding-field-label">Mã trường</span><input className="onboarding-input" value={field.key} disabled={['full_name', 'email', 'application_type'].includes(field.key)} onChange={(event) => updateField(index, { key: event.target.value })} /></label>
        <label className="onboarding-field"><span className="onboarding-field-label">Nhóm</span><input className="onboarding-input" value={field.section || ''} onChange={(event) => updateField(index, { section: event.target.value })} /></label>
        <label className="onboarding-field"><span className="onboarding-field-label">Loại</span><select className="onboarding-select" value={field.type} onChange={(event) => updateField(index, { type: event.target.value })}>{fieldTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
        <span className="onboarding-row-buttons"><button className="onboarding-icon-button" title="Đưa lên" onClick={() => moveField(index, -1)}>↑</button><button className="onboarding-icon-button" title="Đưa xuống" onClick={() => moveField(index, 1)}>↓</button><button className="onboarding-icon-button danger" title="Xóa trường" disabled={['full_name', 'email', 'application_type'].includes(field.key)} onClick={() => setDraft({ ...draft, fields: draft.fields.filter((_, fieldIndex) => fieldIndex !== index) })}><AppIcon name="trash" size={16} /></button></span>
        <label className="onboarding-check"><input type="checkbox" checked={field.active !== false} onChange={(event) => updateField(index, { active: event.target.checked })} /> Hiển thị</label><label className="onboarding-check"><input type="checkbox" checked={Boolean(field.required)} onChange={(event) => updateField(index, { required: event.target.checked })} /> Bắt buộc</label>
        <label className="onboarding-field"><span className="onboarding-field-label">Gợi ý trong ô</span><input className="onboarding-input" value={field.placeholder || ''} onChange={(event) => updateField(index, { placeholder: event.target.value })} /></label>
        <label className="onboarding-field onboarding-builder-help"><span className="onboarding-field-label">Hướng dẫn bên dưới</span><input className="onboarding-input" value={field.description || ''} onChange={(event) => updateField(index, { description: event.target.value })} /></label>
        {field.type === 'number' && <><label className="onboarding-field"><span className="onboarding-field-label">Giá trị nhỏ nhất</span><input className="onboarding-input" type="number" value={field.min ?? ''} onChange={(event) => updateField(index, { min: event.target.value === '' ? undefined : Number(event.target.value) })} /></label><label className="onboarding-field"><span className="onboarding-field-label">Giá trị lớn nhất</span><input className="onboarding-input" type="number" value={field.max ?? ''} onChange={(event) => updateField(index, { max: event.target.value === '' ? undefined : Number(event.target.value) })} /></label></>}
        {field.type === 'file' && <label className="onboarding-field"><span className="onboarding-field-label">Số tệp tối đa</span><input className="onboarding-input" type="number" min={1} max={10} value={field.max_files || 1} onChange={(event) => updateField(index, { max_files: Math.max(1, Math.min(10, Number(event.target.value) || 1)) })} /></label>}
        <label className="onboarding-check"><input type="checkbox" checked={Boolean(field.visible_when)} onChange={(event) => updateField(index, { visible_when: event.target.checked ? { field: 'application_type', operator: 'in', values: ['INTERN'] } : undefined })} /> Hiển thị có điều kiện</label>
        {field.visible_when && <div className="onboarding-builder-condition">
          <label className="onboarding-field"><span className="onboarding-field-label">Dựa vào trường</span><select className="onboarding-select" value={field.visible_when.field || ''} onChange={(event) => updateField(index, { visible_when: { ...field.visible_when, field: event.target.value } })}>{draft.fields.filter((candidate) => candidate.key !== field.key).map((candidate) => <option key={candidate.key} value={candidate.key}>{candidate.label}</option>)}</select></label>
          <label className="onboarding-field"><span className="onboarding-field-label">Điều kiện</span><select className="onboarding-select" value={field.visible_when.operator || 'in'} onChange={(event) => updateField(index, { visible_when: { ...field.visible_when, operator: event.target.value } })}><option value="in">Thuộc một trong</option><option value="not_in">Không thuộc</option></select></label>
          <label className="onboarding-field"><span className="onboarding-field-label">Giá trị (cách nhau bằng dấu phẩy)</span><input className="onboarding-input" value={conditionValuesText(field)} onChange={(event) => updateField(index, { visible_when: { ...field.visible_when, values: conditionValuesFromText(event.target.value) } })} /></label>
        </div>}
        {['select', 'multiselect'].includes(field.type) && <label className="onboarding-field onboarding-builder-options"><span className="onboarding-field-label">Lựa chọn (mỗi dòng: GIÁ_TRỊ|Nhãn hiển thị)</span><textarea className="onboarding-textarea" value={optionsText(field)} onChange={(event) => updateField(index, { options: optionsFromText(event.target.value) })} /></label>}
      </div>)}</div>
      <div className="onboarding-actions"><button className="onboarding-button" onClick={() => setDraft({ ...draft, fields: [...draft.fields, { key: `custom_${Date.now()}`, label: 'Trường mới', type: 'text', active: true, required: false, section: 'Thông tin bổ sung' }] })}><AppIcon name="plus" size={16} /> Thêm trường</button><button className="onboarding-button" disabled={busy} onClick={() => void saveDraft()}>Lưu bản nháp</button><button className="onboarding-button primary" disabled={busy} onClick={() => void publish()}>Phát hành phiên bản mới</button></div>
      {config && <p className="onboarding-help">Đang công khai phiên bản {config.published.version_number}. Việc chỉnh sửa bản nháp không làm thay đổi hồ sơ cũ.</p>}
    </section>}

    {view === 'review' && <div className="onboarding-review-layout"><section className="onboarding-admin-card onboarding-review-list-card"><label className="onboarding-field"><span className="onboarding-field-label">Lọc trạng thái</span><select className="onboarding-select" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">Tất cả</option>{statuses.map((status) => <option key={status} value={status}>{statusLabels[status]}</option>)}</select></label><div className="onboarding-submission-list" style={{ marginTop: 12 }}>{filtered.map((item) => <button className={`onboarding-submission-item${selectedId === item.id ? ' is-active' : ''}`} key={item.id} onClick={() => { setSelectedId(item.id); setNote(item.review_note || ''); setApprovalError(''); setApproval({ machine_employee_id: '', employee_code: '', department_id: '', start_date: String(item.answers.available_start_date || '').slice(0, 10) }) }}><strong>{item.full_name}</strong><div className="onboarding-submission-meta"><span>{item.email}</span><span className={`onboarding-status ${item.status}`}>{statusLabels[item.status] || item.status}</span></div><div className="onboarding-submission-meta"><span>{item.application_type}</span><span>{new Date(item.submitted_at).toLocaleDateString('vi-VN')}</span></div></button>)}{!filtered.length && <p className="onboarding-help">Chưa có hồ sơ phù hợp.</p>}</div></section>
      <section className="onboarding-admin-card onboarding-review-detail">{selected ? <><div className="onboarding-detail-header"><div><h3 style={{ margin: 0 }}>{selected.full_name}</h3><p className="onboarding-help">{selected.email} · Mã theo dõi {selected.public_id}</p></div><span className={`onboarding-status ${selected.status}`}>{statusLabels[selected.status] || selected.status}</span></div><dl className="onboarding-answer-grid">{selected.fields.filter((field) => field.active !== false && field.type !== 'file').map((field) => { const value = selected.answers[field.key]; return <div className="onboarding-answer" key={field.key}><dt>{field.label}</dt><dd>{Array.isArray(value) ? value.join(', ') : String(value ?? '—')}</dd></div> })}</dl>
        <div className="onboarding-attachment-list">{selected.attachments.map((attachment) => <button className="onboarding-button" key={attachment.id} onClick={() => void downloadAttachment(attachment)}><AppIcon name="download" size={15} /> {attachment.original_name}</button>)}</div>
        <div className="onboarding-review-actions"><label className="onboarding-field"><span className="onboarding-field-label">Ghi chú xử lý / nội dung yêu cầu bổ sung</span><textarea className="onboarding-textarea" value={note} onChange={(event) => setNote(event.target.value)} /></label>
          {!selected.employee_id ? <><div className="onboarding-approval-grid"><label className="onboarding-field"><span className="onboarding-field-label">Mã máy chấm công *</span><input ref={machineEmployeeIdRef} className={`onboarding-input${approvalErrorTargetsMachineId ? ' is-invalid' : ''}`} value={approval.machine_employee_id} required aria-invalid={approvalErrorTargetsMachineId} aria-describedby={approvalErrorTargetsMachineId ? 'onboarding-machine-id-error' : undefined} onChange={(event) => { setApproval({ ...approval, machine_employee_id: event.target.value }); if (approvalErrorTargetsMachineId) setApprovalError('') }} />{approvalErrorTargetsMachineId && <small id="onboarding-machine-id-error" className="onboarding-field-error" role="alert"><AppIcon name="warning" size={14} /> {approvalError}</small>}</label><label className="onboarding-field"><span className="onboarding-field-label">Mã nhân viên (để trống để tự tạo)</span><input className="onboarding-input" value={approval.employee_code} onChange={(event) => { setApproval({ ...approval, employee_code: event.target.value }); if (approvalError.toLocaleLowerCase('vi').includes('mã nhân viên')) setApprovalError('') }} /></label><label className="onboarding-field"><span className="onboarding-field-label">Phòng ban</span><select className="onboarding-select" value={approval.department_id} onChange={(event) => setApproval({ ...approval, department_id: event.target.value })}><option value="">Chưa gán</option>{departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label><label className="onboarding-field"><span className="onboarding-field-label">Ngày bắt đầu</span><input className="onboarding-input" type="date" value={approval.start_date} onChange={(event) => setApproval({ ...approval, start_date: event.target.value })} /></label></div>{approvalError && !approvalErrorTargetsMachineId && <div className="onboarding-approval-error" role="alert"><AppIcon name="warning" size={15} /> {approvalError}</div>}<div className="onboarding-actions"><button className="onboarding-button" disabled={busy} onClick={() => void reviewAction('request-changes')}>Yêu cầu bổ sung</button><button className="onboarding-button danger" disabled={busy} onClick={() => void reviewAction('reject')}>Từ chối</button><button className="onboarding-button primary" disabled={busy} onClick={() => void approve()}>{busy ? 'Đang tạo nhân viên...' : 'Phê duyệt & tạo nhân viên'}</button></div></>
            : <label className="onboarding-field"><span className="onboarding-field-label">Giai đoạn onboarding</span><select className="onboarding-select" value={selected.status} onChange={(event) => void updateStatus(event.target.value)}>{statuses.filter((status) => !['NEW', 'NEEDS_INFO', 'REJECTED'].includes(status)).map((status) => <option key={status}>{status}</option>)}</select></label>}
        </div></> : <p className="onboarding-help">Chọn một hồ sơ để kiểm tra.</p>}</section></div>}
  </div>
}
