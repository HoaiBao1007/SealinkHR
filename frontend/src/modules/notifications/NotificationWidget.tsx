import { useCallback, useEffect, useRef, useState } from 'react'
import './notification-widget.css'

type ApiRequest = (path: string, init?: RequestInit) => Promise<Response>

export type NotificationItem = {
  id: number
  category: 'HR' | 'PAYROLL' | 'ATTENDANCE' | 'BONUS' | string
  event_type: string
  title: string
  message: string
  resource_type?: string | null
  resource_id?: string | null
  action_url?: string | null
  action_context?: {
    resource_type?: string | null
    resource_id?: string | null
    job_id?: number
    job_no?: string | null
    period_id?: number
    period_label?: string | null
    sales_rep?: string | null
    employee_id?: number
    employee_name?: string | null
    resource_exists?: boolean
    salary_period?: string | null
    period_start?: string | null
    period_end?: string | null
    attendance_month?: string | null
    target_user_id?: number
    target_employee_id?: number
    target_employee_name?: string | null
    payout_periods?: string[]
    request_id?: number
    request_status?: string | null
  }
  target_name?: string | null
  created_at: string
  is_read: boolean
}

type NotificationPayload = {
  unread_count: number
  items: NotificationItem[]
}

const categoryLabels: Record<string, string> = {
  HR: 'Nhân sự',
  PAYROLL: 'Phiếu lương',
  ATTENDANCE: 'Bảng công',
  BONUS: 'Bonus',
  TIME_OFF: 'Time Off',
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

type NotificationWidgetProps = {
  apiRequest: ApiRequest
  onNavigate?: (path: string, item: NotificationItem) => void
}

export function NotificationWidget({ apiRequest, onNavigate }: NotificationWidgetProps) {
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [badgePulse, setBadgePulse] = useState(false)
  const previousCount = useRef(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const pulseTimer = useRef<number | undefined>(undefined)

  const loadNotifications = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true)
    try {
      const response = await apiRequest('/api/notifications?limit=40')
      const payload = await response.json() as NotificationPayload
      const nextCount = Number(payload.unread_count || 0)
      if (nextCount !== previousCount.current) {
        setBadgePulse(false)
        window.clearTimeout(pulseTimer.current)
        window.requestAnimationFrame(() => setBadgePulse(true))
        pulseTimer.current = window.setTimeout(() => setBadgePulse(false), 520)
      }
      previousCount.current = nextCount
      setUnreadCount(nextCount)
      setItems(payload.items || [])
    } catch {
      // Polling must never interrupt the active screen when the API is restarting.
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [apiRequest])

  useEffect(() => {
    const initialTimer = window.setTimeout(() => void loadNotifications(), 0)
    const timer = window.setInterval(() => void loadNotifications(), 15_000)
    const onFocus = () => void loadNotifications()
    window.addEventListener('focus', onFocus)
    return () => {
      window.clearInterval(timer)
      window.clearTimeout(initialTimer)
      window.clearTimeout(pulseTimer.current)
      window.removeEventListener('focus', onFocus)
    }
  }, [loadNotifications])

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [])

  async function markRead(item: NotificationItem) {
    if (!item.is_read) {
      setItems((current) => current.map((row) => row.id === item.id ? { ...row, is_read: true } : row))
      setUnreadCount((count) => Math.max(0, count - 1))
      previousCount.current = Math.max(0, previousCount.current - 1)
      try {
        await apiRequest(`/api/notifications/items/${item.id}/read`, { method: 'POST' })
      } catch {
        void loadNotifications()
      }
    }
    setOpen(false)
    if (item.action_url || item.resource_type) {
      if (onNavigate) {
        onNavigate(item.action_url || '', item)
      } else if (item.action_url) {
        window.history.pushState({}, '', item.action_url)
        window.dispatchEvent(new PopStateEvent('popstate'))
      }
    }
  }

  async function markAllRead() {
    if (!unreadCount) return
    setItems((current) => current.map((item) => ({ ...item, is_read: true })))
    setUnreadCount(0)
    previousCount.current = 0
    try {
      await apiRequest('/api/notifications/read-all', { method: 'POST' })
    } catch {
      void loadNotifications()
    }
  }

  return (
    <div className="notification-widget" ref={rootRef}>
      <button
        type="button"
        className={`notification-trigger${open ? ' is-open' : ''}`}
        aria-label={`Thông báo${unreadCount ? `, ${unreadCount} chưa đọc` : ''}`}
        aria-expanded={open}
        onClick={() => {
          setOpen((value) => !value)
          if (!open) void loadNotifications(true)
        }}
      >
        <svg className="notification-bell" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M10 21h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        {unreadCount > 0 && (
          <span key={unreadCount} className={`notification-badge${badgePulse ? ' is-popping' : ''}`}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <section className="notification-panel" aria-label="Danh sách thông báo">
          <div className="notification-panel__header">
            <div>
              <h2>Thông báo</h2>
              <p>{unreadCount ? `${unreadCount} thông báo chưa đọc` : 'Bạn đã đọc tất cả thông báo'}</p>
            </div>
            <button type="button" onClick={() => void markAllRead()} disabled={!unreadCount}>Đánh dấu đã đọc</button>
          </div>
          <div className="notification-list">
            {loading && items.length === 0 ? (
              <div className="notification-empty">Đang tải thông báo…</div>
            ) : items.length === 0 ? (
              <div className="notification-empty">Chưa có thông báo phù hợp với quyền tài khoản.</div>
            ) : items.map((item) => (
              <button
                type="button"
                key={item.id}
                className={`notification-item${item.is_read ? '' : ' is-unread'}`}
                onClick={() => void markRead(item)}
              >
                <span className={`notification-category category-${item.category.toLowerCase()}`}>
                  {categoryLabels[item.category] || item.category}
                </span>
                <strong>{item.title}</strong>
                {item.target_name && <span className="notification-recipient">Người nhận: {item.target_name}</span>}
                <span className="notification-message">{item.message}</span>
                <time>{formatTime(item.created_at)}</time>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
