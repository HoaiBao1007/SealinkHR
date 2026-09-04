export const DATA_CHANGED_EVENT = 'sealink:data-changed'

export type DataChangedDetail = {
  method: string
  path: string
  occurredAt: number
}

let pendingDetail: DataChangedDetail | null = null
let pendingTimer: number | null = null

function requestPath(input: RequestInfo | URL) {
  const raw = input instanceof Request ? input.url : String(input)
  try {
    return new URL(raw, window.location.origin).pathname
  } catch {
    return raw
  }
}

export function isDataMutation(method?: string) {
  return !['GET', 'HEAD', 'OPTIONS'].includes(String(method || 'GET').toUpperCase())
}

/**
 * Notify every visible data surface after a successful write.
 *
 * Delivery is deferred and batched so the mutation handler can finish its
 * local state update first. Several writes from one Save action therefore
 * produce one coordinated refresh instead of multiple competing requests.
 */
export function notifyDataChanged(input: RequestInfo | URL, method?: string) {
  const normalizedMethod = String(method || (input instanceof Request ? input.method : 'GET')).toUpperCase()
  if (!isDataMutation(normalizedMethod) || typeof window === 'undefined') return

  const path = requestPath(input)
  // These POST endpoints only inspect/preview input and never persist data.
  if (/(?:inspect|preview)(?:\/|$)/i.test(path) || /\/(?:attendance-json|merge-preview)(?:\/|$)/i.test(path)) return

  pendingDetail = {
    method: normalizedMethod,
    path,
    occurredAt: Date.now(),
  }
  if (pendingTimer !== null) window.clearTimeout(pendingTimer)
  pendingTimer = window.setTimeout(() => {
    const detail = pendingDetail
    pendingDetail = null
    pendingTimer = null
    if (detail) window.dispatchEvent(new CustomEvent<DataChangedDetail>(DATA_CHANGED_EVENT, { detail }))
  }, 60)
}

export function subscribeDataChanged(listener: (detail: DataChangedDetail) => void) {
  const handler = (event: Event) => listener((event as CustomEvent<DataChangedDetail>).detail)
  window.addEventListener(DATA_CHANGED_EVENT, handler)
  return () => window.removeEventListener(DATA_CHANGED_EVENT, handler)
}
