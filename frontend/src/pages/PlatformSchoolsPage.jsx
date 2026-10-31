import { useCallback, useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { apiRequest } from '../services/api.js'

const statuses = ['pending_verification', 'under_review', 'verified', 'rejected', 'suspended']

export default function PlatformSchoolsPage({ navigate }) {
  const [page, setPage] = useState({ results: [] })
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [pageNumber, setPageNumber] = useState(1)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { const query = new URLSearchParams({ page: String(pageNumber) }); if (search) query.set('q', search); if (filter) query.set('status', filter); setPage(await apiRequest(`schools/platform/schools/?${query}`)); setError('') }
    catch (e) { setError(e.message || 'School records could not be loaded.') }
  }, [search, filter, pageNumber])
  useEffect(() => { load() }, [load])
  async function act(school, action) {
    const reason = ['reject', 'suspend', 'reactivate'].includes(action) ? window.prompt(`Reason to ${action} ${school.name}:`) : ''
    if (['reject', 'suspend', 'reactivate'].includes(action) && !reason?.trim()) return
    setBusy(true)
    try { await apiRequest(`schools/platform/schools/${school.id}/${action}/`, { method: 'POST', body: { reason: reason || '' } }); await load() }
    catch (e) { setError(e.message || `Could not ${action} this school.`) }
    finally { setBusy(false) }
  }
  return <main className="platform-page"><header className="app-topbar"><BrandMark /><div className="platform-header"><span>PLATFORM ADMINISTRATION</span><button className="text-button" onClick={() => navigate('/app')}>School workspace</button></div></header><section className="platform-content"><p className="eyebrow">EDUstacked · PLATFORM OWNER</p><h1>School registrations</h1><p className="auth-intro">Review school verification and access status across the platform.</p>
    <div className="platform-filters"><input aria-label="Search schools" placeholder="Search name, email, state, or LGA" value={search} onChange={(e) => { setSearch(e.target.value); setPageNumber(1) }} /><select aria-label="Filter by verification status" value={filter} onChange={(e) => { setFilter(e.target.value); setPageNumber(1) }}><option value="">All verification statuses</option>{statuses.map((item) => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select><button className="secondary-button" onClick={load}>Refresh</button></div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="platform-school-list">{(page.results || []).map((school) => <article className="platform-school-card" key={school.id}><div className="platform-school-heading"><div><h2>{school.name}</h2><p>{[school.school_type, school.state, school.local_government_area].filter(Boolean).join(' · ')}</p></div><span className={`school-status-pill status-${school.verification_status}`}>{school.verification_status.replaceAll('_', ' ')}</span></div><div className="platform-school-metrics"><span>Registered {new Date(school.registration_date).toLocaleDateString()}</span><span>{school.student_count} students</span><span>{school.active_staff_count} active staff</span><span>Setup {school.onboarding?.current_step || 1}/5</span></div>{school.verification_reason && <p className="platform-reason">{school.verification_reason}</p>}<div className="platform-actions"><button className="text-button" disabled={busy} onClick={() => navigate(`/platform/schools/${school.id}`)}>Details &amp; audit</button>{school.verification_status === 'pending_verification' && <button className="secondary-button" disabled={busy} onClick={() => act(school, 'review')}>Start review</button>}{['pending_verification', 'under_review'].includes(school.verification_status) && <><button className="primary-button" disabled={busy} onClick={() => act(school, 'verify')}>Verify</button><button className="secondary-button" disabled={busy} onClick={() => act(school, 'reject')}>Reject</button></>}{school.verification_status !== 'suspended' && <button className="secondary-button" disabled={busy} onClick={() => act(school, 'suspend')}>Suspend</button>}{school.verification_status === 'suspended' && <button className="secondary-button" disabled={busy} onClick={() => act(school, 'reactivate')}>Reactivate</button>}</div></article>)}</div>
    <div className="platform-pagination"><button className="secondary-button" disabled={!page.previous} onClick={() => setPageNumber((n) => Math.max(1, n - 1))}>Previous</button><span>Page {pageNumber}</span><button className="secondary-button" disabled={!page.next} onClick={() => setPageNumber((n) => n + 1)}>Next</button></div>
    {!page.results?.length && !error && <p className="dashboard-empty">No school registrations match this view.</p>}
  </section></main>
}
