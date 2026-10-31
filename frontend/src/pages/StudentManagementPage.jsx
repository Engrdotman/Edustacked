import { useCallback, useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { academicList, apiRequest, ApiError } from '../services/api.js'

const emptyStudent = { admission_number: '', first_name: '', middle_name: '', last_name: '', date_of_birth: '', gender: '', email: '', phone: '', address: '' }

export default function StudentManagementPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const [students, setStudents] = useState([])
  const [sessions, setSessions] = useState([])
  const [classes, setClasses] = useState([])
  const [arms, setArms] = useState([])
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const [guardians, setGuardians] = useState([])
  const [history, setHistory] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [student, setStudent] = useState(emptyStudent)
  const [placement, setPlacement] = useState({ academic_session: '', class_level: '', class_arm: '' })
  const [guardian, setGuardian] = useState({ full_name: '', phone: '', relationship_type: '' })
  const [guardianForm, setGuardianForm] = useState({ full_name: '', phone: '', relationship_type: '' })
  const [showGuardianForm, setShowGuardianForm] = useState(false)
  const [transferFor, setTransferFor] = useState(null)
  const [transferReason, setTransferReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const reload = useCallback(async () => {
    const params = new URLSearchParams()
    if (search.trim()) params.set('search', search.trim())
    const data = await apiRequest(`students/?${params}`)
    setStudents(data.results || data || [])
  }, [search])

  useEffect(() => {
    let live = true
    Promise.all([reload(), academicList('academic-sessions/'), academicList('classes/')])
      .then(([_, sessionRows, classRows]) => { if (live) { setSessions(sessionRows.filter((row) => row.status !== 'completed')); setClasses(classRows.filter((row) => row.is_active)) } })
      .catch((e) => live && setError(e.message || 'Could not load students.'))
    return () => { live = false }
  }, [reload])

  async function openProfile(row) {
    setError(''); setMessage(''); setSelected(row)
    try {
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

  async function admit(event) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    const enrollment = placement.academic_session && placement.class_level && placement.class_arm
      ? { 
          academic_session: Number(placement.academic_session), 
          class_level: Number(placement.class_level), 
          class_arm: Number(placement.class_arm),
          enrollment_date: new Date().toISOString().slice(0, 10), 
          status: 'pending' 
        } : null
    const guardiansPayload = guardian.full_name.trim() && guardian.phone.trim()
      ? [{ ...guardian, is_primary_contact: true }] : []
    try {
      const created = await apiRequest('admissions/', { method: 'POST', body: { student, guardians: guardiansPayload, enrollment } })
      setStudent(emptyStudent); setGuardian({ full_name: '', phone: '', relationship_type: '' }); setPlacement({ academic_session: '', class_level: '', class_arm: '' }); setShowForm(false)
      setMessage('Student admitted successfully.'); await reload(); await openProfile(created)
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
      await apiRequest(`students/${selected.id}/guardians/`, { method: 'POST', body: { ...guardianForm, is_primary_contact: guardians.length === 0 } })
      setGuardianForm({ full_name: '', phone: '', relationship_type: '' }); setShowGuardianForm(false); await openProfile(selected)
    } catch (e) { setError(e.message || 'Could not add guardian.') }
  }

  async function addEnrollment(event) {
    event.preventDefault(); setError('')
    try {
      await apiRequest(`students/${selected.id}/enrollments/`, { method: 'POST', body: { academic_session: Number(placement.academic_session), class_level: Number(placement.class_level), class_arm: Number(placement.class_arm), enrollment_date: new Date().toISOString().slice(0, 10), status: 'pending' } })
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

  return <main className="app-page"><header className="app-topbar"><BrandMark /><button className="text-button" onClick={() => navigate('/app')}>Back to home</button></header>
    <section className="app-content student-page"><p className="eyebrow">{selectedSchool?.school_name} · STUDENTS</p><h1 className="app-heading">Student <em>management</em></h1>
      <p className="intro">Admissions, guardian contacts, and enrollment history for this school.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="success-message" role="status">{message}</p>}
      <div className="student-toolbar"><input aria-label="Search students" placeholder="Search name or admission number" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && reload()} /><button className="primary-button" onClick={() => { setError(''); setShowForm(!showForm) }}>Admit student</button></div>
      {showForm && <form className="student-form" onSubmit={admit}><h2>New admission</h2><div className="student-fields">
        {Object.entries({ admission_number: 'Admission number', first_name: 'First name', middle_name: 'Middle name', last_name: 'Last name', date_of_birth: 'Date of birth', email: 'Email', phone: 'Phone', address: 'Address' }).map(([key, label]) => <label key={key}>{label}<input required={['admission_number', 'first_name', 'last_name'].includes(key)} type={key === 'date_of_birth' ? 'date' : key === 'email' ? 'email' : 'text'} value={student[key]} onChange={(e) => setStudent({ ...student, [key]: e.target.value })} /></label>)}
        <label>Gender<select value={student.gender} onChange={(e) => setStudent({ ...student, gender: e.target.value })}><option value="">Not specified</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="prefer_not_to_say">Prefer not to say</option></select></label>
        <label>Guardian name<input value={guardian.full_name} onChange={(e) => setGuardian({ ...guardian, full_name: e.target.value })} /></label><label>Guardian phone<input value={guardian.phone} onChange={(e) => setGuardian({ ...guardian, phone: e.target.value })} /></label><label>Relationship<input value={guardian.relationship_type} onChange={(e) => setGuardian({ ...guardian, relationship_type: e.target.value })} placeholder="Parent, aunt, etc." /></label>
        <label>Academic session<select value={placement.academic_session} onChange={(e) => setPlacement({ ...placement, academic_session: e.target.value })}><option value="">No enrollment yet</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Class<select value={placement.class_level} onChange={(e) => chooseClass(e.target.value)}><option value="">Choose class</option>{classes.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Arm<select value={placement.class_arm} onChange={(e) => setPlacement({ ...placement, class_arm: e.target.value })}><option value="">Choose arm</option>{arms.filter((row) => row.is_active).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      </div><div className="student-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save admission'}</button><button className="text-button" type="button" onClick={() => setShowForm(false)}>Cancel</button></div></form>}
      <div className="student-layout"><section className="student-list" aria-label="Students">{students.map((row) => <button key={row.id} className={`student-row ${selected?.id === row.id ? 'is-selected' : ''}`} onClick={() => openProfile(row)}><strong>{row.last_name}, {row.first_name} {row.middle_name}</strong><span>{row.admission_number} · {row.current_class || 'Not enrolled'} {row.current_arm || ''}</span></button>)}{!students.length && <p className="academic-empty">No students match this search.</p>}</section>
        <section className="student-profile">{selected ? <><div className="student-profile-heading"><div><p className="panel-kicker">STUDENT PROFILE</p><h2>{selected.first_name} {selected.middle_name} {selected.last_name}</h2><p>{selected.admission_number} · {selected.status}</p></div>{['school_owner', 'school_admin', 'school_manager', 'principal'].includes(selectedSchool?.role) && selected.status === 'active' && <button className="text-button" onClick={deactivate}>Deactivate</button>}</div><h3>Guardians</h3>{guardians.length ? guardians.map((row) => <p key={row.id}>{row.full_name} · {row.relationship_type} · {row.phone}{row.is_primary_contact ? ' · Primary' : ''}</p>) : <p>No guardian contacts recorded.</p>}{['school_owner', 'school_admin', 'school_manager', 'principal', 'receptionist'].includes(selectedSchool?.role) && <><button className="text-button" onClick={() => setShowGuardianForm(!showGuardianForm)}>Add guardian</button>{showGuardianForm && <form className="student-fields" onSubmit={addGuardian}><label>Name<input required value={guardianForm.full_name} onChange={(e) => setGuardianForm({ ...guardianForm, full_name: e.target.value })} /></label><label>Phone<input required value={guardianForm.phone} onChange={(e) => setGuardianForm({ ...guardianForm, phone: e.target.value })} /></label><label>Relationship<input required value={guardianForm.relationship_type} onChange={(e) => setGuardianForm({ ...guardianForm, relationship_type: e.target.value })} /></label><button className="primary-button">Save guardian</button></form>}</>}<h3>Enrollment history</h3>{history.length ? history.map((row) => <div key={row.id}><p>{row.academic_session_name}: {row.class_name} {row.class_arm_name} · {row.status}{row.previous_enrollment_id ? ' · Transfer' : ''}</p>{['school_owner', 'school_admin', 'school_manager', 'principal', 'receptionist'].includes(selectedSchool?.role) && row.status === 'active' && <div className="student-actions"><button className="text-button" onClick={() => { setTransferFor(row.id); setPlacement({ academic_session: '', class_level: '', class_arm: '' }) }}>Transfer placement</button><button className="text-button" onClick={() => withdrawEnrollment(row)}>Withdraw enrollment</button></div>}</div>) : <p>No enrollments recorded.</p>}{transferFor && <form className="student-form" onSubmit={transferEnrollment}><h3>Transfer placement</h3><label>Destination class<select required value={placement.class_level} onChange={(e) => chooseClass(e.target.value)}><option value="">Choose class</option>{classes.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Destination arm<select required value={placement.class_arm} onChange={(e) => setPlacement({ ...placement, class_arm: e.target.value })}><option value="">Choose arm</option>{arms.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Reason<input required value={transferReason} onChange={(e) => setTransferReason(e.target.value)} /></label><button className="primary-button">Confirm transfer</button><button type="button" className="text-button" onClick={() => setTransferFor(null)}>Cancel</button></form>}{['school_owner', 'school_admin', 'school_manager', 'principal', 'receptionist'].includes(selectedSchool?.role) && sessions.length > 0 && <form className="student-form" onSubmit={addEnrollment}><h3>Add enrollment</h3><label>Session<select required value={placement.academic_session} onChange={(e) => setPlacement({ ...placement, academic_session: e.target.value })}><option value="">Choose session</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Class<select required value={placement.class_level} onChange={(e) => chooseClass(e.target.value)}><option value="">Choose class</option>{classes.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Arm<select required value={placement.class_arm} onChange={(e) => setPlacement({ ...placement, class_arm: e.target.value })}><option value="">Choose arm</option>{arms.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><button className="primary-button">Add enrollment</button></form>}</> : <p className="academic-empty">Select a student to view their profile and history.</p>}</section></div>
    </section></main>
}
