import { useEffect, useMemo, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { apiBlobRequest, apiRequest } from '../services/api.js'

const money = (minor) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format((Number(minor) || 0) / 100)

// Fee amounts are entered as naira strings and sent to the API as integer kobo.
// This avoids floating point rounding (for example, 0.1 + 0.2) in payment totals.
function nairaToMinorUnits(value) {
  const text = String(value ?? '').trim()
  if (!text) return null
  const match = text.match(/^(\d+)(?:\.(\d{1,2}))?$/)
  if (!match) return Number.NaN
  const whole = Number(match[1])
  const fraction = Number((match[2] || '').padEnd(2, '0'))
  const minor = whole * 100 + fraction
  return Number.isSafeInteger(minor) ? minor : Number.NaN
}

function summarizeFees(rows) {
  const charges = rows.flatMap((row) => row.charges.map((charge) => ({
    ...charge,
    student_name: charge.student_name || row.student_name,
    school_id: row.school_id,
    school_name: row.school,
  })))
  const paymentMap = new Map()
  rows.flatMap((row) => row.payments).forEach((payment) => {
    const current = paymentMap.get(payment.reference)
    if (current) {
      current.amount_minor += Number(payment.amount_minor) || 0
      current.student_names.add(payment.student_name || '')
    } else {
      paymentMap.set(payment.reference, {
        ...payment,
        amount_minor: Number(payment.amount_minor) || 0,
        student_names: new Set([payment.student_name || '']),
      })
    }
  })
  const summary = rows.reduce((total, row) => ({
    expected_minor: total.expected_minor + (Number(row.summary?.expected_minor) || 0),
    paid_minor: total.paid_minor + (Number(row.summary?.paid_minor) || 0),
    outstanding_minor: total.outstanding_minor + (Number(row.summary?.outstanding_minor) || 0),
    credit_minor: total.credit_minor + (Number(row.summary?.credit_minor) || 0),
  }), { expected_minor: 0, paid_minor: 0, outstanding_minor: 0, credit_minor: 0 })
  return {
    charges,
    payments: [...paymentMap.values()].map((payment) => ({ ...payment, student_names: [...payment.student_names].filter(Boolean) })),
    summary,
  }
}

export default function ParentFeesPage({ navigate }) {
  const [students, setStudents] = useState([])
  const [selection, setSelection] = useState('')
  const [student, setStudent] = useState(null)
  const [fees, setFees] = useState(null)
  const [amounts, setAmounts] = useState({})
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    apiRequest('parent/students/')
      .then((rows) => {
        if (!active) return
        setStudents(rows)
        const requested = new URLSearchParams(window.location.search).get('student_id')
        const requestedStudent = rows.find((row) => String(row.id) === String(requested))
        const initial = requestedStudent ? `student:${requestedStudent.id}` : rows[0] ? `school:${rows[0].school.id}` : ''
        setSelection(initial)
      })
      .catch((requestError) => setError(requestError.message || 'We could not load your linked students. Refresh the page or contact the school.'))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  const selectedStudents = useMemo(() => {
    if (selection.startsWith('student:')) {
      const id = selection.slice('student:'.length)
      return students.filter((row) => String(row.id) === id)
    }
    if (selection.startsWith('school:')) {
      const id = selection.slice('school:'.length)
      return students.filter((row) => String(row.school.id) === id)
    }
    return []
  }, [selection, students])

  useEffect(() => {
    if (!selection || !selectedStudents.length) { setStudent(null); setFees(null); return undefined }
    let active = true
    setLoading(true); setError(''); setMessage('')
    Promise.all(selectedStudents.map((item) => apiRequest(`parent/students/${item.id}/fees/`)))
      .then((rows) => {
        if (!active) return
        const summary = summarizeFees(rows)
        const school = selectedStudents[0].school
        setFees(summary)
        setStudent({
          name: selectedStudents.length === 1 ? selectedStudents[0].name : `${selectedStudents.length} linked students`,
          school,
        })
        setAmounts((current) => {
          const next = { ...current }
          summary.charges.forEach((charge) => { if (next[charge.id] == null) next[charge.id] = '' })
          return next
        })
      })
      .catch((requestError) => active && setError(requestError.message || 'We could not load fee information. Refresh the page or contact the school.'))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [selection, selectedStudents])

  const charges = useMemo(() => fees?.charges || [], [fees])
  const outstanding = charges.filter((charge) => Number(charge.outstanding_minor) > 0)
  const canSubmit = outstanding.some((charge) => {
    const minor = nairaToMinorUnits(amounts[charge.id])
    return Number.isSafeInteger(minor) && minor > 0 && minor <= Number(charge.outstanding_minor)
  })

  async function beginPayment(event) {
    event.preventDefault(); setError(''); setMessage('')
    const allocations = []
    for (const charge of outstanding) {
      const amountMinor = nairaToMinorUnits(amounts[charge.id])
      if (amountMinor == null || amountMinor === 0) continue
      if (!Number.isSafeInteger(amountMinor) || amountMinor < 0 || amountMinor > Number(charge.outstanding_minor)) {
        setError(`Enter a valid amount in naira for ${charge.student_name} that does not exceed its outstanding balance.`)
        return
      }
      allocations.push({ fee_charge_id: charge.id, amount_minor: amountMinor })
    }
    if (!allocations.length) { setError('Enter an amount for at least one outstanding fee before continuing.'); return }
    setWorking(true)
    try {
      const result = await apiRequest('parent/fees/payments/initialize/', { method: 'POST', body: { allocations } })
      if (!result.authorization_url) throw new Error('The school’s online payment checkout could not be opened. Contact the school office for help.')
      window.location.assign(result.authorization_url)
    } catch (requestError) { setError(requestError.message || 'Online checkout could not be started. Please try again or contact the school office.') }
    finally { setWorking(false) }
  }

  async function downloadReceipt(reference) {
    setError('')
    try {
      const blob = await apiBlobRequest(`parent/fees/payments/${encodeURIComponent(reference)}/receipt/`)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `fee-receipt-${reference}.pdf`; anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (requestError) { setError(requestError.message || 'The receipt could not be downloaded yet.') }
  }

  const selectedSchoolIds = new Set(students.map((item) => String(item.school.id)))
  const oneSchoolOnly = selectedSchoolIds.size === 1

  return <main className="app-page parent-portal-page"><header className="app-topbar"><BrandMark navigate={navigate} /><button className="text-button" onClick={() => navigate('/parent')}>Back to parent portal</button></header>
    <section className="app-content parent-content parent-fees-content"><p className="eyebrow">EDUstacked · SECURE SCHOOL FEE PAYMENTS</p><h1 className="app-heading">School fees<br /><em>&amp; payments.</em></h1><p className="intro">Review fees issued by your student’s school and pay online using the payment option enabled by that school.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="form-success" role="status">{message}</p>}{loading && <p className="loading-message" role="status">Loading student and fee information…</p>}
      <section className="parent-panel parent-fees-panel"><div className="parent-section-heading"><div><p className="panel-kicker">SELECT STUDENT OR SCHOOL</p><h2>Choose whose fees to view</h2></div></div>
        {students.length ? <label className="parent-student-picker"><span>Student or school</span><select value={selection} onChange={(event) => setSelection(event.target.value)}>
          {oneSchoolOnly && <option value={`school:${students[0].school.id}`}>All linked students · {students[0].school.name}</option>}
          {!oneSchoolOnly && [...new Map(students.map((item) => [item.school.id, item.school])).values()].map((school) => <option key={`school:${school.id}`} value={`school:${school.id}`}>All linked students · {school.name}</option>)}
          {students.map((item) => <option key={`student:${item.id}`} value={`student:${item.id}`}>{item.name} · {item.school.name}</option>)}
        </select></label> : !loading && <p>No students are linked to your account yet. Ask the school to link your guardian account to a student.</p>}
      </section>
      {student && <section className="parent-panel parent-fees-panel"><div className="parent-section-heading"><div><p className="panel-kicker">{student.school.name}</p><h2>{student.name} · Balances and payments</h2></div></div>
        {fees?.summary && <div className="parent-attendance-stats parent-fee-stats">{[['Expected', fees.summary.expected_minor], ['Paid', fees.summary.paid_minor], ['Outstanding', fees.summary.outstanding_minor], ['Available credit', fees.summary.credit_minor]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{money(value)}</strong></div>)}</div>}
        {charges.length ? <form className="parent-fee-form" onSubmit={beginPayment}><div className="parent-fee-charge-list">{outstanding.map((charge) => <label className="parent-fee-charge" key={charge.id}><span><strong>{charge.student_name}</strong><small>{charge.class_name} {charge.arm_name} · {charge.session_name} · {charge.term_name} · {charge.category}</small><small>Outstanding: {money(charge.outstanding_minor)}</small></span><input type="number" min="0" step="0.01" max={(charge.outstanding_minor / 100).toFixed(2)} inputMode="decimal" aria-label={`Amount to pay for ${charge.student_name} ${charge.category}`} placeholder="Amount in ₦" value={amounts[charge.id] || ''} onChange={(event) => setAmounts((current) => ({ ...current, [charge.id]: event.target.value }))} /></label>)}
          {!outstanding.length && <p>No school-fee balance is outstanding for these linked students.</p>}
        </div>{Boolean(outstanding.length) && <><button className="primary-button" disabled={working || !canSubmit}>{working ? 'Opening secure checkout…' : 'Continue to secure online payment'}</button><p className="parent-policy-note">You may pay part or all of a balance. Fees for linked students at the same school can be combined in one checkout. Each school uses its own configured payment account.</p></>}</form> : <p>No fee records have been issued for this student yet. The school will show them here after creating a fee schedule.</p>}
        <h3>Payment history</h3>{fees?.payments?.length ? <div className="parent-fee-payments">{fees.payments.map((payment) => <article key={payment.reference}><div><strong>{payment.reference}</strong><span>{money(payment.amount_minor)} · {payment.channel === 'physical' ? 'Paid at school' : 'Online'} · {payment.status} · {new Date(payment.created_at).toLocaleDateString()}{payment.student_names?.length > 1 ? ` · ${payment.student_names.join(', ')}` : ''}</span></div><button className="secondary-button" type="button" onClick={() => downloadReceipt(payment.reference)} disabled={payment.status === 'pending' || payment.status === 'failed'}>Download receipt</button></article>)}</div> : <p>Online and school-recorded payments will appear here after the school issues a fee or confirms payment.</p>}
      </section>}
    </section>
  </main>
}
