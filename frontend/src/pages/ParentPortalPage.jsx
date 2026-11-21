import { useCallback, useEffect, useState } from 'react'
import { apiBlobRequest, apiRequest } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'

const errorText = (error) => error?.message || 'Could not load this portal information. Try again.'

export default function ParentPortalPage({ navigate }) {
  const { user, guardianProfile, signOut } = useAuth()
  const [students, setStudents] = useState([])
  const [studentId, setStudentId] = useState('')
  const [student, setStudent] = useState(null)
  const [attendance, setAttendance] = useState(null)
  const [reports, setReports] = useState([])
  const [fees, setFees] = useState(null)
  const [familyFees, setFamilyFees] = useState([])
  const [feeAmounts, setFeeAmounts] = useState({})
  const [receiptCode, setReceiptCode] = useState({})
  const [receiptCodeOpen, setReceiptCodeOpen] = useState('')
  const [feeWorking, setFeeWorking] = useState(false)
  const [feeError, setFeeError] = useState('')
  const [feeSuccess, setFeeSuccess] = useState('')
  const [selectedReport, setSelectedReport] = useState(null)
  const [announcements, setAnnouncements] = useState([])
  const [notifications, setNotifications] = useState([])
  const [profile, setProfile] = useState(guardianProfile)
  const [nameForm, setNameForm] = useState({ first_name: guardianProfile?.first_name || '', last_name: guardianProfile?.last_name || '' })
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const loadGeneral = useCallback(async () => {
    const [linked, schoolNews, noticeRows, guardian] = await Promise.all([
      apiRequest('parent/students/'), apiRequest('parent/announcements/'),
      apiRequest('parent/notifications/'), apiRequest('parent/profile/'),
    ])
    setStudents(linked)
    const feeRows = await Promise.all(linked.map((item) => apiRequest(`parent/students/${item.id}/fees/`).catch(() => null)))
    setFamilyFees(feeRows.filter(Boolean).flatMap((row) => row.charges.map((charge) => ({ ...charge, school_id: row.school_id, school_name: row.school, student_id: row.student_id }))))
    setStudentId((current) => linked.some((item) => String(item.id) === String(current)) ? current : String(linked[0]?.id || ''))
    setAnnouncements(schoolNews.results || [])
    setNotifications(noticeRows.results || [])
    setProfile(guardian)
    setNameForm({ first_name: guardian.first_name || '', last_name: guardian.last_name || '' })
  }, [])

  useEffect(() => {
    loadGeneral().catch((requestError) => setError(errorText(requestError))).finally(() => setLoading(false))
  }, [loadGeneral])

  useEffect(() => {
    if (!studentId) {
      setStudent(null); setAttendance(null); setReports([]); setSelectedReport(null)
      return
    }
    let active = true
    setStudent(null); setAttendance(null); setReports([]); setSelectedReport(null)
    Promise.all([
      apiRequest(`parent/students/${studentId}/`),
      apiRequest(`parent/students/${studentId}/attendance/`),
      apiRequest(`parent/students/${studentId}/report-cards/`),
      apiRequest(`parent/students/${studentId}/fees/`),
    ]).then(([overview, attendanceData, reportRows, feeData]) => {
      if (!active) return
      setStudent(overview)
      setAttendance(attendanceData)
      setReports(reportRows)
      setFees(feeData)
      setFamilyFees((current) => [
        ...current.filter((row) => String(row.student_id) !== String(feeData.student_id)),
        ...feeData.charges.map((charge) => ({ ...charge, school_id: feeData.school_id, school_name: feeData.school, student_id: feeData.student_id })),
      ])
    }).catch((requestError) => active && setError(errorText(requestError)))
    return () => { active = false }
  }, [studentId])

  useEffect(() => {
    const query = new URLSearchParams(window.location.search)
    const reference = query.get('fees_payment')
    if (!reference) return
    let active = true
    const transactionId = query.get('transaction_id')
    setFeeWorking(true); setFeeError(''); setFeeSuccess('')
    apiRequest(`parent/fees/payments/${encodeURIComponent(reference)}/`, { method: 'POST', body: transactionId ? { transaction_id: transactionId } : {} })
      .then((result) => {
        if (!active) return
        if (result.status === 'success') setFeeSuccess(`Payment ${reference} is confirmed. Your receipt is ready below.`)
        else setFeeSuccess(`Payment ${reference} is ${result.status}. The school balance changes only after provider confirmation.`)
        return apiRequest('parent/students/').then((linked) => Promise.all(linked.map((item) => apiRequest(`parent/students/${item.id}/fees/`).catch(() => null))))
          .then((rows) => {
            if (!active) return
            const validRows = rows.filter(Boolean)
            setFamilyFees(validRows.flatMap((row) => row.charges.map((charge) => ({ ...charge, school_id: row.school_id, school_name: row.school, student_id: row.student_id }))))
            const selectedFees = validRows.find((row) => String(row.student_id) === String(studentId)) || validRows[0]
            if (selectedFees) setFees(selectedFees)
          })
      })
      .catch((requestError) => active && setFeeError(requestError.message || 'We could not verify this payment yet. You can check again from your payment history.'))
      .finally(() => active && setFeeWorking(false))
    return () => { active = false }
  }, [])

  async function saveProfile(event) {
    event.preventDefault(); setWorking(true); setError(''); setSuccess('')
    try {
      const updated = await apiRequest('parent/profile/', { method: 'PATCH', body: nameForm })
      setProfile(updated); setSuccess('Profile name updated.')
    } catch (requestError) { setError(errorText(requestError)) }
    finally { setWorking(false) }
  }

  async function openReport(report) {
    setError(''); setSelectedReport(null)
    try { setSelectedReport(await apiRequest(`parent/report-cards/${report.id}/`)) }
    catch (requestError) { setError(errorText(requestError)) }
  }

  async function downloadReport(report) {
    const tab = window.open('', '_blank')
    if (!tab) { setError('Allow pop-up windows to view the report-card PDF.'); return }
    tab.opener = null
    try {
      const blob = await apiBlobRequest(`parent/report-cards/${report.id}/pdf/`)
      const url = URL.createObjectURL(blob)
      tab.location.href = url
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (requestError) { tab.close(); setError(errorText(requestError)) }
  }

  async function downloadFeeReceipt(reference) {
    setFeeError('')
    try {
      const blob = await apiBlobRequest(`parent/fees/payments/${encodeURIComponent(reference)}/receipt/`)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `fee-receipt-${reference}.pdf`; anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (requestError) { setFeeError(requestError.message || 'The payment receipt could not be downloaded.') }
  }

  async function beginFeePayment(event) {
    event.preventDefault(); setFeeError(''); setFeeSuccess('')
    const schoolFees = familyFees.filter((row) => row.school_id === student?.school?.id && Number(feeAmounts[row.id]) > 0)
    if (!schoolFees.length) { setFeeError('Enter an amount for at least one fee for the selected school.'); return }
    setFeeWorking(true)
    try {
      const result = await apiRequest('parent/fees/payments/initialize/', { method: 'POST', body: { allocations: schoolFees.map((row) => ({ fee_charge_id: row.id, amount_minor: Math.round(Number(feeAmounts[row.id]) * 100) })) } })
      window.location.assign(result.authorization_url)
    } catch (requestError) { setFeeError(requestError.message || 'Online checkout could not be started.'); setFeeWorking(false) }
  }

  async function verifyFeeReceipt(reference, resend = false) {
    setFeeError(''); setFeeSuccess('')
    try {
      if (resend) {
        const result = await apiRequest(`parent/fees/payments/${encodeURIComponent(reference)}/receipt/verify/`, { method: 'POST', body: { action: 'resend' } })
        setFeeSuccess(result.detail)
      } else {
        const result = await apiRequest(`parent/fees/payments/${encodeURIComponent(reference)}/receipt/verify/`, { method: 'POST', body: { code: receiptCode[reference] || '' } })
        setFeeSuccess(result.detail)
        setReceiptCodeOpen('')
      }
    } catch (requestError) { setFeeError(requestError.message || 'Receipt verification could not be completed.') }
  }

  async function markRead(notification) {
    try {
      const updated = await apiRequest(`parent/notifications/${notification.id}/read/`, { method: 'POST', body: {} })
      setNotifications((items) => items.map((item) => item.id === updated.id ? updated : item))
    } catch (requestError) { setError(errorText(requestError)) }
  }

  async function logOut() {
    await signOut()
    navigate('/login')
  }

  const currentSchoolFeeRows = familyFees.filter((row) => row.school_id === student?.school?.id)

  if (loading) return <main className="auth-page"><p className="loading-message" role="status">Loading your parent portal…</p></main>

  return <main className="app-page parent-portal-page">
    <header className="app-topbar"><BrandMark navigate={navigate} /><div className="parent-header-actions"><span>{profile?.first_name || user?.first_name || profile?.email}</span><button className="text-button" onClick={logOut}>Sign out</button></div></header>
    <section className="app-content parent-content">
      <p className="eyebrow">EDUstacked · PARENT / GUARDIAN PORTAL</p>
      <h1 className="app-heading">Your family’s<br /><em>school updates.</em></h1>
      <p className="intro">View information for students linked to your account by their school.</p>
      <div className="parent-fees-entry"><div><p className="panel-kicker">ONLINE SCHOOL FEES</p><strong>Review balances and pay securely</strong><span>Choose an individual student or pay for linked students at the same school together.</span></div><button className="primary-button" type="button" disabled={!studentId} onClick={() => navigate('/parent/fees')}>Open family fee payments</button></div>
      {error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}

      <section className="parent-panel parent-profile-panel"><div><p className="panel-kicker">YOUR PROFILE</p><strong>{profile?.email}</strong><span>{profile?.schools?.map((item) => item.name).filter((name, index, names) => names.indexOf(name) === index).join(' · ')}</span></div>
        <form className="parent-profile-form" onSubmit={saveProfile}><label>First name<input value={nameForm.first_name} onChange={(event) => setNameForm({ ...nameForm, first_name: event.target.value })} maxLength="150" /></label><label>Last name<input value={nameForm.last_name} onChange={(event) => setNameForm({ ...nameForm, last_name: event.target.value })} maxLength="150" /></label><button className="secondary-button" disabled={working}>Save profile</button></form>
      </section>

      <section className="parent-panel"><div className="parent-section-heading"><div><p className="panel-kicker">LINKED STUDENTS</p><h2>Your students</h2></div>{students.length > 1 && <label className="parent-student-picker"><span>Select student</span><select value={studentId} onChange={(event) => setStudentId(event.target.value)}>{students.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.school.name}</option>)}</select></label>}</div>
        {!students.length ? <p>No students are currently linked to this account. Contact the school if you expect access.</p> : <div className="parent-student-summary">{students.length > 1 && <div className="parent-student-chips">{students.map((item) => <button key={item.id} className={String(item.id) === studentId ? 'parent-student-chip active' : 'parent-student-chip'} onClick={() => setStudentId(String(item.id))}>{item.name}</button>)}</div>}{student ? <><h3>{student.name}</h3><p>{student.school.name} · Admission no. {student.admission_number}</p>{student.enrollment ? <p>{student.enrollment.session_name} · {student.enrollment.class_name} {student.enrollment.arm_name}</p> : <p>No current enrollment details are available.</p>}</> : <p>Loading selected student…</p>}</div>}
      </section>

      {student && <section className="parent-panel"><div className="parent-section-heading"><div><p className="panel-kicker">ATTENDANCE</p><h2>Recent attendance</h2></div></div>
        {attendance?.summary?.total ? <><div className="parent-attendance-stats">{[['Present', attendance.summary.present], ['Absent', attendance.summary.absent], ['Late', attendance.summary.late], ['Excused', attendance.summary.excused], ['Attendance', attendance.summary.attendance_percentage == null ? '—' : `${attendance.summary.attendance_percentage}%`]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="parent-table-wrap"><table><thead><tr><th>Date</th><th>Session</th><th>Term</th><th>Status</th></tr></thead><tbody>{attendance.results?.map((row) => <tr key={row.id}><td>{row.date}</td><td>{row.session}</td><td>{row.term}</td><td>{row.status}</td></tr>)}</tbody></table></div><p className="parent-policy-note">Finalized attendance only. Missing registers are not counted as absences.</p></> : <p>No finalized attendance records are available for this student yet.</p>}
      </section>}

      {student && <section className="parent-panel"><p className="panel-kicker">ACADEMIC REPORTS</p><h2>Published report cards</h2>
        {reports.length ? <div className="parent-report-list">{reports.map((report) => <article key={report.id}><div><strong>{report.session} · {report.term}</strong><span>{report.class_name} {report.arm_name} · Revision {report.revision_number}</span></div><div><button className="text-button" onClick={() => openReport(report)}>View results</button><button className="secondary-button" onClick={() => downloadReport(report)}>View / download PDF</button></div></article>)}</div> : <p>No finalized report cards have been published for this student yet.</p>}
        {selectedReport && <div className="parent-report-detail"><h3>{selectedReport.snapshot.academic?.session} · {selectedReport.snapshot.academic?.term}</h3><div className="parent-table-wrap"><table><thead><tr><th>Subject</th><th>Total</th><th>Percentage</th><th>Grade</th><th>Remarks</th></tr></thead><tbody>{selectedReport.snapshot.subjects?.map((subject) => <tr key={subject.subject_id}><td>{subject.subject_name}</td><td>{subject.total} / {subject.maximum}</td><td>{subject.percentage}%</td><td>{subject.grade}</td><td>{subject.grade_description || ''}</td></tr>)}</tbody></table></div><div className="parent-report-remarks">{Object.entries(selectedReport.snapshot.remarks || {}).filter(([, value]) => value).map(([key, value]) => <p key={key}><strong>{key.replaceAll('_', ' ')}:</strong> {value}</p>)}</div></div>}
      </section>}

      {student && <section className="parent-panel parent-fees-panel"><div className="parent-section-heading"><div><p className="panel-kicker">SCHOOL FEES</p><h2>Balances and payments</h2></div><span>{student.school.name}</span></div>
        {feeError && <p className="form-error" role="alert">{feeError}</p>}{feeSuccess && <p className="form-success" role="status">{feeSuccess}</p>}
        {feeWorking && <p className="parent-policy-note" role="status">Checking your school-fee payment…</p>}
        {fees?.summary && <div className="parent-attendance-stats parent-fee-stats">{[['Expected', fees.summary.expected_minor], ['Paid', fees.summary.paid_minor], ['Outstanding', fees.summary.outstanding_minor], ['Available credit', fees.summary.credit_minor]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format((value || 0) / 100)}</strong></div>)}</div>}
        {currentSchoolFeeRows.length ? <form className="parent-fee-form" onSubmit={beginFeePayment}><div className="parent-fee-charge-list">{currentSchoolFeeRows.filter((row) => row.outstanding_minor > 0).map((row) => <label className="parent-fee-charge" key={row.id}><span><strong>{row.student_name}</strong><small>{row.class_name} {row.arm_name} · {row.session_name} · {row.term_name} · {row.category}</small><small>Outstanding: {new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(row.outstanding_minor / 100)}</small></span><input type="number" min="0" step="0.01" max={(row.outstanding_minor / 100).toFixed(2)} aria-label={`Amount to pay for ${row.student_name} ${row.category}`} placeholder="Amount in ₦" value={feeAmounts[row.id] || ''} onChange={(event) => setFeeAmounts((current) => ({ ...current, [row.id]: event.target.value }))} /></label>)}
          {!currentSchoolFeeRows.some((row) => row.outstanding_minor > 0) && <p>No school-fee balance is outstanding for this student.</p>}
        </div><button className="primary-button" disabled={feeWorking || !currentSchoolFeeRows.some((row) => Number(feeAmounts[row.id]) > 0)}>Continue to secure online payment</button><p className="parent-policy-note">You can enter a partial amount or pay several listed fees together. Fees from different schools must be paid in separate checkouts.</p></form> : <p>No fee records have been issued for this student yet. The school will show them here after creating a fee schedule.</p>}
        <h3>Payment history</h3>{fees?.payments?.length ? <div className="parent-fee-payments">{fees.payments.map((payment) => <article key={payment.reference}><div><strong>{payment.reference}</strong><span>{new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(payment.amount_minor / 100)} · {payment.channel === 'physical' ? 'Paid at school' : 'Online'} · {payment.status} · {new Date(payment.created_at).toLocaleDateString()}</span></div><div><button className="secondary-button" type="button" onClick={() => downloadFeeReceipt(payment.reference)} disabled={payment.status === 'pending' || payment.status === 'failed'}>Download receipt</button><button className="text-button" type="button" onClick={() => setReceiptCodeOpen((current) => current === payment.reference ? '' : payment.reference)}>Verify receipt</button></div>{receiptCodeOpen === payment.reference && <div className="parent-receipt-code"><button className="text-button" type="button" onClick={() => verifyFeeReceipt(payment.reference, true)}>Send a receipt code by SMS</button><form onSubmit={(event) => { event.preventDefault(); verifyFeeReceipt(payment.reference) }}><label>6-digit code<input inputMode="numeric" maxLength="6" placeholder="Enter code sent to the guardian phone" value={receiptCode[payment.reference] || ''} onChange={(event) => setReceiptCode((current) => ({ ...current, [payment.reference]: event.target.value.replace(/\D/g, '') }))} /></label><button className="secondary-button" type="submit">Verify receipt</button></form></div>}</article>)}</div> : <p>Payments and downloadable receipts will appear here after a school records or confirms them.</p>}
      </section>}

      <section className="parent-panel"><p className="panel-kicker">SCHOOL NEWS</p><h2>Announcements</h2>
        {announcements.length ? <div className="parent-announcements">{announcements.map((item) => <article key={item.id}><span>{item.school_name} · {new Date(item.published_at).toLocaleDateString()}</span><h3>{item.title}</h3><p>{item.message}</p></article>)}</div> : <p>There are no current announcements from your students’ schools.</p>}
      </section>

      <section className="parent-panel"><p className="panel-kicker">PORTAL NOTIFICATIONS</p><h2>Updates</h2>
        {notifications.length ? <div className="parent-notifications">{notifications.map((item) => <article key={item.id} className={item.read_at ? 'read' : 'unread'}><div><strong>{item.title}</strong><p>{item.message}</p><span>{new Date(item.created_at).toLocaleString()}</span></div>{!item.read_at && <button className="text-button" onClick={() => markRead(item)}>Mark read</button>}</article>)}</div> : <p>You’re up to date. New published reports and announcements will appear here.</p>}
      </section>
    </section>
  </main>
}
