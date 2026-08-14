/**
 * Fetch an authenticated API resource while preserving the trusted-device
 * cookie required by IT_ADMIN sessions.
 */
export function credentialedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  return fetch(input, {
    ...init,
    credentials: 'include',
  })
}
