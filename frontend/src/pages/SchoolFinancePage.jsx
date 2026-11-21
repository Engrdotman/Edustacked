import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'
import { academicList, apiBlobRequest, apiRequest } from '../services/api.js'

const money = (minor = 0) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 2 }).format((Number(minor) || 0) / 100)
const emptySchedule = { academic_session: '', term: '', class_level: '', class_arm: '', category: '', description: '', amount: '', due_date: '' }
const emptyConnection = { provider: 'flutterwave', bank_code: '', bank_name: '', account_number: '', account_type: '', business_mobile: '' }

export default function SchoolFinancePage({ navigate }) {
  const { selectedSchool, user } = useAuth()
  const [overview, setOverview] = useState(null)
  const [settings, setSettings] = useState(null)
  const [sessions, setSessions] = useState([])
  const [terms, setTerms] = useState([])
  const [classes, setClasses] = useState([])
  const [arms, setArms] = useState([])
  const [students, setStudents] = useState([])
  const [schedules, setSchedules] = useState([])
  const [charges, setCharges] = useState([])
  const [payments, setPayments] = useState([])
  const [banks, setBanks] = useState([])
  const [selectedCharge, setSelectedCharge] = useState('')
  const [paymentForm, setPaymentForm] = useState({ amount: '', method: 'cash', payer_email: '', description: '' })
  const [scheduleForm, setScheduleForm] = useState(emptySchedule)
  const [connection, setConnection] = useState(emptyConnection)
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ session: '', term: '', class_level: '', method: '', channel: '', status: '', date_from: '', date_to: '', search: '' })
  const [filterTerms, setFilterTerms] = useState([])
  const [chargePage, setChargePage] = useState(1)
  const [chargeCount, setChargeCount] = useState(0)
  const [paymentPage, setPaymentPage] = useState(1)
  const [paymentCount, setPaymentCount] = useState(0)
  const [reversalTarget, setReversalTarget] = useState('')
  const [reversalForm, setReversalForm] = useState({ amount: '', reason: '', external_reference: '' })
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = useCallback(async () => {
    const [summary, feeSettings, sessionRows, classRows, studentRows, scheduleRows, chargeRows, paymentRows] = await Promise.all([
      apiRequest('school-fees/overview/'), apiRequest('school-fees/settings/'),
      academicList('academic-sessions/'), academicList('classes/'),
      apiRequest('students/?status=active&page=1&page_size=200'),
      apiRequest('school-fees/schedules/'), apiRequest('school-fees/charges/?page=1&page_size=200'), apiRequest('school-fees/payments/?page=1&page_size=50'),
    ])
    setOverview(summary); setSettings(feeSettings); setSessions(sessionRows); setClasses(classRows)
    setStudents(studentRows.results || studentRows); setSchedules(scheduleRows)
    setCharges(chargeRows.results || chargeRows); setChargeCount(chargeRows.count ?? (chargeRows.results || chargeRows).length); setChargePage(1)
    setPayments(paymentRows.results || paymentRows); setPaymentCount(paymentRows.count ?? (paymentRows.results || paymentRows).length); setPaymentPage(1)
    setConnection((current) => ({ ...current, provider: feeSettings.provider || current.provider }))
  }, [])

  useEffect(() => { load().catch((e) => setError(e.message || 'School finance could not be loaded.')).finally(() => setLoading(false)) }, [load])

  useEffect(() => {
    if (!scheduleForm.academic_session) { setTerms([]); return }
    academicList(`terms/?academic_session=${scheduleForm.academic_session}`).then(setTerms).catch((e) => setError(e.message))
  }, [scheduleForm.academic_session])

  useEffect(() => {
    if (!scheduleForm.class_level) { setArms([]); return }
    academicList(`classes/${scheduleForm.class_level}/arms/`).then(setArms).catch((e) => setError(e.message))
  }, [scheduleForm.class_level])

  useEffect(() => {
    if (!filters.session) { setFilterTerms([]); return }
    academicList(`terms/?academic_session=${filters.session}`).then(setFilterTerms).catch((e) => setError(e.message))
  }, [filters.session])

  useEffect(() => {
    let active = true
    if (!connection.provider) return
    apiRequest(`school-fees/settings/banks/?provider=${connection.provider}`)
      .then((rows) => { if (active) setBanks(rows) })
      .catch((e) => { if (active) setBanks([]); if (active && connection.bank_code) setError(e.message) })
    return () => { active = false }
  }, [connection.provider])

  const selected = charges.find((charge) => String(charge.id) === String(selectedCharge))
  const visibleCharges = useMemo(() => {
    const query = search.trim().toLowerCase()
    return charges.filter((row) => !query || row.student_name.toLowerCase().includes(query) || row.admission_number.toLowerCase().includes(query) || row.category.toLowerCase().includes(query))
  }, [charges, search])

  async function applyFinanceFilters(event) {
    event.preventDefault(); setBusy(true); setError('')
    const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== '').map(([key, value]) => [key, value]))
    const academicQuery = new URLSearchParams(Object.entries(filters).filter(([key, value]) => ['session', 'term', 'class_level', 'class_arm'].includes(key) && value !== '').map(([key, value]) => [key, value]))
    try {
      const [summary, chargeRows, paymentRows] = await Promise.all([
        apiRequest(`school-fees/overview/?${academicQuery.toString()}`),
        apiRequest(`school-fees/charges/?${new URLSearchParams({ ...Object.fromEntries(academicQuery), search: filters.search, page: '1', page_size: '200' })}`),
        apiRequest(`school-fees/payments/?${new URLSearchParams({ ...Object.fromEntries(query), page: '1', page_size: '50' })}`),
      ])
      setOverview(summary); setCharges(chargeRows.results || chargeRows); setChargeCount(chargeRows.count ?? (chargeRows.results || chargeRows).length); setChargePage(1)
      setPayments(paymentRows.results || paymentRows); setPaymentCount(paymentRows.count ?? (paymentRows.results || paymentRows).length); setPaymentPage(1)
      setSearch(filters.search)
      flashSuccess('Finance filters applied. Summary figures follow the selected academic scope; payment history also uses your transaction filters.')
    } catch (e) { flashError(e.message || 'The finance filters could not be applied.') }
    finally { setBusy(false) }
  }

  async function loadFeePage(page) {
    const query = new URLSearchParams({ page: String(page), page_size: '200' })
    for (const key of ['session', 'term', 'class_level', 'class_arm']) if (filters[key]) query.set(key, filters[key])
    if (filters.search) query.set('search', filters.search)
    try {
      const rows = await apiRequest(`school-fees/charges/?${query.toString()}`)
      setCharges(rows.results || rows); setChargeCount(rows.count ?? (rows.results || rows).length); setChargePage(page)
    } catch (e) { flashError(e.message || 'Fee records could not be loaded.') }
  }

  async function loadPaymentPage(page) {
    const query = new URLSearchParams({ page: String(page), page_size: '50' })
    for (const [key, value] of Object.entries(filters)) if (value && ['session', 'term', 'class_level', 'method', 'channel', 'status', 'date_from', 'date_to', 'search'].includes(key)) query.set(key, value)
    try {
      const rows = await apiRequest(`school-fees/payments/?${query.toString()}`)
      setPayments(rows.results || rows); setPaymentCount(rows.count ?? (rows.results || rows).length); setPaymentPage(page)
    } catch (e) { flashError(e.message || 'Payment history could not be loaded.') }
  }

  function clearFinanceFilters() {
    const cleared = { session: '', term: '', class_level: '', method: '', channel: '', status: '', date_from: '', date_to: '', search: '' }
    setFilters(cleared); setSearch(''); setOverview(null); setLoading(true)
    load().catch((e) => flashError(e.message || 'Finance records could not be refreshed.')).finally(() => setLoading(false))
  }

  function flashError(message) { setSuccess(''); setError(message) }
  function flashSuccess(message) { setError(''); setSuccess(message) }

  async function createSchedule(event) {
    event.preventDefault(); setBusy(true); setError(''); setSuccess('')
    try {
      const saved = await apiRequest('school-fees/schedules/', { method: 'POST', body: {
        ...scheduleForm, class_arm: scheduleForm.class_arm || null,
        amount_minor: Math.round(Number(scheduleForm.amount) * 100),
      } })
      flashSuccess(saved.message || 'Fee schedule saved.')
      setScheduleForm({ ...emptySchedule, academic_session: scheduleForm.academic_session, term: scheduleForm.term, class_level: scheduleForm.class_level })
      await load()
    } catch (e) { flashError(e.message || 'Could not save the fee schedule.') }
    finally { setBusy(false) }
  }

  async function recordPayment(event) {
    event.preventDefault()
    if (!selected) { flashError('Select the student fee you are receiving payment for.'); return }
    setBusy(true); setError(''); setSuccess('')
    try {
      const saved = await apiRequest('school-fees/payments/manual/', { method: 'POST', body: {
        amount_minor: Math.round(Number(paymentForm.amount) * 100), method: paymentForm.method,
        payer_email: paymentForm.payer_email, description: paymentForm.description,
        allocations: [{ fee_charge_id: selected.id, amount_minor: Math.round(Number(paymentForm.amount) * 100) }],
      } })
      setSelectedCharge(''); setPaymentForm({ amount: '', method: 'cash', payer_email: '', description: '' })
      await load()
      flashSuccess(`${saved.detail} Receipt reference: ${saved.reference}.`)
      await downloadReceipt(saved.reference)
    } catch (e) { flashError(e.message || 'Could not record this payment.') }
    finally { setBusy(false) }
  }

  async function downloadReceipt(reference) {
    try {
      const blob = await apiBlobRequest(`school-fees/payments/${encodeURIComponent(reference)}/receipt/`)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `fee-receipt-${reference}.pdf`; anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { flashError(e.message || 'The receipt could not be downloaded.') }
  }

  async function loadBankList(provider) {
    setConnection((current) => ({ ...current, provider, bank_code: '', bank_name: '' }))
  }

  async function connectBank(event) {
    event.preventDefault(); setBusy(true); setError(''); setSuccess('')
    try {
      const result = await apiRequest('school-fees/settings/connect/', { method: 'POST', body: connection })
      await load(); flashSuccess(result.detail)
    } catch (e) { flashError(e.message || 'The bank account could not be verified.') }
    finally { setBusy(false) }
  }

  async function saveSettings(values) {
    setBusy(true); setError(''); setSuccess('')
    try { await apiRequest('school-fees/settings/', { method: 'PATCH', body: values }); await load(); flashSuccess('Finance settings saved.') }
    catch (e) { flashError(e.message || 'Finance settings could not be saved.') }
    finally { setBusy(false) }
  }

  async function recordReversal(event, payment) {
    event.preventDefault(); setBusy(true); setError(''); setSuccess('')
    try {
      const result = await apiRequest(`school-fees/payments/${encodeURIComponent(payment.reference)}/reverse/`, { method: 'POST', body: {
        amount_minor: Math.round(Number(reversalForm.amount) * 100), reason: reversalForm.reason,
        external_reference: reversalForm.external_reference,
      } })
      setReversalTarget(''); setReversalForm({ amount: '', reason: '', external_reference: '' })
      await load(); flashSuccess(result.detail || 'The reversal was recorded in the audit history.')
    } catch (e) { flashError(e.message || 'The reversal could not be recorded.') }
    finally { setBusy(false) }
  }

  if (loading) return <main className="auth-page"><p className="loading-message" role="status">Loading school fees…</p></main>

  return <main className="app-page school-finance-page">
    <header className="app-topbar"><BrandMark navigate={navigate} /><button className="text-button" type="button" onClick={() => navigate('/app')}>Back to dashboard</button></header>
    <section className="app-content finance-content">
      <p className="eyebrow">{selectedSchool?.school_name || 'SCHOOL'} · FINANCE</p>
      <h1 className="app-heading">School fees<br /><em>made clear.</em></h1>
      <p className="intro">Manage fee schedules, record in-person payments, and track online collections for {selectedSchool?.school_name}. Payment records are separate from report-card credits.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}

      <section className="fee-kpis" aria-label="School fee summary">
        {[["Expected", overview?.expected_minor], ["Collected", overview?.collected_minor], ["Outstanding", overview?.outstanding_minor], ["At school", overview?.physical_minor], ["Online", overview?.online_minor], ["Students with balance", overview?.students_with_balance]].map(([label, value]) => <article key={label}><span>{label}</span><strong>{label === 'Students with balance' ? value ?? '—' : money(value)}</strong></article>)}
      </section>
      <div className="fee-count-strip"><span>{overview?.fully_paid_students || 0} fully paid</span><span>{overview?.partially_paid_students || 0} partially paid</span><span>{overview?.students_with_fees || 0} students with fees issued</span></div>

      <section className="fee-panel"><p className="panel-kicker">FINANCE FILTERS</p><h2>Find fees and transactions</h2>
        <form className="fee-form-grid" onSubmit={applyFinanceFilters}>
          <label>Academic session<select value={filters.session} onChange={(e) => setFilters({ ...filters, session: e.target.value, term: '' })}><option value="">All sessions</option>{sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Term<select value={filters.term} onChange={(e) => setFilters({ ...filters, term: e.target.value })}><option value="">All terms</option>{filterTerms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Class<select value={filters.class_level} onChange={(e) => setFilters({ ...filters, class_level: e.target.value })}><option value="">All classes</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Payment method<select value={filters.method} onChange={(e) => setFilters({ ...filters, method: e.target.value })}><option value="">All methods</option><option value="cash">Cash</option><option value="pos">POS</option><option value="bank_transfer">Bank transfer</option><option value="card">Card</option><option value="ussd">USSD</option><option value="other">Other</option></select></label>
          <label>Payment channel<select value={filters.channel} onChange={(e) => setFilters({ ...filters, channel: e.target.value })}><option value="">All channels</option><option value="physical">At school</option><option value="online">Online</option></select></label>
          <label>Payment status<select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option><option value="pending">Pending</option><option value="success">Successful</option><option value="failed">Failed</option><option value="partially_reversed">Partially reversed</option><option value="reversed">Reversed</option><option value="refunded">Refunded</option></select></label>
          <label>From date<input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></label>
          <label>To date<input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></label>
          <label className="fee-wide-field">Student, admission number, or payment reference<input placeholder="Search a student or transaction" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} /></label>
          <div className="fee-filter-actions"><button className="primary-button" disabled={busy}>Apply filters</button><button className="secondary-button" type="button" onClick={clearFinanceFilters} disabled={busy}>Clear</button></div>
        </form>
      </section>

      <section className="fee-panel"><div className="fee-section-heading"><div><p className="panel-kicker">SCHEDULE FEES</p><h2>Create a fee schedule</h2></div><p>Students already enrolled in the chosen class will be charged automatically. New enrollments receive matching active fees.</p></div>
        <form className="fee-form-grid" onSubmit={createSchedule}>
          <label>Academic session<select required value={scheduleForm.academic_session} onChange={(e) => setScheduleForm({ ...scheduleForm, academic_session: e.target.value, term: '' })}><option value="">Select session</option>{sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Term<select required value={scheduleForm.term} onChange={(e) => setScheduleForm({ ...scheduleForm, term: e.target.value })}><option value="">Select term</option>{terms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Class<select required value={scheduleForm.class_level} onChange={(e) => setScheduleForm({ ...scheduleForm, class_level: e.target.value, class_arm: '' })}><option value="">Select class</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Arm (optional)<select value={scheduleForm.class_arm} onChange={(e) => setScheduleForm({ ...scheduleForm, class_arm: e.target.value })}><option value="">All arms in class</option>{arms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Fee category<input required maxLength="100" placeholder="e.g. Tuition, Uniform, Transport" value={scheduleForm.category} onChange={(e) => setScheduleForm({ ...scheduleForm, category: e.target.value })} /></label>
          <label>Amount in naira<input required type="number" min="1" step="0.01" placeholder="e.g. 25000" value={scheduleForm.amount} onChange={(e) => setScheduleForm({ ...scheduleForm, amount: e.target.value })} /></label>
          <label>Due date (optional)<input type="date" value={scheduleForm.due_date} onChange={(e) => setScheduleForm({ ...scheduleForm, due_date: e.target.value })} /></label>
          <label>Description (optional)<input maxLength="300" placeholder="What does this fee cover?" value={scheduleForm.description} onChange={(e) => setScheduleForm({ ...scheduleForm, description: e.target.value })} /></label>
          <button className="primary-button" disabled={busy}>Save and issue fees</button>
        </form>
      </section>

      <section className="fee-panel"><div className="fee-section-heading"><div><p className="panel-kicker">RECEIVE A PAYMENT</p><h2>Record an in-person payment</h2></div><p>Cash, POS, bank transfer, and other approved payments all post to the same student balance ledger.</p></div>
        <form className="fee-form-grid" onSubmit={recordPayment}>
          <label className="fee-wide-field">Find student or fee on this page<input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search the currently loaded fee records" /></label>
          <label className="fee-wide-field">Student fee<select required value={selectedCharge} onChange={(e) => { setSelectedCharge(e.target.value); const row = charges.find((item) => String(item.id) === e.target.value); setPaymentForm((current) => ({ ...current, amount: row ? (row.outstanding_minor / 100).toFixed(2) : '' })) }}><option value="">Select a fee with a balance</option>{visibleCharges.filter((item) => item.outstanding_minor > 0).map((item) => <option key={item.id} value={item.id}>{item.student_name} · {item.admission_number} · {item.class_name} {item.arm_name} · {item.category} · balance {money(item.outstanding_minor)}</option>)}</select></label>
          <label>Amount received<input required type="number" min="0.01" step="0.01" placeholder="Enter naira received" value={paymentForm.amount} onChange={(e) => setPaymentForm({ ...paymentForm, amount: e.target.value })} /></label>
          <label>Payment method<select value={paymentForm.method} onChange={(e) => setPaymentForm({ ...paymentForm, method: e.target.value })}><option value="cash">Cash</option><option value="pos">POS</option><option value="bank_transfer">Bank transfer</option><option value="other">Other</option></select></label>
          <label>Parent email (optional)<input type="email" placeholder="For the payment record" value={paymentForm.payer_email} onChange={(e) => setPaymentForm({ ...paymentForm, payer_email: e.target.value })} /></label>
          <label>Transaction note (optional)<input placeholder="e.g. POS terminal reference" value={paymentForm.description} onChange={(e) => setPaymentForm({ ...paymentForm, description: e.target.value })} /></label>
          {selected && Number(paymentForm.amount) * 100 > selected.outstanding_minor && settings?.allow_excess_credit && <p className="fee-inline-note fee-wide-field">The extra amount will be saved as student credit and applied to another outstanding fee first.</p>}
          <button className="primary-button" disabled={busy || !selectedCharge}>Record payment and download receipt</button>
        </form>
      </section>

      <section className="fee-panel"><div className="fee-section-heading"><div><p className="panel-kicker">STUDENT BALANCES</p><h2>Issued fees</h2></div><span>{chargeCount} fee records · page {chargePage} of {Math.max(1, Math.ceil(chargeCount / 200))}</span></div>
        {charges.length ? <div className="fee-table-wrap"><table><thead><tr><th>Student</th><th>Class</th><th>Session / term</th><th>Fee</th><th>Expected</th><th>Paid</th><th>Balance</th><th>Status</th></tr></thead><tbody>{visibleCharges.slice(0, 300).map((item) => <tr key={item.id}><td><strong>{item.student_name}</strong><small>{item.admission_number}</small></td><td>{item.class_name} {item.arm_name}</td><td>{item.session_name}<small>{item.term_name}</small></td><td>{item.category}</td><td>{money(item.amount_minor)}</td><td>{money(item.paid_minor)}</td><td>{money(item.outstanding_minor)}</td><td><span className={`fee-status fee-status-${item.payment_status}`}>{item.payment_status}</span></td></tr>)}</tbody></table></div> : <p className="fee-empty">No fees have been issued yet. Create a fee schedule to start.</p>}
        {chargeCount > 200 && <div className="fee-pagination"><button className="secondary-button" type="button" disabled={chargePage <= 1} onClick={() => loadFeePage(chargePage - 1)}>Previous fees</button><button className="secondary-button" type="button" disabled={chargePage >= Math.ceil(chargeCount / 200)} onClick={() => loadFeePage(chargePage + 1)}>Next fees</button></div>}
      </section>

      <section className="fee-panel"><p className="panel-kicker">BANK & ONLINE COLLECTIONS</p><h2>Connect this school’s account</h2>
        {settings?.account_status === 'verified' && <p className="fee-inline-note">Verified account: <strong>{settings.account_name}</strong> · {settings.bank_name} · {settings.account_number}. Online payments: {settings.online_enabled ? 'enabled' : 'disabled'}.</p>}
        <form className="fee-form-grid" onSubmit={connectBank}>
          <label>Payment provider<select value={connection.provider} onChange={(e) => loadBankList(e.target.value)}><option value="flutterwave">Flutterwave</option><option value="paystack">Paystack</option></select></label>
          <label>Bank<select required value={connection.bank_code} onChange={(e) => { const bank = banks.find((item) => String(item.code) === e.target.value); setConnection({ ...connection, bank_code: e.target.value, bank_name: bank?.name || '' }) }}><option value="">Select bank</option>{banks.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
          <label>Account number<input required inputMode="numeric" maxLength="12" placeholder="10-digit bank account number" value={connection.account_number} onChange={(e) => setConnection({ ...connection, account_number: e.target.value.replace(/\D/g, '') })} /></label>
          <label>Account type (optional)<input placeholder="e.g. School current account" value={connection.account_type} onChange={(e) => setConnection({ ...connection, account_type: e.target.value })} /></label>
          <label>School phone (optional)<input type="tel" placeholder="+234…" value={connection.business_mobile} onChange={(e) => setConnection({ ...connection, business_mobile: e.target.value })} /></label>
          <button className="primary-button" disabled={busy || !connection.bank_code}>Verify account and connect</button>
        </form>
        <div className="fee-settings-row"><label><input type="checkbox" checked={settings?.allow_excess_credit ?? true} onChange={(e) => saveSettings({ allow_excess_credit: e.target.checked })} /> Allow overpayments to become student credit</label><span>Bank transfer payments are confirmed by the provider checkout. A regular bank transfer cannot be detected automatically without a dedicated bank integration.</span></div>
        {settings?.account_status === 'verified' && <div className="fee-online-options"><h3>Online collection options</h3><label><input type="checkbox" checked={settings.online_enabled} onChange={(e) => saveSettings({ online_enabled: e.target.checked })} /> Allow parents to pay online</label><p>If every option below is unchecked, the provider account’s default payment methods are shown.</p><div>{[['card', 'Card'], ['bank_transfer', 'Bank transfer'], ['ussd', 'USSD']].map(([value, label]) => <label key={value}><input type="checkbox" checked={(settings.allowed_channels || []).includes(value)} onChange={(e) => { const current = settings.allowed_channels || []; const next = e.target.checked ? [...new Set([...current, value])] : current.filter((item) => item !== value); saveSettings({ allowed_channels: next }) }} /> {label}</label>)}</div></div>}
        <p className="fee-inline-note">Payment provider secret keys are managed by EDUstacked on the backend. They are never requested or stored in this school form. School finance SMS: {settings?.sms_status === 'configured' ? 'Termii is configured.' : 'Termii SMS is not configured yet; payments still save and SMS can be retried after Termii is connected.'}</p>
      </section>

      <section className="fee-panel"><p className="panel-kicker">RECENT TRANSACTIONS</p><h2>Payment history</h2><p>{paymentCount} matching payments · page {paymentPage} of {Math.max(1, Math.ceil(paymentCount / 50))}</p><p className="fee-inline-note">An accounting reversal does not move money by itself. Complete an online refund through the provider first, then record its refund reference here.</p>{payments.length ? <div className="fee-payment-list">{payments.map((item) => <article key={item.reference}><div><strong>{money(item.amount_minor)} · {item.reference}</strong><span>{item.channel === 'physical' ? 'At school' : item.provider} · {item.method} · {item.status} · {new Date(item.created_at).toLocaleString()}</span></div><div className="fee-transaction-actions"><button className="secondary-button" type="button" onClick={() => downloadReceipt(item.reference)} disabled={item.status === 'pending' || item.status === 'failed'}>Receipt PDF</button>{['school_owner', 'school_admin', 'accountant'].includes(selectedSchool?.role) && ['success', 'partially_reversed'].includes(item.status) && <button className="secondary-button" type="button" onClick={() => { setReversalTarget((current) => current === item.reference ? '' : item.reference); setReversalForm({ amount: (item.amount_minor / 100).toFixed(2), reason: '', external_reference: '' }) }}>Record reversal</button>}</div>{reversalTarget === item.reference && <form className="fee-reversal-form" onSubmit={(event) => recordReversal(event, item)}><label>Refund amount in naira<input required type="number" min="0.01" max={(item.amount_minor / 100).toFixed(2)} step="0.01" placeholder="Amount being refunded" value={reversalForm.amount} onChange={(event) => setReversalForm({ ...reversalForm, amount: event.target.value })} /></label><label>Reason<textarea required maxLength="500" placeholder="Explain why this payment is being reversed" value={reversalForm.reason} onChange={(event) => setReversalForm({ ...reversalForm, reason: event.target.value })} /></label><label>Refund / adjustment reference<input required={item.channel === 'online'} placeholder="Provider refund ID or cash adjustment reference" value={reversalForm.external_reference} onChange={(event) => setReversalForm({ ...reversalForm, external_reference: event.target.value })} /></label><button className="primary-button" disabled={busy}>Save audited reversal</button></form>}</article>)}</div> : <p>No payment transactions have been recorded.</p>}{paymentCount > 50 && <div className="fee-pagination"><button className="secondary-button" type="button" disabled={paymentPage <= 1} onClick={() => loadPaymentPage(paymentPage - 1)}>Previous payments</button><button className="secondary-button" type="button" disabled={paymentPage >= Math.ceil(paymentCount / 50)} onClick={() => loadPaymentPage(paymentPage + 1)}>Next payments</button></div>}</section>
      <p className="billing-note">Signed in as {user?.first_name || user?.email}. Successful online payments are confirmed server-side before they change a student balance. Physical-payment corrections must be recorded as audited reversals.</p>
    </section>
  </main>
}
