import { notifyDataChanged } from './dataSync'

type CredentialedFetchInit = RequestInit & {
  suppressDataChanged?: boolean
}

/**
 * Fetch an authenticated API resource while preserving the trusted-device
 * cookie required by IT_ADMIN sessions.
 */
export async function credentialedFetch(input: RequestInfo | URL, init: CredentialedFetchInit = {}) {
  const { suppressDataChanged = false, ...requestInit } = init
  const response = await fetch(input, {
    ...requestInit,
    credentials: 'include',
  })
  if (response.ok && !suppressDataChanged) notifyDataChanged(input, requestInit.method)
  return response
}
