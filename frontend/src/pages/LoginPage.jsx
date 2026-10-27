import { useState } from 'react'
import { ApiError } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'

export default function LoginPage({ navigate }) {
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await signIn(email, password)
      navigate('/app')
    } catch (requestError) {
      setError(requestError instanceof ApiError
        ? requestError.message
        : 'Sign in could not be completed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <p className="eyebrow">EDUstacked</p>
        <h1 id="login-title">Welcome back.</h1>
        <p className="auth-intro">Sign in with the email address provided by your school administrator.</p>
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
        <button className="text-button auth-link" type="button" onClick={() => navigate('/forgot-password')}>
          Forgot your password?
        </button>
        <button className="text-button back-link" type="button" onClick={() => navigate('/')}>Back to home</button>
      </section>
    </main>
  )
}
