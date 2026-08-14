import React from 'react'

interface LockWarningModalProps {
  isOpen: boolean
  isLocked: boolean
  onConfirm: () => void
  onCancel: () => void
}

export const LockWarningModal: React.FC<LockWarningModalProps> = ({
  isOpen,
  isLocked,
  onConfirm,
  onCancel,
}) => {
  if (!isOpen) return null

  const title = isLocked ? 'Cảnh báo hệ thống' : 'Xác nhận chỉnh sửa'
  const description = isLocked
    ? 'Bảng công này đã được chốt. Thay đổi có thể ảnh hưởng trực tiếp đến kết quả tính lương. Bạn có chắc chắn muốn ghi đè không?'
    : 'Thay đổi ký hiệu công sẽ được lưu vào lịch sử chỉnh sửa. Bạn có chắc chắn muốn lưu không?'

  return (
    <div className="app-modal-overlay fixed inset-0 z-50 flex items-center justify-center font-roboto">
      <div className="w-full max-w-md rounded-xl border-l-8 border-red-500 bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-start">
          <div className="flex-shrink-0">
            <svg className="h-8 w-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="ml-4">
            <h3 className="text-xl font-bold uppercase tracking-wide text-gray-900">{title}</h3>
            <p className="mt-2 text-sm font-medium leading-relaxed text-gray-600">{description}</p>
          </div>
        </div>
        <div className="mt-6 flex justify-end space-x-3">
          <button type="button" onClick={onCancel} className="rounded-lg bg-gray-100 px-4 py-2 font-semibold text-gray-700 transition-colors hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-400">
            Hủy
          </button>
          <button type="button" onClick={onConfirm} className="rounded-lg bg-red-600 px-4 py-2 font-semibold text-white shadow-md transition-colors hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2">
            Xác nhận lưu
          </button>
        </div>
      </div>
    </div>
  )
}
