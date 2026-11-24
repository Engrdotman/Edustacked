import { useCallback, useEffect, useMemo, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { apiRequest } from '../services/api.js'
import {
  finishOfflineAttendanceSync,
  getOfflineAttendanceRegister,
  listOfflineAttendanceRegisters,
  markOfflineAttendanceSyncError,
  markOfflineAttendanceSyncStarted,
  prepareOfflineAttendance,
  renewOfflineAttendanceGrant,
  saveOfflineAttendanceDraft,
} from '../services/offlineAttendance.js'

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
const displayDate = (value) => value ? new Date(`${value}T12:00:00`).toLocaleDateString() : ''
const rosterFromRegister = (detail) => detail.records.map((row) => ({
  ...row,
  student_id: row.student,
  id: row.student,
  original_status: row.status,
  reason: '',
}))

export default function AttendanceManagementPage({ navigate, registerMode = false }) {
  const { user, selectedSchool, offlineMode } = useAuth()
  const role = selectedSchool?.role
  const canManage = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(role)
  const [date, setDate] = useState(() => new URLSearchParams(window.location.search).get('date') || todayText())
  const [options, setOptions] = useState({ sessions: [], classes: [], terms: [] })
  const [selection, setSelection] = useState(() => {
    const query = new URLSearchParams(window.location.search)
    return { academic_session: query.get('academic_session') || '', class_level: query.get('class_level') || '', class_arm: query.get('class_arm') || '' }
  })
  const [roster, setRoster] = useState([])
  const [register, setRegister] = useState(null)
  const [registers, setRegisters] = useState([])
  const [offlineRegisters, setOfflineRegisters] = useState([])
  const [offlineEntry, setOfflineEntry] = useState(null)
  const [online, setOnline] = useState(() => navigator.onLine)
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
  const [clock, setClock] = useState(Date.now())

  useEffect(() => {
    const updateOnline = () => setOnline(navigator.onLine)
    window.addEventListener('online', updateOnline)
    window.addEventListener('offline', updateOnline)
    return () => {
      window.removeEventListener('online', updateOnline)
      window.removeEventListener('offline', updateOnline)
    }
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const arms = useMemo(() => options.classes.find((item) => String(item.id) === String(selection.class_level))?.arms || [], [options.classes, selection.class_level])
  const selectedSession = useMemo(() => options.sessions.find((item) => String(item.id) === String(selection.academic_session)), [options.sessions, selection.academic_session])
  const sessionTerms = useMemo(() => options.terms.filter((item) => String(item.academic_session_id) === String(selection.academic_session)), [options.terms, selection.academic_session])
  const term = useMemo(() => options.terms.find((item) => String(item.academic_session_id) === String(selection.academic_session) && item.start_date <= date && item.end_date >= date), [options.terms, selection.academic_session, date])
  const filteredRoster = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return roster
    return roster.filter((item) => `${item.first_name} ${item.middle_name || ''} ${item.last_name} ${item.admission_number}`.toLowerCase().includes(query))
  }, [roster, search])

  const loadOptions = useCallback(async (selectedDate = date) => {
    const data = await apiRequest(`attendance/options/?date=${selectedDate}`)
    setOptions(data)
    setSelection((current) => {
      const matchingSession = data.sessions.find((item) => item.start_date <= selectedDate && item.end_date >= selectedDate)
      const existingSession = data.sessions.find((item) => String(item.id) === String(current.academic_session))
      const nextSession = matchingSession || (existingSession && existingSession.start_date <= selectedDate && existingSession.end_date >= selectedDate ? existingSession : data.sessions[0])
      const currentClass = data.classes.find((item) => String(item.id) === String(current.class_level))
      const currentArm = currentClass?.arms.find((item) => String(item.id) === String(current.class_arm))
      return {
        ...current,
        academic_session: nextSession ? String(nextSession.id) : '',
        class_level: currentClass ? current.class_level : '',
        class_arm: currentArm ? current.class_arm : '',
      }
    })
  }, [date])

  const loadRegisters = useCallback(async (filters = registerFilters) => {
    if (!online || offlineMode) {
      const saved = await listOfflineAttendanceRegisters(user?.id, selectedSchool?.school_id)
      setOfflineRegisters(saved)
      return
    }
    const params = new URLSearchParams({ date_from: from, date_to: to })
    Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value) })
    const result = await apiRequest(`attendance/registers/?${params}`)
    setRegisters(result.results || [])
    const saved = await listOfflineAttendanceRegisters(user?.id, selectedSchool?.school_id).catch(() => [])
    setOfflineRegisters(saved)
  }, [from, to, registerFilters, online, offlineMode, user?.id, selectedSchool?.school_id])

  useEffect(() => {
    let live = true
    const query = new URLSearchParams(window.location.search)
    const requestedRegister = query.get('register')
    async function restore() {
      try {
        const [optionData, registerData] = await Promise.all([
          apiRequest(`attendance/options/?date=${date}`),
          apiRequest(`attendance/registers/?date_from=${shiftDate(date, -30)}&date_to=${date}`),
        ])
        if (!live) return
        setOptions(optionData)
        setRegisters(registerData.results || [])
        const dateSession = optionData.sessions.find((item) => item.start_date <= date && item.end_date >= date) || optionData.sessions[0]
        const requestedSession = optionData.sessions.find((item) => String(item.id) === query.get('academic_session'))
        const requestedClass = optionData.classes.find((item) => String(item.id) === query.get('class_level'))
        const requestedArm = requestedClass?.arms.find((item) => String(item.id) === query.get('class_arm'))
        const nextSelection = {
          academic_session: String(requestedSession?.id || dateSession?.id || ''),
          class_level: String(requestedClass?.id || ''),
          class_arm: String(requestedArm?.id || ''),
        }
        setSelection(nextSelection)
        const savedEntries = await listOfflineAttendanceRegisters(user?.id, selectedSchool?.school_id).catch(() => [])
        if (live) setOfflineRegisters(savedEntries)
        if (registerMode && requestedRegister) {
          const detail = await apiRequest(`attendance/registers/${encodeURIComponent(requestedRegister)}/`)
          if (!live) return
          const stored = await getOfflineAttendanceRegister(user?.id, selectedSchool?.school_id, requestedRegister).catch(() => null)
          const active = stored?.pending ? stored : null
          setOfflineEntry(stored)
          setRegister(active?.register || detail)
          setDate((active?.register || detail).attendance_date)
          setSelection({ academic_session: String(detail.academic_session), class_level: String(detail.class_level), class_arm: String(detail.class_arm) })
          setRoster(active?.roster || rosterFromRegister(detail))
          if (active?.pending) setMessage(active.pending.state === 'conflict'
            ? 'Your offline attendance is safe on this device, but the school register changed. Review the conflict before trying to sync again.'
            : 'An offline attendance draft is waiting to sync to the school workspace.')
          return
        }
        if (registerMode && nextSelection.academic_session && nextSelection.class_level && nextSelection.class_arm) {
          const params = new URLSearchParams({ ...nextSelection, date })
          const rows = await apiRequest(`attendance/eligible-students/?${params}`)
          if (!live) return
          setRoster(rows.map((item) => ({ ...item, student_id: item.id, note: item.note || '', original_status: null })))
          setMessage(rows.length ? `${rows.length} eligible student${rows.length === 1 ? '' : 's'} loaded.` : '')
          if (!rows.length) setError('No students are eligible for this date and placement. Check the selected class, arm, session, and student enrollment dates.')
        }
      } catch (e) {
        if (!live) return
        const storedEntries = await listOfflineAttendanceRegisters(user?.id, selectedSchool?.school_id).catch(() => [])
        setOfflineRegisters(storedEntries)
        if (registerMode && requestedRegister) {
          const stored = await getOfflineAttendanceRegister(user?.id, selectedSchool?.school_id, requestedRegister).catch(() => null)
          if (stored) {
            setOfflineEntry(stored)
            setOptions(stored.options || { sessions: [], classes: [], terms: [] })
            setRegister(stored.register)
            setDate(stored.register.attendance_date)
            setSelection({ academic_session: String(stored.register.academic_session), class_level: String(stored.register.class_level), class_arm: String(stored.register.class_arm) })
            setRoster(stored.roster || rosterFromRegister(stored.register))
            setMessage(stored.pending
              ? stored.pending.state === 'conflict'
                ? 'This register has a sync conflict. Your offline marks remain saved on this device; reconnect and review before syncing.'
                : 'Offline register opened. Your unsynced marks remain on this device until you sync.'
              : 'Offline register opened. Marks are saved on this device and are not yet in the school workspace.')
            return
          }
        }
        setError(online
          ? (e.message || 'Could not load attendance setup.')
          : 'No prepared attendance register is available on this device. Connect to the internet, open the register, and choose “Prepare for offline use” first.')
      } finally {
        if (live) setLoading(false)
      }
    }
    restore()
    return () => { live = false }
  }, [date, registerMode, user?.id, selectedSchool?.school_id, online])

  async function chooseDate(value) {
    setDate(value); setRegister(null); setRoster([]); setError(''); setMessage('')
    try { await loadOptions(value) } catch (e) { setError(e.message || 'Could not load attendance options.') }
  }

  async function loadEligible() {
    setError(''); setMessage(''); setRegister(null)
    if (!selection.academic_session || !selection.class_level || !selection.class_arm) {
      setError('Choose a session, class, and arm first.'); return
    }
    if (!term) {
      const ranges = sessionTerms.map((item) => `${item.name}: ${displayDate(item.start_date)}–${displayDate(item.end_date)}`).join(' · ')
      setError(sessionTerms.length
        ? `Choose a date within a term in ${selectedSession?.name || 'the selected session'}. Valid dates: ${ranges}.`
        : `No terms are set up for ${selectedSession?.name || 'this session'}. Ask a school administrator to add term dates in Classes & subjects, then try attendance again.`)
      return
    }
    setWorking(true)
    try {
      const params = new URLSearchParams({ academic_session: selection.academic_session, class_level: selection.class_level, class_arm: selection.class_arm, date })
      const rows = await apiRequest(`attendance/eligible-students/?${params}`)
      setRoster(rows.map((item) => ({ ...item, student_id: item.id, note: item.note || '' })))
      if (rows.length === 0) {
        setError('No students are eligible for this date and placement. A student needs an active or completed enrollment in the selected session, class, and arm, with an enrollment date on or before the attendance date. Check the enrollment status and date, or choose a later date.')
      } else {
        setMessage(`${rows.length} eligible student${rows.length === 1 ? '' : 's'} loaded.`)
      }
      const route = new URLSearchParams({ ...selection, date })
      navigate(`/app/attendance/register?${route}`)
    } catch (e) { setRoster([]); setError(e.message || 'Could not load eligible students.') }
    finally { setWorking(false) }
  }

  async function createRegister() {
    if (!term || !roster.length) return
    setWorking(true); setError(''); setMessage('')
    try {
      const created = await apiRequest('attendance/registers/create/', { method: 'POST', body: { ...selection, academic_session: Number(selection.academic_session), class_level: Number(selection.class_level), class_arm: Number(selection.class_arm), term: term.id, attendance_date: date } })
      setRegister(created); setRoster(rosterFromRegister(created))
      setMessage('Draft register created with a saved roster snapshot.')
      const route = new URLSearchParams({ ...selection, date, register: String(created.id) })
      navigate(`/app/attendance/register?${route}`)
      await loadRegisters()
    } catch (e) { setError(e.message || 'Could not create the register.') }
    finally { setWorking(false) }
  }

  async function openRegister(item) {
    setError(''); setMessage(''); setWorking(true)
    try {
      let detail
      let stored
      if (!online || offlineMode) {
        stored = await getOfflineAttendanceRegister(user?.id, selectedSchool?.school_id, item.id)
        if (!stored) throw new Error('This register was not prepared on this device. Open it while online and choose “Prepare for offline use”.')
        detail = stored.register
      } else {
        stored = await getOfflineAttendanceRegister(user?.id, selectedSchool?.school_id, item.id).catch(() => null)
        try {
          detail = await apiRequest(`attendance/registers/${item.id}/`)
        } catch (networkError) {
          if (!stored) throw networkError
          detail = stored.register
        }
      }
      setRegister(detail); setDate(detail.attendance_date)
      setSelection({ academic_session: String(detail.academic_session), class_level: String(detail.class_level), class_arm: String(detail.class_arm) })
      setOfflineEntry(stored)
      setRoster(stored?.pending ? stored.roster : rosterFromRegister(detail))
      if (!online || offlineMode) setMessage('Offline register opened. Save marks on this device, then sync when connected.')
      setHistory([]); setHistoryStudent('')
      const route = new URLSearchParams({ academic_session: String(detail.academic_session), class_level: String(detail.class_level), class_arm: String(detail.class_arm), date: detail.attendance_date, register: String(detail.id) })
      navigate(`/app/attendance/register?${route}`)
    } catch (e) { setError(e.message || 'Could not open this register.') }
    finally { setWorking(false) }
  }

  function updateRoster(studentId, changes) {
    setRoster((current) => current.map((item) => item.student_id === studentId ? { ...item, ...changes } : item))
  }

  function changeStudentStatus(item, nextStatus) {
    let reason = ''
    if (item.original_status && item.original_status !== nextStatus) {
      reason = window.prompt(`Why are you changing ${item.admission_number}'s saved attendance status?`) || ''
      if (!reason.trim()) return
    }
    updateRoster(item.student_id, { status: nextStatus, reason: nextStatus === item.original_status ? '' : reason.trim() })
  }

  async function prepareRegisterOffline() {
    if (!register || !user || !selectedSchool || !online || offlineMode) return
    setWorking(true); setError(''); setMessage('')
    try {
      const grant = await apiRequest('attendance/offline/grants/', {
        method: 'POST', body: { register_id: register.id },
      })
      if (!grant?.token || !grant?.register || !grant?.expires_at) {
        throw new Error('The server did not confirm offline access. Connect to the internet and try again; no offline register was prepared.')
      }
      if (offlineEntry?.pending) {
        await renewOfflineAttendanceGrant({
          userId: user.id, schoolId: selectedSchool.school_id, user, selectedSchool, register: grant.register,
          token: grant.token, expiresAt: grant.expires_at,
        })
      } else {
        await prepareOfflineAttendance({
          user,
          selectedSchool,
          register: grant.register,
          roster: rosterFromRegister(grant.register),
          options,
          token: grant.token,
          expiresAt: grant.expires_at,
        })
      }
      const saved = await getOfflineAttendanceRegister(user.id, selectedSchool.school_id, register.id)
      setOfflineEntry(saved)
      if (!saved?.pending) {
        setRegister(grant.register)
        setRoster(saved?.roster || rosterFromRegister(grant.register))
      }
      setMessage(saved?.pending
        ? `Offline access renewed without replacing your saved marks. They are ready to sync until ${new Date(grant.expires_at).toLocaleString()}.`
        : `This register is ready for offline use on this device until ${new Date(grant.expires_at).toLocaleString()}.`)
      setOfflineRegisters(await listOfflineAttendanceRegisters(user.id, selectedSchool.school_id))
    } catch (e) {
      setError(e.message || 'Could not prepare this register for offline use. Keep this page open and try again while connected.')
    } finally { setWorking(false) }
  }

  async function syncOfflineAttendance() {
    const pending = offlineEntry?.pending
    if (!pending || !offlineEntry?.token) return
    if (!online) { setError('Connect to the internet before syncing attendance to the school workspace.'); return }
    if (pending.state === 'conflict') {
      setError('The school register changed after this device went offline. Your marks are safe here. Reopen the latest register while online and reconcile the marked students before preparing a new offline copy.')
      return
    }
    setWorking(true); setError(''); setMessage('')
    try {
      await markOfflineAttendanceSyncStarted(user.id, selectedSchool.school_id, register.id, pending.syncId)
      const saved = await apiRequest('attendance/offline/sync/', {
        method: 'POST',
        headers: { Authorization: `Offline ${offlineEntry.token}` },
        body: { version: pending.version, sync_id: pending.syncId, records: pending.records },
      }, false)
      if (!Array.isArray(saved?.records) || !saved.version) {
        throw new Error('The server did not confirm the attendance sync. Your marks remain saved on this device; reconnect and try again.')
      }
      const updated = await finishOfflineAttendanceSync(user.id, selectedSchool.school_id, register.id, pending.syncId, saved)
      setOfflineEntry(updated)
      setRegister(saved)
      setRoster(rosterFromRegister(saved))
      setMessage('Attendance synced to the school workspace. Your draft is now up to date.')
      await loadRegisters()
    } catch (e) {
      const conflict = e.statusCode === 409
      await markOfflineAttendanceSyncError(user.id, selectedSchool.school_id, register.id, pending.syncId, e.message || '', conflict).catch(() => {})
      const preserved = await getOfflineAttendanceRegister(user.id, selectedSchool.school_id, register.id).catch(() => offlineEntry)
      setOfflineEntry(preserved)
      setError(conflict
        ? 'The school register changed while you were offline. Your saved marks remain on this device and have not overwritten the newer register. Ask an administrator to help reconcile them.'
        : (e.message || 'Attendance is still saved on this device. Reconnect and try syncing again.'))
    } finally { setWorking(false) }
  }

  async function saveCurrentDraftOnDevice() {
    const pending = await saveOfflineAttendanceDraft({
      userId: user.id,
      schoolId: selectedSchool.school_id,
      registerId: register.id,
      register,
      roster,
    })
    const saved = await getOfflineAttendanceRegister(user.id, selectedSchool.school_id, register.id)
    setOfflineEntry(saved)
    setOfflineRegisters(await listOfflineAttendanceRegisters(user.id, selectedSchool.school_id))
    return pending
  }

  async function saveDraft() {
    if (!register) return
    if (online && !offlineMode && offlineEntry?.pending) {
      setError('Sync the saved offline attendance first. This protects your offline marks from being overwritten by a newer register.')
      return
    }
    const changedRows = roster.filter((item) => item.status)
    if (!changedRows.length) { setError('Mark at least one student before saving.'); return }
    const missingReasons = changedRows.filter((item) => item.original_status && item.original_status !== item.status && !item.reason?.trim())
    if (missingReasons.length) { setError('Add a correction reason for each student whose saved attendance status you changed.'); return }
    setWorking(true); setError(''); setMessage('')
    try {
      if (!online || offlineMode) {
        const pending = await saveCurrentDraftOnDevice()
        setMessage(`Attendance saved on this device (${pending.records.length} marked). It is not in the school workspace until sync completes.`)
        return
      }
      let saved
      try {
        saved = await apiRequest(`attendance/registers/${register.id}/records/`, { method: 'PATCH', body: {
          version: register.version,
          records: changedRows.map((item) => ({ student_id: item.student_id, status: item.status, note: item.note || '', reason: item.reason || '' })),
        } })
        if (!Array.isArray(saved?.records) || !saved.version) throw new Error('The server did not confirm that attendance was saved.')
      } catch (saveError) {
        if (!offlineEntry?.token) throw saveError
        const pending = await saveCurrentDraftOnDevice()
        setMessage(`The school workspace could not confirm the save. Your ${pending.records.length} marked records are safely saved on this device only; reconnect and sync them.`)
        return
      }
      setRegister(saved); setRoster(rosterFromRegister(saved)); setOfflineEntry(null)
      setMessage('Attendance saved as a draft.'); await loadRegisters()
    } catch (e) { setError(e.message || 'Could not save attendance.') }
    finally { setWorking(false) }
  }

  async function runRegisterAction(action) {
    if (!register) return
    if (!online || offlineMode) { setError('Submitting and finalizing registers needs an internet connection. Your saved offline marks can sync when you reconnect.'); return }
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
      setRegister(result); setRoster(rosterFromRegister(result))
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
  const editingOffline = !online || offlineMode
  const offlineGrantExpired = Boolean(offlineEntry?.expiresAt && Date.parse(offlineEntry.expiresAt) <= clock)
  const offlineExpired = Boolean(editingOffline && offlineGrantExpired)
  const offlineQueueBlocked = ['inflight', 'conflict'].includes(offlineEntry?.pending?.state)
  const hasUnsavedStatusChanges = roster.some((item) => item.status !== item.original_status)

  return <main className="app-page"><header className="app-topbar"><BrandMark navigate={navigate} /><button className="text-button" onClick={() => navigate(registerMode ? '/app/attendance' : '/app')}>{registerMode ? 'Back to attendance' : 'Back to dashboard'}</button></header>
    <section className={`app-content attendance-page${registerMode ? ' attendance-register-mode' : ''}`}><p className="eyebrow">{selectedSchool?.school_name} · ATTENDANCE</p><h1 className="app-heading">{registerMode ? <>Take <em>attendance</em></> : <>Student <em>attendance</em></>}</h1><p className="intro">{registerMode ? 'Record each student’s attendance for the selected class and date.' : 'Create a dated class register, review attendance history, and check finalized summaries.'}</p>
      {editingOffline && <aside className="attendance-offline-notice" role="status"><strong>You’re offline</strong><span>Only registers prepared on this device can be marked. Save your draft here, then sync it when your connection returns. Offline access expires after 24 hours.</span></aside>}
      {offlineExpired && <p className="form-error" role="alert">This offline access has expired. Reconnect and prepare the register again before making more marks.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="form-success" role="status">{message}</p>}{loading && <p className="loading-message" role="status">Loading attendance…</p>}
      {!loading && !editingOffline && role === 'teacher' && options.sessions.length === 0 && <aside className="attendance-assignment-notice" role="status"><div><p className="panel-kicker">TEACHER ACCESS</p><h2>No attendance class is assigned for this date</h2><p>The attendance list only shows active teaching assignments linked to your login and covering {date}. Ask your school owner or administrator to check your staff-profile link, active teacher designation, assignment dates, session, class, and arm.</p></div><button className="secondary-button" type="button" onClick={() => navigate('/app/staff')}>View my assignments</button></aside>}
      <section className="attendance-panel"><div className="attendance-panel-heading"><div><p className="panel-kicker">{registerMode ? 'ATTENDANCE ENTRY' : 'CLASS REGISTER'}</p><h2>{registerMode ? 'Class register' : 'Take attendance'}</h2></div>{register && <span className={`attendance-state attendance-state-${register.status}`}>{register.status} · version {register.version}</span>}</div>
        {!editingOffline && (!registerMode || (!register && !roster.length)) && <div className="attendance-selectors"><label>Session<select value={selection.academic_session} onChange={(e) => setSelection({ ...selection, academic_session: e.target.value })}><option value="">Select session</option>{options.sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="attendance-date-filter">Date<input type="date" value={date} max={todayText()} onChange={(e) => chooseDate(e.target.value)} /></label><label>Class<select value={selection.class_level} onChange={(e) => setSelection({ ...selection, class_level: e.target.value, class_arm: '' })}><option value="">Select class</option>{options.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Arm<select value={selection.class_arm} onChange={(e) => setSelection({ ...selection, class_arm: e.target.value })}><option value="">Select arm</option>{arms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="attendance-term">Term<strong>{term ? `${term.name} · ${displayDate(term.start_date)}–${displayDate(term.end_date)}` : 'No term for selected date'}</strong></div></div>}
        {!editingOffline && (!registerMode || (!register && !roster.length)) && selectedSession && <p className={term ? 'attendance-term-guidance' : 'attendance-term-guidance attendance-term-guidance-warning'} role="status">{term ? `This date is within ${term.name} (${displayDate(term.start_date)}–${displayDate(term.end_date)}).` : sessionTerms.length ? `The selected date must be within one of the terms for ${selectedSession.name}: ${sessionTerms.map((item) => `${item.name}, ${displayDate(item.start_date)}–${displayDate(item.end_date)}`).join(' · ')}.` : `No terms have been configured for ${selectedSession.name}. A school administrator can add them under Classes & subjects → Academic terms.`}</p>}
        {registerMode && (register || roster.length > 0) && <div className="attendance-context-card"><span>{displayDate(date)}</span><strong>{selectedSession?.name || 'Selected session'} · {options.classes.find((item) => String(item.id) === String(selection.class_level))?.name || 'Class'} {arms.find((item) => String(item.id) === String(selection.class_arm))?.name || ''}</strong><span>{term?.name || 'Term not found for this date'}</span></div>}
        {!editingOffline && <div className="attendance-actions">{(!registerMode || (!register && !roster.length)) && <button className="secondary-button" type="button" onClick={loadEligible} disabled={working}>{working ? 'Loading…' : 'Load eligible students'}</button>}{registerMode && !register && roster.length > 0 && <button className="primary-button" type="button" onClick={createRegister} disabled={working}>Create draft register</button>}</div>}
        {register && <><div className="attendance-register-tools"><input aria-label="Search register" placeholder="Search name or admission number" value={search} onChange={(e) => setSearch(e.target.value)} /><strong>{roster.filter((item) => item.status).length} / {roster.length} marked</strong></div>
          {offlineEntry?.pending && <aside className={`attendance-offline-notice${offlineEntry.pending.state === 'conflict' ? ' attendance-offline-warning' : ''}`} role="status"><strong>{offlineEntry.pending.state === 'conflict' ? 'Needs conflict review' : 'Saved attendance is waiting to sync'}</strong><span>{offlineEntry.pending.state === 'conflict' ? 'The school copy changed after this device went offline. Your marks remain here and were not used to overwrite the newer copy.' : 'Your marks are stored on this device. They are not in the school workspace until sync finishes.'}</span></aside>}
          {offlineEntry?.pending && offlineGrantExpired && online && <p className="attendance-term-guidance attendance-term-guidance-warning">Offline sync access expired. Renew access while connected; the saved marks will stay on this device.</p>}
          {editingOffline && !offlineEntry?.token && <p className="attendance-term-guidance attendance-term-guidance-warning">This register has not been prepared on this device. Connect first, open it, and choose “Prepare for offline use.”</p>}
          <div className="attendance-roster">{filteredRoster.map((item) => <div className="attendance-student" key={item.student_id}><div className="attendance-student-name"><strong>{item.last_name}, {item.first_name} {item.middle_name}</strong><span>{item.admission_number}</span></div><label>Status<select value={item.status || ''} disabled={!editable || working || offlineQueueBlocked || (online && !offlineMode && Boolean(offlineEntry?.pending)) || (editingOffline && (!offlineEntry?.token || offlineExpired))} onChange={(e) => changeStudentStatus(item, e.target.value)}><option value="">Not marked</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Note<input value={item.note || ''} disabled={!editable || working || offlineQueueBlocked || (online && !offlineMode && Boolean(offlineEntry?.pending)) || (editingOffline && (!offlineEntry?.token || offlineExpired))} maxLength={300} placeholder="Optional attendance note" onChange={(e) => updateRoster(item.student_id, { note: e.target.value })} /></label></div>)}{!filteredRoster.length && <p className="academic-empty">No eligible students match this search.</p>}</div>
          <div className="attendance-actions">
            {register.status === 'draft' && online && !offlineMode && (!offlineEntry?.pending || offlineGrantExpired) && <button className="secondary-button" type="button" onClick={prepareRegisterOffline} disabled={working || (!offlineEntry?.pending && hasUnsavedStatusChanges)}>{working ? 'Preparing…' : offlineEntry?.pending ? 'Renew offline access' : 'Prepare for offline use'}</button>}
            {offlineEntry?.pending && <button className="primary-button" type="button" onClick={syncOfflineAttendance} disabled={working || !online || offlineGrantExpired || offlineEntry.pending.state === 'conflict'}>{working ? 'Syncing…' : 'Sync saved attendance'}</button>}
            {editable && (!offlineEntry?.pending || (editingOffline && offlineEntry.pending.state === 'pending')) && <button className="primary-button" type="button" onClick={saveDraft} disabled={working || offlineQueueBlocked || (editingOffline && (!offlineEntry?.token || offlineExpired))}>{working ? 'Saving…' : editingOffline ? offlineEntry?.pending ? 'Update saved offline draft' : 'Save draft on this device' : 'Save draft'}</button>}
            {register.status === 'draft' && <button className="secondary-button" type="button" onClick={() => runRegisterAction('submit')} disabled={working || !allMarked || editingOffline || Boolean(offlineEntry?.pending)}>Submit register</button>}
            {canManage && register.status === 'submitted' && <button className="primary-button" type="button" onClick={() => runRegisterAction('finalize')} disabled={working || editingOffline}>Finalize register</button>}
            {canManage && register.status === 'finalized' && <button className="secondary-button" type="button" onClick={() => runRegisterAction('reopen')} disabled={working || editingOffline}>Reopen for correction</button>}
          </div>
          {register.audit_events?.length > 0 && <details className="attendance-audit"><summary>Register audit history ({register.audit_events.length})</summary>{register.audit_events.map((event) => <p key={event.id}>{event.event_type} · {event.actor_name} · {new Date(event.created_at).toLocaleString()}{event.reason ? ` · ${event.reason}` : ''}</p>)}</details>}
        </>}
      </section>

      {(offlineRegisters.length > 0 || editingOffline) && <section className="attendance-panel attendance-secondary-panel"><div className="attendance-panel-heading"><div><p className="panel-kicker">THIS DEVICE</p><h2>Prepared attendance registers</h2></div></div><p className="attendance-policy">Open a register prepared on this device to work without internet. Offline marks stay here until they are synced.</p><div className="attendance-register-list">{offlineRegisters.map((entry) => <button className="attendance-register-row" key={entry.register.id} type="button" onClick={() => openRegister(entry.register)} disabled={working}><strong>{displayDate(entry.register.attendance_date)} · {entry.register.class_name} {entry.register.arm_name}</strong><span>{entry.register.session_name} · {entry.register.term_name} · {entry.pending ? 'Attendance waiting to sync' : 'Prepared for offline use'}</span></button>)}{!offlineRegisters.length && <p className="academic-empty">No prepared registers are saved on this device. Connect and prepare one first.</p>}</div></section>}

      {!editingOffline && <section className="attendance-panel attendance-secondary-panel"><div className="attendance-panel-heading"><div><p className="panel-kicker">REGISTER HISTORY</p><h2>Review registers</h2></div></div><div className="attendance-selectors"><label className="attendance-date-filter">From<input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} /></label><label className="attendance-date-filter">To<input type="date" value={to} min={from} max={todayText()} onChange={(e) => setTo(e.target.value)} /></label><label>Session<select value={registerFilters.academic_session} onChange={(e) => setRegisterFilters({ ...registerFilters, academic_session: e.target.value })}><option value="">All sessions</option>{options.sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Class<select value={registerFilters.class_level} onChange={(e) => setRegisterFilters({ ...registerFilters, class_level: e.target.value })}><option value="">All classes</option>{options.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Status<select value={registerFilters.status} onChange={(e) => setRegisterFilters({ ...registerFilters, status: e.target.value })}><option value="">All statuses</option><option value="draft">Draft</option><option value="submitted">Submitted</option><option value="finalized">Finalized</option></select></label><button className="secondary-button" type="button" onClick={() => loadRegisters()} disabled={working}>Filter</button></div><div className="attendance-register-list">{registers.map((item) => <button className="attendance-register-row" key={item.id} onClick={() => openRegister(item)}><strong>{item.attendance_date} · {item.class_name} {item.arm_name}</strong><span>{item.session_name} · {item.term_name} · {item.status} · {item.total_students} students</span></button>)}{!registers.length && <p className="academic-empty">No registers in this date range.</p>}</div></section>}

      {!editingOffline && <section className="attendance-panel attendance-secondary-panel"><div className="attendance-panel-heading"><div><p className="panel-kicker">FINALIZED SUMMARY</p><h2>Attendance report</h2></div><button className="secondary-button" onClick={loadReport} disabled={working}>Refresh report</button></div><p className="attendance-policy">Only finalized registers count. Present and late count as attended; excused absences remain in the denominator. Missing registers are excluded.</p>{report && <><div className="attendance-totals">{[['Present', report.totals.present], ['Absent', report.totals.absent], ['Late', report.totals.late], ['Excused', report.totals.excused], ['Attendance', `${report.totals.attendance_percentage}%`]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="attendance-register-list">{report.daily.map((item) => <div className="attendance-register-row" key={item.register__attendance_date}><strong>{item.register__attendance_date}</strong><span>{item.present} present · {item.absent} absent · {item.late} late · {item.excused} excused · {item.total} recorded</span></div>)}{!report.daily.length && <p className="academic-empty">No finalized records for this date range.</p>}</div></>}
        <label className="attendance-history-select">Student history<select value={historyStudent} onChange={(e) => loadStudentHistory(e.target.value)}><option value="">Choose a student from the loaded register</option>{roster.map((item) => <option key={item.student_id} value={item.student_id}>{item.admission_number} · {item.first_name} {item.last_name}</option>)}</select></label>{history.length > 0 && <div className="attendance-register-list">{history.map((item) => <div key={item.id} className="attendance-register-row"><strong>{item.attendance_date} · {statusLabels[item.status]}</strong><span>{item.note || item.register_status}</span></div>)}</div>}
      </section>}
    </section>
  </main>
}
