/**
 * Chuẩn hóa cách hiển thị tiền trên toàn bộ portal.
 *
 * Giá trị vẫn được lưu và tính toán dưới dạng number (VND). Các hàm trong
 * tệp này chỉ định dạng dữ liệu giao diện, không thay đổi công thức nghiệp vụ.
 */
export type VndFormatOptions = {
  suffix?: boolean
  maximumFractionDigits?: number
  minimumFractionDigits?: number
  fallback?: string
}

export function formatVietnameseNumber(value: unknown, options: Omit<VndFormatOptions, 'suffix'> = {}): string {
  const numeric = toVndNumber(value, Number.NaN)
  if (!Number.isFinite(numeric)) return options.fallback ?? '—'

  return new Intl.NumberFormat('vi-VN', {
    minimumFractionDigits: options.minimumFractionDigits ?? 0,
    maximumFractionDigits: options.maximumFractionDigits ?? 0,
  }).format(numeric)
}

export function toVndNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : fallback
  const raw = String(value ?? '').trim().replace(/\s|VND|VNĐ/gi, '')
  if (!raw) return fallback

  // Chuỗi từ input dùng quy ước Việt Nam: dấu chấm phân tách hàng nghìn,
  // dấu phẩy phân tách phần thập phân. Giá trị number từ API vẫn giữ nguyên.
  let normalized = raw
  if (raw.includes(',')) {
    normalized = raw.replace(/\./g, '').replace(',', '.')
  } else if (/^-?\d{1,3}(?:\.\d{3})+$/.test(raw)) {
    normalized = raw.replace(/\./g, '')
  }

  const directNumber = Number(normalized)
  if (Number.isFinite(directNumber)) return directNumber
  const numberValue = Number(raw.replace(/[^0-9-]/g, ''))
  return Number.isFinite(numberValue) ? numberValue : fallback
}

export function formatVnd(value: unknown, options: VndFormatOptions = {}): string {
  const amount = formatVietnameseNumber(value, options)
  if (amount === (options.fallback ?? '—')) return amount

  return options.suffix ? `${amount} VNĐ` : amount
}

/** Định dạng số nguyên VNĐ trong input, không chèn hậu tố VNĐ vào ô nhập. */
export function formatVndInput(value: unknown): string {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  // VND is displayed as a whole-number currency throughout the portal.
  // Keeping the input formatter integer-only also prevents inconsistent
  // values such as "79.415,5" from appearing beside rounded payroll values.
  return formatVnd(toVndNumber(value), { fallback: '', maximumFractionDigits: 0 })
}

/** Chuyển chuỗi VNĐ đã định dạng, ví dụ "2.530.000", về number. */
export function parseVndInput(value: string): number {
  const raw = String(value ?? '').trim()
  if (!raw) return 0

  // VND input is whole-number only. While a user types, a formatted value
  // such as "2.777" may temporarily become "2.7770". Treat every dot as a
  // thousands separator here; Number("2.7770") would otherwise turn it into
  // the decimal 2.777 and make the field jump to an unrelated value.
  const digits = raw.replace(/\D/g, '')
  if (!digits) return 0
  const amount = Number(digits)
  return Number.isSafeInteger(amount) ? amount : 0
}
