import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, InputHTMLAttributes, KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'

type BrandedDateInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'value' | 'defaultValue'> & {
  value: string
  placeholder?: string
  containerClassName?: string
}

const WEEKDAYS = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
const DISPLAY_DATE = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })
const DISPLAY_MONTH = new Intl.DateTimeFormat('vi-VN', { month: 'long', year: 'numeric' })

function parseIsoDate(value: string) {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return null
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12)
  return Number.isNaN(date.getTime()) ? null : date
}

function isoDate(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function monthStart(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), 1, 12)
}

function addDays(date: Date, amount: number) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + amount, 12)
}

function CalendarIcon({ active }: { active: boolean }) {
  return (
    <svg className={`branded-date-icon${active ? ' is-active' : ''}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.25" y="5.25" width="17.5" height="15" rx="3" />
      <path className="branded-date-icon-rings" d="M8 3.5v4M16 3.5v4M3.5 9.5h17" />
      <path className="branded-date-icon-days" d="M7.75 13h.01M12 13h.01M16.25 13h.01M7.75 16.5h.01M12 16.5h.01" />
    </svg>
  )
}

export function BrandedDateInput({
  value,
  min,
  max,
  disabled = false,
  required = false,
  className = '',
  containerClassName = '',
  style,
  placeholder = 'Chọn ngày',
  onChange,
  onInvalid,
  'aria-label': ariaLabel,
  ...nativeProps
}: BrandedDateInputProps) {
  const generatedId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLElement>(null)
  const today = useMemo(() => new Date(), [])
  const todayIso = isoDate(today)
  const selected = parseIsoDate(value)
  const initialDate = selected || today
  const [open, setOpen] = useState(false)
  const [viewMonth, setViewMonth] = useState(() => monthStart(initialDate))
  const [focusDate, setFocusDate] = useState(() => isoDate(initialDate))
  const [position, setPosition] = useState({ top: 0, left: 0, width: 320 })

  const days = useMemo(() => {
    const firstWeekday = (viewMonth.getDay() + 6) % 7
    const firstVisible = addDays(viewMonth, -firstWeekday)
    return Array.from({ length: 42 }, (_, index) => addDays(firstVisible, index))
  }, [viewMonth])

  function isDisabled(candidate: string) {
    return Boolean((min && candidate < String(min)) || (max && candidate > String(max)))
  }

  function activeCalendarDate() {
    if (selected && !isDisabled(value)) return selected
    if (!isDisabled(todayIso)) return today
    return parseIsoDate(String(min || '')) || parseIsoDate(String(max || '')) || today
  }

  function emitChange(nextValue: string) {
    const input = inputRef.current
    if (!input || !onChange) return
    const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
    if (valueSetter) valueSetter.call(input, nextValue)
    else input.value = nextValue
    onChange({ target: input, currentTarget: input } as ChangeEvent<HTMLInputElement>)
  }

  function choose(candidate: string) {
    if (isDisabled(candidate)) return
    emitChange(candidate)
    setOpen(false)
  }

  function updatePosition() {
    const trigger = triggerRef.current
    if (!trigger) return
    const rect = trigger.getBoundingClientRect()
    const width = Math.min(320, window.innerWidth - 24)
    const left = Math.min(Math.max(12, rect.left), Math.max(12, window.innerWidth - width - 12))
    const estimatedHeight = 374
    const below = window.innerHeight - rect.bottom
    const top = below >= estimatedHeight + 12
      ? rect.bottom + 8
      : Math.max(12, rect.top - estimatedHeight - 8)
    setPosition({ top, left, width })
  }

  function toggleCalendar() {
    if (disabled) return
    if (!open) {
      const activeDate = activeCalendarDate()
      setViewMonth(monthStart(activeDate))
      setFocusDate(isoDate(activeDate))
      requestAnimationFrame(updatePosition)
    }
    setOpen((current) => !current)
  }

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, current: Date) {
    const moves: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
    if (!(event.key in moves)) return
    event.preventDefault()
    const next = addDays(current, moves[event.key])
    const candidate = isoDate(next)
    if (isDisabled(candidate)) return
    setViewMonth(monthStart(next))
    setFocusDate(candidate)
  }

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (!triggerRef.current?.contains(target) && !popoverRef.current?.contains(target)) setOpen(false)
    }
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const reposition = () => updatePosition()
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    requestAnimationFrame(() => {
      popoverRef.current?.querySelector<HTMLButtonElement>(`[data-calendar-date="${focusDate}"]`)?.focus()
    })
  }, [focusDate, open, viewMonth])

  const monthTitle = DISPLAY_MONTH.format(viewMonth)
  const todayAllowed = !isDisabled(todayIso)
  const triggerId = nativeProps.id || `date-${generatedId}`

  return (
    <span className={`branded-date-picker${containerClassName ? ` ${containerClassName}` : ''}${open ? ' is-open' : ''}${disabled ? ' is-disabled' : ''}`}>
      <input
        {...nativeProps}
        ref={inputRef}
        id={triggerId}
        className="branded-date-native"
        type="date"
        value={value}
        min={min}
        max={max}
        disabled={disabled}
        required={required}
        aria-label={ariaLabel}
        onChange={onChange}
        onInvalid={(event) => {
          setOpen(true)
          requestAnimationFrame(updatePosition)
          onInvalid?.(event)
        }}
      />
      <button
        ref={triggerRef}
        type="button"
        className={`branded-date-trigger${value ? ' has-value' : ''}${className ? ` ${className}` : ''}`}
        style={style}
        aria-label={ariaLabel || 'Chọn ngày'}
        aria-controls={`${triggerId}-calendar`}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={toggleCalendar}
      >
        <span>{selected ? DISPLAY_DATE.format(selected) : placeholder}</span>
        <CalendarIcon active={open} />
      </button>
      {open && createPortal(
        <section
          ref={popoverRef}
          id={`${triggerId}-calendar`}
          className="branded-date-popover"
          style={position}
          role="dialog"
          aria-modal="false"
          aria-label="Chọn ngày"
        >
          <header>
            <button type="button" aria-label="Tháng trước" onClick={() => setViewMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1, 12))}>‹</button>
            <strong>{monthTitle.charAt(0).toUpperCase() + monthTitle.slice(1)}</strong>
            <button type="button" aria-label="Tháng sau" onClick={() => setViewMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1, 12))}>›</button>
          </header>
          <div className="branded-date-weekdays" aria-hidden="true">
            {WEEKDAYS.map((day) => <span key={day}>{day}</span>)}
          </div>
          <div className="branded-date-days" role="grid">
            {days.map((date) => {
              const candidate = isoDate(date)
              const candidateDisabled = isDisabled(candidate)
              const outside = date.getMonth() !== viewMonth.getMonth()
              return (
                <button
                  type="button"
                  role="gridcell"
                  data-calendar-date={candidate}
                  className={`${outside ? 'outside ' : ''}${candidate === value ? 'selected ' : ''}${candidate === todayIso ? 'today' : ''}`.trim()}
                  aria-label={DISPLAY_DATE.format(date)}
                  aria-selected={candidate === value}
                  aria-current={candidate === todayIso ? 'date' : undefined}
                  disabled={candidateDisabled}
                  tabIndex={candidate === focusDate ? 0 : -1}
                  onFocus={() => setFocusDate(candidate)}
                  onKeyDown={(event) => moveFocus(event, date)}
                  onClick={() => choose(candidate)}
                  key={candidate}
                >
                  {date.getDate()}
                </button>
              )
            })}
          </div>
          <footer>
            <button type="button" className="branded-date-clear" disabled={!value} onClick={() => { emitChange(''); setOpen(false) }}>Xóa ngày</button>
            <button type="button" className="branded-date-today" disabled={!todayAllowed} onClick={() => choose(todayIso)}>Hôm nay</button>
          </footer>
        </section>,
        document.body,
      )}
    </span>
  )
}
