import { useCallback, useEffect, useMemo, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { apiRequest } from '../services/api.js'

const money = (minor) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 2 }).format(Number(minor || 0) / 100)
const asError = (error) => error?.message || 'We could not complete that SMS request. Please try again.'

export default function SchoolSMSPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const [data, setData] = useState(null)
  const [recipients, setRecipients] = useState('')
  const [message, setMessage] = useState('')
  const [provider, setProvider] = useState('flutterwave')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try { setData(await apiRequest('sms/overview/')); setError('') }
    catch (requestError) { setError(asError(requestError)) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const reference = params.get('reference')
    if (!reference) return
    let active = true
    setWorking(true)
    apiRequest(`sms/purchases/${encodeURIComponent(reference)}/verify/?transaction_id=${encodeURIComponent(params.get('transaction_id') || params.get('transaction') || '')}`, { method: 'POST', body: {} })
      .then((result) => { if (active) { setSuccess(result.status === 'success' ? `${result.credits} SMS credits were added to your school wallet.` : 'Payment is still being confirmed. Refresh this page in a moment.'); return load() } })
      .catch((requestError) => active && setError(asError(requestError)))
      .finally(() => { if (active) { setWorking(false); window.history.replaceState({}, '', `${window.location.pathname}`) } })
    return () => { active = false }
  }, [load])

  const available = useMemo(() => Number(data?.monthly_allowance?.remaining_credits || 0) + Number(data?.wallet?.purchased_balance || 0), [data])

  async function sendSMS(event) {
    event.preventDefault(); setWorking(true); setError(''); setSuccess('')
    const phones = recipients.split(/[\n,;]+/).map((phone) => phone.trim()).filter(Boolean)
    try {
      const result = await apiRequest('sms/send/', { method: 'POST', headers: { 'Idempotency-Key': globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}` }, body: { recipients: phones, message } })
      const rejected = result.messages?.filter((row) => row.status === 'failed').length || 0
      setSuccess(`${result.recipient_count} recipient(s) processed using ${result.total_segments} SMS segment(s). ${result.free_credits} free and ${result.paid_credits} purchased credits used.${rejected ? ` ${rejected} message(s) were rejected and credited back.` : ''}`)
      setRecipients(''); setMessage(''); await load()
    } catch (requestError) { setError(asError(requestError)) }
    finally { setWorking(false) }
  }

  async function purchase(bundle) {
    setWorking(true); setError(''); setSuccess('')
    try {
      const result = await apiRequest('sms/purchases/', { method: 'POST', body: { bundle: bundle.id, provider } })
      if (!result.authorization_url) throw new Error('The payment provider did not return a checkout link. Please try again or contact support.')
      window.location.assign(result.authorization_url)
    } catch (requestError) { setError(asError(requestError)); setWorking(false) }
  }

  const allowance = data?.monthly_allowance || {}
  const usagePercent = allowance.allowance_credits ? Math.min(100, Number(allowance.used_credits || 0) * 100 / allowance.allowance_credits) : 0

  return <main className="app-page"><header className="app-topbar"><BrandMark navigate={navigate} /><button className="text-button" onClick={() => navigate('/app')}>Back to dashboard</button></header>
    <section className="app-content school-sms-page"><p className="eyebrow">{selectedSchool?.school_name} · SMS MANAGEMENT</p><h1 className="app-heading">School <em>messaging</em></h1><p className="intro">Send school updates to families, track delivery, and add prepaid credits when needed.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}{loading && <p className="loading-message" role="status">Loading SMS wallet…</p>}
      {data && <>
        {!data.configured && <div className="school-sms-notice" role="status">SMS sending is not configured yet. Contact EDUstacked to finish the Termii setup.</div>}
        {data.wallet?.sending_suspended && <div className="form-error" role="status">SMS sending is paused for this school. {data.wallet.suspension_reason || 'Contact EDUstacked support.'}</div>}
        {!data.wallet?.sending_suspended && data.wallet?.purchased_balance > 0 && data.wallet?.purchased_balance <= data.wallet?.low_balance_threshold && <p className="school-sms-notice" role="status">Your prepaid SMS balance is running low ({data.wallet.purchased_balance} credit(s) left). Consider topping up.</p>}
        {!data.wallet?.sending_suspended && data.wallet?.purchased_balance === 0 && data.monthly_allowance?.remaining_credits === 0 && <p className="form-error" role="status">No SMS credits are available. Purchase a bundle to send more messages.</p>}
        <div className="school-sms-metrics">
          <article><span>Monthly free SMS</span><strong>{allowance.remaining_credits ?? 0} / {allowance.allowance_credits ?? 50}</strong><div className="sms-progress"><i style={{ width: `${usagePercent}%` }} /></div><small>{allowance.used_credits ?? 0} used this month · resets monthly</small></article>
          <article><span>Purchased credits</span><strong>{data.wallet?.purchased_balance ?? 0}</strong><small>Available balance · never expires</small></article>
          <article><span>SMS segments this month</span><strong>{data.monthly_usage?.segments ?? 0}</strong><small>{data.monthly_usage?.delivered ?? 0} delivered · {data.monthly_usage?.failed ?? 0} failed</small></article>
          <article><span>Available to send</span><strong>{available}</strong><small>Free allowance is used before purchased credits</small></article>
        </div>
        {data.monthly_allowance?.remaining_credits <= 10 && data.monthly_allowance?.remaining_credits > 0 && <p className="school-sms-notice">You have {data.monthly_allowance.remaining_credits} free SMS credit(s) left this month.</p>}
        {data.monthly_allowance?.remaining_credits === 0 && <p className="school-sms-notice">Your monthly free SMS allowance is used. Purchased credits will be used for the next message.</p>}
        <div className="school-sms-columns">
          <section className="report-card-panel"><p className="panel-kicker">NEW MESSAGE</p><h2>Send an SMS</h2><form className="school-sms-form" onSubmit={sendSMS}>
            <label>Phone numbers<textarea required rows="4" maxLength="6400" placeholder="Enter one number per line, or separate numbers with commas. Example: 08031234567" value={recipients} onChange={(event) => setRecipients(event.target.value)} /></label>
            <label>Message<textarea required rows="5" maxLength="5000" placeholder="Write the message to send to parents or staff." value={message} onChange={(event) => setMessage(event.target.value)} /><small>{message.length} / 5,000 characters. Long messages may use more than one credit per recipient.</small></label>
            <button className="primary-button" type="submit" disabled={working || !data.configured || data.wallet?.sending_suspended}>{working ? 'Sending…' : 'Send message'}</button>
          </form></section>
          <section className="report-card-panel"><p className="panel-kicker">PREPAID BUNDLES</p><h2>Top up SMS credits</h2>{data.can_manage ? <><label className="sms-provider-choice">Payment method<select value={provider} onChange={(event) => setProvider(event.target.value)}><option value="flutterwave">Flutterwave</option><option value="bachs">Bachs</option><option value="paystack">Paystack</option></select></label><div className="school-sms-bundles">{data.bundles?.map((bundle) => <article key={bundle.id}><div><h3>{bundle.name}</h3><strong>{bundle.credits.toLocaleString()} credits</strong></div><p>{money(bundle.price_minor)} total · {money(bundle.unit_price_minor)} each</p><button className="secondary-button" disabled={working} onClick={() => purchase(bundle)}>Buy {bundle.name}</button></article>)}</div></> : <p className="dashboard-empty">Ask a school owner or administrator to purchase SMS credits.</p>}</section>
        </div>
        {data.can_manage && <section className="report-card-panel"><h2>Wallet activity</h2><div className="school-sms-history">{data.transactions?.map((row) => <article key={row.id}><strong>{row.description}</strong><span>{row.credits > 0 ? '+' : ''}{row.credits} credits · {new Date(row.created_at).toLocaleString()}</span></article>)}{!data.transactions?.length && <p className="dashboard-empty">SMS purchases and usage will appear here.</p>}</div></section>}
        <section className="report-card-panel"><h2>Recent messages</h2><div className="school-sms-history">{data.recent_messages?.map((row) => <article key={row.id}><strong>{row.phone} · {row.status.replaceAll('_', ' ')}</strong><span>{row.segments} segment(s) · {row.free_credits} free · {row.paid_credits} purchased · {new Date(row.created_at).toLocaleString()}</span><p>{row.message}</p>{row.last_error && <small>{row.last_error}</small>}</article>)}{!data.recent_messages?.length && <p className="dashboard-empty">No SMS messages have been sent yet.</p>}</div></section>
      </>}
    </section>
  </main>
}
