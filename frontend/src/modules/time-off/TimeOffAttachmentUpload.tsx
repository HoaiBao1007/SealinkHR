import { useRef, useState } from 'react'
import { BUSINESS_TRAVEL_REQUEST } from './TimeOffRequestIntent'
import './time-off-attachment-upload.css'

type ApiRequest = (path: string, init?: RequestInit) => Promise<Response>

export type TimeOffAttachment = {
  id: number
  file_name: string
  content_type: string
  size_bytes: number
  uploaded_at: string
  is_staged?: boolean
}

type Props = {
  apiRequest: ApiRequest
  requestType: string
  attachments: TimeOffAttachment[]
  onChange: (attachments: TimeOffAttachment[]) => void
  disabled?: boolean
}

const MAX_FILES = 10
const MAX_FILE_BYTES = 100 * 1024 * 1024
const ACCEPTED_FILES = '.pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.csv,.txt,.zip'

async function responseJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error((payload as { detail?: string }).detail || 'Không thể tải file đính kèm.')
  return payload as T
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`
  return `${(value / (1024 * 1024)).toLocaleString('vi-VN', { maximumFractionDigits: 1 })} MB`
}

export function TimeOffAttachmentUpload({ apiRequest, requestType, attachments, onChange, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isBusinessTravel = requestType === BUSINESS_TRAVEL_REQUEST

  async function uploadFiles(files: File[]) {
    setError(null)
    if (!files.length) return
    if (attachments.length + files.length > MAX_FILES) {
      setError(`Chỉ được đính kèm tối đa ${MAX_FILES} file.`)
      return
    }
    const tooLarge = files.find((file) => file.size > MAX_FILE_BYTES)
    if (tooLarge) {
      setError(`“${tooLarge.name}” vượt quá giới hạn 100 MB.`)
      return
    }

    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    setUploading(true)
    try {
      const payload = await responseJson<{ items: TimeOffAttachment[] }>(await apiRequest('/api/time-off/attachments', {
        method: 'POST',
        body: formData,
      }))
      onChange([...attachments, ...(payload.items || [])])
    } catch (uploadError) {
      setError((uploadError as Error).message)
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function removeStagedAttachment(attachment: TimeOffAttachment) {
    if (!attachment.is_staged) return
    setError(null)
    try {
      const response = await apiRequest(`/api/time-off/attachments/${attachment.id}`, { method: 'DELETE' })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string }
        throw new Error(payload.detail || 'Không thể gỡ file đính kèm.')
      }
      onChange(attachments.filter((item) => item.id !== attachment.id))
    } catch (removeError) {
      setError((removeError as Error).message)
    }
  }

  return (
    <section className="time-off-attachments" aria-label="File đính kèm">
      <div className="time-off-attachments-heading">
        <h4>File đính kèm{isBusinessTravel && <b> *</b>}</h4>
        <p>{isBusinessTravel ? 'Vui lòng upload quyết định của BGĐ' : 'File đính kèm nếu có (không bắt buộc)'}</p>
      </div>
      <div className="time-off-attachments-upload-row">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_FILES}
          disabled={disabled || uploading || attachments.length >= MAX_FILES}
          onChange={(event) => void uploadFiles(Array.from(event.target.files || []))}
        />
        <button type="button" className="time-off-attachments-upload-button" onClick={() => inputRef.current?.click()} disabled={disabled || uploading || attachments.length >= MAX_FILES}>
          <span aria-hidden="true">⇧</span>{uploading ? 'Đang tải…' : 'Upload'}
        </button>
        <small>Size limit: 100 MB. File limit: 10.</small>
      </div>
      {attachments.length > 0 && (
        <ul className="time-off-attachments-list">
          {attachments.map((attachment) => (
            <li key={attachment.id}>
              <span aria-hidden="true">▧</span>
              <strong title={attachment.file_name}>{attachment.file_name}</strong>
              <small>{formatBytes(attachment.size_bytes)}{attachment.is_staged ? ' · Sẵn sàng gửi' : ' · Đã đính kèm'}</small>
              {attachment.is_staged && (
                <button type="button" onClick={() => void removeStagedAttachment(attachment)} disabled={disabled || uploading} aria-label={`Gỡ ${attachment.file_name}`}>×</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="time-off-attachments-error" role="alert">{error}</p>}
    </section>
  )
}

