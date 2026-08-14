import { useState } from 'react'

type RawCheckinDayEntry = {
  day_label: string
  time_values: string[]
  attendance_symbol?: string | null
}

type RawCheckinEmployeeBlock = {
  employee_id: string
  employee_name: string
  department_name: string
  day_entries: RawCheckinDayEntry[]
}

type EmployeeBlockFilters = {
  employee_id: string
  employee_name: string
  department_name: string
}

type PreviewEmployee = {
  id: number
  machine_employee_id: string
  biometric_id: string | null
  full_name: string
  department_name: string | null
}

type EmployeeBlockPreviewProps = {
  visibleBlocks: RawCheckinEmployeeBlock[]
  filteredBlockCount: number
  totalBlockCount: number
  searchValue: string
  pageSize: string
  pageSizeNumber: number
  filters: EmployeeBlockFilters
  onSearchChange: (value: string) => void
  onPageSizeChange: (value: string) => void
  onFilterChange: (field: keyof EmployeeBlockFilters, value: string) => void
  onResetFilters: () => void
  onShowMore: () => void
  employees: PreviewEmployee[]
}

type TimeChipTone = 'normal' | 'warning' | 'danger'

function normalizePreviewText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function isLateValue(value: string): boolean {
  const normalized = normalizePreviewText(value)
  return normalized.includes('tre') || normalized.includes('late')
}

function isEarlyValue(value: string): boolean {
  const normalized = normalizePreviewText(value)
  return normalized.includes('som') || normalized.includes('early')
}

function isAlertValue(value: string): boolean {
  const normalized = normalizePreviewText(value)
  return normalized.includes('bo lo') || normalized.includes('miss') || normalized.includes('tre') || normalized.includes('som')
}

function sanitizeTimeValue(value: string): string {
  return value.replace(/\*/g, '').trim()
}

function getTimeChipTone(value: string): TimeChipTone {
  const normalized = normalizePreviewText(value)
  if (normalized.includes('bo lo') || normalized.includes('miss')) return 'danger'
  if (isLateValue(value) || isEarlyValue(value)) return 'warning'
  return 'normal'
}

function getTimeChipClassName(value: string): string {
  const normalized = normalizePreviewText(value)
  if (normalized.includes('bo lo')) {
    return 'bg-rose-100 text-rose-600 ring-1 ring-rose-300'
  }

  const tone = getTimeChipTone(value)
  if (tone === 'danger') return 'bg-red-50 text-red-600 ring-1 ring-red-100'
  if (tone === 'warning') return 'bg-orange-50 text-orange-700 ring-1 ring-orange-100'
  return 'bg-[#EAF4FF] text-[#4D6B87]'
}

function findMatchedEmployee(block: RawCheckinEmployeeBlock, employees: PreviewEmployee[]): PreviewEmployee | undefined {
  return employees.find(
    (employee) =>
      employee.machine_employee_id === block.employee_id ||
      (employee.biometric_id != null && employee.biometric_id === block.employee_id),
  )
}

function TimeValuesRender({ times }: { times: string[] }) {
  if (!times || times.length === 0) {
    return <div className="mt-7 text-center text-xs text-slate-400">Chưa có mốc giờ</div>
  }

  const firstTime = times[0]
  const lastTime = times[times.length - 1]
  const hasDistinctEndTime = times.length > 1 && firstTime !== lastTime

  return (
    <div className="mt-4 flex h-[126px] flex-col justify-between">
      <div className="space-y-1.5 text-[11px]">
        <div className="flex items-center justify-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          <span className="text-slate-500">Mốc đầu:</span>
          <strong className={`rounded border px-1.5 py-0.5 text-slate-700 ${getTimeChipClassName(firstTime)}`}>{firstTime}</strong>
        </div>
        {hasDistinctEndTime && (
          <div className="flex items-center justify-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
            <span className="text-slate-500">Mốc cuối:</span>
            <strong className={`rounded border px-1.5 py-0.5 text-slate-700 ${getTimeChipClassName(lastTime)}`}>{lastTime}</strong>
          </div>
        )}
      </div>

      <div className="group relative mx-auto">
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-300 bg-slate-100 text-lg font-bold text-slate-700 shadow-sm transition hover:border-sky-300 hover:bg-sky-50 focus:outline-none focus:ring-2 focus:ring-sky-300"
          aria-label={`Xem ${times.length} mốc quét thẻ`}
          title="Di chuột hoặc dùng bàn phím để xem toàn bộ mốc quét"
        >
          …
        </button>
        <div className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-3 hidden w-52 -translate-x-1/2 rounded-2xl border border-slate-300 bg-white/95 p-3 shadow-xl backdrop-blur-sm group-hover:block group-focus-within:block">
          <p className="mb-2 text-center text-[10px] font-bold uppercase tracking-wide text-slate-500">Lịch sử quét thẻ trong ngày</p>
          <div className="grid grid-cols-3 gap-1">
            {times.map((value, index) => (
              <span key={`${value}-${index}`} className={`rounded border px-1 py-1 text-center text-[10px] font-semibold leading-none ${getTimeChipClassName(value)}`}>
                {value}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function EmployeeAttendanceDetail({
  block,
  employees,
  onBack,
}: {
  block: RawCheckinEmployeeBlock
  employees: PreviewEmployee[]
  onBack: () => void
}) {
  const matchedEmployee = findMatchedEmployee(block, employees)

  return (
    <section className="mt-4 overflow-visible rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 bg-slate-50/80 p-4 sm:p-5">
        <button
          type="button"
          onClick={onBack}
          className="mb-4 inline-flex items-center rounded-xl border border-slate-300 bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-200"
        >
          ← Quay lại danh sách nhân viên
        </button>

        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto] lg:items-center">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Nhân viên</p>
            <h3 className="mt-1 text-lg font-bold text-slate-900">{matchedEmployee?.full_name || block.employee_name || 'Chưa xác định'}</h3>
            <p className="mt-1 text-sm text-slate-500">Tên từ máy: {block.employee_name || 'Chưa có tên'}</p>
          </div>
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Thông tin chấm công</p>
            <p className="mt-1 text-sm font-semibold text-slate-700">ID máy: #{block.employee_id || '-'}</p>
            <p className="mt-1 text-sm text-slate-500">Phòng ban: {matchedEmployee?.department_name || block.department_name || 'Chưa gán'}</p>
          </div>
          <span className="w-fit rounded-full bg-sky-50 px-3 py-1.5 text-xs font-bold text-sky-700 ring-1 ring-sky-200">
            {block.day_entries.length} ngày có dữ liệu
          </span>
        </div>
      </div>

      <div className="bg-slate-50/70 p-4">
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(132px,1fr))]">
          {block.day_entries.map((entry) => {
            const displayValues = entry.time_values.map(sanitizeTimeValue).filter(Boolean)
            const hasAlertValue = displayValues.some(isAlertValue)

            return (
              <article key={`${block.employee_id}-${entry.day_label}`} className="relative overflow-visible rounded-[18px] border border-[#D6E6F4] bg-white p-3 shadow-[0_10px_28px_-24px_rgba(15,23,42,0.4)] transition hover:border-sky-200">
                <div className="flex items-start justify-between gap-3">
                  <h4 className="text-[26px] font-bold leading-none tracking-[-0.03em] text-[#0B74B4]">{entry.day_label}</h4>
                  <span className={hasAlertValue ? 'rounded-full bg-red-50 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-red-600' : 'rounded-full bg-sky-50 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-sky-700'}>
                    {displayValues.length} mốc giờ
                  </span>
                </div>
                <TimeValuesRender times={displayValues} />
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}

export function EmployeeBlockPreview({
  visibleBlocks,
  filteredBlockCount,
  totalBlockCount,
  searchValue,
  pageSize,
  pageSizeNumber,
  filters,
  onSearchChange,
  onPageSizeChange,
  onFilterChange,
  onResetFilters,
  onShowMore,
  employees,
}: EmployeeBlockPreviewProps) {
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string | null>(null)
  const selectedBlock = selectedEmployeeId
    ? visibleBlocks.find((block) => block.employee_id === selectedEmployeeId) ?? null
    : null
  const hasActiveFilter = Boolean(
    searchValue.trim() || filters.employee_id.trim() || filters.employee_name.trim() || filters.department_name.trim(),
  )

  if (selectedBlock) {
    return <EmployeeAttendanceDetail block={selectedBlock} employees={employees} onBack={() => setSelectedEmployeeId(null)} />
  }

  return (
    <div className="mt-4 space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-end">
          <label className="block text-sm font-medium text-slate-600">
            Tìm nhanh theo mã, tên hoặc phòng ban
            <input
              value={searchValue}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Ví dụ: NGUYEN THANH TR, IT, 001"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            />
          </label>
          <label className="block text-sm font-medium text-slate-600">
            Số nhân viên hiển thị
            <select value={pageSize} onChange={(event) => onPageSizeChange(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100">
              <option value="5">5 người</option>
              <option value="10">10 người</option>
            </select>
          </label>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <label className="block text-sm font-medium text-slate-600">
            Mã nhân viên
            <input value={filters.employee_id} onChange={(event) => onFilterChange('employee_id', event.target.value)} placeholder="Lọc theo mã" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100" />
          </label>
          <label className="block text-sm font-medium text-slate-600">
            Họ tên
            <input value={filters.employee_name} onChange={(event) => onFilterChange('employee_name', event.target.value)} placeholder="Lọc theo họ tên" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100" />
          </label>
          <label className="block text-sm font-medium text-slate-600">
            Phòng ban
            <input value={filters.department_name} onChange={(event) => onFilterChange('department_name', event.target.value)} placeholder="Lọc theo phòng ban" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100" />
          </label>
        </div>

        <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <p>Đang hiển thị <strong className="text-slate-700">{visibleBlocks.length}</strong> / <strong className="text-slate-700">{filteredBlockCount}</strong> / <strong className="text-slate-700">{totalBlockCount}</strong> nhân viên.</p>
          {hasActiveFilter && (
            <button type="button" onClick={onResetFilters} className="inline-flex w-fit items-center justify-center rounded-xl border border-slate-300 bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-200">
              Bỏ toàn bộ lọc
            </button>
          )}
        </div>
      </section>

      {visibleBlocks.length > 0 ? (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {visibleBlocks.map((block) => {
            const matchedEmployee = findMatchedEmployee(block, employees)
            return (
              <article key={`${block.employee_id}-${block.employee_name}-${block.department_name}`} className="flex min-h-[220px] flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-sky-200 hover:shadow-md">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">ID máy chấm công</p>
                    <p className="mt-1 font-mono text-base font-bold text-slate-900">#{block.employee_id || '-'}</p>
                  </div>
                  <span className="rounded-full bg-sky-50 px-2.5 py-1 text-[11px] font-bold text-sky-700">{block.day_entries.length} ngày</span>
                </div>

                <div className="mt-4 space-y-3">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Họ tên hệ thống</p>
                    <p className={`mt-1 text-sm font-semibold ${matchedEmployee ? 'text-emerald-700' : 'text-rose-600'}`}>{matchedEmployee?.full_name || 'Không tìm thấy hồ sơ hệ thống'}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div><p className="text-xs text-slate-400">Tên từ máy</p><p className="mt-1 font-medium text-slate-700">{block.employee_name || '-'}</p></div>
                    <div><p className="text-xs text-slate-400">Phòng ban</p><p className="mt-1 font-medium text-slate-700">{matchedEmployee?.department_name || block.department_name || 'Chưa gán'}</p></div>
                  </div>
                </div>

                <div className="mt-auto pt-5">
                  <div className="mb-3 text-xs font-semibold">
                    {matchedEmployee ? <span className="text-emerald-700">● Đã khớp hồ sơ nhân viên</span> : <span className="text-rose-600">● Chưa khớp hồ sơ nhân viên</span>}
                  </div>
                  <button type="button" onClick={() => setSelectedEmployeeId(block.employee_id)} className="w-full rounded-xl border border-slate-300 bg-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-900 transition hover:bg-slate-200">
                    Xem chi tiết chấm công
                  </button>
                </div>
              </article>
            )
          })}
        </section>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500 shadow-sm">Không có nhân viên nào phù hợp với bộ lọc hiện tại.</div>
      )}

      {visibleBlocks.length < filteredBlockCount && (
        <div className="flex justify-center">
          <button type="button" onClick={onShowMore} className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-slate-100 px-5 py-3 text-sm font-semibold text-slate-900 shadow-sm transition hover:bg-slate-200">
            Xem thêm {pageSizeNumber} người
          </button>
        </div>
      )}
    </div>
  )
}
