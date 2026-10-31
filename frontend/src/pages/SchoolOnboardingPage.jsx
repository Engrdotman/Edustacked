import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'
import { apiRequest } from '../services/api.js'

export default function SchoolOnboardingPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(() => apiRequest('schools/onboarding/').then(setSummary).catch((e) => setError(e.message)), [])
  useEffect(() => { load() }, [load])
  async function openStep(step) {
    await apiRequest('schools/onboarding/', { method: 'PATCH', body: { current_step: step.id } }).then(setSummary)
    if (step.id < 5) navigate(step.path)
    else navigate('/app')
  }
  const statusText = {
    pending_verification: 'Your school is awaiting verification. You can continue setting it up while verification is pending.',
    under_review: 'Your school is under review. You can continue setting it up in the meantime.',
    verified: 'Your school has been successfully verified.',
    rejected: `Your school registration needs attention. ${summary?.verification_reason || 'Review the feedback and contact support if you need help.'}`,
    suspended: 'Your school account is currently suspended. Please contact support.',
  }[summary?.school_status]
  return <main className="onboarding-page"><header className="app-topbar"><BrandMark /><button className="text-button" onClick={() => navigate('/app')}>Go to dashboard</button></header><section className="onboarding-content"><p className="eyebrow">SCHOOL SETUP · {selectedSchool?.school_name}</p><h1>Let’s get your school ready.</h1><p className="auth-intro">Your progress is saved as you go. You can leave any optional step and return later.</p>
    {statusText && <div className={`school-status school-status-${summary?.school_status}`} role="status">{statusText}</div>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {summary && <><div className="onboarding-progress"><div><strong>{summary.completed_steps} of {summary.total_steps} setup steps complete</strong><span>{summary.percentage}%</span></div><div className="onboarding-progress-track"><i style={{ width: `${summary.percentage}%` }} /></div></div><div className="onboarding-steps">{summary.steps.map((step) => <article key={step.id} className={step.completed ? 'onboarding-step completed' : 'onboarding-step'}><div className="onboarding-step-number">{step.completed ? '✓' : step.id}</div><div><h2>{step.label}</h2><p>{step.completed ? 'Completed' : step.id === summary.current_step ? 'In progress' : 'Ready when you are'}</p></div><button className="secondary-button" onClick={() => openStep(step)}>{step.id === 5 ? 'Review setup' : step.completed ? 'Edit' : 'Continue'}</button></article>)}</div></>}
    <p className="dashboard-empty">Your school workspace remains available while you complete these steps.</p>
  </section></main>
}
