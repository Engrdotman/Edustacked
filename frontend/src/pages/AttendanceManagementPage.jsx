import { useCallback, useEffect, useMemo, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { apiRequest } from '../services/api.js'

const todayText = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
const shiftDate = (value, days) => {
  const date = new Date(`${value}T12:00:00`)
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
const statusLabels = { present: 'Present', absent: 'Absent', late: 'Late', excused: 'Excused absence' }

export default function AttendanceManagementPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const role = selectedSchool?.role
  const canManage = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(role)
  const [date, setDate] = useState(todayText)
  const [options, setOptions] = useState({ sessions: [], classes: [], terms: [] })
  const [selection, setSelection] = useState({ academic_session: '', class_level: '', class_arm: '' })
  const [roster, setRoster] = useState([])
  const [register, setRegister] = useState(null)
  const [registers, setRegisters] = useState([])
  const [from, setFrom] = useState(shiftDate(todayText(), -30))
  const [to, setTo] = useState(todayText)
  const [registerFilters, setRegisterFilters] = useState({ academic_session: '', class_level: '', class_arm: '', status: '' })
  const [report, setReport] = useState(null)
  const [historyStudent, setHistoryStudent] = useState('')
  const [history, setHistory] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const arms = useMemo(() => options.classes.find((item) => String(item.id) === String(selection.class_level))?.arms || [], [options.classes, selection.class_level])
  const term = useMemo(() => options.terms.find((item) => String(item.academic_session_id) === String(selection.academic_session) && item.start_date <= date && item.end_date >= date), [options.terms, selection.academic_session, date])
  const filteredRoster = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return roster
    return roster.filter((item) => `${item.first_name} ${item.middle_name || ''} ${item.last_name} ${item.admission_number}`.toLowerCase().includes(query))
  }, [roster, search])

  const loadOptions = useCallback(async (selectedDate = date) => {
    const data = await apiRequest(`attendance/options/?date=${selectedDate}`)
    setOptions(data)
    if (selection.class_level && !data.classes.some((item) => String(item.id) === String(selection.class_level))) {
      setSelection((current) => ({ ...current, class_level: '', class_arm: '' }))
    }
  }, [date, selection.class_level])

  const loadRegisters = useCallback(async (filters = registerFilters) => {
    const params = new URLSearchParams({ date_from: from, date_to: to })
    Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value) })
    const result = await apiRequest(`attendance/registers/?${params}`)
    setRegisters(result.results || [])
  }, [from, to, registerFilters])

  useEffect(() => {
    let live = true
    Promise.all([apiRequest(`attendance/options/?date=${date}`), apiRequest(`attendance/registers/?date_from=${shiftDate(date, -30)}&date_to=${date}`)])
      .then(([optionData, registerData]) => {
        if (!live) return
        setOptions(optionData)
        setRegisters(registerData.results || [])
        if (optionData.sessions.length) setSelection((current) => ({ ...current, academic_session: current.academic_session || String(optionData.sessions[0].id) }))
      })
      .catch((e) => live && setError(e.message || 'Could not load attendance setup.'))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [])

  async function chooseDate(value) {
    setDate(value); setRegister(null); setRoster([]); setError(''); setMessage('')
    try { await loadOptions(value) } catch (e) { setError(e.message || 'Could not load attendance options.') }
  }

  async function loadEligible() {
    setError(''); setMessage(''); setRegister(null)
    if (!selection.academic_session || !selection.class_level || !selection.class_arm) {
      setError('Choose a session, class, and arm first.'); return
    }
    if (!term) { setError('The selected date must fall within a term in this session.'); return }
    setWorking(true)
    try {
      const params = new URLSearchParams({ academic_session: selection.academic_session, class_level: selection.class_level, class_arm: selection.class_arm, date })
      const rows = await apiRequest(`attendance/eligible-students/?${params}`)
      setRoster(rows.map((item) => ({ ...item, student_id: item.id, note: item.note || '' })))
      setMessage(`${rows.length} eligible student${rows.length === 1 ? '' : 's'} loaded.`)
    } catch (e) { setRoster([]); setError(e.message || 'Could not load eligible students.') }
    finally { setWorking(false) }
  }

  async function createRegister() {
    if (!term || !roster.length) return
    setWorking(true); setError(''); setMessage('')
    try {
      const created = await apiRequest('attendance/registers/create/', { method: 'POST', body: { ...selection, academic_session: Number(selection.academic_session), class_level: Number(selection.class_level), class_arm: Number(selection.class_arm), term: term.id, attendance_date: date } })
      setRegister(created); setRoster(created.records.map((row) => ({ ...row, student_id: row.student, id: row.student })))
      setMessage('Draft register created with a saved roster snapshot.'); await loadRegisters()
    } catch (e) { setError(e.message || 'Could not create the register.') }
    finally { setWorking(false) }
  }

  async function openRegister(item) {
    setError(''); setMessage(''); setWorking(true)
    try {
      const detail = await apiRequest(`attendance/registers/${item.id}/`)
      setRegister(detail); setDate(detail.attendance_date)
      setSelection({ academic_session: String(detail.academic_session), class_level: String(detail.class_level), class_arm: String(detail.class_arm) })
      setRoster(detail.records.map((row) => ({ ...row, student_id: row.student, id: row.student })))
      setHistory([]); setHistoryStudent('')
    } catch (e) { setError(e.message || 'Could not open this register.') }
    finally { setWorking(false) }
  }

  function updateRoster(studentId, changes) {
    setRoster((current) => current.map((item) => item.student_id === studentId ? { ...item, ...changes } : item))
  }

  async function saveDraft() {
    if (!register) return
    const changedRows = roster.filter((item) => item.status)
    if (!changedRows.length) { setError('Mark at least one student before saving.'); return }
    setWorking(true); setError(''); setMessage('')
    try {
      const saved = await apiRequest(`attendance/registers/${register.id}/records/`, { method: 'PATCH', body: {
        version: register.version,
        records: changedRows.map((item) => ({ student_id: item.student_id, status: item.status, note: item.note || '', reason: item.reason || '' })),
      } })
      setRegister(saved); setRoster(saved.records.map((row) => ({ ...row, student_id: row.student, id: row.student })))
      setMessage('Attendance saved as a draft.'); await loadRegisters()
    } catch (e) { setError(e.message || 'Could not save attendance.') }
    finally { setWorking(false) }
  }

  async function runRegisterAction(action) {
    if (!register) return
    if (action === 'submit' && !window.confirm('Submit this register? All eligible students must have a status.')) return
    if (action === 'finalize' && !window.confirm('Finalize this register? It will be locked until an administrator reopens it.')) return
    let reason = ''
    if (action === 'reopen') {
      reason = window.prompt('Reason for reopening this register:') || ''
      if (!reason.trim()) return
    }
    setWorking(true); setError(''); setMessage('')
    try {
      const result = await apiRequest(`attendance/registers/${register.id}/${action}/`, { method: 'POST', body: { version: register.version, reason } })
      setRegister(result); setRoster(result.records.map((row) => ({ ...row, student_id: row.student, id: row.student })))
      const actionLabels = { submit: 'submitted', finalize: 'finalized', reopen: 'reopened' }
      setMessage(`Register ${actionLabels[action]}.`); await loadRegisters()
    } catch (e) { setError(e.message || `Could not ${action} the register.`) }
    finally { setWorking(false) }
  }

  async function loadReport() {
    setError(''); setWorking(true)
    try {
      const result = await apiRequest(`attendance/reports/summary/?date_from=${from}&date_to=${to}`)
      setReport(result)
    } catch (e) { setError(e.message || 'Could not load attendance summary.') }
    finally { setWorking(false) }
  }

  async function loadStudentHistory(studentId) {
    setHistoryStudent(studentId); setError('')
    if (!studentId) { setHistory([]); return }
    try {
      const result = await apiRequest(`attendance/students/${studentId}/history/`)
      setHistory(result.results || result || [])
    } catch (e) { setError(e.message || 'Could not load student history.') }
  }

  const editable = register && register.status !== 'finalized' && (register.status === 'draft' || canManage)
  const allMarked = roster.length > 0 && roster.every((item) => Boolean(item.status))

  return <main className="app-page"><header className="app-topbar"><BrandMark /><button className="text-button" onClick={() => navigate('/app')}>Back to home</button></header>
    <section className="app-content attendance-page"><p className="eyebrow">{selectedSchool?.school_name} · ATTENDANCE</p><h1 className="app-heading">Student <em>attendance</em></h1><p className="intro">Create a dated class register, record each eligible student, and keep corrections auditable.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="form-success" role="status">{message}</p>}{loading && <p className="loading-message" role="status">Loading attendance…</p>}
      <section className="attendance-panel"><div className="attendance-panel-heading"><div><p className="panel-kicker">CLASS REGISTER</p><h2>Take attendance</h2></div>{register && <span className={`attendance-state attendance-state-${register.status}`}>{register.status} · version {register.version}</span>}</div>
        <div className="attendance-selectors"><label>Session<select value={selection.academic_session} onChange={(e) => setSelection({ ...selection, academic_session: e.target.value })}><option value="">Select session</option>{options.sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Date<input type="date" value={date} max={todayText()} onChange={(e) => chooseDate(e.target.value)} /></label><label>Class<select value={selection.class_level} onChange={(e) => setSelection({ ...selection, class_level: e.target.value, class_arm: '' })}><option value="">Select class</option>{options.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Arm<select value={selection.class_arm} onChange={(e) => setSelection({ ...selection, class_arm: e.target.value })}><option value="">Select arm</option>{arms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="attendance-term">Term<strong>{term?.name || 'No term for selected date'}</strong></div></div>
        <div className="attendance-actions"><button className="secondary-button" type="button" onClick={loadEligible} disabled={working}>{working ? 'Loading…' : 'Load eligible students'}</button>{!register && roster.length > 0 && <button className="primary-button" type="button" onClick={createRegister} disabled={working}>Create draft register</button>}</div>
        {register && <><div className="attendance-register-tools"><input aria-label="Search register" placeholder="Search name or admission number" value={search} onChange={(e) => setSearch(e.target.value)} /><strong>{roster.filter((item) => item.status).length} / {roster.length} marked</strong></div>
          <div className="attendance-roster">{filteredRoster.map((item) => <div className="attendance-student" key={item.student_id}><div className="attendance-student-name"><strong>{item.last_name}, {item.first_name} {item.middle_name}</strong><span>{item.admission_number}</span></div><label>Status<select value={item.status || ''} disabled={!editable || working} onChange={(e) => updateRoster(item.student_id, { status: e.target.value, reason: '' })}><option value="">Not marked</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Note<input value={item.note || ''} disabled={!editable || working} maxLength={300} onChange={(e) => updateRoster(item.student_id, { note: e.target.value })} /></label></div>)}{!filteredRoster.length && <p className="academic-empty">No eligible students match this search.</p>}</div>
          <div className="attendance-actions">{editable && <button className="primary-button" type="button" onClick={saveDraft} disabled={working}>Save draft</button>}{register.status === 'draft' && <button className="secondary-button" type="button" onClick={() => runRegisterAction('submit')} disabled={working || !allMarked}>Submit register</button>}{canManage && register.status === 'submitted' && <button className="primary-button" type="button" onClick={() => runRegisterAction('finalize')} disabled={working}>Finalize register</button>}{canManage && register.status === 'finalized' && <button className="secondary-button" type="button" onClick={() => runRegisterAction('reopen')} disabled={working}>Reopen for correction</button>}</div>
          {register.audit_events?.length > 0 && <details className="attendance-audit"><summary>Register audit history ({register.audit_events.length})</summary>{register.audit_events.map((event) => <p key={event.id}>{event.event_type} · {event.actor_name} · {new Date(event.created_at).toLocaleString()}{event.reason ? ` · ${event.reason}` : ''}</p>)}</details>}
        </>}
      </section>

      <section className="attendance-panel"><div className="attendance-panel-heading"><div><p className="panel-kicker">REGISTER HISTORY</p><h2>Review registers</h2></div></div><div className="attendance-selectors"><label>From<input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} /></label><label>To<input type="date" value={to} min={from} max={todayText()} onChange={(e) => setTo(e.target.value)} /></label><label>Session<select value={registerFilters.academic_session} onChange={(e) => setRegisterFilters({ ...registerFilters, academic_session: e.target.value })}><option value="">All sessions</option>{options.sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Class<select value={registerFilters.class_level} onChange={(e) => setRegisterFilters({ ...registerFilters, class_level: e.target.value })}><option value="">All classes</option>{options.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Status<select value={registerFilters.status} onChange={(e) => setRegisterFilters({ ...registerFilters, status: e.target.value })}><option value="">All statuses</option><option value="draft">Draft</option><option value="submitted">Submitted</option><option value="finalized">Finalized</option></select></label><button className="secondary-button" type="button" onClick={() => loadRegisters()} disabled={working}>Filter</button></div><div className="attendance-register-list">{registers.map((item) => <button className="attendance-register-row" key={item.id} onClick={() => openRegister(item)}><strong>{item.attendance_date} · {item.class_name} {item.arm_name}</strong><span>{item.session_name} · {item.term_name} · {item.status} · {item.total_students} students</span></button>)}{!registers.length && <p className="academic-empty">No registers in this date range.</p>}</div></section>

      <section className="attendance-panel"><div className="attendance-panel-heading"><div><p className="panel-kicker">FINALIZED SUMMARY</p><h2>Attendance report</h2></div><button className="secondary-button" onClick={loadReport} disabled={working}>Refresh report</button></div><p className="attendance-policy">Only finalized registers count. Present and late count as attended; excused absences remain in the denominator. Missing registers are excluded.</p>{report && <><div className="attendance-totals">{[['Present', report.totals.present], ['Absent', report.totals.absent], ['Late', report.totals.late], ['Excused', report.totals.excused], ['Attendance', `${report.totals.attendance_percentage}%`]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="attendance-register-list">{report.daily.map((item) => <div className="attendance-register-row" key={item.register__attendance_date}><strong>{item.register__attendance_date}</strong><span>{item.present} present · {item.absent} absent · {item.late} late · {item.excused} excused · {item.total} recorded</span></div>)}{!report.daily.length && <p className="academic-empty">No finalized records for this date range.</p>}</div></>}
        <label className="attendance-history-select">Student history<select value={historyStudent} onChange={(e) => loadStudentHistory(e.target.value)}><option value="">Choose a student from the loaded register</option>{roster.map((item) => <option key={item.student_id} value={item.student_id}>{item.admission_number} · {item.first_name} {item.last_name}</option>)}</select></label>{history.length > 0 && <div className="attendance-register-list">{history.map((item) => <div key={item.id} className="attendance-register-row"><strong>{item.attendance_date} · {statusLabels[item.status]}</strong><span>{item.note || item.register_status}</span></div>)}</div>}
      </section>
    </section>
  </main>
}
