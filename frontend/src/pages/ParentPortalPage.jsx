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
    ]).then(([overview, attendanceData, reportRows]) => {
      if (!active) return
      setStudent(overview)
      setAttendance(attendanceData)
      setReports(reportRows)
    }).catch((requestError) => active && setError(errorText(requestError)))
    return () => { active = false }
  }, [studentId])

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

  if (loading) return <main className="auth-page"><p className="loading-message" role="status">Loading your parent portal…</p></main>

  return <main className="app-page parent-portal-page">
    <header className="app-topbar"><BrandMark /><div className="parent-header-actions"><span>{profile?.first_name || user?.first_name || profile?.email}</span><button className="text-button" onClick={logOut}>Sign out</button></div></header>
    <section className="app-content parent-content">
      <p className="eyebrow">EDUstacked · PARENT / GUARDIAN PORTAL</p>
      <h1 className="app-heading">Your family’s<br /><em>school updates.</em></h1>
      <p className="intro">View information for students linked to your account by their school.</p>
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

      <section className="parent-panel"><p className="panel-kicker">SCHOOL NEWS</p><h2>Announcements</h2>
        {announcements.length ? <div className="parent-announcements">{announcements.map((item) => <article key={item.id}><span>{item.school_name} · {new Date(item.published_at).toLocaleDateString()}</span><h3>{item.title}</h3><p>{item.message}</p></article>)}</div> : <p>There are no current announcements from your students’ schools.</p>}
      </section>

      <section className="parent-panel"><p className="panel-kicker">PORTAL NOTIFICATIONS</p><h2>Updates</h2>
        {notifications.length ? <div className="parent-notifications">{notifications.map((item) => <article key={item.id} className={item.read_at ? 'read' : 'unread'}><div><strong>{item.title}</strong><p>{item.message}</p><span>{new Date(item.created_at).toLocaleString()}</span></div>{!item.read_at && <button className="text-button" onClick={() => markRead(item)}>Mark read</button>}</article>)}</div> : <p>You’re up to date. New published reports and announcements will appear here.</p>}
      </section>
    </section>
  </main>
}
