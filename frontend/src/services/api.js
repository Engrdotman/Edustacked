// Production uses the Vercel same-origin proxy so mobile browsers keep the
// HttpOnly refresh cookie as a first-party cookie. Local development may still
// point at a separately configured API.
const API_BASE_URL = (import.meta.env.PROD ? '/api' : (import.meta.env.VITE_API_BASE_URL || '/api')).replace(/\/$/, '')
const API_VERSION = 'v1'

let accessToken = null
let selectedSchoolId = null
let csrfToken = null
let refreshInFlight = null

export class ApiError extends Error {
  constructor(message, statusCode = 0) {
    super(message)
    this.name = 'ApiError'
    this.statusCode = statusCode
  }
}

export function setAccessToken(token) {
  accessToken = token || null
}

export function setSelectedSchoolId(schoolId) {
  selectedSchoolId = schoolId || null
}

function endpoint(path) {
  return `${API_BASE_URL}/${API_VERSION}/${path.replace(/^\/+/, '')}`
}

function flattenError(value) {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(flattenError)
  if (value && typeof value === 'object') return Object.values(value).flatMap(flattenError)
  return []
}

function readableError(body, fallback) {
  if (typeof body?.detail === 'string') return body.detail
  const messages = flattenError(body)
  if (messages.length) return messages.join(' ')
  return fallback
}

function userFacingHttpFallback(status) {
  if (status === 401) return 'Please sign in again to continue.'
  if (status === 403) return 'Your account does not have permission to do this. Contact your school administrator if you need access.'
  if (status === 404) return 'We could not find that information. Refresh the page and try again.'
  if (status === 429) return 'You have tried this too many times. Wait a moment and try again.'
  if (status >= 500) return 'Something went wrong on our side. Please try again shortly.'
  return 'We could not complete that request. Check the information and try again.'
}

async function send(path, { method = 'GET', body, headers = {}, signal, responseType = 'json' } = {}) {
  const requestHeaders = { Accept: 'application/json', ...headers }
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData
  if (body !== undefined && !isFormData) requestHeaders['Content-Type'] = 'application/json'
  if (accessToken && !requestHeaders.Authorization) {
    requestHeaders.Authorization = `Bearer ${accessToken}`
  }
  if (selectedSchoolId && !requestHeaders['X-School-ID']) {
    requestHeaders['X-School-ID'] = String(selectedSchoolId)
  }
  if (csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
    requestHeaders['X-CSRFToken'] = csrfToken
  }

  let response
  try {
    response = await fetch(endpoint(path), {
      method,
      credentials: 'include',
      headers: requestHeaders,
      body: body === undefined ? undefined : (isFormData ? body : JSON.stringify(body)),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    const offline = typeof navigator !== 'undefined' && navigator.onLine === false
    throw new ApiError(offline
      ? 'Your device appears to be offline. Check your internet connection, then try again.'
      : 'We could not connect to EDUstacked. Check your connection and try again in a moment.')
  }

  const data = responseType === 'blob' && response.ok
    ? await response.blob()
    : await response.json().catch(() => null)
  return { response, data, contentType: response.headers.get('content-type') || '' }
}

export async function getCsrfToken() {
  let result
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      result = await send('auth/csrf/')
      if (![502, 503, 504].includes(result.response.status) || attempt > 0) break
    } catch (error) {
      if (attempt > 0 || (typeof navigator !== 'undefined' && navigator.onLine === false)) throw error
    }
    await new Promise((resolve) => window.setTimeout(resolve, 900))
  }
  const { response, data, contentType } = result
  if (!response.ok) {
    const message = response.status >= 500
      ? 'Sign-in is temporarily unavailable. Please wait a moment and try again.'
      : response.status === 404
        ? 'We could not find the sign-in service. Refresh this page and try again. If it continues, contact EDUstacked support (AUTH-404).'
        : 'We could not start sign-in. Refresh this page and try again. If it continues, contact EDUstacked support.'
    throw new ApiError(message, response.status)
  }
  if (!data?.csrfToken) {
    const isHtml = contentType.includes('text/html')
    throw new ApiError(isHtml
      ? 'The sign-in page could not reach the authentication service. Please try again later or contact EDUstacked support (AUTH-ROUTE).'
      : 'The authentication service returned an unexpected response. Please try again later or contact EDUstacked support (AUTH-RESPONSE).', response.status)
  }
  csrfToken = data.csrfToken
  return csrfToken
}

export async function refreshSession() {
  if (refreshInFlight) return refreshInFlight

  refreshInFlight = (async () => {
    await getCsrfToken()
    const { response, data } = await send('auth/refresh/', {
      method: 'POST',
      body: {},
    })
    if (!response.ok || !data?.access) {
      setAccessToken(null)
      throw new ApiError('Your session has expired. Please sign in again.', response.status)
    }
    setAccessToken(data.access)
    return data.access
  })()

  try {
    return await refreshInFlight
  } finally {
    refreshInFlight = null
  }
}

export async function apiRequest(path, options = {}, canRefresh = true) {
  const { response, data, contentType } = await send(path, options)
  const isAuthEndpoint = path.startsWith('auth/login') || path.startsWith('auth/refresh')

  if (path.startsWith('auth/') && contentType.includes('text/html')) {
    throw new ApiError(
      'The sign-in service returned a web page instead of an account response. The live connection needs attention. Please try again shortly or contact EDUstacked support (AUTH-ROUTE).',
      response.status,
    )
  }

  if (response.status === 401 && canRefresh && accessToken && !isAuthEndpoint) {
    try {
      await refreshSession()
      return apiRequest(path, options, false)
    } catch (refreshError) {
      if ([401, 403].includes(refreshError.statusCode)) setAccessToken(null)
      else throw refreshError
    }
  }

  if (!response.ok) {
    const fallback = userFacingHttpFallback(response.status)
    const error = new ApiError(
      response.status >= 500 ? fallback : readableError(data, fallback),
      response.status,
    )
    error.fields = data && typeof data === 'object' ? data : {}
    throw error
  }
  return data
}

export async function apiBlobRequest(path, canRefresh = true) {
  const { response, data } = await send(path, { responseType: 'blob' })
  if (response.status === 401 && canRefresh && accessToken) {
    await refreshSession()
    return apiBlobRequest(path, false)
  }
  if (!response.ok) throw new ApiError('The requested file could not be loaded.', response.status)
  return data
}

export function getSchoolProfile() {
  return apiRequest('schools/profile/')
}

export function updateSchoolProfile(values) {
  return apiRequest('schools/profile/', { method: 'PATCH', body: values })
}

export function getSchoolSettings() {
  return apiRequest('schools/settings/')
}

export function updateSchoolSettings(values) {
  return apiRequest('schools/settings/', { method: 'PATCH', body: values })
}

export function getSchoolLogo() {
  return apiBlobRequest('schools/profile/logo/')
}

export function uploadSchoolLogo(file) {
  const body = new FormData()
  body.append('logo', file)
  return apiRequest('schools/profile/logo/', { method: 'POST', body })
}

export function getPrincipalSignature() {
  return apiBlobRequest('schools/profile/principal-signature/')
}

export function uploadPrincipalSignature(file) {
  const body = new FormData()
  body.append('signature', file)
  return apiRequest('schools/profile/principal-signature/', { method: 'POST', body })
}

export async function academicList(path) {
  let page = 1
  const rows = []
  let next = true
  while (next) {
    const response = await apiRequest(`academics/${path}${path.includes('?') ? '&' : '?'}page=${page}`)
    if (Array.isArray(response)) return response
    rows.push(...(response?.results || []))
    next = Boolean(response?.next)
    page += 1
  }
  return rows
}

export function academicRequest(path, options) {
  return apiRequest(`academics/${path}`, options)
}

export function cbtRequest(path, options) {
  return apiRequest(`cbt/${path}`, options)
}

export async function cbtList(path) {
  let page = 1
  const rows = []
  let next = true
  while (next) {
    const separator = path.includes('?') ? '&' : '?'
    const response = await cbtRequest(`${path}${separator}page=${page}`)
    if (Array.isArray(response)) return response
    rows.push(...(response?.results || []))
    next = Boolean(response?.next)
    page += 1
  }
  return rows
}

export function getServiceEntitlements() {
  return apiRequest('services/entitlements/')
}

export function getServicePlans() {
  return apiRequest('services/plans/')
}

export function getServiceEntitlementLicense(licenseId) {
  return apiRequest(`services/entitlements/${licenseId}/license/`)
}

export async function login(email, password) {
  await getCsrfToken()
  const data = await apiRequest('auth/login/', {
    method: 'POST',
    body: { email, password },
  })
  setAccessToken(data.access)
  return data.user
}

export function signupSchool(values) {
  return apiRequest('auth/signup/', { method: 'POST', body: values })
}

export function verifySchoolEmail(values) {
  return apiRequest('auth/verify-email/', { method: 'POST', body: values })
}

export function resendSchoolEmailVerification(email) {
  return apiRequest('auth/verify-email/resend/', { method: 'POST', body: { email } })
}

export function requestSchoolDemo(values) {
  return apiRequest('auth/demo-request/', { method: 'POST', body: values })
}

export async function logout() {
  try {
    await apiRequest('auth/logout/', { method: 'POST', body: {} }, false)
  } finally {
    setAccessToken(null)
    setSelectedSchoolId(null)
  }
}

export function getApiHealth(options) {
  return apiRequest('health/', options)
}
