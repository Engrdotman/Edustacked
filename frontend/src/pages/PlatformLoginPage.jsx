import { useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import PasswordField from '../components/PasswordField.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import GoogleSignInButton from '../components/GoogleSignInButton.jsx'

export default function PlatformLoginPage({ navigate }) {
  const { user, signIn, signOut } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setWorking(true)
    try {
      await signIn(email, password, { portal: 'platform' })
      navigate('/platform')
    } catch (requestError) {
      setError(requestError?.message || 'Platform sign in could not be completed. Please try again.')
    } finally {
      setWorking(false)
    }
  }

  async function handleSignOut() {
    setWorking(true)
    setError('')
    try {
      await signOut()
    } catch (requestError) {
      setError(requestError?.message || 'Could not sign out of the current account. Please try again.')
    } finally {
      setWorking(false)
    }
  }

  return <main className="auth-page platform-auth-page"><section className="auth-card platform-auth-card">
    <BrandMark navigate={navigate} />
    <p className="eyebrow">EDUSTACKED PLATFORM ADMINISTRATION</p>
    <h1>Platform sign in.</h1>
    <p className="auth-intro">This access is reserved for EDUstacked platform administrators. School owners and staff should use the school sign-in page.</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {user ? <div className="platform-session-notice"><strong>Another account is signed in</strong><span>{user.email}</span><p>Sign out of this school account before opening the platform dashboard.</p><button className="primary-button" type="button" onClick={handleSignOut} disabled={working}>{working ? 'Signing out…' : 'Sign out and continue'}</button></div> : <form className="auth-form" onSubmit={handleSubmit}>
      <label htmlFor="platform-email">Administrator email</label>
      <input id="platform-email" name="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
      <label htmlFor="platform-password">Password</label>
      <PasswordField id="platform-password" name="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
      <button className="primary-button" type="submit" disabled={working}>{working ? 'Signing in…' : 'Sign in to platform'}</button>
    </form>}
    {!user && import.meta.env.VITE_GOOGLE_CLIENT_ID && <GoogleSignInButton
      portal="platform"
      onSuccess={() => navigate('/platform')}
      onError={setError}
      onBusy={setWorking}
    />}
    <button className="text-button platform-school-login-link" type="button" onClick={() => navigate('/login')}>School owner and staff sign in</button>
  </section></main>
}
