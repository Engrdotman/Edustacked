import { useCallback, useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { apiRequest } from '../services/api.js'

const money = (minor) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 2 }).format(Number(minor || 0) / 100)
const todayISO = () => new Date().toISOString().slice(0, 10)
const minusDays = (count) => { const date = new Date(); date.setDate(date.getDate() - count); return date.toISOString().slice(0, 10) }
const blankBundle = { name: '', credits: '', price_minor: '', display_order: '0', is_active: true }

export default function PlatformSMSPage({ navigate }) {
  const [data, setData] = useState({ overview: {}, schools: [], bundles: [], configuration: {} })
  const [from, setFrom] = useState(minusDays(29))
  const [to, setTo] = useState(todayISO())
  const [search, setSearch] = useState('')
  const [config, setConfig] = useState({ monthly_free_allowance: 50, provider_cost_per_credit_minor: 600, low_balance_threshold: 100 })
  const [bundle, setBundle] = useState(blankBundle)
  const [editingBundle, setEditingBundle] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const query = new URLSearchParams({ from, to })
      if (search.trim()) query.set('q', search.trim())
      const result = await apiRequest(`platform/sms/overview/?${query}`)
      setData(result); setConfig(result.configuration); setError('')
    } catch (requestError) { setError(requestError.message || 'SMS platform analytics could not be loaded.') }
    finally { setLoading(false) }
  }, [from, to, search])

  useEffect(() => { const timer = window.setTimeout(load, 200); return () => window.clearTimeout(timer) }, [load])

  async function saveConfig(event) {
    event.preventDefault(); setWorking(true); setError(''); setSuccess('')
    try { await apiRequest('platform/sms/configuration/', { method: 'PATCH', body: { monthly_free_allowance: Number(config.monthly_free_allowance), provider_cost_per_credit_minor: Number(config.provider_cost_per_credit_minor), low_balance_threshold: Number(config.low_balance_threshold) } }); setSuccess('SMS allowance and cost settings saved. New monthly allowances use the updated amount.'); await load() }
    catch (requestError) { setError(requestError.message || 'SMS settings could not be saved.') }
    finally { setWorking(false) }
  }

  function beginEdit(item) {
    setEditingBundle(item.id)
    setBundle({ name: item.name, credits: String(item.credits), price_minor: String(item.price_minor), display_order: String(item.display_order), is_active: item.is_active })
  }

  async function saveBundle(event) {
    event.preventDefault(); setWorking(true); setError(''); setSuccess('')
    const payload = { ...bundle, credits: Number(bundle.credits), price_minor: Number(bundle.price_minor), display_order: Number(bundle.display_order) }
    try {
      await apiRequest(editingBundle ? `platform/sms/bundles/${editingBundle}/` : 'platform/sms/bundles/', { method: editingBundle ? 'PATCH' : 'POST', body: payload })
      setSuccess(editingBundle ? 'SMS bundle updated.' : 'SMS bundle created.')
      setBundle(blankBundle); setEditingBundle(null); await load()
    } catch (requestError) { setError(requestError.message || 'SMS bundle could not be saved.') }
    finally { setWorking(false) }
  }

  async function toggleBundle(item) {
    setWorking(true); setError(''); setSuccess('')
    try { await apiRequest(`platform/sms/bundles/${item.id}/`, { method: 'PATCH', body: { is_active: !item.is_active } }); setSuccess(`${item.name} bundle ${item.is_active ? 'hidden from schools' : 'made available'}.`); await load() }
    catch (requestError) { setError(requestError.message || 'Bundle availability could not be changed.') }
    finally { setWorking(false) }
  }

  async function openSchool(school) {
    setWorking(true); setError('')
    try { const query = new URLSearchParams({ from, to }); setDetail(await apiRequest(`platform/sms/schools/${school.school_id}/?${query}`)) }
    catch (requestError) { setError(requestError.message || 'School SMS details could not be loaded.') }
    finally { setWorking(false) }
  }

  async function setSuspension(school) {
    const action = school.sending_suspended ? 'resume' : 'suspend'
    const reason = action === 'suspend' ? window.prompt(`Why pause SMS sending for ${school.school_name}?`) : ''
    if (action === 'suspend' && !reason?.trim()) return
    setWorking(true); setError(''); setSuccess('')
    try { const result = await apiRequest(`platform/sms/schools/${school.school_id}/${action}/`, { method: 'POST', body: { reason } }); setSuccess(result.detail); await load(); if (detail?.school_id === school.school_id) await openSchool(school) }
    catch (requestError) { setError(requestError.message || 'SMS sending status could not be updated.') }
    finally { setWorking(false) }
  }

  const values = data.overview || {}
  const metrics = [
    ['SMS segments', values.total_segments_sent, 'Free and paid messages accepted by Termii'],
    ['Free credits used', values.free_credits_consumed, 'Monthly school allowance consumption'],
    ['Purchased credits used', values.paid_credits_consumed, 'Paid credits consumed'],
    ['Delivered', values.delivered_messages, `${values.failed_messages || 0} failed`],
    ['Bundle cash collected', money(values.sales_revenue_minor), 'Verified payment receipts in this date range'],
    ['Provider expenditure', money(values.provider_expenditure_minor), 'Actual charges when reported; otherwise estimated'],
    ['Average provider cost', money(values.average_provider_cost_per_segment_minor), 'Per SMS segment in the selected period'],
    ['Free SMS subsidy', money(values.free_subsidy_cost_minor), 'Estimated cost of included free credits'],
    ['Outstanding credit value', money(values.outstanding_credit_liability_minor), 'Unconsumed bundle value; not counted as profit'],
    ['Realized gross margin', money(values.estimated_gross_profit_minor), 'Consumed paid value minus attributable provider cost'],
    ['Average paid credit value', money(values.average_paid_sale_value_per_credit_minor), 'Recognized paid wallet value per consumed credit'],
  ]

  return <main className="platform-page"><header className="app-topbar"><BrandMark navigate={navigate} /><div className="platform-header"><span>PLATFORM OWNER · SMS</span><button className="text-button" onClick={() => navigate('/platform')}>Back to platform</button></div></header>
    <section className="platform-content platform-sms-content"><p className="eyebrow">EDUstacked · SMS MONITORING</p><h1>SMS management</h1><p className="auth-intro">Review message use, verified bundle income, provider costs, school balances, and sending controls.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}{loading && <p className="loading-message" role="status">Updating SMS overview…</p>}
      <section className="platform-sms-filters"><div className="platform-sms-presets"><button className="secondary-button" onClick={() => { setFrom(todayISO()); setTo(todayISO()) }}>Today</button><button className="secondary-button" onClick={() => { setFrom(minusDays(6)); setTo(todayISO()) }}>7 days</button><button className="secondary-button" onClick={() => { setFrom(minusDays(29)); setTo(todayISO()) }}>30 days</button><button className="secondary-button" onClick={() => { const date = new Date(); setFrom(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-01`); setTo(todayISO()) }}>This month</button><button className="secondary-button" onClick={() => { const date = new Date(); const first = new Date(date.getFullYear(), date.getMonth() - 1, 1); const last = new Date(date.getFullYear(), date.getMonth(), 0); setFrom(first.toISOString().slice(0, 10)); setTo(last.toISOString().slice(0, 10)) }}>Previous month</button></div><label>From<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label><label>To<input type="date" value={to} onChange={(event) => setTo(event.target.value)} /></label></section>
      <div className="platform-metric-grid platform-sms-metrics">{metrics.map(([label, value, note]) => <article className="platform-metric" key={label}><span>{label}</span><strong>{value ?? 0}</strong><small>{note}</small></article>)}</div>
      <section className="platform-user-section"><div className="platform-user-heading"><div><p className="panel-kicker">SCHOOL USAGE</p><h2>SMS activity by school</h2></div><span>{data.schools?.length || 0} schools shown</span></div><input className="platform-sms-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search school name" />
        <div className="platform-sms-table-wrap"><table className="platform-sms-table"><thead><tr><th>School</th><th>Messages</th><th>Segments</th><th>Free used</th><th>Paid used</th><th>Free left</th><th>Prepaid left</th><th>Bundle payments</th><th>Provider cost</th><th>SMS controls</th><th>Last activity</th><th></th></tr></thead><tbody>{data.schools?.map((school) => <tr key={school.school_id}><td>{school.school_name}<small>{school.school_status.replaceAll('_', ' ')}</small></td><td>{school.messages}</td><td>{school.segments}</td><td>{school.free_used}</td><td>{school.paid_used}</td><td>{school.free_remaining}</td><td>{school.purchased_balance}</td><td>{school.bundle_purchases} · {money(school.cash_collected_minor)}</td><td>{money(school.provider_cost_minor)}</td><td>{school.sending_suspended ? 'Paused' : 'Active'}<button className="text-button" disabled={working} onClick={() => setSuspension(school)}>{school.sending_suspended ? 'Resume' : 'Pause'}</button></td><td>{school.last_sms_at ? new Date(school.last_sms_at).toLocaleString() : 'No activity'}</td><td><button className="secondary-button" disabled={working} onClick={() => openSchool(school)}>Details</button></td></tr>)}</tbody></table></div>
        {!data.schools?.length && !loading && <p className="dashboard-empty">No school SMS activity was found for this date range.</p>}
      </section>
      {detail && <section className="platform-user-section platform-sms-detail"><div className="platform-user-heading"><div><p className="panel-kicker">SCHOOL DETAIL</p><h2>{detail.school_name}</h2></div><button className="text-button" onClick={() => setDetail(null)}>Close details</button></div><div className="platform-detail-grid">{[['Free remaining', detail.free_remaining], ['Prepaid balance', detail.purchased_balance], ['Messages', detail.messages], ['Segments', detail.segments], ['Bundle cash', money(detail.cash_collected_minor)], ['Provider cost', money(detail.provider_cost_minor)], ['Paid value consumed', money(detail.paid_sales_value_consumed_minor)], ['Paid cost', money(detail.paid_provider_cost_minor)]].map(([name, value]) => <div key={name}><span>{name}</span><strong>{value}</strong></div>)}</div><h3>Recent bundle purchases</h3><div className="school-sms-history">{detail.purchases?.map((row) => <article key={row.id}><strong>{row.bundle_name} · {row.status}</strong><span>{row.credits.toLocaleString()} credits · {money(row.amount_minor)} · {row.provider} · {new Date(row.created_at).toLocaleString()}</span></article>)}{!detail.purchases?.length && <p className="dashboard-empty">No bundle purchases found.</p>}</div><h3>Monthly free allowance history</h3><div className="school-sms-history">{detail.monthly_allowances?.map((row) => <article key={row.month_start}><strong>{new Date(`${row.month_start}T00:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</strong><span>{row.used_credits} used of {row.allowance_credits} free credits</span></article>)}</div><h3>Recent SMS and delivery status</h3><div className="school-sms-history">{detail.messages?.map((row) => <article key={row.id}><strong>{row.phone} · {row.status}</strong><span>{row.free_credits} free · {row.paid_credits} paid · {row.actual_provider_cost_minor == null ? 'estimated cost' : money(row.actual_provider_cost_minor)}</span><p>{row.message}</p>{row.last_error && <small>{row.last_error}</small>}</article>)}{!detail.messages?.length && <p className="dashboard-empty">No messages found for this school.</p>}</div><h3>Recent wallet transactions</h3><div className="school-sms-history">{detail.transactions?.map((row) => <article key={row.id}><strong>{row.description}</strong><span>{row.credits > 0 ? '+' : ''}{row.credits} credits · {new Date(row.created_at).toLocaleString()}</span></article>)}</div></section>}
      <section className="platform-user-section"><div className="platform-user-heading"><div><p className="panel-kicker">PLATFORM SETTINGS</p><h2>SMS allowance and provider cost</h2></div><span>Provider credentials stay in Railway variables</span></div><form className="platform-sms-settings" onSubmit={saveConfig}><label>Free SMS per school each month<input type="number" min="0" max="10000" required value={config.monthly_free_allowance ?? 50} onChange={(event) => setConfig({ ...config, monthly_free_allowance: event.target.value })} /></label><label>Provider cost per credit (kobo)<input type="number" min="1" required value={config.provider_cost_per_credit_minor ?? 600} onChange={(event) => setConfig({ ...config, provider_cost_per_credit_minor: event.target.value })} /><small>₦{(Number(config.provider_cost_per_credit_minor || 0) / 100).toFixed(2)} per segment</small></label><label>Low balance alert threshold<input type="number" min="0" required value={config.low_balance_threshold ?? 100} onChange={(event) => setConfig({ ...config, low_balance_threshold: event.target.value })} /></label><button className="primary-button" disabled={working}>Save settings</button></form>
        <h3>Prepaid bundles</h3><div className="platform-sms-bundle-list">{data.bundles?.map((item) => <article key={item.id}><div><strong>{item.name}</strong><span>{item.credits.toLocaleString()} credits · {money(item.price_minor)}</span><small>{item.is_active ? 'Available to schools' : 'Hidden from schools'}</small></div><div><button className="secondary-button" disabled={working} onClick={() => beginEdit(item)}>Edit</button><button className="text-button" disabled={working} onClick={() => toggleBundle(item)}>{item.is_active ? 'Deactivate' : 'Activate'}</button></div></article>)}</div>
        <form className="platform-sms-settings platform-sms-bundle-form" onSubmit={saveBundle}><h3>{editingBundle ? 'Edit bundle' : 'Add bundle'}</h3><label>Bundle name<input required maxLength="80" placeholder="e.g. Growth" value={bundle.name} onChange={(event) => setBundle({ ...bundle, name: event.target.value })} /></label><label>Credits<input type="number" min="1" required placeholder="e.g. 2,000" value={bundle.credits} onChange={(event) => setBundle({ ...bundle, credits: event.target.value })} /></label><label>Price (kobo)<input type="number" min="1" required placeholder="e.g. 1,400,000" value={bundle.price_minor} onChange={(event) => setBundle({ ...bundle, price_minor: event.target.value })} /><small>Enter ₦14,000 as 1,400,000 kobo.</small></label><label>Display order<input type="number" min="0" value={bundle.display_order} onChange={(event) => setBundle({ ...bundle, display_order: event.target.value })} /></label><button className="primary-button" disabled={working}>{working ? 'Saving…' : editingBundle ? 'Save bundle' : 'Create bundle'}</button>{editingBundle && <button className="text-button" type="button" onClick={() => { setBundle(blankBundle); setEditingBundle(null) }}>Cancel editing</button>}</form>
      </section>
    </section>
  </main>
}
