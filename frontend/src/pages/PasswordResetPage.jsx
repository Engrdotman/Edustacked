import { useState } from 'react'
import { apiRequest, ApiError } from '../services/api.js'

export default function PasswordResetPage({ navigate, mode = 'confirm' }) {
  const params = new URLSearchParams(window.location.search)
  const uid = params.get('uid') || ''
  const token = params.get('token') || ''
  const isRequest = mode === 'request'
  const hasResetLink = Boolean(uid && token)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const invalidLink = !isRequest && !hasResetLink
  const resetFinished = !isRequest && Boolean(message)
  const linkExpired = !isRequest && error.toLowerCase().includes('invalid or expired')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    if (!isRequest && password !== passwordConfirmation) {
      setError('The passwords do not match. Enter the same password in both fields.')
      return
    }
    setSubmitting(true)
    try {
      if (isRequest) {
        const response = await apiRequest('auth/password/reset/', {
          method: 'POST',
          body: { email },
        })
        setMessage(response.detail)
      } else {
        const response = await apiRequest('auth/password/reset/confirm/', {
          method: 'POST',
          body: { uid, token, new_password: password },
        })
        setPassword('')
        setPasswordConfirmation('')
        setMessage(response.detail)
      }
    } catch (requestError) {
      setError(requestError instanceof ApiError
        ? requestError.message
        : 'We could not complete the request. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const heading = isRequest
    ? 'Forgot your password?'
    : invalidLink
      ? 'Reset link unavailable.'
      : linkExpired
        ? 'This reset link has expired.'
        : resetFinished
          ? 'Your password has been updated.'
          : 'Set a new password.'

  const intro = isRequest
    ? 'Enter the email address on your account. We’ll send a secure link to choose a new password.'
    : invalidLink
      ? 'This page needs the secure link from your reset email. Request a new link and open it on this device.'
      : linkExpired
        ? 'For your account security, reset links expire. Request a fresh link to choose a new password.'
        : resetFinished
          ? 'Your EDUstacked password is ready. You can now sign in with the new password.'
          : 'Choose a new password for your EDUstacked account. The secure link can only be used once. If it expires, request another one.'

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="reset-title">
        <p className="eyebrow">ACCOUNT SECURITY</p>
        <h1 id="reset-title">{heading}</h1>
        <p className="auth-intro">{intro}</p>
        {(isRequest || (!invalidLink && !resetFinished && !linkExpired)) && <form className="auth-form" onSubmit={handleSubmit}>
          {isRequest ? (
            <>
              <label htmlFor="reset-email">Email address</label>
              <input id="reset-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
            </>
          ) : (
            <>
              <label htmlFor="new-password">New password</label>
              <input id="new-password" type="password" autoComplete="new-password" minLength="8" required value={password} onChange={(event) => setPassword(event.target.value)} />
              <label htmlFor="confirm-new-password">Confirm new password</label>
              <input id="confirm-new-password" type="password" autoComplete="new-password" minLength="8" required value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} />
            </>
          )}
          {message && <p className="form-success" role="status">{message}</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? 'Please wait…' : isRequest ? 'Send reset instructions' : 'Save new password'}
          </button>
        </form>}
        {!isRequest && (invalidLink || linkExpired) && <p className="form-error" role="alert">{error || 'This reset link is missing details or has expired. Request a fresh password reset email to continue.'}</p>}
        {!isRequest && resetFinished && <p className="form-success" role="status">{message}</p>}
        {!isRequest && (invalidLink || linkExpired) && <button className="primary-button auth-reset-action" type="button" onClick={() => navigate('/forgot-password')}>Request a new reset link</button>}
        {!isRequest && resetFinished
          ? <button className="primary-button auth-reset-action" type="button" onClick={() => navigate('/login')}>Go to sign in</button>
          : <button className="text-button auth-link" type="button" onClick={() => navigate('/login')}>Return to sign in</button>}
      </section>
    </main>
  )
}
