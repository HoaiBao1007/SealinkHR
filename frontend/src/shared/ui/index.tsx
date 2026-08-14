import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TableHTMLAttributes } from 'react'

export function Button({ className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`ui-button ui-button-primary ${className}`.trim()} {...props} />
}

export function Input({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`ui-input ${className}`.trim()} {...props} />
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`ui-card ${className}`.trim()}>{children}</section>
}

export function Table({ className = '', ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return <div className="ui-table-wrap"><table className={`ui-table ${className}`.trim()} {...props} /></div>
}

export function LoadingState({ label = 'Đang tải dữ liệu…' }: { label?: string }) {
  return <div className="ui-state" role="status">{label}</div>
}

export function EmptyState({ label = 'Chưa có dữ liệu để hiển thị.' }: { label?: string }) {
  return <div className="ui-state">{label}</div>
}

export function ErrorState({ label = 'Không thể tải dữ liệu. Vui lòng thử lại.' }: { label?: string }) {
  return <div className="ui-state ui-state-error" role="alert">{label}</div>
}
