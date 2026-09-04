import { useEffect, useMemo, useRef, useState } from 'react'
import { BrandedDateInput } from '../../shared/ui/BrandedDateInput'
import { AppIcon } from '../../shared/ui/AppIcon'
import './date-time-range-picker.css'

type Props = {
  startAt: string
  endAt: string
  onChange: (range: { startAt: string; endAt: string }) => void
  disabled?: boolean
  compact?: boolean
}

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, index) => pad(index))
const MINUTE_OPTIONS = ['00', '30']

function pad(value: number) {
  return String(value).padStart(2, '0')
}

export function toLocalDateTimeValue(value: Date) {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`
}

export function defaultTimeOffRange(reference = new Date()) {
  const start = new Date(reference)
  if (start.getDay() === 6) start.setDate(start.getDate() + 2)
  if (start.getDay() === 0) start.setDate(start.getDate() + 1)
  start.setHours(8, 0, 0, 0)
  const end = new Date(start)
  end.setHours(17, 0, 0, 0)
  return { startAt: toLocalDateTimeValue(start), endAt: toLocalDateTimeValue(end) }
}

function parseLocalDateTime(value: string) {
  if (!value) return null
  const [datePart, timePart = '00:00'] = value.split('T')
  const [year, month, day] = datePart.split('-').map(Number)
  const [hour, minute] = timePart.split(':').map(Number)
  const result = new Date(year, month - 1, day, hour, minute)
  return Number.isNaN(result.getTime()) ? null : result
}

function dateTimeParts(value: string) {
  const parsed = parseLocalDateTime(value) || new Date()
  return {
    date: `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`,
    hour: pad(parsed.getHours()),
    minute: parsed.getMinutes() < 30 ? '00' : '30',
  }
}

function composeDateTime(parts: { date: string; hour: string; minute: string }) {
  return `${parts.date}T${parts.hour}:${parts.minute}`
}

export function snapDateTimeToHalfHour(value: string) {
  const parsed = parseLocalDateTime(value)
  if (!parsed) return value
  const minute = parsed.getMinutes()
  if (minute < 15) parsed.setMinutes(0, 0, 0)
  else if (minute < 45) parsed.setMinutes(30, 0, 0)
  else {
    parsed.setHours(parsed.getHours() + 1)
    parsed.setMinutes(0, 0, 0)
  }
  return toLocalDateTimeValue(parsed)
}

function formatValue(value: string) {
  const date = parseLocalDateTime(value)
  if (!date) return 'Chưa chọn'
  return `${pad(date.getHours())}:${pad(date.getMinutes())} ${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`
}

function durationLabel(startAt: string, endAt: string) {
  const start = parseLocalDateTime(startAt)
  const end = parseLocalDateTime(endAt)
  if (!start || !end || end <= start) return 'Khoảng thời gian chưa hợp lệ'
  if (start.toDateString() === end.toDateString()) {
    const clockRange = `${pad(start.getHours())}:${pad(start.getMinutes())}-${pad(end.getHours())}:${pad(end.getMinutes())}`
    if (clockRange === '08:00-17:00') return '1 ngày công'
    if (clockRange === '08:00-12:00' || clockRange === '13:00-17:00') return '0,5 ngày công'
  }
  const totalMinutes = Math.round((end.getTime() - start.getTime()) / 60_000)
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60
  return [days ? `${days} ngày` : '', hours ? `${hours} giờ` : '', minutes ? `${minutes} phút` : '']
    .filter(Boolean)
    .join(' ') || '0 phút'
}

export function DateTimeRangePicker({ startAt, endAt, onChange, disabled = false, compact = false }: Props) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const duration = useMemo(() => durationLabel(startAt, endAt), [startAt, endAt])
  const startParts = dateTimeParts(startAt)
  const endParts = dateTimeParts(endAt)

  useEffect(() => {
    if (!open) return
    function handlePointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  function updateStart(nextStart: string) {
    let nextEnd = endAt
    const startDate = parseLocalDateTime(nextStart)
    const endDate = parseLocalDateTime(endAt)
    if (startDate && (!endDate || endDate <= startDate)) {
      const adjustedEnd = new Date(startDate)
      adjustedEnd.setHours(adjustedEnd.getHours() + 1)
      nextEnd = toLocalDateTimeValue(adjustedEnd)
    }
    onChange({ startAt: nextStart, endAt: nextEnd })
  }

  function updateStartPart(part: 'date' | 'hour' | 'minute', value: string) {
    updateStart(composeDateTime({ ...startParts, [part]: value }))
  }

  function updateEndPart(part: 'date' | 'hour' | 'minute', value: string) {
    onChange({ startAt, endAt: composeDateTime({ ...endParts, [part]: value }) })
  }

  function useWorkingDay() {
    const base = parseLocalDateTime(startAt) || new Date()
    const range = defaultTimeOffRange(base)
    onChange(range)
  }

  function extendToNextDay() {
    const start = parseLocalDateTime(startAt) || new Date()
    const currentEnd = parseLocalDateTime(endAt)
    const nextEnd = new Date(start)
    nextEnd.setDate(nextEnd.getDate() + 1)
    nextEnd.setHours(currentEnd?.getHours() ?? 17, currentEnd?.getMinutes() ?? 0, 0, 0)
    onChange({ startAt: toLocalDateTimeValue(start), endAt: toLocalDateTimeValue(nextEnd) })
  }

  return (
    <div ref={containerRef} className={`date-time-range${compact ? ' is-compact' : ''}`}>
      <span className="date-time-range-label">Ngày & giờ nghỉ *</span>
      <button
        type="button"
        className="date-time-range-trigger"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        disabled={disabled}
      >
        <span className="date-time-range-calendar" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M7 3v3m10-3v3M4.5 9.5h15M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" /></svg>
        </span>
        <span className="date-time-range-summary">
          <strong>{formatValue(startAt)}</strong>
          <AppIcon name="arrow-right" size={14} />
          <strong>{formatValue(endAt)}</strong>
        </span>
        <small>{duration}</small>
        <span className="date-time-range-chevron"><AppIcon name="chevron-down" size={15} /></span>
      </button>

      {open && (
        <div className="date-time-range-popover" role="dialog" aria-label="Chọn khoảng ngày và giờ nghỉ">
          <div className="date-time-range-popover-heading">
            <div>
              <strong>Khoảng thời gian nghỉ</strong>
              <span>{duration}</span>
            </div>
            <button type="button" className="app-close-button app-close-button--compact" onClick={() => setOpen(false)} aria-label="Đóng"><AppIcon name="close" size={14} /></button>
          </div>

          <div className="date-time-range-row" role="group" aria-label="Thời gian bắt đầu">
            <span>Bắt đầu</span>
            <div className="date-time-range-controls">
              <BrandedDateInput
                value={startParts.date}
                onChange={(event) => updateStartPart('date', event.target.value)}
                aria-label="Ngày bắt đầu"
                lang="vi"
                required
              />
              <div className="date-time-range-clock">
                <select value={startParts.hour} onChange={(event) => updateStartPart('hour', event.target.value)} aria-label="Giờ bắt đầu">
                  {HOUR_OPTIONS.map((hour) => <option key={hour} value={hour}>{hour}</option>)}
                </select>
                <span>:</span>
                <select value={startParts.minute} onChange={(event) => updateStartPart('minute', event.target.value)} aria-label="Phút bắt đầu">
                  {MINUTE_OPTIONS.map((minute) => <option key={minute} value={minute}>{minute}</option>)}
                </select>
              </div>
            </div>
          </div>
          <div className="date-time-range-row" role="group" aria-label="Thời gian kết thúc">
            <span>Kết thúc</span>
            <div className="date-time-range-controls">
              <BrandedDateInput
                value={endParts.date}
                min={startParts.date}
                onChange={(event) => updateEndPart('date', event.target.value)}
                aria-label="Ngày kết thúc"
                lang="vi"
                required
              />
              <div className="date-time-range-clock">
                <select value={endParts.hour} onChange={(event) => updateEndPart('hour', event.target.value)} aria-label="Giờ kết thúc">
                  {HOUR_OPTIONS.map((hour) => <option key={hour} value={hour}>{hour}</option>)}
                </select>
                <span>:</span>
                <select value={endParts.minute} onChange={(event) => updateEndPart('minute', event.target.value)} aria-label="Phút kết thúc">
                  {MINUTE_OPTIONS.map((minute) => <option key={minute} value={minute}>{minute}</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="date-time-range-shortcuts">
            <button type="button" onClick={useWorkingDay}>08:00–17:00</button>
            <button type="button" onClick={extendToNextDay}>Qua ngày sau</button>
          </div>
          <button type="button" className="date-time-range-done" onClick={() => setOpen(false)}>Xong</button>
        </div>
      )}
    </div>
  )
}
