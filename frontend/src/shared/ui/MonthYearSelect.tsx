import { useMemo } from 'react'
import './MonthYearSelect.css'

const PERIOD_PATTERN = /^(\d{4})-(0[1-9]|1[0-2])$/

export function currentMonthPeriod(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function compareMonthPeriods(left: string, right: string): number {
  return left.localeCompare(right)
}

export function closestMonthPeriod(periods: readonly string[], target = currentMonthPeriod()): string {
  const validPeriods = Array.from(new Set(periods.filter((period) => PERIOD_PATTERN.test(period))))
  if (validPeriods.length === 0) return ''
  const [targetYear, targetMonth] = target.split('-').map(Number)
  const targetIndex = (targetYear * 12) + targetMonth
  return validPeriods.sort((left, right) => {
    const [leftYear, leftMonth] = left.split('-').map(Number)
    const [rightYear, rightMonth] = right.split('-').map(Number)
    const leftDistance = Math.abs(((leftYear * 12) + leftMonth) - targetIndex)
    const rightDistance = Math.abs(((rightYear * 12) + rightMonth) - targetIndex)
    return leftDistance - rightDistance || right.localeCompare(left)
  })[0]
}

type MonthYearSelectProps = {
  value: string
  onChange: (period: string) => void
  availablePeriods?: readonly string[]
  minYear?: number
  maxYear?: number
  disabled?: boolean
  compact?: boolean
  showLabels?: boolean
  className?: string
  id?: string
  yearLabel?: string
  monthLabel?: string
  emptyLabel?: string
  allowEmpty?: boolean
}

const MONTH_LABELS = Array.from({ length: 12 }, (_, index) => ({
  value: String(index + 1).padStart(2, '0'),
  label: `Tháng ${String(index + 1).padStart(2, '0')}`,
}))

export function MonthYearSelect({
  value,
  onChange,
  availablePeriods,
  minYear,
  maxYear,
  disabled = false,
  compact = false,
  showLabels = true,
  className = '',
  id = 'month-year-select',
  yearLabel = 'Năm',
  monthLabel = 'Tháng',
  emptyLabel = 'Chưa có kỳ dữ liệu',
  allowEmpty = false,
}: MonthYearSelectProps) {
  const now = new Date()
  const currentYear = now.getFullYear()
  const currentMonth = String(now.getMonth() + 1).padStart(2, '0')
  const matchedValue = PERIOD_PATTERN.exec(value)
  const selectedYear = matchedValue?.[1] || ''
  const selectedMonth = matchedValue?.[2] || ''
  const restrictedPeriods = useMemo(
    () => availablePeriods === undefined
      ? undefined
      : Array.from(new Set(availablePeriods.filter((period) => PERIOD_PATTERN.test(period)))).sort(compareMonthPeriods),
    [availablePeriods],
  )
  const years = useMemo(() => {
    if (restrictedPeriods !== undefined) {
      return Array.from(new Set(restrictedPeriods.map((period) => period.slice(0, 4))))
        .sort((left, right) => Number(right) - Number(left))
    }
    const first = minYear ?? Math.min(currentYear - 5, Number(selectedYear) || currentYear)
    const last = maxYear ?? Math.max(currentYear + 5, Number(selectedYear) || currentYear)
    return Array.from({ length: Math.max(1, last - first + 1) }, (_, index) => String(last - index))
  }, [currentYear, maxYear, minYear, restrictedPeriods, selectedYear])
  const months = useMemo(() => {
    if (restrictedPeriods === undefined) return MONTH_LABELS
    if (!selectedYear) return []
    const allowed = new Set(
      restrictedPeriods
        .filter((period) => period.startsWith(`${selectedYear}-`))
        .map((period) => period.slice(5, 7)),
    )
    return MONTH_LABELS.filter((month) => allowed.has(month.value))
  }, [restrictedPeriods, selectedYear])
  const hasOptions = restrictedPeriods === undefined || restrictedPeriods.length > 0
  const isDisabled = disabled || !hasOptions

  const selectYear = (nextYear: string) => {
    if (!nextYear) {
      onChange('')
      return
    }
    const allowedMonths = restrictedPeriods === undefined
      ? MONTH_LABELS.map((month) => month.value)
      : restrictedPeriods.filter((period) => period.startsWith(`${nextYear}-`)).map((period) => period.slice(5, 7))
    const preferredMonth = allowedMonths.includes(selectedMonth)
      ? selectedMonth
      : allowedMonths.includes(currentMonth)
        ? currentMonth
        : [...allowedMonths].sort().reverse()[0]
    onChange(preferredMonth ? `${nextYear}-${preferredMonth}` : '')
  }

  const selectMonth = (nextMonth: string) => {
    if (!nextMonth) {
      onChange('')
      return
    }
    const fallbackYear = selectedYear || years[0] || String(currentYear)
    onChange(`${fallbackYear}-${nextMonth}`)
  }

  return (
    <div className={`month-year-select${compact ? ' month-year-select--compact' : ''} ${className}`.trim()}>
      <label className="month-year-select__field">
        <span className={showLabels ? 'month-year-select__label' : 'month-year-select__label month-year-select__label--sr'}>{yearLabel}</span>
        <select
          id={`${id}-year`}
          aria-label={yearLabel}
          value={selectedYear}
          disabled={isDisabled}
          onChange={(event) => selectYear(event.target.value)}
        >
          {(allowEmpty || !selectedYear) && <option value="">{hasOptions ? 'Chọn năm' : emptyLabel}</option>}
          {years.map((year) => <option key={year} value={year}>{year}</option>)}
        </select>
      </label>
      <label className="month-year-select__field">
        <span className={showLabels ? 'month-year-select__label' : 'month-year-select__label month-year-select__label--sr'}>{monthLabel}</span>
        <select
          id={`${id}-month`}
          aria-label={monthLabel}
          value={selectedMonth}
          disabled={isDisabled || !selectedYear}
          onChange={(event) => selectMonth(event.target.value)}
        >
          {(allowEmpty || !selectedMonth) && <option value="">{hasOptions ? 'Chọn tháng' : emptyLabel}</option>}
          {months.map((month) => <option key={month.value} value={month.value}>{month.label}</option>)}
        </select>
      </label>
    </div>
  )
}
