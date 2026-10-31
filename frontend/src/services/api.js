const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const API_VERSION = 'v1'

let accessToken = null
let selectedSchoolId = null
let csrfToken = null

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
    throw new ApiError('The API could not be reached.')
  }

  const data = responseType === 'blob' && response.ok
    ? await response.blob()
    : await response.json().catch(() => null)
  return { response, data }
}

export async function getCsrfToken() {
  const { response, data } = await send('auth/csrf/')
  if (!response.ok || !data?.csrfToken) {
    throw new ApiError('Could not prepare a secure sign-in request.', response.status)
  }
  csrfToken = data.csrfToken
  return csrfToken
}

export async function refreshSession() {
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
}

export async function apiRequest(path, options = {}, canRefresh = true) {
  const { response, data } = await send(path, options)
  const isAuthEndpoint = path.startsWith('auth/login') || path.startsWith('auth/refresh')

  if (response.status === 401 && canRefresh && accessToken && !isAuthEndpoint) {
    try {
      await refreshSession()
      return apiRequest(path, options, false)
    } catch {
      setAccessToken(null)
    }
  }

  if (!response.ok) {
    const error = new ApiError(
      readableError(data, `The API returned an error (${response.status}).`),
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
