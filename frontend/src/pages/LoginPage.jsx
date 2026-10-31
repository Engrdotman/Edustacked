import { useState } from 'react'
import { ApiError } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { resendSchoolEmailVerification } from '../services/api.js'

export default function LoginPage({ navigate }) {
  const { signIn } = useAuth()
  const [email, setEmail] = useState(() => new URLSearchParams(window.location.search).get('email') || '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [notice, setNotice] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const profile = await signIn(email, password)
      navigate(profile.guardian_portal ? '/parent' : '/app')
    } catch (requestError) {
      setError(requestError instanceof ApiError
        ? requestError.message
        : 'Sign in could not be completed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function resendVerification() {
    setNotice('')
    try { const result = await resendSchoolEmailVerification(email); setNotice(result.detail) }
    catch (e) { setError(e.message || 'Could not resend verification email.') }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <p className="eyebrow">EDUstacked</p>
        <h1 id="login-title">Welcome back.</h1>
        <p className="auth-intro">Sign in with your EDUstacked administrator account.</p>
        {new URLSearchParams(window.location.search).get('registered') === '1' && <p className="form-success" role="status">Your school account has been created. Check your email and verify it to continue.</p>}
        {new URLSearchParams(window.location.search).get('verify') === '1' && <p className="form-success" role="status">Enter your email address and request a fresh verification link.</p>}
        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="email">Email address</label>
          <input id="email" name="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        {notice && <p className="form-success" role="status">{notice}</p>}
        {(new URLSearchParams(window.location.search).get('registered') === '1' || new URLSearchParams(window.location.search).get('verify') === '1' || error.toLowerCase().includes('verify your email')) && <button className="text-button auth-link" type="button" onClick={resendVerification}>Resend verification email</button>}
        <button className="text-button auth-link" type="button" onClick={() => navigate('/forgot-password')}>
          Forgot your password?
        </button>
        <button className="text-button auth-link" type="button" onClick={() => navigate('/signup')}>Register a school</button>
        <button className="text-button back-link" type="button" onClick={() => navigate('/')}>Back to home</button>
      </section>
    </main>
  )
}
