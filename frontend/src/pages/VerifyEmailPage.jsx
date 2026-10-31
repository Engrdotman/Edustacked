import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext.jsx'
import { ApiError } from '../services/api.js'

export default function VerifyEmailPage({ navigate }) {
  const { completeEmailVerification } = useAuth()
  const [message, setMessage] = useState('Verifying your email address…')
  const [error, setError] = useState(false)
  useEffect(() => {
    const query = new URLSearchParams(window.location.search)
    const selector = query.get('selector')
    const token = query.get('token')
    if (!selector || !token) { setMessage('This verification link is incomplete. Request a new email verification link.'); setError(true); return }
    let active = true
    completeEmailVerification(selector, token)
      .then(() => { if (active) { setMessage('Email verified. Taking you to your school setup…'); setTimeout(() => navigate('/app/onboarding'), 700) } })
      .catch((requestError) => { if (active) { setMessage(requestError instanceof ApiError ? requestError.message : 'This verification link is invalid or expired.'); setError(true) } })
    return () => { active = false }
  }, [completeEmailVerification, navigate])
  return <main className="auth-page"><section className="auth-card" aria-live="polite"><p className="eyebrow">EDUstacked · EMAIL VERIFICATION</p><h1>{error ? 'We couldn’t verify that link.' : 'Almost there.'}</h1><p className={error ? 'form-error' : 'auth-intro'}>{message}</p>{error && <button className="primary-button" onClick={() => navigate('/login?verify=1')}>Request another link</button>}</section></main>
}
