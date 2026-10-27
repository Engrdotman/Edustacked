import { useState } from 'react'
import { apiRequest, ApiError } from '../services/api.js'

export default function PasswordResetPage({ navigate, mode = 'confirm' }) {
  const params = new URLSearchParams(window.location.search)
  const uid = params.get('uid') || ''
  const token = params.get('token') || ''
  const isRequest = mode === 'request'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setMessage('')
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
        setMessage(response.detail)
      }
    } catch (requestError) {
      setError(requestError instanceof ApiError
        ? requestError.message
        : 'The request could not be completed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="reset-title">
        <p className="eyebrow">ACCOUNT SECURITY</p>
        <h1 id="reset-title">{isRequest ? 'Reset your password.' : 'Choose a new password.'}</h1>
        <p className="auth-intro">
          {isRequest
            ? 'If an active account matches your email, we’ll send a secure reset link.'
            : 'Use a strong password you do not use for another account.'}
        </p>
        <form className="auth-form" onSubmit={handleSubmit}>
          {isRequest ? (
            <>
              <label htmlFor="reset-email">Email address</label>
              <input id="reset-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
            </>
          ) : (
            <>
              <label htmlFor="new-password">New password</label>
              <input id="new-password" type="password" autoComplete="new-password" minLength="8" required value={password} onChange={(event) => setPassword(event.target.value)} />
            </>
          )}
          {message && <p className="form-success" role="status">{message}</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={submitting || (!isRequest && (!uid || !token))}>
            {submitting ? 'Please wait…' : isRequest ? 'Send reset instructions' : 'Set new password'}
          </button>
        </form>
        <button className="text-button auth-link" type="button" onClick={() => navigate('/login')}>Return to sign in</button>
      </section>
    </main>
  )
}
