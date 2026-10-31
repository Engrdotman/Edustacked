import { useEffect, useState } from 'react'
import { ApiError, apiRequest } from '../services/api.js'

export default function GuardianActivationPage({ navigate }) {
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') || '')
  const [password, setPassword] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    window.history.replaceState({}, '', '/guardian/activate')
  }, [])

  async function submit(event) {
    event.preventDefault()
    setWorking(true)
    setError('')
    try {
      await apiRequest('guardian/activate/', { method: 'POST', body: { token, password } })
      setSuccess(true)
      setPassword('')
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : 'This invitation could not be activated.')
    } finally { setWorking(false) }
  }

  return <main className="auth-page"><section className="auth-card">
    <p className="eyebrow">EDUstacked · PARENT PORTAL</p>
    <h1>Activate portal access.</h1>
    {success ? <><p className="form-success" role="status">Your parent portal is ready. Sign in with the invited email and password.</p><button className="primary-button" onClick={() => navigate('/login')}>Go to sign in</button></> : <>
      <p className="auth-intro">Set a password to activate the invitation sent by your school. If you already have an EDUstacked account with this email, enter that account's current password.</p>
      {!token && <p className="form-error" role="alert">The invitation link is missing or incomplete. Ask the school to send a new invitation.</p>}
      <form className="auth-form" onSubmit={submit}>
        <label htmlFor="activation-password">Password</label>
        <input id="activation-password" type="password" autoComplete="new-password" minLength="8" required value={password} onChange={(event) => setPassword(event.target.value)} />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button" type="submit" disabled={working || !token}>{working ? 'Activating…' : 'Activate parent portal'}</button>
      </form>
      <button className="text-button back-link" type="button" onClick={() => navigate('/login')}>Back to sign in</button>
    </>}
  </section></main>
}
