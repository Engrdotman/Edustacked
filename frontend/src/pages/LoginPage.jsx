import { useState } from 'react'
import { ApiError } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { resendSchoolEmailVerification } from '../services/api.js'
import BrandMark from '../components/BrandMark.jsx'
import PasswordField from '../components/PasswordField.jsx'
import GoogleSignInButton from '../components/GoogleSignInButton.jsx'

export default function LoginPage({ navigate, sessionRequired = false }) {
  const { signIn } = useAuth()
  const [email, setEmail] = useState(() => new URLSearchParams(window.location.search).get('email') || '')
  const [password, setPassword] = useState('')
  const [portal, setPortal] = useState('school')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [notice, setNotice] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const profile = await signIn(email, password, { portal })
      navigate(portal === 'parent' && profile.guardian_portal ? '/parent' : '/app')
    } catch (requestError) {
      setError(requestError instanceof ApiError
        ? requestError.message
        : requestError?.message || 'Sign in could not be completed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function resendVerification() {
    setNotice('')
    try { const result = await resendSchoolEmailVerification(email); setNotice(result.detail) }
    catch (e) { setError(e.message || 'Could not resend verification email.') }
  }

  function handleGoogleSuccess() {
    navigate(portal === 'parent' ? '/parent' : '/app')
  }

  return (
    <main className="auth-page auth-page-split auth-page-login">
      <section className="auth-visual" aria-label="EDUstacked school management">
        <BrandMark navigate={navigate} />
        <div className="auth-visual-copy"><p>EDUstacked · SCHOOL MANAGEMENT</p><h2>More clarity for every school day.</h2><span>Bring student records, staff, attendance, academics, and reports into one calm, connected workspace.</span></div>
        <small>Built for schools · edustackedng@gmail.com</small>
      </section>
      <div className="auth-panel"><section className="auth-card auth-card-login" aria-labelledby="login-title">
        <div className="auth-mode-tabs" aria-label="Account access">
          <button type="button" onClick={() => navigate('/signup')}>Sign up</button>
          <button type="button" className="is-active" aria-current="page">Sign in</button>
        </div>
        <h1 id="login-title">Welcome back.</h1>
        <p className="auth-intro">{sessionRequired ? 'Your session needs a fresh sign-in. Enter your account details to continue.' : 'Choose your account type, then sign in to continue.'}</p>
        <label htmlFor="login-portal">I am signing in as  </label>
        <select id="login-portal" name="portal" className="auth-portal-select" value={portal} onChange={(event) => { setPortal(event.target.value); setError('') }}>
          <option value="school">School owner or staff</option>
          <option value="parent">Parent or guardian</option>
        </select>
        <p className="parent-login-hint">{portal === 'parent'
          ? 'Use the email the school invited and the password you set from the activation link. You will go directly to your linked students.'
          : 'Use the email and password for your school workspace. Parent and guardian accounts should choose the parent option.'}</p>
        {new URLSearchParams(window.location.search).get('registered') === '1' && <p className="form-success" role="status">Your school account has been created. Check your email inbox or spam folder and verify it to continue.</p>}
        {new URLSearchParams(window.location.search).get('verify') === '1' && <p className="form-success" role="status">Enter your email address and request a fresh verification link.</p>}
        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="email">Email address</label>
          <input id="email" name="email" type="email" autoComplete="username" placeholder="you@school.com" required value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="password">Password</label>
          <PasswordField id="password" name="password" autoComplete="current-password" placeholder="Enter your password" required value={password} onChange={(event) => setPassword(event.target.value)} />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        {import.meta.env.VITE_GOOGLE_CLIENT_ID && <GoogleSignInButton
          portal={portal}
          onSuccess={handleGoogleSuccess}
          onError={setError}
          onBusy={setSubmitting}
        />}
        {notice && <p className="form-success" role="status">{notice}</p>}
        {(new URLSearchParams(window.location.search).get('registered') === '1' || new URLSearchParams(window.location.search).get('verify') === '1' || error.toLowerCase().includes('verify your email')) && <button className="text-button auth-link" type="button" onClick={resendVerification}>Resend verification email</button>}
        <div className='auth-link-flex-spaceinbtw'>
          
   <button className="text-button auth-link" type="button" onClick={() => navigate('/forgot-password')}>
          Forgot your password?
        </button>
        </div>
   
        <button className="text-button back-link" type="button" onClick={() => navigate('/')}>Back to home</button>
        
      </section></div>
    </main>
  )
}
