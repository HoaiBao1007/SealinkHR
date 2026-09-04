import { useEffect, useMemo, useState } from 'react'
import { AppIcon } from '../../shared/ui/AppIcon'
import type { OffboardingField, OffboardingFormConfig } from './OffboardingPublic'
import '../onboarding/onboarding.css'

type ApiRequest = (path: string, init?: RequestInit) => Promise<Response>
type Attachment = { id: number; original_name: string; download_url: string }
type Submission = {
  id: number; public_id: string; status: string; full_name: string; email?: string; employee_id?: number | null
  employee_code?: string | null; position?: string | null; department?: string | null; review_note?: string | null
  submitted_at: string; desired_last_working_date: string; confirmed_last_working_date?: string | null; last_pay_date?: string | null
  answers: Record<string, unknown>; fields: OffboardingField[]; attachments: Attachment[]
}
type EmployeeOption = { id: number; full_name: string; employee_code?: string | null; personal_email?: string | null; company_email?: string | null }
type ConfigResponse = { published: OffboardingFormConfig; draft: OffboardingFormConfig; public_path: string }

const fieldTypes = ['text', 'textarea', 'email', 'phone', 'date', 'select', 'multiselect', 'number', 'file']
const systemFields = ['full_name', 'email', 'reason', 'desired_last_working_date']
const statusLabels: Record<string, string> = { NEW: 'Chờ duyệt', NEEDS_INFO: 'Cần bổ sung', REJECTED: 'Từ chối', APPROVED: 'Đã duyệt' }

async function responseJson<T>(response: Response): Promise<T> {
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || 'Yêu cầu không thành công.')
  return data
}
function optionsText(field: OffboardingField) { return (field.options || []).map((item) => `${item.value}|${item.label}`).join('\n') }
function optionsFromText(value: string) { return value.split('\n').map((line) => line.trim()).filter(Boolean).map((line) => { const [raw, ...rest] = line.split('|'); return { value: raw.trim(), label: rest.join('|').trim() || raw.trim() } }) }

export function OffboardingAdmin({ apiRequest, onNotice }: { apiRequest: ApiRequest; onNotice: (message: string) => void }) {
  const [view, setView] = useState<'review' | 'builder'>('review')
  const [config, setConfig] = useState<ConfigResponse | null>(null)
  const [draft, setDraft] = useState<OffboardingFormConfig | null>(null)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [employees, setEmployees] = useState<EmployeeOption[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [approval, setApproval] = useState({ employee_id: '', confirmed_last_working_date: '', last_pay_date: '' })
  const publicUrl = `${window.location.origin}/offboarding`
  const selected = submissions.find((item) => item.id === selectedId) || null
  const filtered = useMemo(() => filter ? submissions.filter((item) => item.status === filter) : submissions, [filter, submissions])

  async function load(silent = false) {
    if (!silent) setBusy(true)
    try {
      const [configuration, rows, employeeRows] = await Promise.all([
        apiRequest('/api/offboarding/admin/config').then(responseJson<ConfigResponse>),
        apiRequest('/api/offboarding/admin/submissions').then(responseJson<Submission[]>),
        apiRequest('/api/offboarding/admin/employees').then(responseJson<EmployeeOption[]>),
      ])
      setConfig(configuration); setDraft((current) => current && view === 'builder' ? current : structuredClone(configuration.draft)); setSubmissions(rows); setEmployees(employeeRows)
      setSelectedId((current) => current && rows.some((item) => item.id === current) ? current : rows[0]?.id || null)
    } catch (reason) { onNotice((reason as Error).message) }
    finally { if (!silent) setBusy(false) }
  }

  useEffect(() => { void load() }, [])
  useEffect(() => { const timer = window.setInterval(() => void load(true), 15000); return () => window.clearInterval(timer) }, [view])

  function updateField(index: number, patch: Partial<OffboardingField>) { setDraft((current) => current ? { ...current, fields: current.fields.map((item, position) => position === index ? { ...item, ...patch } : item) } : current) }
  function moveField(index: number, offset: number) { setDraft((current) => { if (!current) return current; const target = index + offset; if (target < 0 || target >= current.fields.length) return current; const fields = [...current.fields]; [fields[index], fields[target]] = [fields[target], fields[index]]; return { ...current, fields } }) }

  async function saveDraft() {
    if (!draft) return; setBusy(true)
    try { const saved = await apiRequest('/api/offboarding/admin/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: draft.title, description: draft.description, success_message: draft.success_message, fields: draft.fields }) }).then(responseJson<OffboardingFormConfig>); setDraft(saved); onNotice('Đã lưu bản nháp biểu mẫu nghỉ việc.') }
    catch (reason) { onNotice((reason as Error).message) } finally { setBusy(false) }
  }
  async function publish() {
    if (!draft) return; setBusy(true)
    try { const value = await apiRequest('/api/offboarding/admin/config/publish', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: draft.title, description: draft.description, success_message: draft.success_message, fields: draft.fields }) }).then(responseJson<{ published: OffboardingFormConfig; draft: OffboardingFormConfig }>); setConfig((current) => current ? { ...current, ...value } : null); setDraft(structuredClone(value.draft)); onNotice(`Đã phát hành biểu mẫu nghỉ việc phiên bản ${value.published.version_number}.`) }
    catch (reason) { onNotice((reason as Error).message) } finally { setBusy(false) }
  }
  async function reviewAction(action: 'request-changes' | 'reject') {
    if (!selected || note.trim().length < 3) { onNotice('Vui lòng nhập lý do tối thiểu 3 ký tự.'); return }
    setBusy(true)
    try { await apiRequest(`/api/offboarding/admin/submissions/${selected.id}/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note }) }).then(responseJson<Submission>); setNote(''); await load(true); onNotice(action === 'reject' ? 'Đã từ chối hồ sơ.' : 'Đã yêu cầu bổ sung hồ sơ.') }
    catch (reason) { onNotice((reason as Error).message) } finally { setBusy(false) }
  }
  async function approve() {
    if (!selected) return; setBusy(true)
    try { await apiRequest(`/api/offboarding/admin/submissions/${selected.id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note: note || null, employee_id: approval.employee_id ? Number(approval.employee_id) : null, confirmed_last_working_date: approval.confirmed_last_working_date || selected.desired_last_working_date, last_pay_date: approval.last_pay_date || null }) }).then(responseJson<Submission>); await load(true); onNotice('Đã phê duyệt và chuyển nhân viên sang trạng thái Đã nghỉ việc.') }
    catch (reason) { onNotice((reason as Error).message) } finally { setBusy(false) }
  }
  async function downloadAttachment(attachment: Attachment) { try { const response = await apiRequest(attachment.download_url); if (!response.ok) throw new Error('Không thể tải tệp.'); const href = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = href; link.download = attachment.original_name; link.click(); URL.revokeObjectURL(href) } catch (reason) { onNotice((reason as Error).message) } }

  return <div className="onboarding-admin">
    <section className="onboarding-admin-card onboarding-admin-hero"><div><h2>Offboarding nhân viên</h2><p>Gửi link cố định cho nhân viên điền đơn; HR duyệt hồ sơ và quản lý mẫu ngay tại đây.</p></div><div className="onboarding-link-box"><code>{publicUrl}</code><button className="onboarding-icon-button" title="Sao chép link" onClick={() => { void navigator.clipboard.writeText(publicUrl); onNotice('Đã sao chép link offboarding.') }}><AppIcon name="copy" size={17} /></button></div></section>
    <div className="onboarding-admin-tabs" role="tablist"><button className={view === 'review' ? 'is-active' : ''} onClick={() => setView('review')}>Hồ sơ chờ duyệt ({submissions.filter((item) => item.status === 'NEW').length})</button><button className={view === 'builder' ? 'is-active' : ''} onClick={() => setView('builder')}>Thiết kế mẫu</button></div>

    {view === 'builder' && draft && <section className="onboarding-admin-card"><div className="onboarding-config-grid"><label className="onboarding-field"><span className="onboarding-field-label">Tiêu đề</span><input className="onboarding-input" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label className="onboarding-field"><span className="onboarding-field-label">Thông báo sau khi gửi</span><input className="onboarding-input" value={draft.success_message} onChange={(event) => setDraft({ ...draft, success_message: event.target.value })} /></label><label className="onboarding-field is-wide"><span className="onboarding-field-label">Mô tả</span><textarea className="onboarding-textarea" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label></div>
      <div className="onboarding-builder-list">{draft.fields.map((field, index) => <div className="onboarding-builder-row" key={`${field.key}-${index}`}><label className="onboarding-field onboarding-builder-display-label"><span className="onboarding-field-label">Nhãn hiển thị</span><input className="onboarding-input" value={field.label} onChange={(event) => updateField(index, { label: event.target.value })} /></label><label className="onboarding-field"><span className="onboarding-field-label">Mã trường</span><input className="onboarding-input" value={field.key} disabled={systemFields.includes(field.key)} onChange={(event) => updateField(index, { key: event.target.value })} /></label><label className="onboarding-field"><span className="onboarding-field-label">Nhóm</span><input className="onboarding-input" value={field.section || ''} onChange={(event) => updateField(index, { section: event.target.value })} /></label><label className="onboarding-field"><span className="onboarding-field-label">Loại</span><select className="onboarding-select" value={field.type} onChange={(event) => updateField(index, { type: event.target.value })}>{fieldTypes.map((type) => <option key={type}>{type}</option>)}</select></label><span className="onboarding-row-buttons"><button className="onboarding-icon-button" title="Đưa lên" onClick={() => moveField(index, -1)}>↑</button><button className="onboarding-icon-button" title="Đưa xuống" onClick={() => moveField(index, 1)}>↓</button><button className="onboarding-icon-button danger" title="Xóa" disabled={systemFields.includes(field.key)} onClick={() => setDraft({ ...draft, fields: draft.fields.filter((_, position) => position !== index) })}><AppIcon name="trash" size={16} /></button></span><label className="onboarding-check"><input type="checkbox" checked={field.active !== false} onChange={(event) => updateField(index, { active: event.target.checked })} /> Hiển thị</label><label className="onboarding-check"><input type="checkbox" checked={Boolean(field.required)} onChange={(event) => updateField(index, { required: event.target.checked })} /> Bắt buộc</label><label className="onboarding-field"><span className="onboarding-field-label">Gợi ý trong ô</span><input className="onboarding-input" value={field.placeholder || ''} onChange={(event) => updateField(index, { placeholder: event.target.value })} /></label>{field.type === 'file' && <label className="onboarding-field"><span className="onboarding-field-label">Số tệp tối đa</span><input className="onboarding-input" type="number" min={1} max={10} value={field.max_files || 1} onChange={(event) => updateField(index, { max_files: Math.max(1, Math.min(10, Number(event.target.value) || 1)) })} /></label>}{['select', 'multiselect'].includes(field.type) && <label className="onboarding-field onboarding-builder-options"><span className="onboarding-field-label">Lựa chọn (GIÁ_TRỊ|Nhãn, mỗi dòng)</span><textarea className="onboarding-textarea" value={optionsText(field)} onChange={(event) => updateField(index, { options: optionsFromText(event.target.value) })} /></label>}</div>)}</div>
      <div className="onboarding-actions"><button className="onboarding-button" onClick={() => setDraft({ ...draft, fields: [...draft.fields, { key: `custom_${Date.now()}`, label: 'Trường mới', type: 'text', active: true, required: false, section: 'Thông tin bổ sung' }] })}><AppIcon name="plus" size={16} /> Thêm trường</button><button className="onboarding-button" disabled={busy} onClick={() => void saveDraft()}>Lưu bản nháp</button><button className="onboarding-button primary" disabled={busy} onClick={() => void publish()}>Phát hành phiên bản mới</button></div>{config && <p className="onboarding-help">Link công khai đang dùng phiên bản {config.published.version_number}; hồ sơ cũ luôn giữ đúng mẫu đã nộp.</p>}</section>}

    {view === 'review' && <div className="onboarding-review-layout"><section className="onboarding-admin-card onboarding-review-list-card"><label className="onboarding-field"><span className="onboarding-field-label">Lọc trạng thái</span><select className="onboarding-select" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">Tất cả</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><div className="onboarding-submission-list" style={{ marginTop: 12 }}>{filtered.map((item) => <button className={`onboarding-submission-item${selectedId === item.id ? ' is-active' : ''}`} key={item.id} onClick={() => { setSelectedId(item.id); setNote(item.review_note || ''); setApproval({ employee_id: item.employee_id ? String(item.employee_id) : '', confirmed_last_working_date: item.confirmed_last_working_date || item.desired_last_working_date, last_pay_date: item.last_pay_date || '' }) }}><strong>{item.full_name}</strong><div className="onboarding-submission-meta"><span>{item.email || '—'}</span><span className={`onboarding-status ${item.status}`}>{statusLabels[item.status] || item.status}</span></div><div className="onboarding-submission-meta"><span>{item.department || '—'}</span><span>{new Date(item.submitted_at).toLocaleDateString('vi-VN')}</span></div></button>)}{!filtered.length && <p className="onboarding-help">Chưa có hồ sơ phù hợp.</p>}</div></section>
      <section className="onboarding-admin-card onboarding-review-detail">{selected ? <><div className="onboarding-detail-header"><div><h3 style={{ margin: 0 }}>{selected.full_name}</h3><p className="onboarding-help">{selected.email || '—'} · Mã theo dõi {selected.public_id}</p></div><span className={`onboarding-status ${selected.status}`}>{statusLabels[selected.status] || selected.status}</span></div><dl className="onboarding-answer-grid">{selected.fields.filter((field) => field.active !== false && field.type !== 'file').map((field) => <div className="onboarding-answer" key={field.key}><dt>{field.label}</dt><dd>{Array.isArray(selected.answers[field.key]) ? (selected.answers[field.key] as unknown[]).join(', ') : String(selected.answers[field.key] ?? '—')}</dd></div>)}</dl><div className="onboarding-attachment-list">{selected.attachments.map((attachment) => <button className="onboarding-button" key={attachment.id} onClick={() => void downloadAttachment(attachment)}><AppIcon name="download" size={15} /> {attachment.original_name}</button>)}</div>
        <div className="onboarding-review-actions"><label className="onboarding-field"><span className="onboarding-field-label">Ghi chú xử lý</span><textarea className="onboarding-textarea" value={note} onChange={(event) => setNote(event.target.value)} /></label><div className="onboarding-approval-grid"><label className="onboarding-field"><span className="onboarding-field-label">Đối chiếu nhân viên</span><select className="onboarding-select" value={approval.employee_id} onChange={(event) => setApproval({ ...approval, employee_id: event.target.value })}><option value="">Tự động theo mã / email</option>{employees.map((item) => <option key={item.id} value={item.id}>{item.employee_code ? `${item.employee_code} · ` : ''}{item.full_name}</option>)}</select></label><label className="onboarding-field"><span className="onboarding-field-label">Ngày làm việc cuối cùng</span><input className="onboarding-input" type="date" value={approval.confirmed_last_working_date || selected.desired_last_working_date} onChange={(event) => setApproval({ ...approval, confirmed_last_working_date: event.target.value })} /></label><label className="onboarding-field"><span className="onboarding-field-label">Ngày trả lương cuối</span><input className="onboarding-input" type="date" value={approval.last_pay_date} onChange={(event) => setApproval({ ...approval, last_pay_date: event.target.value })} /></label></div><div className="onboarding-actions"><button className="onboarding-button" disabled={busy} onClick={() => void reviewAction('request-changes')}>Yêu cầu bổ sung</button><button className="onboarding-button danger" disabled={busy} onClick={() => void reviewAction('reject')}>Từ chối</button><button className="onboarding-button primary" disabled={busy} onClick={() => void approve()}>Phê duyệt</button></div></div></> : <p className="onboarding-help">Chọn một hồ sơ để kiểm tra.</p>}</section></div>}
  </div>
}
