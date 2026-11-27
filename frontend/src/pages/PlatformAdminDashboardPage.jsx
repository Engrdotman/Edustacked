import { useCallback, useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { apiRequest } from '../services/api.js'

function money(amountMinor, currency) {
  try {
    return new Intl.NumberFormat('en-NG', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(amountMinor || 0) / 100)
  } catch {
    return `${currency} ${(Number(amountMinor || 0) / 100).toFixed(2)}`
  }
}

export default function PlatformAdminDashboardPage({ navigate }) {
  const { user } = useAuth()
  const [data, setData] = useState({ results: [], overview: {} })
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [pageNumber, setPageNumber] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [workingId, setWorkingId] = useState(null)
  const [actionId, setActionId] = useState(null)
  const [action, setAction] = useState('suspend')
  const [reason, setReason] = useState('')
  const [feedback, setFeedback] = useState({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const query = new URLSearchParams({ page: String(pageNumber) })
      if (search.trim()) query.set('q', search.trim())
      if (filter) query.set('status', filter)
      setData(await apiRequest(`schools/platform/users/?${query}`))
      setError('')
    } catch (e) {
      setError(e.message || 'Platform accounts could not be loaded. Please refresh and try again.')
    } finally {
      setLoading(false)
    }
  }, [search, filter, pageNumber])

  useEffect(() => {
    const timer = window.setTimeout(load, 220)
    return () => window.clearTimeout(timer)
  }, [load])

  function beginAction(account, nextAction) {
    setActionId(account.id)
    setAction(nextAction)
    setReason('')
    setFeedback((current) => ({ ...current, [account.id]: '' }))
  }

  async function submitAction(account) {
    if (!reason.trim()) {
      setFeedback((current) => ({ ...current, [account.id]: 'Add a short reason before continuing.' }))
      return
    }
    setWorkingId(account.id)
    setFeedback((current) => ({ ...current, [account.id]: '' }))
    try {
      const result = await apiRequest(`schools/platform/users/${account.id}/${action}/`, { method: 'POST', body: { reason: reason.trim() } })
      setFeedback((current) => ({ ...current, [account.id]: result.detail || 'Account access updated.' }))
      setActionId(null)
      setReason('')
      await load()
    } catch (e) {
      setFeedback((current) => ({ ...current, [account.id]: e.message || 'The account could not be updated. Please try again.' }))
    } finally {
      setWorkingId(null)
    }
  }

  const overview = data.overview || {}
  const cards = [
    ['Schools', overview.schools_total ?? '—', `${overview.schools_verified ?? 0} verified`],
    ['Accounts', overview.users_total ?? '—', `${overview.users_active ?? 0} active · ${overview.users_inactive ?? 0} inactive`],
    ['Awaiting verification', overview.schools_pending ?? '—', `${overview.schools_suspended ?? 0} suspended schools`],
    ['Credit purchases', overview.credit_purchase_count ?? '—', `${overview.schools_with_credit_purchases ?? 0} schools have paid`],
  ]

  return <main className="platform-page"><header className="app-topbar"><BrandMark navigate={navigate} /><div className="platform-header"><span>PLATFORM ADMINISTRATION</span><button className="text-button" onClick={() => navigate('/app')}>School workspace</button></div></header>
    <section className="platform-content platform-admin-content">
      <p className="eyebrow">EDUstacked · PLATFORM OWNER</p><h1>Platform overview</h1>
      <p className="auth-intro">Monitor school access, accounts, and verified payments across EDUstacked.</p>
      <div className="platform-dashboard-actions"><button className="primary-button" onClick={() => navigate('/platform/schools')}>Review school registrations</button><button className="secondary-button" onClick={() => navigate('/platform/sms')}>SMS, credits &amp; seat pricing</button><button className="secondary-button" onClick={load} disabled={loading}>Refresh overview</button></div>

      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="platform-metric-grid">{cards.map(([label, value, note]) => <article className="platform-metric" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div>

      <section className="platform-revenue-panel"><div><p className="panel-kicker">VERIFIED REVENUE</p><h2>Successful credit purchases</h2><p>Only completed payments with a verification timestamp are counted. EDUstacked currently sells one-time report-card credit packs; this is purchase activity, not a recurring subscription.</p></div>
        {overview.verified_revenue?.length ? <div className="platform-revenue-values">{overview.verified_revenue.map((row) => <article key={row.currency}><span>{row.currency} received</span><strong>{money(row.amount_minor, row.currency)}</strong><small>{row.payment_count} verified payment{row.payment_count === 1 ? '' : 's'}</small></article>)}</div> : <p className="dashboard-empty">No verified credit purchases have been recorded yet.</p>}
        {overview.top_credit_purchasers?.length > 0 && <div className="platform-purchaser-list"><h3>Schools with the most verified purchases</h3>{overview.top_credit_purchasers.map((school) => <button key={`${school.school_id}-${school.currency}`} onClick={() => navigate(`/platform/schools/${school.school_id}`)}><span>{school.school__name}<small>{school.payment_count} payment{school.payment_count === 1 ? '' : 's'} · {school.currency}</small></span><strong>{money(school.amount_minor, school.currency)}</strong></button>)}</div>}
      </section>

      <section className="platform-user-section"><div className="platform-user-heading"><div><p className="panel-kicker">PLATFORM ACCOUNTS</p><h2>Users and school access</h2></div><span>{data.count ?? 0} accounts</span></div>
        <div className="platform-filters"><input aria-label="Search platform accounts" placeholder="Search name, email, or username" value={search} onChange={(e) => { setSearch(e.target.value); setPageNumber(1) }} /><select aria-label="Filter accounts by status" value={filter} onChange={(e) => { setFilter(e.target.value); setPageNumber(1) }}><option value="">All account statuses</option><option value="active">Active accounts</option><option value="inactive">Inactive accounts</option></select></div>
        <div className="platform-user-list">{(data.results || []).map((account) => <article className="platform-user-card" key={account.id}>
          <div className="platform-user-main"><div><h3>{account.full_name || account.email || `Account ${account.id}`}</h3><p>{account.email || 'No email on file'}{account.is_superuser ? ' · Platform administrator' : ''}</p></div><span className={`platform-user-status ${account.is_active ? 'is-active' : 'is-inactive'}`}>{account.is_active ? 'Active' : 'Inactive'}</span></div>
          <div className="platform-user-meta"><span>Joined {account.created_at ? new Date(account.created_at).toLocaleDateString() : '—'}</span><span>{account.memberships?.length || 0} school link{account.memberships?.length === 1 ? '' : 's'}</span></div>
          {account.memberships?.length > 0 && <div className="platform-memberships">{account.memberships.map((membership) => <span key={membership.school_id}>{membership.school_name} · {membership.role.replaceAll('_', ' ')}{!membership.is_active ? ' · access inactive' : ''}</span>)}</div>}
          {account.latest_platform_action && <p className="platform-last-action">Last platform action: {account.latest_platform_action.action} · {account.latest_platform_action.actor_email}{account.latest_platform_action.reason ? ` · ${account.latest_platform_action.reason}` : ''}</p>}
          {!account.is_superuser && <div className="platform-actions">{account.is_active ? <button className="secondary-button" disabled={workingId === account.id || account.id === user?.id} onClick={() => beginAction(account, 'suspend')}>Suspend account</button> : account.can_reactivate ? <button className="secondary-button" disabled={workingId === account.id} onClick={() => beginAction(account, 'reactivate')}>Reactivate account</button> : <span className="platform-last-action">This account is inactive outside platform suspension controls.</span>}</div>}
          {actionId === account.id && <div className="platform-user-action-form"><label htmlFor={`platform-reason-${account.id}`}>{action === 'suspend' ? 'Why is this account being suspended?' : 'Why is this account being reactivated?'}</label><textarea id={`platform-reason-${account.id}`} rows="2" maxLength="2000" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Add a short note for the platform audit history" /><div className="platform-actions"><button className="primary-button" disabled={workingId === account.id} onClick={() => submitAction(account)}>{workingId === account.id ? 'Saving…' : action === 'suspend' ? 'Confirm suspension' : 'Confirm reactivation'}</button><button className="text-button" disabled={workingId === account.id} onClick={() => setActionId(null)}>Cancel</button></div></div>}
          {feedback[account.id] && <p className={feedback[account.id].toLowerCase().includes('success') || feedback[account.id].toLowerCase().includes('reactivated') ? 'form-success' : 'form-error'} role="status">{feedback[account.id]}</p>}
        </article>)}
          {!data.results?.length && !loading && !error && <p className="dashboard-empty">No accounts match these filters.</p>}
          {loading && <p className="dashboard-empty" role="status">Loading platform accounts…</p>}
        </div>
        <div className="platform-pagination"><button className="secondary-button" disabled={!data.previous || loading} onClick={() => setPageNumber((n) => Math.max(1, n - 1))}>Previous</button><span>Page {pageNumber}</span><button className="secondary-button" disabled={!data.next || loading} onClick={() => setPageNumber((n) => n + 1)}>Next</button></div>
      </section>
    </section>
  </main>
}
