import { useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { ApiError, getServiceEntitlementLicense, getServiceEntitlements, getServicePlans } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'

const money = (amount, currency = 'NGN') => new Intl.NumberFormat('en-NG', { style: 'currency', currency }).format(amount / 100)

export default function ServicesPage({ navigate }) {
  const { selectedSchool, signOut } = useAuth()
  const [plans, setPlans] = useState([])
  const [licenses, setLicenses] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const canDownloadLicense = ['platform_superadmin', 'school_owner', 'school_admin', 'principal'].includes(selectedSchool?.role)

  useEffect(() => {
    let mounted = true
    Promise.all([getServicePlans(), getServiceEntitlements()])
      .then(([nextPlans, nextLicenses]) => {
        if (!mounted) return
        setPlans(nextPlans)
        setLicenses(nextLicenses)
      })
      .catch((requestError) => {
        if (mounted) setError(requestError instanceof ApiError ? requestError.message : 'Could not load service information.')
      })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [])

  const activeCbt = licenses.find((license) => license.service_code === 'offline_cbt' && license.is_current)

  async function downloadLicense(license) {
    setDownloading(true)
    setError('')
    try {
      const signed = await getServiceEntitlementLicense(license.id)
      const file = new Blob([JSON.stringify({ signed_license: signed.signed_license }, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(file)
      const link = document.createElement('a')
      link.href = url
      link.download = `edustacked-cbt-license-${signed.license_id}.json`
      link.click()
      URL.revokeObjectURL(url)
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : 'Could not download this license.')
    } finally { setDownloading(false) }
  }

  async function handleSignOut() {
    await signOut()
    navigate('/')
  }

  return (
    <main className="app-page">
      <header className="app-topbar">
        <BrandMark />
        <nav className="page-actions" aria-label="Page actions">
          <button className="text-button" type="button" onClick={() => navigate('/app')}>Dashboard</button>
          <button className="text-button" type="button" onClick={handleSignOut}>Sign out</button>
        </nav>
      </header>
      <section className="app-content">
        <p className="eyebrow">{selectedSchool?.school_name} · OPTIONAL SERVICES</p>
        <h1 className="app-heading">Services <em>&amp; licenses</em></h1>
        <p className="intro">Add-on services are licensed separately. Your core school management tools and report-card credits remain available independently.</p>

        {error && <p className="form-error" role="alert">{error}</p>}
        {loading ? <p className="loading-message" role="status">Loading service licenses…</p> : (
          <>
            <section className="access-panel" aria-labelledby="cbt-title">
              <div>
                <p className="panel-kicker">OFFLINE EXAMINATIONS</p>
                <h2 id="cbt-title">Offline CBT</h2>
              </div>
              <p role="status"><strong>{activeCbt ? 'Active' : 'Not licensed'}</strong></p>
              {activeCbt ? (
                <dl className="session-details">
                  <div><dt>Package</dt><dd>{activeCbt.plan_name || activeCbt.package_type}</dd></div>
                  <div><dt>Student capacity</dt><dd>{activeCbt.student_capacity}</dd></div>
                  <div><dt>Valid through</dt><dd>{activeCbt.expires_on}</dd></div>
                  {canDownloadLicense && <div><button className="secondary-button" type="button" disabled={downloading} onClick={() => downloadLicense(activeCbt)}>{downloading ? 'Preparing license…' : 'Download signed license update'}</button></div>}
                </dl>
              ) : <p className="selection-note">This school can use the core EDUstacked system without CBT. To enable offline examinations, an administrator must activate a separate CBT license.</p>}
            </section>

            <section className="access-panel" aria-labelledby="plans-title">
              <div>
                <p className="panel-kicker">SEPARATELY LICENSED</p>
                <h2 id="plans-title">Available service plans</h2>
              </div>
              {plans.length ? <div className="service-plan-list">{plans.map((plan) => (
                <article className="service-plan" key={plan.id}>
                  <div><h3>{plan.name}</h3><p>{plan.description || `${plan.student_capacity} students · ${plan.duration_days} days`}</p></div>
                  <strong>{money(plan.price_minor, plan.currency)}</strong>
                </article>
              ))}</div> : <p className="selection-note">No service plans are currently published. Contact EDUstacked to request CBT licensing.</p>}
              <p className="selection-note">Plan pricing is shown separately from report-card credits. Online purchase and renewal checkout will be added in a later phase; no payment or license activation is simulated here.</p>
            </section>
          </>
        )}

        <section className="access-panel" aria-labelledby="license-history-title">
          <p className="panel-kicker">LICENSE HISTORY</p>
          <h2 id="license-history-title">School service records</h2>
          {!loading && licenses.length === 0 && <p>No service licenses have been issued to this school.</p>}
          {licenses.map((license) => <article className="service-plan" key={license.id}>
            <div><h3>{license.service_code.replaceAll('_', ' ')}</h3><p>{license.package_type} · {license.starts_on} to {license.expires_on}</p></div>
            <strong>{license.is_current ? 'Active' : license.status}</strong>
          </article>)}
        </section>
      </section>
    </main>
  )
}
