import type { ReactNode, SVGProps } from 'react'

export type AppIconName =
  | 'arrow-left'
  | 'arrow-right'
  | 'bank'
  | 'bolt'
  | 'briefcase'
  | 'calendar'
  | 'chart'
  | 'check'
  | 'chevron-down'
  | 'close'
  | 'copy'
  | 'document'
  | 'download'
  | 'edit'
  | 'expand'
  | 'folder'
  | 'history'
  | 'home'
  | 'leave'
  | 'lock'
  | 'message'
  | 'money'
  | 'plus'
  | 'refresh'
  | 'save'
  | 'settings'
  | 'sparkle'
  | 'trash'
  | 'unlock'
  | 'undo'
  | 'upload'
  | 'user'
  | 'users'
  | 'wallet'
  | 'warning'

type Props = Omit<SVGProps<SVGSVGElement>, 'name'> & {
  name: AppIconName
  size?: number
}

const paths: Record<AppIconName, ReactNode> = {
  'arrow-left': <path d="M19 12H5m0 0 6-6m-6 6 6 6" />,
  'arrow-right': <path d="M5 12h14m0 0-6-6m6 6-6 6" />,
  bank: <><path d="M3 9h18" /><path d="M5 9v8m4-8v8m6-8v8m4-8v8M3 19h18M12 3l9 4H3l9-4Z" /></>,
  bolt: <path d="M13 2 4.5 13H11l-1 9L19.5 10H13l0-8Z" />,
  briefcase: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M8 3v4m8-4v4M3 10h18" /></>,
  chart: <><path d="M4 20V10m6 10V4m6 16v-7m4 7H2" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  'chevron-down': <path d="m6 9 6 6 6-6" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
  document: <><path d="M6 3h8l4 4v14H6V3Z" /><path d="M14 3v5h5M9 13h6m-6 4h6" /></>,
  download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14" /></>,
  edit: <><path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z" /><path d="m14 7 3 3" /></>,
  expand: <><path d="M8 3H3v5m13-5h5v5M8 21H3v-5m13 5h5v-5" /><path d="M3 8 8 3m8 0 5 5M3 16l5 5m8 0 5-5" /></>,
  folder: <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6Z" />,
  history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></>,
  home: <><path d="m3 11 9-8 9 8" /><path d="M5 10v10h14V10M9 20v-6h6v6" /></>,
  leave: <><path d="M8 11V5a1.5 1.5 0 0 1 3 0v5-6a1.5 1.5 0 0 1 3 0v6-4a1.5 1.5 0 0 1 3 0v6-2a1.5 1.5 0 0 1 3 0v4c0 4-3 7-7 7h-1c-3 0-5-2-7-5l-2-3a1.6 1.6 0 0 1 2.5-2l2.5 2" /></>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
  message: <path d="M4 4h16v12H8l-4 4V4Z" />,
  money: <><circle cx="12" cy="12" r="9" /><path d="M15 8.5c-.7-.5-1.7-.8-3-.8-1.7 0-3 .8-3 2.1 0 3.2 6 1.5 6 4.5 0 1.3-1.3 2.2-3.2 2.2-1.2 0-2.4-.4-3.3-1M12 5.5v13" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  refresh: <><path d="M20 7v5h-5" /><path d="M18.3 16A8 8 0 1 1 20 12" /></>,
  save: <><path d="M5 3h12l2 2v16H5V3Z" /><path d="M8 3v6h8V3M8 21v-7h8v7" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19 13.5a7.7 7.7 0 0 0 0-3l2-1.5-2-3.4-2.4 1a8 8 0 0 0-2.6-1.5L13.7 3h-4l-.3 2.1a8 8 0 0 0-2.6 1.5l-2.4-1-2 3.4 2 1.5a7.7 7.7 0 0 0 0 3l-2 1.5 2 3.4 2.4-1a8 8 0 0 0 2.6 1.5l.3 2.1h4l.3-2.1a8 8 0 0 0 2.6-1.5l2.4 1 2-3.4-2-1.5Z" /></>,
  sparkle: <><path d="m12 3 1.4 4.1L17.5 8.5l-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3Z" /><path d="m18.5 14 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2ZM5 14l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2Z" /></>,
  trash: <><path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6" /></>,
  unlock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 7.5-2" /></>,
  undo: <><path d="M9 7 4 12l5 5" /><path d="M4 12h10a6 6 0 0 1 6 6" /></>,
  upload: <><path d="M12 16V4m0 0L8 8m4-4 4 4M5 20h14" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  users: <><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0M16 5a3 3 0 0 1 0 6m1 3a6 6 0 0 1 4 6" /></>,
  wallet: <><path d="M4 6a2 2 0 0 1 2-2h12v16H6a2 2 0 0 1-2-2V6Z" /><path d="M4 8h14m0 4h3v5h-3a2.5 2.5 0 0 1 0-5Z" /></>,
  warning: <><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 9v5m0 3h.01" /></>,
}

export function AppIcon({ name, size = 18, className = '', ...props }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={`app-icon ${className}`.trim()}
      {...props}
    >
      {paths[name]}
    </svg>
  )
}
