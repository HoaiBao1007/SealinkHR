import { useEffect, useState } from 'react'
import type { ReactNode, ReactElement } from 'react'
import logoSealink from '../../assets/LOGO SEALINK.jpg'
import { NotificationWidget } from '../notifications/NotificationWidget'
import type { NotificationItem } from '../notifications/NotificationWidget'

export type EnterpriseShellIcon = 'dashboard' | 'upload' | 'employees' | 'departments' | 'timesheets' | 'export' | 'salary' | 'commission' | 'settings'

export type EnterpriseShellItem = {
  key: string
  label: string
  title: string
  description: string
  icon: EnterpriseShellIcon
}

type EnterpriseShellProps = {
  tabs: EnterpriseShellItem[]
  activeTab: string
  onTabChange: (key: string) => void
  apiBase: string
  loading: boolean
  message: string
  currentUser: any
  onLogout: () => void
  apiRequest: (path: string, init?: RequestInit) => Promise<Response>
  onNotificationNavigate?: (path: string, item: NotificationItem) => void
  notificationNotice?: NotificationItem | null
  onDismissNotificationNotice?: () => void
  headerControls?: ReactNode
  children: ReactNode
}

// ── Sidebar colour tokens ────────────────────────────────
const SB = {
  bg: '#1e91ca',
  bgTop: '#1e91ca',
  border: 'rgba(255,255,255,0.15)',
  itemActive: 'rgba(255,255,255,0.22)',
  itemHover: 'rgba(255,255,255,0.12)',
  iconActive: 'rgba(255,255,255,0.3)',
  iconDefault: 'rgba(255,255,255,0.12)',
  label: 'rgba(255,255,255,0.65)',
  text: 'rgba(255,255,255,0.92)',
  textActive: '#ffffff',
} as const

const SIDEBAR_W = 252   // expanded width in px
const TOGGLE_HALF = 13  // half of toggle button width (26px / 2)

// ── Navigation icon ──────────────────────────────────────
function NavIcon({ name, active }: { name: EnterpriseShellIcon; active: boolean }) {
  const c = active ? '#ffffff' : 'rgba(255,255,255,0.65)'
  const s = { width: 18, height: 18, color: c } as const

  const paths: Record<EnterpriseShellIcon, ReactElement> = {
    dashboard: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <path d="M4 5.5h7v5H4zM13 5.5h7v8h-7zM4 12.5h7V20H4zM13 15.5h7V20h-7z" />
      </svg>
    ),
    upload: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <path d="M12 15V5" /><path d="m8 9 4-4 4 4" />
        <path d="M5 16.5v1A1.5 1.5 0 0 0 6.5 19h11a1.5 1.5 0 0 0 1.5-1.5v-1" />
      </svg>
    ),
    employees: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <path d="M16 21v-1.2A3.8 3.8 0 0 0 12.2 16H7.8A3.8 3.8 0 0 0 4 19.8V21" />
        <path d="M10 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" />
        <path d="M16.5 8.5a3.1 3.1 0 0 1 0 6.2" />
        <path d="M19.5 21v-1a3.3 3.3 0 0 0-2.8-3.2" />
      </svg>
    ),
    departments: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
      </svg>
    ),
    timesheets: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <path d="M7 3v3" /><path d="M17 3v3" /><path d="M4.5 8.5h15" />
        <rect x="4.5" y="5.5" width="15" height="14" rx="2" />
        <path d="m9 13 1.7 1.7L15.5 10" />
      </svg>
    ),
    export: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <path d="M12 4v11" /><path d="m8 11 4 4 4-4" /><path d="M5 18.5h14" />
      </svg>
    ),
    salary: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <line x1="12" y1="1" x2="12" y2="23" />
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
    commission: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <circle cx="9" cy="7" r="2.5" />
        <circle cx="15" cy="17" r="2.5" />
        <line x1="6" y1="20" x2="18" y2="4" />
      </svg>
    ),
    settings: (
      <svg viewBox="0 0 24 24" fill="none" style={s} stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="12" r="3.2" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.05 2.05-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.04 1.56V20.3h-2.9v-.09A1.7 1.7 0 0 0 10.86 18.65a1.7 1.7 0 0 0-1.88.34l-.06.06-2.05-2.05.06-.06A1.7 1.7 0 0 0 7.27 15a1.7 1.7 0 0 0-1.56-1.04h-.09v-2.9h.09a1.7 1.7 0 0 0 1.56-1.04 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.05-2.05.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.04-1.56v-.09h2.9v.09a1.7 1.7 0 0 0 1.04 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.05 2.05-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.04h.09v2.9h-.09A1.7 1.7 0 0 0 19.4 15Z" />
      </svg>
    ),
  }

  return paths[name] ?? paths.export
}

// ════════════════════════════════════════════════════════
export function EnterpriseShell({
  tabs,
  activeTab,
  onTabChange,
  apiBase,
  loading,
  message,
  currentUser,
  onLogout,
  apiRequest,
  onNotificationNavigate,
  notificationNotice,
  onDismissNotificationNotice,
  headerControls,
  children,
}: EnterpriseShellProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const activeItem = tabs.find((t) => t.key === activeTab) ?? tabs[0]
  const settingTabKeys = new Set(['employees', 'departments', 'it-backups', 'it-audit'])
  const settingTabs = tabs.filter((tab) => settingTabKeys.has(tab.key))
  const mainTabs = tabs.filter((tab) => !settingTabKeys.has(tab.key))
  const isSettingActive = settingTabs.some((tab) => tab.key === activeTab)

  useEffect(() => {
    if (isSettingActive) setSettingsOpen(true)
  }, [isSettingActive])
  const roleLabel: Record<string, string> = {
    ADMIN: 'Kế toán trưởng',
    HR_ADMIN: 'Admin vận hành',
    IT_ADMIN: 'Quản trị hệ thống cấp cao',
    USER: 'Nhân viên',
  }
  const roleDescription: Record<string, string> = {
    ADMIN: 'Toàn quyền kế toán, lương, commission và vận hành hệ thống.',
    HR_ADMIN: 'Quản lý hồ sơ, phòng ban và bảng công; không truy cập lương hoặc bonus.',
    IT_ADMIN: 'Toàn quyền nghiệp vụ kế toán và quản trị IT, bao gồm Backup và Audit.',
    USER: 'Xem phiếu lương, bảng công và bonus đang giữ của cá nhân.',
  }

  const initials = (() => {
    if (!currentUser) return 'US'
    const name = currentUser.fullname || currentUser.username || 'User'
    return name.split(' ').map((p: string) => p[0]).join('').slice(0, 2).toUpperCase()
  })()

  // Toggle button left position: sits on the right edge of sidebar
  const toggleLeft = collapsed ? 12 : SIDEBAR_W - TOGGLE_HALF

  const renderNavItem = (tab: EnterpriseShellItem, nested = false) => {
    const isActive = tab.key === activeTab
    return (
      <button
        key={tab.key}
        type="button"
        aria-current={isActive ? 'page' : undefined}
        onClick={() => onTabChange(tab.key)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          width: '100%',
          padding: nested ? '7px 8px 7px 10px' : '8px 10px',
          borderRadius: 8,
          border: 'none',
          background: isActive ? SB.itemActive : 'transparent',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          transition: 'background 0.15s',
          textAlign: 'left',
        }}
        onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = SB.itemHover }}
        onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent' }}
      >
        <span
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: nested ? 28 : 32,
            height: nested ? 28 : 32,
            borderRadius: 7,
            background: isActive ? SB.iconActive : SB.iconDefault,
            flexShrink: 0,
          }}
        >
          <NavIcon name={tab.icon} active={isActive} />
        </span>
        <span
          style={{
            fontSize: nested ? 13 : 13.5,
            fontWeight: isActive ? 600 : 400,
            color: isActive ? SB.textActive : SB.text,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            letterSpacing: '-0.01em',
          }}
        >
          {tab.label}
        </span>
      </button>
    )
  }

  return (
    // ── App container: full-viewport flexbox row ──────────
    <div
      style={{
        display: 'flex',
        flexDirection: 'row',
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        fontFamily: "Roboto, Arial, sans-serif",
        background: '#f0f5fb',
      }}
    >
      {/* ══════════════ FLOATING TOGGLE BUTTON ══════════════ */}
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        aria-label={collapsed ? 'Mở rộng sidebar' : 'Thu gọn sidebar'}
        style={{
          position: 'fixed',
          left: toggleLeft,
          top: 24,
          zIndex: 200,
          width: 26,
          height: 26,
          borderRadius: '50%',
          background: '#1e91ca',
          border: '2.5px solid #ffffff',
          boxShadow: '0 4px 16px rgba(30,145,202,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          padding: 0,
          color: '#ffffff',
          transition: 'left 0.3s cubic-bezier(0.4,0,0.2,1), background 0.18s',
        }}
        onMouseEnter={e => (e.currentTarget.style.background = '#136e9b')}
        onMouseLeave={e => (e.currentTarget.style.background = '#1e91ca')}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.8"
          style={{
            width: 13,
            height: 13,
            transform: collapsed ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.3s cubic-bezier(0.4,0,0.2,1)',
          }}
        >
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>

      {/* ══════════════════ SIDEBAR ══════════════════════════ */}
      <aside
        className={collapsed ? 'collapsed' : ''}
        style={{
          flexShrink: 0,
          width: collapsed ? 0 : SIDEBAR_W,
          minWidth: collapsed ? 0 : SIDEBAR_W,
          maxWidth: collapsed ? 0 : SIDEBAR_W,
          overflow: 'hidden',
          opacity: collapsed ? 0 : 1,
          pointerEvents: collapsed ? 'none' : 'auto',
          background: `linear-gradient(180deg, ${SB.bgTop} 0%, ${SB.bg} 100%)`,
          borderRight: collapsed ? 'none' : `1px solid ${SB.border}`,
          transition: 'width 0.3s cubic-bezier(0.4,0,0.2,1), min-width 0.3s cubic-bezier(0.4,0,0.2,1), max-width 0.3s cubic-bezier(0.4,0,0.2,1), opacity 0.3s cubic-bezier(0.4,0,0.2,1)',
        }}
      >
        {/* Inner: fixed-width scroll container (does NOT shrink) */}
        <div
          style={{
            width: SIDEBAR_W,
            height: '100vh',
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            overflowX: 'hidden',
            // hide scrollbar
            scrollbarWidth: 'none',
            opacity: collapsed ? 0 : 1,
            visibility: collapsed ? 'hidden' : 'visible',
            transition: 'opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1), visibility 0.2s',
          }}
        >
          {/* Logo */}
          <div
            style={{
              padding: '20px 16px 14px',
              borderBottom: `1px solid ${SB.border}`,
              display: 'flex',
              justifyContent: 'center',
            }}
          >
            <div
              style={{
                background: '#ffffff',
                borderRadius: 12,
                padding: '6px 10px',
                boxShadow: '0 2px 10px rgba(0,0,0,0.25)',
                width: 180,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
              }}
            >
              <img
                src={logoSealink}
                alt="Sealink"
                style={{ width: 156, height: 'auto', objectFit: 'contain', display: 'block' }}
              />
            </div>
          </div>

          {/* Nav section */}
          <div style={{ padding: '14px 12px', flex: 1 }}>
            <p
              style={{
                margin: '0 0 8px 4px',
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                color: SB.label,
                whiteSpace: 'nowrap',
              }}
            >
              Điều hướng
            </p>

            <nav style={{ display: 'grid', gap: 2 }}>
              {mainTabs.map((tab) => renderNavItem(tab))}

              {settingTabs.length > 0 && (
                <>
                  <button
                    type="button"
                    aria-expanded={settingsOpen}
                    aria-controls="admin-settings-navigation"
                    onClick={() => setSettingsOpen((value) => !value)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: 8,
                      border: settingsOpen || isSettingActive ? `1px solid ${SB.border}` : '1px solid transparent',
                      background: settingsOpen || isSettingActive ? 'rgba(255,255,255,0.1)' : 'transparent',
                      color: SB.text,
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'background 0.15s, border-color 0.15s',
                    }}
                    onMouseEnter={e => { if (!settingsOpen && !isSettingActive) e.currentTarget.style.background = SB.itemHover }}
                    onMouseLeave={e => { if (!settingsOpen && !isSettingActive) e.currentTarget.style.background = 'transparent' }}
                  >
                    <span
                      style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32,
                        borderRadius: 7, background: settingsOpen || isSettingActive ? SB.iconActive : SB.iconDefault, flexShrink: 0,
                      }}
                    >
                      <NavIcon name="settings" active={settingsOpen || isSettingActive} />
                    </span>
                    <span style={{ flex: 1, fontSize: 13.5, fontWeight: 600, color: SB.text }}>Setting</span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" style={{ width: 16, height: 16, transition: 'transform 0.2s', transform: settingsOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}>
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </button>

                  {settingsOpen && (
                    <div
                      id="admin-settings-navigation"
                      style={{
                        margin: '3px 0 5px 26px',
                        padding: '3px 0 3px 9px',
                        borderLeft: `1px solid ${SB.border}`,
                        display: 'grid',
                        gap: 1,
                      }}
                    >
                      {settingTabs.map((tab) => (
                        <div key={tab.key} style={{ position: 'relative' }}>
                          <span style={{ position: 'absolute', left: -13, top: 18, width: 7, height: 7, borderRadius: '50%', background: tab.key === activeTab ? '#ffffff' : 'rgba(255,255,255,0.58)', boxShadow: `0 0 0 2px ${SB.bg}` }} />
                          {renderNavItem(tab, true)}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </nav>
          </div>

          {/* Resource card at bottom */}
          <div style={{ padding: '0 12px 20px' }}>
            <div style={{ height: 1, background: SB.border, marginBottom: 12 }} />
            <p
              style={{
                margin: '0 0 8px 4px',
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                color: SB.label,
                whiteSpace: 'nowrap',
              }}
            >
              Tài nguyên
            </p>
            <div
              style={{
                borderRadius: 12,
                border: `1px solid ${SB.border}`,
                background: 'rgba(255,255,255,0.07)',
                padding: '12px 14px',
              }}
            >
              <p style={{ margin: 0, fontSize: 10, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', color: SB.label }}>
                Chu kỳ mặc định
              </p>
              <p style={{ margin: '8px 0 6px', fontSize: 24, fontWeight: 800, letterSpacing: '-0.03em', color: '#ffffff' }}>
                23 → 22
              </p>
              <p style={{ margin: 0, fontSize: 12, lineHeight: 1.6, color: SB.text }}>
                Theo dõi import, bảng công và lịch sử điều chỉnh trên cùng một không gian làm việc.
              </p>
            </div>
          </div>
        </div>
      </aside>

      {/* ══════════════════ MAIN CONTENT ═════════════════════ */}
      <div
        style={{
          flex: 1,
          width: 'auto',
          height: '100vh',
          overflowY: 'auto',
          overflowX: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          transition: 'all 0.3s cubic-bezier(0.4,0,0.2,1)',
          minWidth: 0,
        }}
      >
        {/* Header */}
        <header
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 12,
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #dce8f5',
            background: '#ffffff',
            padding: '14px 24px',
            flexShrink: 0,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: 10, fontWeight: 700, letterSpacing: '0.22em', textTransform: 'uppercase', color: '#94a3b8' }}>
              SEALINK Enterprise Dashboard
            </p>
            <h1
              style={{
                margin: '2px 0 0',
                fontSize: 20,
                fontWeight: 700,
                letterSpacing: '-0.02em',
                color: '#0f172a',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {activeItem?.title ?? 'Dashboard'}
            </h1>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              className="hidden lg:block"
              style={{
                borderRadius: 999,
                border: '1px solid #dce8f5',
                background: '#f0f6ff',
                padding: '5px 14px',
                fontSize: 12,
                fontWeight: 600,
                color: '#64748b',
              }}
            >
              API: {apiBase}
            </div>

            <NotificationWidget apiRequest={apiRequest} onNavigate={onNotificationNavigate} />

            <details style={{ position: 'relative' }}>
              <summary
                style={{
                  listStyle: 'none',
                  display: 'flex',
                  cursor: 'pointer',
                  alignItems: 'center',
                  gap: 10,
                  borderRadius: 999,
                  border: '1px solid #dce8f5',
                  background: '#ffffff',
                  padding: '6px 12px 6px 6px',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                  userSelect: 'none',
                }}
              >
                <span
                  style={{
                    display: 'flex',
                    width: 34,
                    height: 34,
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: '50%',
                    background: '#102a4c',
                    fontSize: 13,
                    fontWeight: 700,
                    color: '#ffffff',
                  }}
                >
                  {initials}
                </span>
                <span className="hidden sm:block" style={{ textAlign: 'left' }}>
                  <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#0f172a' }}>
                    {currentUser?.fullname || currentUser?.username || 'User'}
                  </span>
                  <span style={{ display: 'block', fontSize: 11, color: '#64748b' }}>
                    {roleLabel[currentUser?.role] || currentUser?.role || 'Người dùng'}
                  </span>
                </span>
                <svg viewBox="0 0 24 24" fill="none" style={{ width: 14, height: 14, color: '#94a3b8' }} stroke="currentColor" strokeWidth="2">
                  <path d="m7 10 5 5 5-5" />
                </svg>
              </summary>

              <div
                style={{
                  position: 'absolute',
                  right: 0,
                  zIndex: 20,
                  marginTop: 8,
                  width: 260,
                  borderRadius: 16,
                  border: '1px solid #dce8f5',
                  background: '#ffffff',
                  padding: 12,
                  boxShadow: '0 20px 50px -20px rgba(15,23,42,0.3)',
                }}
              >
                <div style={{ borderRadius: 10, background: '#f0f6ff', padding: '12px 14px' }}>
                  <p style={{ margin: 0, fontSize: 10, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', color: '#94a3b8' }}>
                    Tài khoản đăng nhập
                  </p>
                  <p style={{ margin: '6px 0 0', fontSize: 13, fontWeight: 600, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    @{currentUser?.username}
                  </p>
                  <p style={{ margin: '4px 0 0', fontSize: 11, color: '#64748b' }}>
                    {roleDescription[currentUser?.role] || 'Tài khoản hệ thống Sealink.'}
                  </p>
                </div>
                <div style={{ marginTop: 8 }}>
                  <button
                    type="button"
                    onClick={onLogout}
                    style={{
                      display: 'flex',
                      width: '100%',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      borderRadius: 8,
                      background: '#fff1f2',
                      color: '#e11d48',
                      fontWeight: 600,
                      fontSize: 13,
                      padding: '8px 12px',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <span>Đăng xuất</span>
                    <span>→</span>
                  </button>
                </div>
              </div>
            </details>
          </div>
        </header>

        {/* Description bar */}
        <div style={{ borderBottom: '1px solid #dce8f5', background: '#ffffff', padding: '10px 24px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ maxWidth: 800, fontSize: 13, lineHeight: 1.7, color: '#64748b', margin: 0 }}>
            {activeItem?.description}
          </p>
          {headerControls && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              {headerControls}
            </div>
          )}
        </div>

        {notificationNotice && (
          <div
            role="status"
            style={{
              margin: '14px 24px 0',
              border: '1px solid #bfdbfe',
              borderLeft: '4px solid #2563eb',
              borderRadius: 12,
              background: '#eff6ff',
              padding: '12px 14px',
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: 16,
              flexShrink: 0,
            }}
          >
            <div style={{ minWidth: 0 }}>
              <p style={{ margin: 0, color: '#1e3a8a', fontSize: 13, fontWeight: 700 }}>
                {notificationNotice.title}
              </p>
              <p style={{ margin: '4px 0 0', color: '#475569', fontSize: 12.5, lineHeight: 1.55 }}>
                {notificationNotice.message}
              </p>
            </div>
            <button
              type="button"
              aria-label="Đóng nội dung thông báo"
              onClick={onDismissNotificationNotice}
              className="app-close-button app-close-button--compact"
              style={{
                border: '1px solid #bfdbfe',
                borderRadius: 8,
                background: '#ffffff',
                color: '#334155',
                width: 30,
                height: 30,
                cursor: 'pointer',
                flexShrink: 0,
                fontSize: 18,
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>
        )}

        {/* Main scrollable content */}
        <main style={{ flex: 1, padding: '24px', minWidth: 0 }}>{children}</main>

        {/* Footer */}
        <footer style={{ borderTop: '1px solid #dce8f5', background: '#ffffff', padding: '10px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, flexWrap: 'wrap' }}>
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                flexShrink: 0,
                background: loading ? '#f59e0b' : '#10b981',
              }}
            />
            <span style={{ fontWeight: 600, color: '#1e293b' }}>
              {loading ? 'Đang xử lý dữ liệu' : 'Hệ thống sẵn sàng'}
            </span>
            <span style={{ color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {message}
            </span>
          </div>
        </footer>
      </div>
    </div>
  )
}
