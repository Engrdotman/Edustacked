import { useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { getApiHealth } from '../services/api.js'

export default function WelcomePage({ onLogin }) {
  const [apiStatus, setApiStatus] = useState('checking')

  useEffect(() => {
    const controller = new AbortController()
    getApiHealth({ signal: controller.signal })
      .then(() => setApiStatus('connected'))
      .catch(() => {
        if (!controller.signal.aborted) setApiStatus('unavailable')
      })

    return () => controller.abort()
  }, [])

  const statusLabel = {
    checking: 'Checking API connection',
    connected: 'API connected',
    unavailable: 'API unavailable — start the backend to connect',
  }[apiStatus]

  return (
    <main className="page-shell">
      <header className="topbar">
        <BrandMark />
        <div className="topbar-actions">
          <span className="edition">EDUstacked WORKSPACE</span>
          <button className="text-button" type="button" onClick={onLogin}>Sign in</button>
        </div>
      </header>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow"><span className="status-dot" /> A calmer way to run your school</p>
          <h1 id="hero-title">More time for<br /><em>what matters.</em></h1>
          <p className="intro">A thoughtful foundation for the everyday work of school communities. Built to grow with your school, one useful step at a time.</p>
          <div className="coming-soon"><span className="line" /> Your school workspace is taking shape</div>
          <p className={`api-status api-status-${apiStatus}`} role="status" aria-live="polite">
            <span className="api-status-dot" /> {statusLabel}
          </p>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" /><div className="orbit orbit-two" />
          <div className="sun" />
          <div className="book book-back" /><div className="book book-front" />
          <div className="art-caption"><span>01</span><span>BUILT FOR BETTER DAYS</span></div>
        </div>
      </section>
      <footer className="footer"><span>Made for the people who make a school.</span><span>FOUNDATION IN PROGRESS <i /></span></footer>
    </main>
  )
}
