import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { credentialedFetch } from '../../shared/api/credentialedFetch'
import '../onboarding/onboarding.css'

export type OffboardingField = {
  key: string; label: string; type: string; required?: boolean; active?: boolean; section?: string
  placeholder?: string; description?: string; options?: { value: string; label: string }[]
  min?: number; max?: number; max_files?: number
}
export type OffboardingFormConfig = {
  id: number; version_number: number; status: string; title: string; description: string
  success_message: string; fields: OffboardingField[]
}

export function OffboardingPublic({ apiBase }: { apiBase: string }) {
  const [config, setConfig] = useState<OffboardingFormConfig | null>(null)
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({ request_date: new Date().toISOString().slice(0, 10) })
  const [files, setFiles] = useState<Record<string, File[]>>({})
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<{ public_id: string; message: string } | null>(null)

  useEffect(() => {
    credentialedFetch(`${apiBase}/api/offboarding/form`).then(async (response) => {
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Không thể tải biểu mẫu nghỉ việc.')
      return payload
    }).then(setConfig).catch((reason: Error) => setError(reason.message))
  }, [apiBase])

  const sections = useMemo(() => {
    const grouped = new Map<string, OffboardingField[]>()
    for (const field of config?.fields || []) {
      if (field.active === false) continue
      const section = field.section || 'Thông tin khác'
      grouped.set(section, [...(grouped.get(section) || []), field])
    }
    return [...grouped.entries()]
  }, [config])

  const setValue = (key: string, value: string | string[]) => setAnswers((current) => ({ ...current, [key]: value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!config) return
    setSubmitting(true); setError('')
    try {
      const body = new FormData(); body.append('answers_json', JSON.stringify(answers)); body.append('website', '')
      const fileKeys: string[] = []
      Object.entries(files).forEach(([key, selected]) => selected.forEach((file) => { fileKeys.push(key); body.append('files', file) }))
      body.append('file_keys_json', JSON.stringify(fileKeys))
      const response = await credentialedFetch(`${apiBase}/api/offboarding/submissions`, { method: 'POST', body })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Gửi đơn nghỉ việc thất bại.')
      setResult(payload); window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (reason) { setError((reason as Error).message) }
    finally { setSubmitting(false) }
  }

  if (result) return <main className="onboarding-public-page"><div className="onboarding-public-shell"><section className="onboarding-card onboarding-success">
    <div className="onboarding-brand-mark" style={{ margin: '0 auto 18px' }}>SL</div><h1>Đã gửi đơn thành công</h1>
    <p className="onboarding-lead">{result.message}</p><div className="onboarding-success-code">Mã theo dõi: {result.public_id}</div>
    <p className="onboarding-help">Hãy lưu mã này. Bộ phận Nhân sự sẽ liên hệ nếu cần bổ sung thông tin.</p>
  </section></div></main>

  return <main className="onboarding-public-page"><div className="onboarding-public-shell">
    <div className="onboarding-brand"><div className="onboarding-brand-mark">SL</div><div><strong>SEALINK INTERNATIONAL</strong><span>Employee Offboarding Portal</span></div></div>
    <form className="onboarding-card" onSubmit={submit}>
      <h1>{config?.title || 'Đang tải biểu mẫu…'}</h1><p className="onboarding-lead">{config?.description}</p>
      {config && <span className="onboarding-version">Phiên bản {config.version_number}</span>}{error && <div className="onboarding-alert">{error}</div>}
      {sections.map(([section, fields]) => <section className="onboarding-section" key={section}><h2>{section}</h2><div className="onboarding-field-grid">
        {fields.map((field) => {
          const wide = ['textarea', 'multiselect', 'file'].includes(field.type)
          return <label className={`onboarding-field${wide ? ' is-wide' : ''}`} key={field.key}><span className="onboarding-field-label">{field.label}{field.required && <span className="onboarding-required">*</span>}</span>
            {field.type === 'textarea' ? <textarea className="onboarding-textarea" required={field.required} placeholder={field.placeholder} value={String(answers[field.key] || '')} onChange={(event) => setValue(field.key, event.target.value)} />
              : field.type === 'select' ? <select className="onboarding-select" required={field.required} value={String(answers[field.key] || '')} onChange={(event) => setValue(field.key, event.target.value)}><option value="">-- Chọn --</option>{(field.options || []).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
              : field.type === 'multiselect' ? <span className="onboarding-options">{(field.options || []).map((option) => { const values = (answers[field.key] as string[]) || []; const selected = values.includes(option.value); return <span className="onboarding-option" key={option.value}><input type="checkbox" checked={selected} onChange={() => setValue(field.key, selected ? values.filter((value) => value !== option.value) : [...values, option.value])} />{option.label}</span> })}</span>
              : field.type === 'file' ? <span className="onboarding-file"><input className="onboarding-input" type="file" required={field.required && !files[field.key]?.length} multiple={(field.max_files || 1) > 1} accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx" onChange={(event) => setFiles((current) => ({ ...current, [field.key]: Array.from(event.target.files || []).slice(0, field.max_files || 1) }))} /></span>
              : <input className="onboarding-input" type={field.type === 'phone' ? 'tel' : field.type} required={field.required} min={field.min} max={field.max} placeholder={field.placeholder} value={String(answers[field.key] || '')} onChange={(event) => setValue(field.key, event.target.value)} />}
            {field.description && <p className="onboarding-help">{field.description}</p>}</label>
        })}
      </div></section>)}
      <div className="onboarding-actions"><button className="onboarding-button primary" type="submit" disabled={!config || submitting}>{submitting ? 'Đang gửi đơn…' : 'Gửi đơn xin nghỉ việc'}</button></div>
    </form>
  </div></main>
}
