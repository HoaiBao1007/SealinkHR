import { useEffect, useRef, useState, type InputHTMLAttributes } from 'react'
import { formatVndInput, parseVndInput } from '../utils/currency'

type VndInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'type' | 'value'> & {
  value: number | string | null | undefined
  onValueChange: (value: number) => void
  onEmpty?: () => void
}

/**
 * Integer VND input that is safe to clear and retype while preserving the
 * Vietnamese thousands separator. The visible draft is kept locally while
 * focused so a parent value of 0 does not immediately replace an empty field.
 */
export function VndInput({ value, onValueChange, onEmpty, onFocus, onBlur, ...inputProps }: VndInputProps) {
  const focused = useRef(false)
  const [displayValue, setDisplayValue] = useState(() => formatVndInput(value))

  useEffect(() => {
    if (!focused.current) setDisplayValue(formatVndInput(value))
  }, [value])

  return (
    <input
      {...inputProps}
      type="text"
      inputMode="numeric"
      pattern="[0-9.]*"
      value={displayValue}
      onFocus={(event) => {
        focused.current = true
        onFocus?.(event)
      }}
      onBlur={(event) => {
        focused.current = false
        setDisplayValue(formatVndInput(value))
        onBlur?.(event)
      }}
      onChange={(event) => {
        const raw = event.target.value
        if (!raw.replace(/\D/g, '')) {
          setDisplayValue('')
          if (onEmpty) onEmpty()
          else onValueChange(0)
          return
        }
        const amount = parseVndInput(raw)
        setDisplayValue(formatVndInput(amount))
        onValueChange(amount)
      }}
    />
  )
}
