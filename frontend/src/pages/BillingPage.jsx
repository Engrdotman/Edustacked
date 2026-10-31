import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'

const canManage = (role) => ['platform_superadmin', 'school_owner', 'school_admin', 'accountant'].includes(role)
const naira = (minor) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format((minor || 0) / 100)

export default function BillingPage({ navigate }) {
  const { selectedSchool, user } = useAuth()
  const [balance, setBalance] = useState(null)
  const [packages, setPackages] = useState([])
  const [payments, setPayments] = useState([])
  const [transactions, setTransactions] = useState([])
  const [payment, setPayment] = useState(null)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const reference = new URLSearchParams(window.location.search).get('reference')
  const mayPurchase = canManage(selectedSchool?.role)

  const refresh = useCallback(async () => {
    const [overview, available, paymentRows, ledger] = await Promise.all([
      apiRequest('billing/credits/'), apiRequest('billing/packages/'),
      apiRequest('billing/payments/'), apiRequest('billing/transactions/'),
    ])
    setBalance(overview.balance)
    setPackages(available)
    setPayments(paymentRows.results || paymentRows)
    setTransactions(ledger.results || ledger)
  }, [])

  useEffect(() => {
    refresh().catch((requestError) => setError(requestError.message))
  }, [refresh])

  useEffect(() => {
    if (!reference) return
    setWorking(true)
    apiRequest(`billing/payments/${encodeURIComponent(reference)}/`, { method: 'POST', body: {} })
      .then(async (result) => { setPayment(result); setBalance(result.balance); await refresh() })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setWorking(false))
  }, [reference])

  async function beginPurchase(packageId) {
    setError('')
    setWorking(true)
    try {
      const checkout = await apiRequest('billing/purchases/', { method: 'POST', body: { package: packageId } })
      window.location.assign(checkout.authorization_url)
    } catch (requestError) {
      setError(requestError.message)
      setWorking(false)
    }
  }

  async function checkPayment() {
    if (!reference) return
    setWorking(true)
    setError('')
    try {
      const result = await apiRequest(`billing/payments/${encodeURIComponent(reference)}/`, { method: 'POST', body: {} })
      setPayment(result)
      await refresh()
    } catch (requestError) { setError(requestError.message) }
    finally { setWorking(false) }
  }

  return <main className="app-page">
    <header className="app-topbar"><BrandMark /><button className="text-button" type="button" onClick={() => navigate('/app')}>Back to dashboard</button></header>
    <section className="app-content billing-content">
      <p className="eyebrow">SCHOOL BILLING</p>
      <h1 className="app-heading">Report-card<br /><em>credits.</em></h1>
      <p className="intro">{selectedSchool?.school_name} · signed in as {user?.first_name || user?.email}</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      {reference && <section className="billing-panel" aria-live="polite">
        <h2>Payment status: {payment?.status || (working ? 'checking' : 'pending')}</h2>
        <p>{payment?.status === 'success' ? `${payment.credits} credits were verified and added.` : payment?.status === 'failed' ? 'This payment was not completed. No credits were added.' : 'Checkout redirects do not confirm payment. We verify with Paystack before adding any credits.'}</p>
        {payment?.status !== 'success' && <button className="secondary-button" type="button" onClick={checkPayment} disabled={working}>Verify payment</button>}
      </section>}
      <section className="billing-overview">
        <div><span>AVAILABLE REPORT-CARD CREDITS</span><strong>{balance ?? '—'}</strong></div>
        <p>One credit is used for a student's first finalized report card in a school, academic session, and term. Drafts, previews, downloads, reprints, and correction revisions do not use another credit.</p>
      </section>
      <section className="billing-panel"><h2>Credit packages</h2>
        {packages.length ? <div className="billing-packages">{packages.map((item) => <article key={item.id} className="billing-package"><h3>{item.name}</h3><strong>{item.credits} credits</strong><p className="billing-package-total">{naira(item.price_minor)} total</p><p className="billing-package-unit">{naira(Math.round(item.price_minor / item.credits))} per credit · about {item.credits} finalized report cards</p>{item.description && <p>{item.description}</p>}{mayPurchase && <button className="primary-button" type="button" disabled={working} onClick={() => beginPurchase(item.id)}>Purchase</button>}</article>)}</div> : <p>No active packages are available yet. A platform administrator can configure packages.</p>}
      </section>
      <section className="billing-panel"><h2>Recent payments</h2>{payments.length ? <div className="billing-history">{payments.slice(0, 8).map((item) => <div key={item.reference}><strong>{item.package_name} · {item.credits} credits</strong><span>{naira(item.amount_minor)} · {item.status} · {new Date(item.created_at).toLocaleDateString()}</span></div>)}</div> : <p>No purchases yet.</p>}</section>
      <section className="billing-panel"><h2>Credit activity</h2>{transactions.length ? <div className="billing-history">{transactions.slice(0, 10).map((item) => <div key={item.id}><strong>{item.description}</strong><span>{item.amount > 0 ? '+' : ''}{item.amount} credits · {new Date(item.created_at).toLocaleDateString()}</span></div>)}</div> : <p>No credit activity yet.</p>}</section>
      <p className="billing-note">Payment status and credit balance are confirmed by the server. Paystack checkout requires the school account email and a configured server-side integration.</p>
    </section>
  </main>
}
