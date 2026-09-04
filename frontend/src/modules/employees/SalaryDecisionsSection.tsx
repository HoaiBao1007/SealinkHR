import { useState, useEffect } from 'react'
import { useConfirmDialog } from '../../shared/ui/ConfirmDialog'
import { VndInput } from '../../shared/ui/VndInput'
import { BrandedDateInput } from '../../shared/ui/BrandedDateInput'
import { formatVnd } from '../../shared/utils/currency'
import { AppIcon } from '../../shared/ui/AppIcon'
import { credentialedFetch } from '../../shared/api/credentialedFetch'

type SalaryDecision = {
  id: number
  employee_id: number
  old_salary: number
  new_salary: number
  meal_allowance?: number
  trans_allowance?: number
  phone_allowance?: number
  other_allowance?: number
  bonus_coefficient?: number
  old_employee_type?: string | null
  new_employee_type?: string | null
  effective_date: string
  reason: string | null
  status: string
}

export function SalaryDecisionsSection({ 
  apiBase, 
  token, 
  employeeId, 
  currentSalary,
  departmentId: _departmentId
}: { 
  apiBase: string, 
  token: string | null, 
  employeeId: number, 
  currentSalary: number,
  departmentId: number | null
}) {
  const confirm = useConfirmDialog()
  const [decisions, setDecisions] = useState<SalaryDecision[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const [showAdd, setShowAdd] = useState(false)
  const [oldSalary, setOldSalary] = useState(currentSalary)
  const [newSalary, setNewSalary] = useState(currentSalary)
  const [mealAllowance, setMealAllowance] = useState(1200000)
  const [transAllowance, setTransAllowance] = useState(2000000)
  const [phoneAllowance, setPhoneAllowance] = useState(2000000)
  const [otherAllowance, setOtherAllowance] = useState(0)
  const [effectiveDate, setEffectiveDate] = useState('')
  const [reason, setReason] = useState('')




  async function loadDecisions() {
    setLoading(true)
    try {
      const res = await credentialedFetch(`${apiBase}/api/employees/${employeeId}/salary-decisions`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Không thể tải lịch sử lương')
      const data = await res.json()
      setDecisions(data)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (employeeId) {
      loadDecisions()
      setOldSalary(currentSalary)
      setNewSalary(currentSalary)
    }
  }, [apiBase, currentSalary, employeeId, token])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!effectiveDate) return alert('Vui lòng chọn ngày hiệu lực')
    setLoading(true)
    try {
      const res = await credentialedFetch(`${apiBase}/api/employees/${employeeId}/salary-decisions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        credentials: 'include',
        body: JSON.stringify({
          employee_id: employeeId,
          old_salary: oldSalary,
          new_salary: newSalary,
          meal_allowance: mealAllowance,
          trans_allowance: transAllowance,
          phone_allowance: phoneAllowance,
          other_allowance: otherAllowance,
          effective_date: effectiveDate,
          reason: reason || null
        })
      })
      if (!res.ok) throw new Error('Không thể tạo quyết định lương')
      await loadDecisions()
      setShowAdd(false)
      setEffectiveDate('')
      setReason('')
    } catch (err: any) {
      alert(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(id: number) {
    if (!await confirm({ title: 'Xóa quyết định lương', message: 'Bạn có chắc chắn muốn xóa quyết định lương này?', confirmLabel: 'Xóa', tone: 'danger' })) return
    setLoading(true)
    try {
      const res = await credentialedFetch(`${apiBase}/api/salary-decisions/${id}`, {
        method: 'DELETE',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Không thể xóa')
      await loadDecisions()
    } catch (err: any) {
      alert(err.message)
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (val: number) => formatVnd(val, { suffix: true })
  const typeLabel = (type?: string | null) => ({
    FULLTIME: 'Chính thức',
    PROBATION: 'Thử việc',
    INTERN: 'Học việc',
    TRAINEE: 'Thực tập',
  }[type || ''] || type || '—')

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 mt-6">
      <div className="flex justify-between items-center mb-4">
        <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400"><AppIcon name="money" size={15} /> Lịch sử biến động lương</p>
        <button 
          onClick={() => setShowAdd(!showAdd)}
          className="text-xs font-semibold text-[#163B66] hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-lg transition cursor-pointer"
        >
          {showAdd ? 'Hủy' : '+ Thêm quyết định'}
        </button>
      </div>

      {showAdd && (
        <form onSubmit={handleCreate} className="mb-4 bg-white p-4 rounded-xl border border-blue-100 shadow-sm animate-[fadeIn_0.2s_ease-out_forwards]">
          <h4 className="text-xs font-bold text-slate-700 mb-3 uppercase tracking-wider">Tạo quyết định điều chỉnh lương</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs font-semibold text-slate-700 mb-1">Mức lương cũ</span>
              <VndInput
                required 
                className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200" 
                value={oldSalary}
                onValueChange={setOldSalary}
              />
            </div>
            <div>
              <span className="block text-xs font-semibold text-slate-700 mb-1">Mức lương mới</span>
              <VndInput
                required 
                className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200" 
                value={newSalary}
                onValueChange={setNewSalary}
              />
            </div>
            <div>
              <span className="block text-xs font-semibold text-slate-700 mb-1">Ngày áp dụng</span>
              <BrandedDateInput
                required 
                className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200" 
                value={effectiveDate} 
                onChange={e => setEffectiveDate(e.target.value)} 
              />
            </div>
            <div>
              <span className="block text-xs font-semibold text-slate-700 mb-1">Lý do (Tùy chọn)</span>
              <input 
                type="text" 
                className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200" 
                placeholder="Review lương định kỳ..."
                value={reason} 
                onChange={e => setReason(e.target.value)} 
              />
            </div>
            <div>
              <span className="block text-xs font-semibold text-slate-700 mb-1">Phụ cấp Cơm</span>
              <VndInput
                required 
                className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200" 
                value={mealAllowance}
                onValueChange={setMealAllowance}
              />
            </div>
            <div>
              <span className="block text-xs font-semibold text-slate-700 mb-1">Phụ cấp Xăng xe</span>
              <VndInput
                required 
                className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200" 
                value={transAllowance}
                onValueChange={setTransAllowance}
              />
            </div>
            <div>
              <span className="block text-xs font-semibold text-slate-700 mb-1">Phụ cấp Điện thoại</span>
              <VndInput
                required 
                className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200" 
                value={phoneAllowance}
                onValueChange={setPhoneAllowance}
              />
            </div>
            <div>
              <span className="block text-xs font-semibold text-slate-700 mb-1">Phụ cấp Khác</span>
              <VndInput
                required 
                className="h-9 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200" 
                value={otherAllowance}
                onValueChange={setOtherAllowance}
              />
            </div>
          </div>
          <div className="mt-4 flex justify-end">
            <button disabled={loading} className="bg-blue-600 hover:bg-blue-700 cursor-pointer text-white font-semibold text-xs px-4 py-2 rounded-lg transition disabled:opacity-50">
              Lưu quyết định
            </button>
          </div>
        </form>
      )}

      {loading && !decisions.length ? (
        <div className="text-center py-4 text-slate-400 text-sm animate-pulse">Đang tải...</div>
      ) : error ? (
        <div className="text-center py-4 text-rose-500 text-sm bg-rose-50 rounded-lg">{error}</div>
      ) : decisions.length === 0 ? (
        <div className="text-center py-6 text-slate-400 text-sm bg-white rounded-xl border border-slate-100">Chưa có lịch sử biến động lương.</div>
      ) : (
        <div className="space-y-2">
          {decisions.map(d => (
            <div key={d.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 bg-white border border-slate-200 rounded-xl hover:border-slate-300 transition">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  {d.new_employee_type ? (
                    <span className="text-sm font-bold text-slate-800">{typeLabel(d.old_employee_type)} → {typeLabel(d.new_employee_type)}</span>
                  ) : (
                    <>
                      <span className="text-sm font-bold text-slate-800">{formatCurrency(d.new_salary)}</span>
                      <span className="text-xs text-slate-400 line-through">{formatCurrency(d.old_salary)}</span>
                    </>
                  )}
                  {d.status === 'ACTIVE' ? (
                    <span className="bg-emerald-100 text-emerald-700 text-[11px] font-bold px-2 py-0.5 rounded-full">HIỆU LỰC</span>
                  ) : (
                    <span className="bg-amber-100 text-amber-700 text-[11px] font-bold px-2 py-0.5 rounded-full">CHỜ (PENDING)</span>
                  )}
                </div>
                <p className="text-xs text-slate-500">
                  <span className="font-semibold text-slate-600">Ngày áp dụng:</span> {new Date(d.effective_date).toLocaleDateString('vi-VN')}
                  {d.reason && <span className="ml-2 border-l border-slate-300 pl-2 text-slate-400">{d.reason}</span>}
                </p>
                <div className="mt-2 text-[11px] text-slate-500 flex flex-wrap gap-x-4 gap-y-1">
                  <span><strong className="text-slate-600">Cơm:</strong> {formatCurrency(d.meal_allowance || 0)}</span>
                  <span><strong className="text-slate-600">Xăng xe:</strong> {formatCurrency(d.trans_allowance || 0)}</span>
                  <span><strong className="text-slate-600">Điện thoại:</strong> {formatCurrency(d.phone_allowance || 0)}</span>
                  {(d.other_allowance || 0) > 0 && (
                    <span><strong className="text-slate-600">Khác:</strong> {formatCurrency(d.other_allowance || 0)}</span>
                  )}
                </div>
              </div>
              <button 
                onClick={() => handleDelete(d.id)}
                className="app-delete-button mt-2 sm:mt-0 p-1.5 text-rose-600 hover:text-rose-700 hover:bg-rose-100 rounded-lg transition cursor-pointer"
                title="Xóa"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
