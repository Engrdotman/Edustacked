import { useCallback, useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { academicList, apiRequest } from '../services/api.js'
import OwnershipTransferPanel from '../components/OwnershipTransferPanel.jsx'

const blankStaff = { staff_number: '', first_name: '', middle_name: '', last_name: '', work_email: '', phone: '', job_title: '', department: '', employment_type: 'full_time', employment_start_date: '', employment_end_date: '', status: 'active', user: '' }
const blankAssignment = { teacher: '', academic_session: '', class_level: '', class_arm: '', subject: '', start_date: '' }

async function listAll(path) {
  const rows = []
  let page = 1
  let hasNext = true
  while (hasNext) {
    const separator = path.includes('?') ? '&' : '?'
    const result = await apiRequest(`${path}${separator}page=${page}&page_size=200`)
    if (Array.isArray(result)) return result
    rows.push(...(result.results || []))
    hasNext = Boolean(result.next)
    page += 1
  }
  return rows
}

export default function StaffManagementPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const role = selectedSchool?.role
  const canManage = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(role)
  const isTeacher = role === 'teacher'
  const [rows, setRows] = useState([])
  const [assignableTeachers, setAssignableTeachers] = useState([])
  const [assignments, setAssignments] = useState([])
  const [sessions, setSessions] = useState([])
  const [classes, setClasses] = useState([])
  const [arms, setArms] = useState([])
  const [subjects, setSubjects] = useState([])
  const [selected, setSelected] = useState(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState(() => new URLSearchParams(window.location.search).get('status') || '')
  const [filters, setFilters] = useState({ academic_session: '', class_level: '', class_arm: '', subject: '', teacher: '' })
  const [staffForm, setStaffForm] = useState(blankStaff)
  const [assignmentForm, setAssignmentForm] = useState(blankAssignment)
  const [showStaffForm, setShowStaffForm] = useState(false)
  const [showAssignmentForm, setShowAssignmentForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [replaceFor, setReplaceFor] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [invite, setInvite] = useState({ email: '', first_name: '', last_name: '', role: 'teacher' })

  const loadAssignments = useCallback(async (filterValues = filters) => {
    const params = new URLSearchParams(Object.entries(filterValues).filter(([, value]) => value))
    setAssignments(await listAll(`assignments/${params.size ? `?${params}` : ''}`))
  }, [filters])

  const reload = useCallback(async () => {
    setLoading(true); setError('')
    try {
      if (isTeacher) {
        const [me, rowsAssignments] = await Promise.all([apiRequest('staff/me/'), listAll('assignments/')])
        setSelected(me.staff); setAssignments(rowsAssignments); setRows([me.staff])
      } else if (canManage) {
        const params = new URLSearchParams()
        if (search.trim()) params.set('search', search.trim())
        if (statusFilter) params.set('status', statusFilter)
        const [staffRows, activeStaffRows, sessionRows, classRows, subjectRows, assignmentResult] = await Promise.all([
          listAll(`staff/${params.size ? `?${params}` : ''}`), listAll('staff/?status=active'), academicList('academic-sessions/'), academicList('classes/'), academicList('subjects/'), listAll('assignments/'),
        ])
        setRows(staffRows); setSessions(sessionRows); setClasses(classRows.filter((r) => r.is_active)); setSubjects(subjectRows.filter((r) => r.is_active)); setAssignments(assignmentResult)
        setAssignableTeachers(activeStaffRows)
      } else {
        const params = new URLSearchParams()
        if (search.trim()) params.set('search', search.trim())
        if (statusFilter) params.set('status', statusFilter)
        setRows(await listAll(`staff/${params.size ? `?${params}` : ''}`))
      }
    } catch (e) { setError(e.message || 'Could not load staff information.') }
    finally { setLoading(false) }
  }, [isTeacher, canManage, search, statusFilter])

  useEffect(() => { reload() }, [reload])

  async function chooseClass(value) {
    setAssignmentForm((current) => ({ ...current, class_level: value, class_arm: '', subject: '' }))
    if (!value) { setArms([]); return }
    const [armRows, classSubjects] = await Promise.all([academicList(`classes/${value}/arms/`), academicList(`classes/${value}/subjects/`)])
    setArms(armRows.filter((r) => r.is_active))
    const activeIds = classSubjects.filter((r) => r.is_active).map((r) => r.subject)
    setSubjects((current) => current.map((r) => ({ ...r, availableForClass: !activeIds.length || activeIds.includes(r.id) })))
  }

  async function saveStaff(event) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    const payload = { ...staffForm, user: staffForm.user || null, employment_end_date: staffForm.employment_end_date || null }
    try {
      await apiRequest(editingId ? `staff/${editingId}/` : 'staff/', { method: editingId ? 'PATCH' : 'POST', body: payload })
      setMessage(editingId ? 'Staff profile updated.' : 'Staff profile created.'); setStaffForm(blankStaff); setEditingId(null); setShowStaffForm(false); await reload()
    } catch (e) { setError(e.message || 'Could not save staff profile.') }
    finally { setBusy(false) }
  }

  async function sendInvite(event) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      await apiRequest(`schools/${selectedSchool.school_id}/memberships/`, { method: 'POST', body: invite })
      setInvite({ email: '', first_name: '', last_name: '', role: 'teacher' })
      setMessage('Invitation created. The staff member will receive secure account setup and email verification links.')
    } catch (e) { setError(e.message || 'Could not invite this staff member.') }
    finally { setBusy(false) }
  }

  function editStaff(row) {
    if (!canManage) return
    setEditingId(row.id); setStaffForm({ ...blankStaff, ...row, user: row.user || '' }); setShowStaffForm(true)
  }

  async function toggleTeacher(row) {
    try {
      if (row.is_teacher) {
        const teaching_status = row.teacher_status === 'active' ? 'inactive' : 'active'
        await apiRequest(`staff/${row.id}/teacher/`, { method: 'PATCH', body: { teaching_status } })
        setMessage(`Teacher designation set ${teaching_status}.`)
      } else {
        await apiRequest(`staff/${row.id}/teacher/`, { method: 'POST', body: {} })
        setMessage('Teacher designation created.')
      }
      await reload()
    } catch (e) { setError(e.message || 'Could not update teacher designation.') }
  }

  async function saveAssignment(event) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const body = { ...assignmentForm, teacher: Number(assignmentForm.teacher), academic_session: Number(assignmentForm.academic_session), class_level: Number(assignmentForm.class_level), class_arm: Number(assignmentForm.class_arm), subject: Number(assignmentForm.subject) }
      if (replaceFor) {
        await apiRequest(`assignments/${replaceFor.id}/replace/`, { method: 'POST', body: { ...body, reason: 'Authorized reassignment' } })
        setMessage('Assignment replaced; prior assignment is retained.')
      } else {
        await apiRequest('assignments/', { method: 'POST', body })
        setMessage('Teaching assignment created.')
      }
      setAssignmentForm(blankAssignment); setShowAssignmentForm(false); setReplaceFor(null); await loadAssignments()
    } catch (e) { setError(e.message || 'Could not create assignment.') }
    finally { setBusy(false) }
  }

  async function transitionAssignment(row, nextStatus) {
    const action = nextStatus === 'ended' ? 'End' : 'Cancel'
    if (!window.confirm(`${action} this teaching assignment? Its history will be preserved.`)) return
    try {
      await apiRequest(`assignments/${row.id}/transition/`, { method: 'POST', body: { status: nextStatus, end_date: new Date().toISOString().slice(0, 10) } })
      setMessage(`Assignment ${nextStatus}.`); await loadAssignments()
    } catch (e) { setError(e.message || `Could not ${action.toLowerCase()} assignment.`) }
  }

  return <main className="app-page"><header className="app-topbar"><BrandMark /><button className="text-button" onClick={() => navigate('/app')}>Back to home</button></header>
    <section className="app-content student-page"><p className="eyebrow">{selectedSchool?.school_name} · STAFF</p><h1 className="app-heading">Staff &amp; <em>teachers</em></h1><p className="intro">Employment profiles are separate from account access. Teaching responsibilities are recorded by session, class, arm, and subject.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="success-message" role="status">{message}</p>}
      {!isTeacher && <div className="student-toolbar"><input aria-label="Search staff" placeholder="Search name, staff number, or job title" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && reload()} /><select aria-label="Filter staff by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">All staff</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="suspended">Suspended</option><option value="former">Former</option></select>{canManage && <button className="primary-button" onClick={() => { setStaffForm(blankStaff); setEditingId(null); setShowStaffForm(!showStaffForm) }}>Add staff</button>}</div>}
      {canManage && <form className="membership-invite" onSubmit={sendInvite}><div><p className="panel-kicker">SCHOOL ACCESS</p><h2>Invite a staff member</h2></div><label>Email<input type="email" required value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} /></label><label>First name<input required value={invite.first_name} onChange={(e) => setInvite({ ...invite, first_name: e.target.value })} /></label><label>Last name<input value={invite.last_name} onChange={(e) => setInvite({ ...invite, last_name: e.target.value })} /></label><label>Role<select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}><option value="principal">Principal</option><option value="school_manager">School administrator</option><option value="teacher">Teacher</option><option value="accountant">Bursar</option><option value="receptionist">Other staff</option></select></label><button className="primary-button" disabled={busy}>{busy ? 'Sending…' : 'Invite staff'}</button></form>}
      {role === 'school_owner' && <OwnershipTransferPanel schoolId={selectedSchool.school_id} />}
      {showStaffForm && canManage && <form className="student-form" onSubmit={saveStaff}><h2>{editingId ? 'Edit staff profile' : 'New staff profile'}</h2><div className="student-fields">
        {Object.entries({ staff_number: 'Staff number', first_name: 'First name', middle_name: 'Middle name', last_name: 'Last name', work_email: 'Work email', phone: 'Phone', job_title: 'Job title', department: 'Department', employment_start_date: 'Start date', employment_end_date: 'End date', user: 'Existing account ID (optional)' }).map(([key, label]) => <label key={key}>{label}<input required={['staff_number', 'first_name', 'last_name', 'job_title', 'employment_start_date'].includes(key)} type={key.includes('date') ? 'date' : key === 'work_email' ? 'email' : 'text'} value={staffForm[key] || ''} onChange={(e) => setStaffForm({ ...staffForm, [key]: e.target.value })} /></label>)}
        <label>Employment type<select value={staffForm.employment_type} onChange={(e) => setStaffForm({ ...staffForm, employment_type: e.target.value })}><option value="full_time">Full time</option><option value="part_time">Part time</option><option value="contract">Contract</option><option value="temporary">Temporary</option></select></label><label>Status<select value={staffForm.status} onChange={(e) => setStaffForm({ ...staffForm, status: e.target.value })}><option value="active">Active</option><option value="inactive">Inactive</option><option value="suspended">Suspended</option><option value="former">Former</option></select></label>
      </div><div className="student-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save staff'}</button><button className="text-button" type="button" onClick={() => setShowStaffForm(false)}>Cancel</button></div><p className="academic-empty">Linking an account does not grant school access. The account must already have active membership here.</p></form>}
      {canManage && <section className="student-form"><div className="student-profile-heading"><h2>Teaching assignments</h2><button className="primary-button" onClick={() => setShowAssignmentForm(!showAssignmentForm)}>Add assignment</button></div>
        <p className="academic-hint">First assign subjects to a class in Classes &amp; subjects. Students enrolled in that class receive those subjects automatically; teaching assignments then connect each subject to a teacher.</p><div className="student-fields">{[['academic_session', sessions, 'Academic session'], ['class_level', classes, 'Class'], ['class_arm', arms, 'Arm'], ['subject', subjects, 'Subject']].map(([key, options, label]) => <label key={key}>{label}<select value={filters[key] || ''} onChange={async (e) => { const value = e.target.value; setFilters({ ...filters, [key]: value }); if (key === 'class_level' && value) { const [armRows, classSubjects] = await Promise.all([academicList(`classes/${value}/arms/`), academicList(`classes/${value}/subjects/`)]); setArms(armRows); const ids = classSubjects.filter((r) => r.is_active).map((r) => r.subject); setSubjects((prev) => prev.map((s) => ({ ...s, availableForClass: !ids.length || ids.includes(s.id) }))) } await loadAssignments({ ...filters, [key]: value }) }}><option value="">All</option>{options.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>)}<label>Teacher<select value={filters.teacher} onChange={(e) => { const next = { ...filters, teacher: e.target.value }; setFilters(next); loadAssignments(next) }}><option value="">All</option>{assignableTeachers.filter((r) => r.teacher_id && r.teacher_status === 'active').map((r) => <option key={r.id} value={r.teacher_id}>{r.first_name} {r.last_name}</option>)}</select></label></div>
        {showAssignmentForm && <form className="student-fields" onSubmit={saveAssignment}><h3>{replaceFor ? 'Replace teaching assignment' : 'New teaching assignment'}</h3>{!assignableTeachers.some((r) => r.teacher_id && r.teacher_status === 'active') && <p className="academic-empty">No assignable teachers yet. Add staff, then choose “Designate teacher” in the staff directory. Only active staff with an active teacher designation can be assigned.</p>}<label>Teacher<select required value={assignmentForm.teacher} onChange={(e) => setAssignmentForm({ ...assignmentForm, teacher: e.target.value })}><option value="">Choose teacher</option>{assignableTeachers.filter((r) => r.teacher_id && r.teacher_status === 'active').map((r) => <option key={r.id} value={r.teacher_id}>{r.first_name} {r.last_name} · {r.staff_number}</option>)}</select></label><label>Session<select required value={assignmentForm.academic_session} onChange={(e) => setAssignmentForm({ ...assignmentForm, academic_session: e.target.value })}><option value="">Choose session</option>{sessions.filter((r) => r.status !== 'completed').map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label><label>Class<select required value={assignmentForm.class_level} onChange={(e) => chooseClass(e.target.value)}><option value="">Choose class</option>{classes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label><label>Arm<select required value={assignmentForm.class_arm} onChange={(e) => setAssignmentForm({ ...assignmentForm, class_arm: e.target.value })}><option value="">Choose arm</option>{arms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label><label>Subject<select required value={assignmentForm.subject} onChange={(e) => setAssignmentForm({ ...assignmentForm, subject: e.target.value })}><option value="">Choose subject</option>{subjects.filter((r) => r.availableForClass !== false).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label><label>Start date<input type="date" required value={assignmentForm.start_date} onChange={(e) => setAssignmentForm({ ...assignmentForm, start_date: e.target.value })} /></label><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : replaceFor ? 'Confirm replacement' : 'Create assignment'}</button><button type="button" className="text-button" onClick={() => { setShowAssignmentForm(false); setReplaceFor(null) }}>Cancel</button></form>}
      </section>}
      {loading ? <p role="status">Loading staff…</p> : <div className="student-layout"><section className="student-list" aria-label="Staff directory">{rows.map((row) => <div key={row.id} className={`student-row ${selected?.id === row.id ? 'is-selected' : ''}`}><button className="staff-row-select" onClick={() => setSelected(row)}><strong>{row.last_name}, {row.first_name} {row.middle_name}</strong><span>{row.staff_number} · {row.job_title || 'Staff'} · {row.status}{row.is_teacher ? ` · ${row.teacher_status === 'active' ? 'Designated teacher' : 'Teacher inactive'}` : row.job_title?.toLowerCase().includes('teacher') ? ' · Designation needed' : ''}</span></button>{canManage && <div className="student-actions"><button className="text-button" onClick={() => editStaff(row)}>Edit</button><button className="text-button" disabled={!row.is_teacher && row.status !== 'active'} onClick={() => toggleTeacher(row)}>{row.is_teacher ? `${row.teacher_status === 'active' ? 'Deactivate' : 'Activate'} teacher` : 'Designate teacher'}</button></div>}</div>)}{!rows.length && <p className="academic-empty">No staff profiles found.</p>}</section>
        <section className="student-profile">{selected && !isTeacher && <><p className="panel-kicker">STAFF PROFILE</p><h2>{selected.first_name} {selected.middle_name} {selected.last_name}</h2><p>{selected.staff_number} · {selected.job_title || 'Staff'} · {selected.status}</p>{selected.work_email && <p>{selected.work_email}</p>}{selected.phone && <p>{selected.phone}</p>}{selected.employment_type && <p>{selected.employment_type} · {selected.employment_start_date}{selected.employment_end_date ? ` to ${selected.employment_end_date}` : ''}</p>}</>}<h2>{isTeacher ? 'My teaching assignments' : 'Assignment history'}</h2>{assignments.map((item) => <div key={item.id} className="staff-assignment"><strong>{item.teacher_name} · {item.subject_name}</strong><span>{item.academic_session_name} · {item.class_name} {item.class_arm_name} · {item.status}</span><span>{item.start_date}{item.end_date ? ` to ${item.end_date}` : ''}{item.previous_assignment_id ? ' · replacement history' : ''}</span>{canManage && item.status === 'active' && <div className="student-actions"><button className="text-button" onClick={() => transitionAssignment(item, 'ended')}>End</button><button className="text-button" onClick={() => transitionAssignment(item, 'cancelled')}>Cancel</button><button className="text-button" onClick={() => { setReplaceFor(item); setAssignmentForm({ ...blankAssignment, academic_session: String(item.academic_session) }); setShowAssignmentForm(true) }}>Replace</button></div>}</div>)}{!assignments.length && <p className="academic-empty">No teaching assignments found.</p>}</section></div>}
    </section></main>
}
