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

function readableError(body, fallback) {
  if (typeof body?.detail === 'string') return body.detail
  if (typeof body?.non_field_errors?.[0] === 'string') return body.non_field_errors[0]
  if (body && Object.keys(body).length) return Object.values(body).flat().join(' ')
  return fallback
}

async function send(path, { method = 'GET', body, headers = {}, signal } = {}) {
  const requestHeaders = { Accept: 'application/json', ...headers }
  if (body !== undefined) requestHeaders['Content-Type'] = 'application/json'
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
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError('The API could not be reached.')
  }

  const data = await response.json().catch(() => null)
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
    throw new ApiError(
      readableError(data, `The API returned an error (${response.status}).`),
      response.status,
    )
  }
  return data
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
