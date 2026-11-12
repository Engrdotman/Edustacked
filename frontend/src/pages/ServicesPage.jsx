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
  const featuredPlanId = plans.reduce((featured, plan) => !featured || plan.student_capacity > featured.student_capacity ? plan : featured, null)?.id

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
        <BrandMark navigate={navigate} />
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
            <section className={activeCbt ? 'cbt-license-card is-active' : 'cbt-license-card'} aria-labelledby="cbt-title">
              <div className="cbt-license-heading">
                <span className="cbt-license-icon" aria-hidden="true">CBT</span>
                <span className={activeCbt ? 'license-status is-active' : 'license-status'} role="status">{activeCbt ? 'License active' : 'Optional add-on'}</span>
              </div>
              <p className="panel-kicker">OFFLINE EXAMINATIONS</p>
              <h2 id="cbt-title">Offline CBT</h2>
              {activeCbt ? (
                <><p className="cbt-license-description">Run assessments on your school network, then sync results into EDUstacked.</p><div className="cbt-license-stats"><div><span>Plan</span><strong>{activeCbt.plan_name || activeCbt.package_type}</strong></div><div><span>Capacity</span><strong>{activeCbt.student_capacity} students</strong></div><div><span>Valid through</span><strong>{activeCbt.expires_on}</strong></div></div><div className="cbt-license-actions"><button className="cbt-cta cbt-cta-light" type="button" onClick={() => navigate('/app/cbt')}>Open CBT workspace <span aria-hidden="true">→</span></button>{canDownloadLicense && <button className="text-button" type="button" disabled={downloading} onClick={() => downloadLicense(activeCbt)}>{downloading ? 'Preparing license…' : 'Download signed license'}</button>}</div></>
              ) : <><p className="cbt-license-description">Prepare question banks and exams, run them on a local network, and sync results when internet access returns.</p><div className="cbt-benefit-row"><span>Local exam delivery</span><span>Central result review</span><span>Separate license</span></div><a className="cbt-cta" href={`mailto:edustackedng@gmail.com?subject=${encodeURIComponent('Offline CBT license request')}&body=${encodeURIComponent(`Hello EDUstacked,\n\nPlease share Offline CBT license options for ${selectedSchool?.school_name || 'our school'}.`)}`}>Request a CBT license <span aria-hidden="true">↗</span></a></>}
            </section>

            <section className="access-panel" aria-labelledby="plans-title">
              <div>
                <p className="panel-kicker">SEPARATELY LICENSED</p>
                <h2 id="plans-title">Available service plans</h2>
              </div>
              {plans.length ? <div className="service-plan-list">{plans.map((plan) => (
                <article className={plan.id === featuredPlanId ? 'service-plan service-plan-card is-featured' : 'service-plan service-plan-card'} key={plan.id}>
                  {plan.id === featuredPlanId && <span className="service-plan-badge">MOST CAPACITY</span>}
                  <p className="service-plan-category">OFFLINE CBT · {plan.package_type.replaceAll('_', ' ')}</p>
                  <h3>{plan.name}</h3>
                  <p className="service-plan-description">{plan.description || 'Everything your school needs to run secure exams on its local network.'}</p>
                  <strong className="service-plan-price">{money(plan.price_minor, plan.currency)}</strong>
                  <span className="service-plan-price-caption">per {plan.duration_days}-day license period</span>
                  <div className="service-plan-specs"><span><b>{plan.student_capacity}</b> student capacity</span><span><b>{plan.duration_days}</b> days of access</span></div>
                  <a className="service-plan-cta" href={`mailto:edustackedng@gmail.com?subject=${encodeURIComponent(`CBT license request: ${plan.name}`)}&body=${encodeURIComponent(`Hello EDUstacked,\n\nWe are interested in the ${plan.name} Offline CBT license (${plan.student_capacity} students for ${plan.duration_days} days) for ${selectedSchool?.school_name || 'our school'}. Please contact us with the next steps.`)}`}>Ask about this plan <span aria-hidden="true">↗</span></a>
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
