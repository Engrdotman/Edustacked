import { useCallback, useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { academicList, apiRequest, ApiError } from '../services/api.js'

const emptyStudent = { admission_number: '', first_name: '', middle_name: '', last_name: '', date_of_birth: '', gender: '', email: '', phone: '', address: '' }
const localDate = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
async function listAllStudents(path) {
  const rows = []
  let page = 1
  let hasNext = true
  while (hasNext) {
    const data = await apiRequest(`${path}${path.includes('?') ? '&' : '?'}page=${page}&page_size=200`)
    if (Array.isArray(data)) return data
    rows.push(...(data.results || []))
    hasNext = Boolean(data.next)
    page += 1
  }
  return rows
}

export default function StudentManagementPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const isTeacher = selectedSchool?.role === 'teacher'
  const canAdmitStudents = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'receptionist'].includes(selectedSchool?.role)
  const canManageGuardians = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'receptionist'].includes(selectedSchool?.role)
  const [students, setStudents] = useState([])
  const [sessions, setSessions] = useState([])
  const [classes, setClasses] = useState([])
  const [arms, setArms] = useState([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState(() => new URLSearchParams(window.location.search).get('status') || '')
  const [selected, setSelected] = useState(null)
  const [guardians, setGuardians] = useState([])
  const [history, setHistory] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [student, setStudent] = useState(emptyStudent)
  const [placement, setPlacement] = useState({ academic_session: '', class_level: '', class_arm: '' })
  const [enrollmentDate, setEnrollmentDate] = useState(localDate)
  const [guardian, setGuardian] = useState({ full_name: '', phone: '', email: '', relationship_type: '', can_receive_communications: true })
  const [sendGuardianInvitation, setSendGuardianInvitation] = useState(true)
  const [guardianForm, setGuardianForm] = useState({ guardian_id: '', full_name: '', phone: '', email: '', relationship_type: '', can_receive_communications: true })
  const [guardianMode, setGuardianMode] = useState('new')
  const [guardianSearch, setGuardianSearch] = useState('')
  const [guardianOptions, setGuardianOptions] = useState([])
  const [showGuardianForm, setShowGuardianForm] = useState(false)
  const [guardianEmailEditId, setGuardianEmailEditId] = useState(null)
  const [guardianEmailDraft, setGuardianEmailDraft] = useState('')
  const [guardianActionId, setGuardianActionId] = useState(null)
  const [transferFor, setTransferFor] = useState(null)
  const [transferReason, setTransferReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const reload = useCallback(async () => {
    const params = new URLSearchParams()
    if (search.trim()) params.set('search', search.trim())
    if (statusFilter) params.set('status', statusFilter)
    setStudents(await listAllStudents(`students/?${params}`))
  }, [search, statusFilter])

  useEffect(() => {
    let live = true
    const academicSetup = isTeacher ? Promise.resolve([[], []]) : Promise.all([academicList('academic-sessions/'), academicList('classes/')])
    Promise.all([reload(), academicSetup])
      .then(([_, [sessionRows, classRows]]) => { if (live) { setSessions(sessionRows.filter((row) => row.status !== 'completed')); setClasses(classRows.filter((row) => row.is_active)) } })
      .catch((e) => live && setError(e.message || 'Could not load students.'))
    return () => { live = false }
  }, [reload, isTeacher])

  async function openProfile(row) {
    setError(''); setMessage(''); setSelected(row)
    try {
      if (isTeacher) {
        const detail = await apiRequest(`students/${row.id}/`)
        setSelected(detail); setGuardians([]); setHistory([])
        return
      }
      const [detail, links, enrollments] = await Promise.all([
        apiRequest(`students/${row.id}/`), apiRequest(`students/${row.id}/guardians/`), apiRequest(`students/${row.id}/enrollments/`),
      ])
      setSelected(detail); setGuardians(links.results || links); setHistory(enrollments.results || enrollments)
    } catch (e) { setError(e.message || 'Could not load this student profile.') }
  }

  async function chooseClass(value) {
    setPlacement((current) => ({ ...current, class_level: value, class_arm: '' }))
    setArms(value ? await academicList(`classes/${value}/arms/`) : [])
  }

  function chooseSession(value) {
    const session = sessions.find((row) => String(row.id) === String(value))
    setPlacement((current) => ({ ...current, academic_session: value }))
    if (!session) return
    const today = localDate()
    setEnrollmentDate(today < session.start_date ? session.start_date : today > session.end_date ? session.end_date : today)
  }

  async function admit(event) {
    event.preventDefault(); setError(''); setMessage('')
    if (placement.academic_session && (!placement.class_level || !placement.class_arm)) {
      setError('Choose both a class and arm, or clear the academic session to admit without enrollment.')
      return
    }
    setBusy(true)
    const enrollment = placement.academic_session && placement.class_level && placement.class_arm
      ? { 
          academic_session: Number(placement.academic_session), 
          class_level: Number(placement.class_level), 
          class_arm: Number(placement.class_arm),
          enrollment_date: enrollmentDate,
          status: 'pending' 
        } : null
    const guardiansPayload = guardian.full_name.trim() && guardian.phone.trim()
      ? [{ ...guardian, is_primary_contact: true }] : []
    try {
      const created = await apiRequest('admissions/', { method: 'POST', body: { student, guardians: guardiansPayload, enrollment } })
      setStudent(emptyStudent); setGuardian({ full_name: '', phone: '', email: '', relationship_type: '', can_receive_communications: true }); setPlacement({ academic_session: '', class_level: '', class_arm: '' }); setShowForm(false)
      await reload(); await openProfile(created)
      const guardianEmail = guardian.email.trim()
      const shouldSendInvitation = sendGuardianInvitation && guardiansPayload.length > 0 && guardianEmail
      if (shouldSendInvitation) {
        try {
          const linkResponse = await apiRequest(`students/${created.id}/guardians/`)
          const links = linkResponse.results || linkResponse
          const newGuardianLink = links.find((row) => row.email?.trim().toLowerCase() === guardianEmail.toLowerCase())
          if (!newGuardianLink) throw new Error('The guardian was saved, but their student link could not be found.')
          await apiRequest(`parent/staff/students/${created.id}/guardians/${newGuardianLink.id}/invite/`, { method: 'POST', body: {} })
          setMessage(`Student admitted. A one-time parent portal setup link has been emailed to ${guardianEmail}.`)
        } catch (invitationError) {
          setMessage('Student admitted successfully.')
          setError(`The student was admitted, but the parent setup email was not sent. Open this student’s Guardians section and choose “Send activation link” to retry. ${invitationError.message || ''}`.trim())
        }
      } else {
        setMessage('Student admitted successfully. Add a guardian email in the student profile and choose “Send activation link” to set up parent access.')
      }
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Admission could not be saved.') }
    finally { setBusy(false) }
  }

  async function deactivate() {
    if (!selected || !window.confirm('Deactivate this student record? Enrollment history will be retained.')) return
    try { await apiRequest(`students/${selected.id}/`, { method: 'PATCH', body: { status: 'inactive' } }); setMessage('Student record deactivated.'); await reload(); await openProfile({ ...selected, status: 'inactive' }) }
    catch (e) { setError(e.message || 'Could not update student status.') }
  }

  async function addGuardian(event) {
    event.preventDefault(); setError('')
    try {
      const body = guardianMode === 'existing'
        ? { guardian_id: Number(guardianForm.guardian_id), relationship_type: guardianForm.relationship_type, is_primary_contact: guardians.length === 0, can_receive_communications: guardianForm.can_receive_communications }
        : { full_name: guardianForm.full_name, phone: guardianForm.phone, email: guardianForm.email, relationship_type: guardianForm.relationship_type, is_primary_contact: guardians.length === 0, can_receive_communications: guardianForm.can_receive_communications }
      await apiRequest(`students/${selected.id}/guardians/`, { method: 'POST', body })
      setGuardianForm({ guardian_id: '', full_name: '', phone: '', email: '', relationship_type: '', can_receive_communications: true }); setShowGuardianForm(false); await openProfile(selected); setMessage(guardianMode === 'existing' ? 'Existing guardian linked to this student. One phone number will receive each school SMS once.' : 'Guardian added. Add their email address and send an activation link so they can sign in to the parent portal.')
    } catch (e) { setError(e.message || 'Could not add guardian.') }
  }

  async function findGuardians() {
    setError('')
    const query = guardianSearch.trim()
    if (query.length < 2) { setError('Enter at least two letters or digits to search existing guardian contacts.'); return }
    try {
      const result = await apiRequest(`guardians/?search=${encodeURIComponent(query)}&page_size=100`)
      const linkedIds = new Set(guardians.map((row) => row.guardian_id))
      setGuardianOptions((result.results || result).filter((row) => row.is_active && !linkedIds.has(row.id)))
    } catch (e) { setError(e.message || 'Could not search existing guardian contacts.') }
  }

  async function updateCommunicationPreference(row, enabled) {
    setError(''); setMessage(''); setGuardianActionId(row.id)
    try {
      await apiRequest(`students/${selected.id}/guardians/${row.id}/`, { method: 'PATCH', body: { can_receive_communications: enabled } })
      await openProfile(selected)
      setMessage(enabled ? 'This guardian can receive school announcements.' : 'This guardian is excluded from school announcements and SMS.')
    } catch (e) { setError(e.message || 'Could not update the guardian’s school communication preference.') }
    finally { setGuardianActionId(null) }
  }

  function toggleGuardianForm() {
    setShowGuardianForm((open) => !open)
    setGuardianMode('new')
    setGuardianSearch('')
    setGuardianOptions([])
    setGuardianForm({ guardian_id: '', full_name: '', phone: '', email: '', relationship_type: '', can_receive_communications: true })
  }

  async function saveGuardianEmail(event, row) {
    event.preventDefault(); setError(''); setMessage(''); setGuardianActionId(row.id)
    try {
      await apiRequest(`guardians/${row.guardian_id}/`, { method: 'PATCH', body: { email: guardianEmailDraft.trim() } })
      await openProfile(selected)
      setGuardianEmailEditId(null); setGuardianEmailDraft('')
      setMessage('Guardian email saved. You can now email the parent portal activation link.')
    } catch (e) { setError(e.message || 'Could not save the guardian email.') }
    finally { setGuardianActionId(null) }
  }

  async function inviteGuardian(row) {
    setError(''); setMessage(''); setGuardianActionId(row.id)
    try {
      const result = await apiRequest(`parent/staff/students/${selected.id}/guardians/${row.id}/invite/`, { method: 'POST', body: {} })
      setMessage(result.detail || 'The parent portal activation link was emailed to the guardian.')
    } catch (e) { setError(e.message || 'The parent invitation could not be sent. Check the guardian email and school email setup.') }
    finally { setGuardianActionId(null) }
  }

  async function addEnrollment(event) {
    event.preventDefault(); setError('')
    try {
      await apiRequest(`students/${selected.id}/enrollments/`, { method: 'POST', body: { academic_session: Number(placement.academic_session), class_level: Number(placement.class_level), class_arm: Number(placement.class_arm), enrollment_date: enrollmentDate, status: 'pending' } })
      setMessage('Enrollment added.'); await openProfile(selected)
    } catch (e) { setError(e.message || 'Could not add enrollment.') }
  }

  async function transferEnrollment(event) {
    event.preventDefault()
    if (!transferFor || !placement.class_level || !placement.class_arm || !transferReason.trim()) return
    try {
      await apiRequest(`enrollments/${transferFor}/transfer/`, { method: 'POST', body: { class_level: Number(placement.class_level), class_arm: Number(placement.class_arm), transfer_date: new Date().toISOString().slice(0, 10), reason: transferReason } })
      setTransferFor(null); setTransferReason(''); setMessage('Student placement transferred.'); await openProfile(selected)
    } catch (e) { setError(e.message || 'Transfer could not be completed.') }
  }

  async function withdrawEnrollment(row) {
    const reason = window.prompt('Withdrawal reason:')
    if (!reason) return
    try {
      await apiRequest(`enrollments/${row.id}/transition/`, { method: 'POST', body: { status: 'withdrawn', withdrawal_date: new Date().toISOString().slice(0, 10), withdrawal_reason: reason } })
      setMessage('Enrollment withdrawn.'); await openProfile(selected)
    } catch (e) { setError(e.message || 'Could not withdraw enrollment.') }
  }

  async function activateEnrollment(row) {
    setError(''); setMessage('')
    try {
      await apiRequest(`enrollments/${row.id}/transition/`, { method: 'POST', body: { status: 'active' } })
      setMessage('Enrollment activated.'); await openProfile(selected); await reload()
    } catch (e) { setError(e.message || 'Could not activate enrollment.') }
  }

  return <main className="app-page"><header className="app-topbar"><BrandMark navigate={navigate} /><button className="text-button" onClick={() => navigate('/app')}>Back to home</button></header>
    <section className="app-content student-page"><p className="eyebrow">{selectedSchool?.school_name} · STUDENTS</p><h1 className="app-heading">Student <em>{isTeacher ? 'roster' : 'management'}</em></h1>
      <p className="intro">{isTeacher ? 'View students in classes assigned to you. Use Attendance to take a class register.' : 'Admissions, guardian contacts, and enrollment history for this school.'}</p>
      {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="success-message" role="status">{message}</p>}
      <div className="student-toolbar"><input aria-label="Search students" placeholder="Search name or admission number" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && reload()} /><select aria-label="Filter students by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">All students</option><option value="active">Active</option><option value="inactive">Inactive</option></select>{canAdmitStudents && <button className="primary-button" onClick={() => { setError(''); setShowForm(!showForm) }}>Admit student</button>}</div>
      {showForm && canAdmitStudents && <form className="student-form" onSubmit={admit}><h2>New admission</h2><div className="student-fields">
        {Object.entries({ admission_number: 'Admission number', first_name: 'First name', middle_name: 'Middle name', last_name: 'Last name', date_of_birth: 'Date of birth', email: 'Email', phone: 'Phone', address: 'Address' }).map(([key, label]) => <label key={key}>{label}<input required={['admission_number', 'first_name', 'last_name'].includes(key)} type={key === 'date_of_birth' ? 'date' : key === 'email' ? 'email' : 'text'} value={student[key]} onChange={(e) => setStudent({ ...student, [key]: e.target.value })} /></label>)}
        <label>Gender<select value={student.gender} onChange={(e) => setStudent({ ...student, gender: e.target.value })}><option value="">Not specified</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="prefer_not_to_say">Prefer not to say</option></select></label>
        <label>Guardian name<input value={guardian.full_name} onChange={(e) => setGuardian({ ...guardian, full_name: e.target.value })} /></label><label>Guardian phone<input value={guardian.phone} onChange={(e) => setGuardian({ ...guardian, phone: e.target.value })} /></label><label>Guardian email<input type="email" placeholder="parent@example.com" value={guardian.email} onChange={(e) => setGuardian({ ...guardian, email: e.target.value })} /></label><label>Relationship<input value={guardian.relationship_type} onChange={(e) => setGuardian({ ...guardian, relationship_type: e.target.value })} placeholder="Parent, aunt, etc." /></label><label className="guardian-communications-toggle"><input type="checkbox" checked={guardian.can_receive_communications} onChange={(e) => setGuardian({ ...guardian, can_receive_communications: e.target.checked })} /><span>May receive school announcements and SMS</span></label>
        <label className="guardian-communications-toggle"><input type="checkbox" checked={sendGuardianInvitation} disabled={!guardian.full_name.trim() || !guardian.phone.trim() || !guardian.email.trim()} onChange={(e) => setSendGuardianInvitation(e.target.checked)} /><span>Email a one-time parent portal setup link after admission (guardian name, phone, and email required)</span></label>
        <label>Academic session<select value={placement.academic_session} onChange={(e) => chooseSession(e.target.value)}><option value="">No enrollment yet</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.name} ({row.start_date} – {row.end_date})</option>)}</select></label>{placement.academic_session && <label>Enrollment date<input required type="date" min={sessions.find((row) => String(row.id) === String(placement.academic_session))?.start_date} max={sessions.find((row) => String(row.id) === String(placement.academic_session))?.end_date} value={enrollmentDate} onChange={(e) => setEnrollmentDate(e.target.value)} /></label>}<label>Class<select required={Boolean(placement.academic_session)} value={placement.class_level} onChange={(e) => chooseClass(e.target.value)}><option value="">Choose class</option>{classes.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Arm<select required={Boolean(placement.academic_session)} value={placement.class_arm} onChange={(e) => setPlacement({ ...placement, class_arm: e.target.value })}><option value="">Choose arm</option>{arms.filter((row) => row.is_active).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      </div><div className="student-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save admission'}</button><button className="text-button" type="button" onClick={() => setShowForm(false)}>Cancel</button></div></form>}
      <div className="student-layout"><section className="student-list" aria-label="Students">{students.map((row) => <button key={row.id} className={`student-row ${selected?.id === row.id ? 'is-selected' : ''}`} onClick={() => openProfile(row)}><strong>{row.last_name}, {row.first_name} {row.middle_name}</strong><span>{row.admission_number} · {row.current_class ? `${row.current_enrollment_status === 'pending' ? 'Pending enrollment' : 'Enrolled'} · ${row.current_class} ${row.current_arm || ''}` : 'Not enrolled'}</span></button>)}{!students.length && <p className="academic-empty">No students match this search.</p>}</section>
        <section className="student-profile">{selected ? <>
          <div className="student-profile-heading"><div><p className="panel-kicker">STUDENT PROFILE</p><h2>{selected.first_name} {selected.middle_name} {selected.last_name}</h2><p>{selected.admission_number} · {selected.status}</p></div>{['school_owner', 'school_admin', 'school_manager', 'principal'].includes(selectedSchool?.role) && selected.status === 'active' && <button className="text-button" onClick={deactivate}>Deactivate</button>}</div>
          <h3>Guardians</h3><p className="student-hint">Active guardian links marked for school communications receive school-wide announcements and SMS.</p>
          {guardians.length ? <div className="student-guardian-list">{guardians.map((row) => <article className="student-guardian-row" key={row.id}><div><strong>{row.full_name}{row.is_primary_contact ? ' · Primary' : ''}</strong><span>{row.relationship_type} · {row.phone} · {row.email || 'Email not added'}</span></div>{canManageGuardians && <div className="student-guardian-actions"><label className="guardian-communications-toggle"><input type="checkbox" checked={row.can_receive_communications} disabled={guardianActionId === row.id} onChange={(event) => updateCommunicationPreference(row, event.target.checked)} /><span>School announcements and SMS</span></label>{row.portal_access ? <span className="guardian-portal-active">Parent portal active</span> : row.email ? <button className="secondary-button" type="button" disabled={guardianActionId === row.id} onClick={() => inviteGuardian(row)}>{guardianActionId === row.id ? 'Sending…' : 'Send activation link'}</button> : <button className="text-button" type="button" onClick={() => { setGuardianEmailEditId(row.id); setGuardianEmailDraft('') }}>Add email to invite</button>}{row.email && !row.portal_access && <button className="text-button" type="button" onClick={() => { setGuardianEmailEditId(row.id); setGuardianEmailDraft(row.email) }}>Edit email</button>}{guardianEmailEditId === row.id && <form className="student-guardian-email-form" onSubmit={(event) => saveGuardianEmail(event, row)}><label>Parent or guardian email<input required type="email" autoComplete="email" placeholder="parent@example.com" value={guardianEmailDraft} onChange={(event) => setGuardianEmailDraft(event.target.value)} /></label><button className="primary-button" disabled={guardianActionId === row.id}>Save email</button><button className="text-button" type="button" onClick={() => setGuardianEmailEditId(null)}>Cancel</button></form>}</div>}</article>)}</div> : <p>No guardian contacts recorded.</p>}
          {canManageGuardians && <><button className="text-button" type="button" onClick={toggleGuardianForm}>{showGuardianForm ? 'Close guardian form' : 'Add or link a guardian'}</button>{showGuardianForm && <form className="student-fields student-guardian-form" onSubmit={addGuardian}>
            <label>Guardian record<select value={guardianMode} onChange={(event) => { setGuardianMode(event.target.value); setGuardianOptions([]); setGuardianForm({ guardian_id: '', full_name: '', phone: '', email: '', relationship_type: '', can_receive_communications: true }) }}><option value="new">Create new guardian record</option><option value="existing">Link an existing guardian record</option></select></label>
            {guardianMode === 'existing' ? <><label>Search by guardian name, phone, or email<input value={guardianSearch} onChange={(event) => setGuardianSearch(event.target.value)} placeholder="e.g. Grace or 080…" /></label><button className="secondary-button" type="button" onClick={findGuardians}>Find guardian</button><label>Matching guardian<select required value={guardianForm.guardian_id} onChange={(event) => setGuardianForm({ ...guardianForm, guardian_id: event.target.value })}><option value="">Choose a guardian</option>{guardianOptions.map((row) => <option key={row.id} value={row.id}>{row.full_name} · {row.phone}</option>)}</select></label><p className="student-hint">Link the same guardian record to each of their children. The parent account stays connected to all linked children, and SMS is sent once per unique phone number.</p></> : <><label>Name<input required value={guardianForm.full_name} onChange={(event) => setGuardianForm({ ...guardianForm, full_name: event.target.value })} placeholder="Parent or guardian full name" /></label><label>Phone<input required value={guardianForm.phone} onChange={(event) => setGuardianForm({ ...guardianForm, phone: event.target.value })} placeholder="e.g. 08012345678" /></label><label>Email for portal access<input type="email" placeholder="parent@example.com" value={guardianForm.email} onChange={(event) => setGuardianForm({ ...guardianForm, email: event.target.value })} /></label></>}
            <label>Relationship<input required value={guardianForm.relationship_type} onChange={(event) => setGuardianForm({ ...guardianForm, relationship_type: event.target.value })} placeholder="Parent, aunt, guardian…" /></label><label className="guardian-communications-toggle"><input type="checkbox" checked={guardianForm.can_receive_communications} onChange={(event) => setGuardianForm({ ...guardianForm, can_receive_communications: event.target.checked })} /><span>May receive school announcements and SMS</span></label><button className="primary-button">{guardianMode === 'existing' ? 'Link guardian to student' : 'Save guardian'}</button>
          </form>}</>}
          <h3>Enrollment history</h3>{history.length ? history.map((row) => { const session = sessions.find((item) => item.id === row.academic_session); const canManage = ['school_owner', 'school_admin', 'school_manager', 'principal', 'receptionist'].includes(selectedSchool?.role); return <div className="student-enrollment" key={row.id}><p>{row.academic_session_name}: {row.class_name} {row.class_arm_name} · <strong className={`enrollment-status enrollment-status-${row.status}`}>{row.status}</strong>{row.previous_enrollment_id ? ' · Transfer' : ''}</p>{canManage && row.status === 'pending' && <div className="student-actions"><button className="primary-button" disabled={session?.status !== 'active'} onClick={() => activateEnrollment(row)}>Activate enrollment</button>{session?.status !== 'active' && <span className="student-hint">Activate this session in Academic setup first.</span>}</div>}{canManage && row.status === 'active' && <div className="student-actions"><button className="text-button" onClick={() => { setTransferFor(row.id); setPlacement({ academic_session: '', class_level: '', class_arm: '' }) }}>Transfer placement</button><button className="text-button" onClick={() => withdrawEnrollment(row)}>Withdraw enrollment</button></div>}</div>}) : <p>No enrollments recorded.</p>}
          {transferFor && <form className="student-form" onSubmit={transferEnrollment}><h3>Transfer placement</h3><label>Destination class<select required value={placement.class_level} onChange={(event) => chooseClass(event.target.value)}><option value="">Choose class</option>{classes.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Destination arm<select required value={placement.class_arm} onChange={(event) => setPlacement({ ...placement, class_arm: event.target.value })}><option value="">Choose arm</option>{arms.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Reason<input required value={transferReason} onChange={(event) => setTransferReason(event.target.value)} /></label><button className="primary-button">Confirm transfer</button><button type="button" className="text-button" onClick={() => setTransferFor(null)}>Cancel</button></form>}
          {['school_owner', 'school_admin', 'school_manager', 'principal', 'receptionist'].includes(selectedSchool?.role) && sessions.length > 0 && <form className="student-form" onSubmit={addEnrollment}><h3>Add enrollment</h3><label>Session<select required value={placement.academic_session} onChange={(event) => chooseSession(event.target.value)}><option value="">Choose session</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.name} ({row.start_date} – {row.end_date})</option>)}</select></label><label>Enrollment date<input required type="date" min={sessions.find((row) => String(row.id) === String(placement.academic_session))?.start_date} max={sessions.find((row) => String(row.id) === String(placement.academic_session))?.end_date} value={enrollmentDate} onChange={(event) => setEnrollmentDate(event.target.value)} /></label><label>Class<select required value={placement.class_level} onChange={(event) => chooseClass(event.target.value)}><option value="">Choose class</option>{classes.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Arm<select required value={placement.class_arm} onChange={(event) => setPlacement({ ...placement, class_arm: event.target.value })}><option value="">Choose arm</option>{arms.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><button className="primary-button">Add enrollment</button></form>}
        </> : <p className="academic-empty">Select a student to view their profile and history.</p>}</section>
      </div>
    </section></main>
}
