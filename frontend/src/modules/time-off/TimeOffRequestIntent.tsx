import './time-off-request-intent.css'
import { AppIcon, type AppIconName } from '../../shared/ui/AppIcon'

export const LEAVE_REQUEST = 'LEAVE_REQUEST'
export const WORK_FROM_HOME_REQUEST = 'WORK_FROM_HOME_REQUEST'
export const BUSINESS_TRAVEL_REQUEST = 'BUSINESS_TRAVEL_REQUEST'

export type LeaveBalance = {
  annual_quota: number
  annual_used: number
  reserved_request_days: number
  available: number
}

type Props = {
  value: string
  onChange: (value: string) => void
  leaveBalance?: LeaveBalance | null
}

const intents: Array<{ value: string; icon: AppIconName; title: string; description: string }> = [
  {
    value: LEAVE_REQUEST,
    icon: 'leave',
    title: 'Leave Request',
    description: 'Nghỉ có phép, tính lương sau khi được duyệt.',
  },
  {
    value: WORK_FROM_HOME_REQUEST,
    icon: 'home',
    title: 'Work From Home Request',
    description: 'Đề nghị làm việc tại nhà, hưởng lương sau khi được duyệt.',
  },
  {
    value: BUSINESS_TRAVEL_REQUEST,
    icon: 'briefcase',
    title: 'Business Travel Request',
    description: 'Đề nghị đi công tác theo quy định của công ty.',
  },
]

function formatDays(value: number) {
  return Number.isInteger(value) ? String(value) : value.toLocaleString('vi-VN', { maximumFractionDigits: 2 })
}

export function TimeOffRequestIntent({ value, onChange, leaveBalance }: Props) {
  return (
    <div className="time-off-intent-selector" role="group" aria-labelledby="time-off-intent-title">
      <div className="time-off-intent-heading">
        <span id="time-off-intent-title">Xin hãy chọn dự định của bạn <b>*</b></span>
        {value === LEAVE_REQUEST && leaveBalance && (
          <small>
            Còn <strong>{formatDays(leaveBalance.available)} ngày phép</strong>
            {' '}trong số {formatDays(leaveBalance.annual_quota)} ngày/năm.
          </small>
        )}
      </div>
      <div className="time-off-intent-options">
        {intents.map((intent) => (
          <button
            key={intent.value}
            type="button"
            className={value === intent.value ? 'is-selected' : ''}
            onClick={() => onChange(intent.value)}
            aria-pressed={value === intent.value}
          >
            <span className="time-off-intent-icon"><AppIcon name={intent.icon} size={17} /></span>
            <span><strong>{intent.title}</strong><small>{intent.description}</small></span>
          </button>
        ))}
      </div>
    </div>
  )
}
