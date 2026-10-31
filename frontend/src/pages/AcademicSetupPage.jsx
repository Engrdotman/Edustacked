import { useCallback, useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { academicList, academicRequest, ApiError } from '../services/api.js'

const sections = [
  ['sessions', 'Sessions & terms'], ['classes', 'Classes & arms'],
  ['subjects', 'Subjects'], ['grading', 'Grading scales'],
]
const emptySession = { name: '', start_date: '', end_date: '' }
const emptyTerm = { name: '', sequence: '1', start_date: '', end_date: '' }
const emptyClass = { name: '', code: '', category: '', description: '' }
const emptyArm = { name: '', description: '' }
const emptySubject = { name: '', code: '', description: '' }
const emptyScale = { name: '', maximum_score: '100.00', description: '' }
const emptyBand = { label: '', min_score: '', max_score: '', description: '', grade_point: '' }

function messageFor(error) {
  if (error instanceof ApiError) {
    if (error.fields && typeof error.fields === 'object') {
      const details = Object.values(error.fields).flat().filter((value) => typeof value === 'string')
      if (details.length) return details.join(' ')
    }
    return error.message
  }
  return 'The request could not be completed.'
}

function FormField({ label, children }) {
  return <label className="academic-field">{label}{children}</label>
}

function EntryList({ rows, empty, render }) {
  if (!rows.length) return <p className="academic-empty">{empty}</p>
  return <div className="academic-record-list">{rows.map(render)}</div>
}

export default function AcademicSetupPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const [section, setSection] = useState('sessions')
  const [sessions, setSessions] = useState([])
  const [terms, setTerms] = useState([])
  const [classes, setClasses] = useState([])
  const [arms, setArms] = useState([])
  const [subjects, setSubjects] = useState([])
  const [assignments, setAssignments] = useState([])
  const [scales, setScales] = useState([])
  const [bands, setBands] = useState([])
  const [sessionId, setSessionId] = useState('')
  const [classId, setClassId] = useState('')
  const [scaleId, setScaleId] = useState('')
  const [sessionForm, setSessionForm] = useState(emptySession)
  const [sessionEditId, setSessionEditId] = useState(null)
  const [termForm, setTermForm] = useState(emptyTerm)
  const [termEditId, setTermEditId] = useState(null)
  const [classForm, setClassForm] = useState(emptyClass)
  const [classEditId, setClassEditId] = useState(null)
  const [armForm, setArmForm] = useState(emptyArm)
  const [armEditId, setArmEditId] = useState(null)
  const [subjectForm, setSubjectForm] = useState(emptySubject)
  const [subjectEditId, setSubjectEditId] = useState(null)
  const [scaleForm, setScaleForm] = useState(emptyScale)
  const [scaleEditId, setScaleEditId] = useState(null)
  const [bandForm, setBandForm] = useState(emptyBand)
  const [bandEditId, setBandEditId] = useState(null)
  const [assignmentSubject, setAssignmentSubject] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const refreshSessions = useCallback(async () => setSessions(await academicList('academic-sessions/')), [])
  const refreshClasses = useCallback(async () => setClasses(await academicList('classes/')), [])
  const refreshSubjects = useCallback(async () => setSubjects(await academicList('subjects/')), [])
  const refreshScales = useCallback(async () => setScales(await academicList('grading-scales/')), [])

  const refreshTerms = useCallback(async (id) => {
    setTerms(id ? await academicList(`terms/?academic_session=${id}`) : [])
  }, [])
  const refreshClassChildren = useCallback(async (id) => {
    if (!id) { setArms([]); setAssignments([]); return }
    const [armRows, assignmentRows] = await Promise.all([
      academicList(`classes/${id}/arms/`), academicList(`classes/${id}/subjects/`),
    ])
    setArms(armRows)
    setAssignments(assignmentRows)
  }, [])
  const refreshBands = useCallback(async (id) => {
    setBands(id ? await academicList(`grading-scales/${id}/bands/`) : [])
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [sessionRows, classRows, subjectRows, scaleRows] = await Promise.all([
        academicList('academic-sessions/'), academicList('classes/'),
        academicList('subjects/'), academicList('grading-scales/'),
      ])
      setSessions(sessionRows)
      setClasses(classRows)
      setSubjects(subjectRows)
      setScales(scaleRows)
      setSessionId((current) => sessionRows.some((item) => String(item.id) === String(current)) ? current : String(sessionRows[0]?.id || ''))
      setClassId((current) => classRows.some((item) => String(item.id) === String(current)) ? current : String(classRows[0]?.id || ''))
      setScaleId((current) => scaleRows.some((item) => String(item.id) === String(current)) ? current : String(scaleRows[0]?.id || ''))
    } catch (loadError) {
      setError(messageFor(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setSessionId(''); setClassId(''); setScaleId('')
    setTerms([]); setArms([]); setAssignments([]); setBands([])
    setSessionEditId(null); setSessionForm(emptySession)
    setTermEditId(null); setTermForm(emptyTerm)
    setClassEditId(null); setClassForm(emptyClass)
    setArmEditId(null); setArmForm(emptyArm)
    setSubjectEditId(null); setSubjectForm(emptySubject)
    setScaleEditId(null); setScaleForm(emptyScale)
    setBandEditId(null); setBandForm(emptyBand)
    reload()
  }, [reload, selectedSchool?.school_id])
  useEffect(() => { refreshTerms(sessionId).catch((loadError) => setError(messageFor(loadError))) }, [refreshTerms, sessionId])
  useEffect(() => { refreshClassChildren(classId).catch((loadError) => setError(messageFor(loadError))) }, [refreshClassChildren, classId])
  useEffect(() => { refreshBands(scaleId).catch((loadError) => setError(messageFor(loadError))) }, [refreshBands, scaleId])

  async function submit(action, after) {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await action()
      await after?.()
      setSuccess('Academic setup saved.')
    } catch (requestError) {
      setError(messageFor(requestError))
    } finally {
      setSaving(false)
    }
  }

  async function saveSession(event) {
    event.preventDefault()
    const path = sessionEditId ? `academic-sessions/${sessionEditId}/` : 'academic-sessions/'
    await submit(() => academicRequest(path, { method: sessionEditId ? 'PATCH' : 'POST', body: sessionForm }), async () => {
      setSessionForm(emptySession); setSessionEditId(null); await refreshSessions()
    })
  }

  async function saveTerm(event) {
    event.preventDefault()
    if (!sessionId) { setError('Create or select an academic session first.'); return }
    const payload = { ...termForm, sequence: Number(termForm.sequence), academic_session: Number(sessionId) }
    const path = termEditId ? `terms/${termEditId}/` : 'terms/'
    await submit(() => academicRequest(path, { method: termEditId ? 'PATCH' : 'POST', body: payload }), async () => {
      setTermForm(emptyTerm); setTermEditId(null); await refreshTerms(sessionId)
    })
  }

  async function saveClass(event) {
    event.preventDefault()
    const path = classEditId ? `classes/${classEditId}/` : 'classes/'
    await submit(() => academicRequest(path, { method: classEditId ? 'PATCH' : 'POST', body: classForm }), async () => {
      setClassForm(emptyClass); setClassEditId(null); await refreshClasses()
    })
  }

  async function saveArm(event) {
    event.preventDefault()
    if (!classId) { setError('Create or select a class first.'); return }
    const path = `classes/${classId}/arms/${armEditId ? `${armEditId}/` : ''}`
    await submit(() => academicRequest(path, { method: armEditId ? 'PATCH' : 'POST', body: armForm }), async () => {
      setArmForm(emptyArm); setArmEditId(null); await refreshClassChildren(classId)
    })
  }

  async function saveSubject(event) {
    event.preventDefault()
    const path = subjectEditId ? `subjects/${subjectEditId}/` : 'subjects/'
    await submit(() => academicRequest(path, { method: subjectEditId ? 'PATCH' : 'POST', body: subjectForm }), async () => {
      setSubjectForm(emptySubject); setSubjectEditId(null); await refreshSubjects()
    })
  }

  async function saveAssignment(event) {
    event.preventDefault()
    if (!classId || !assignmentSubject) return
    await submit(() => academicRequest(`classes/${classId}/subjects/`, {
      method: 'POST', body: { subject: Number(assignmentSubject) },
    }), async () => { setAssignmentSubject(''); await refreshClassChildren(classId) })
  }

  async function saveScale(event) {
    event.preventDefault()
    const path = scaleEditId ? `grading-scales/${scaleEditId}/` : 'grading-scales/'
    await submit(() => academicRequest(path, { method: scaleEditId ? 'PATCH' : 'POST', body: scaleForm }), async () => {
      setScaleForm(emptyScale); setScaleEditId(null); await refreshScales()
    })
  }

  async function saveBand(event) {
    event.preventDefault()
    if (!scaleId) { setError('Create or select a grading scale first.'); return }
    const payload = { ...bandForm, grade_point: bandForm.grade_point || null }
    const path = `grading-scales/${scaleId}/bands/${bandEditId ? `${bandEditId}/` : ''}`
    await submit(() => academicRequest(path, { method: bandEditId ? 'PATCH' : 'POST', body: payload }), async () => {
      setBandForm(emptyBand); setBandEditId(null); await refreshBands(scaleId)
    })
  }

  async function changeStatus(path, field, value, refresh, confirmText) {
    if (confirmText && !window.confirm(confirmText)) return
    await submit(() => academicRequest(path, { method: 'PATCH', body: { [field]: value } }), refresh)
  }

  function cancelAll() {
    setSessionEditId(null); setSessionForm(emptySession)
    setTermEditId(null); setTermForm(emptyTerm)
    setClassEditId(null); setClassForm(emptyClass)
    setArmEditId(null); setArmForm(emptyArm)
    setSubjectEditId(null); setSubjectForm(emptySubject)
    setScaleEditId(null); setScaleForm(emptyScale)
    setBandEditId(null); setBandForm(emptyBand)
    setError(''); setSuccess('')
  }

  const matching = (rows) => rows.filter((item) => JSON.stringify(item).toLowerCase().includes(search.toLowerCase()))
  const selectedSession = sessions.find((item) => String(item.id) === String(sessionId))
  const selectedClass = classes.find((item) => String(item.id) === String(classId))
  const selectedScale = scales.find((item) => String(item.id) === String(scaleId))

  return (
    <main className="app-page academic-page">
      <header className="app-topbar"><BrandMark /><button className="text-button" type="button" onClick={() => navigate('/app')}>Back to workspace</button></header>
      <section className="app-content academic-content">
        <p className="eyebrow">{selectedSchool?.school_name || 'SELECTED SCHOOL'} · ACADEMIC SETUP</p>
        <h1 className="app-heading">Academic<br /><em>structure.</em></h1>
        <p className="intro">Set up sessions, terms, classes, subjects, and a grading scale for this school. These settings are independent between schools.</p>
        <div className="academic-tabs" role="tablist" aria-label="Academic setup sections">
          {sections.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={section === key} className={section === key ? 'active' : ''} onClick={() => { setSection(key); setSearch(''); setError(''); setSuccess('') }}>{label}</button>)}
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        {success && <p className="form-success" role="status">{success}</p>}
        {loading ? <p className="loading-message" role="status">Loading academic configuration…</p> : (
          <>
            <div className="academic-toolbar"><label>Search this section<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search records" /></label><button className="secondary-button" type="button" onClick={cancelAll}>Clear forms</button></div>

            {section === 'sessions' && <div className="academic-columns">
              <div className="academic-panel"><h2>Academic sessions</h2>
                <EntryList rows={matching(sessions)} empty="No sessions yet. Create the first session for this school." render={(row) => <article className={`academic-record ${String(row.id) === String(sessionId) ? 'selected' : ''}`} key={row.id}>
                  <button className="academic-record-main" type="button" onClick={() => setSessionId(String(row.id))}><strong>{row.name}</strong><span>{row.start_date} – {row.end_date} · {row.status}</span></button>
                  {row.status === 'draft' && <button className="small-button" type="button" onClick={() => { setSessionEditId(row.id); setSessionForm({ name: row.name, start_date: row.start_date, end_date: row.end_date }) }}>Edit</button>}
                  {row.status !== 'completed' && <button className="small-button" type="button" disabled={saving} onClick={() => changeStatus(`academic-sessions/${row.id}/`, 'status', row.status === 'draft' ? 'active' : 'completed', refreshSessions, `${row.status === 'draft' ? 'Activate' : 'Complete'} this session?`)}>{row.status === 'draft' ? 'Activate' : 'Complete'}</button>}
                </article>} />
                <form className="academic-form" onSubmit={saveSession}><h3>{sessionEditId ? 'Edit draft session' : 'Add session'}</h3>
                  <FormField label="Session name"><input required maxLength="100" value={sessionForm.name} onChange={(e) => setSessionForm({ ...sessionForm, name: e.target.value })} placeholder="2026/2027" /></FormField>
                  <div className="academic-form-grid"><FormField label="Starts"><input type="date" required value={sessionForm.start_date} onChange={(e) => setSessionForm({ ...sessionForm, start_date: e.target.value })} /></FormField><FormField label="Ends"><input type="date" required value={sessionForm.end_date} onChange={(e) => setSessionForm({ ...sessionForm, end_date: e.target.value })} /></FormField></div>
                  <div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : sessionEditId ? 'Save session' : 'Create session'}</button>{sessionEditId && <button className="secondary-button" type="button" onClick={() => { setSessionEditId(null); setSessionForm(emptySession) }}>Cancel</button>}</div>
                </form>
              </div>
              <div className="academic-panel"><h2>Terms{selectedSession ? ` · ${selectedSession.name}` : ''}</h2>
                {!selectedSession ? <p className="academic-empty">Select or create a session to add its terms.</p> : <>
                  <EntryList rows={matching(terms)} empty="No terms configured for this session." render={(row) => <article className="academic-record" key={row.id}>
                    <div className="academic-record-main"><strong>{row.sequence}. {row.name}</strong><span>{row.start_date} – {row.end_date} · {row.status}</span></div>
                    {row.status === 'draft' && <button className="small-button" type="button" onClick={() => { setTermEditId(row.id); setTermForm({ name: row.name, sequence: String(row.sequence), start_date: row.start_date, end_date: row.end_date }) }}>Edit</button>}
                    {row.status === 'draft' && selectedSession.status === 'active' && <button className="small-button" type="button" disabled={saving} onClick={() => changeStatus(`terms/${row.id}/`, 'status', 'active', () => refreshTerms(sessionId), 'Activate this term?')}>Activate</button>}
                    {row.status === 'active' && <button className="small-button" type="button" disabled={saving} onClick={() => changeStatus(`terms/${row.id}/`, 'status', 'completed', () => refreshTerms(sessionId), 'Complete this term?')}>Complete</button>}
                  </article>} />
                  {selectedSession.status !== 'completed' ? <form className="academic-form" onSubmit={saveTerm}><h3>{termEditId ? 'Edit draft term' : 'Add term'}</h3>
                    <div className="academic-form-grid"><FormField label="Term name"><input required maxLength="60" value={termForm.name} onChange={(e) => setTermForm({ ...termForm, name: e.target.value })} placeholder="First Term" /></FormField><FormField label="Sequence"><input type="number" min="1" required value={termForm.sequence} onChange={(e) => setTermForm({ ...termForm, sequence: e.target.value })} /></FormField>
                      <FormField label="Starts"><input type="date" required value={termForm.start_date} onChange={(e) => setTermForm({ ...termForm, start_date: e.target.value })} /></FormField><FormField label="Ends"><input type="date" required value={termForm.end_date} onChange={(e) => setTermForm({ ...termForm, end_date: e.target.value })} /></FormField></div>
                    <div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : termEditId ? 'Save term' : 'Create term'}</button>{termEditId && <button className="secondary-button" type="button" onClick={() => { setTermEditId(null); setTermForm(emptyTerm) }}>Cancel</button>}</div>
                  </form> : <p className="academic-hint">This session is completed; its term history is read only.</p>}
                </>}
              </div>
            </div>}

            {section === 'classes' && <div className="academic-columns">
              <div className="academic-panel"><h2>Classes / grade levels</h2>
                <EntryList rows={matching(classes)} empty="No classes added yet." render={(row) => <article className={`academic-record ${String(row.id) === String(classId) ? 'selected' : ''}`} key={row.id}>
                  <button className="academic-record-main" type="button" onClick={() => setClassId(String(row.id))}><strong>{row.name}</strong><span>{row.code || row.category || 'No code'} · {row.is_active ? 'Active' : 'Inactive'}</span></button>
                  <button className="small-button" type="button" onClick={() => { setClassEditId(row.id); setClassForm({ name: row.name, code: row.code, category: row.category, description: row.description }) }}>Edit</button>
                  <button className="small-button" disabled={saving} type="button" onClick={() => changeStatus(`classes/${row.id}/`, 'is_active', !row.is_active, refreshClasses, `${row.is_active ? 'Deactivate' : 'Activate'} ${row.name}?`)}>{row.is_active ? 'Deactivate' : 'Activate'}</button>
                </article>} />
                <form className="academic-form" onSubmit={saveClass}><h3>{classEditId ? 'Edit class' : 'Add class'}</h3>
                  <FormField label="Class name"><input required maxLength="100" value={classForm.name} onChange={(e) => setClassForm({ ...classForm, name: e.target.value })} placeholder="Primary 1" /></FormField>
                  <div className="academic-form-grid"><FormField label="Code (optional)"><input maxLength="30" value={classForm.code} onChange={(e) => setClassForm({ ...classForm, code: e.target.value })} /></FormField><FormField label="Category"><select value={classForm.category} onChange={(e) => setClassForm({ ...classForm, category: e.target.value })}><option value="">Choose category</option><option value="early_years">Early years</option><option value="primary">Primary</option><option value="junior_secondary">Junior secondary</option><option value="senior_secondary">Senior secondary</option><option value="other">Other</option></select></FormField></div>
                  <FormField label="Description"><textarea rows="2" value={classForm.description} onChange={(e) => setClassForm({ ...classForm, description: e.target.value })} /></FormField>
                  <div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : classEditId ? 'Save class' : 'Create class'}</button>{classEditId && <button className="secondary-button" type="button" onClick={() => { setClassEditId(null); setClassForm(emptyClass) }}>Cancel</button>}</div>
                </form>
              </div>
              <div className="academic-panel"><h2>Arms &amp; assigned subjects{selectedClass ? ` · ${selectedClass.name}` : ''}</h2>
                {!selectedClass ? <p className="academic-empty">Select or create a class to configure arms and subjects.</p> : <>
                  <h3 className="academic-subheading">Class arms</h3>
                  <EntryList rows={matching(arms)} empty="No arms configured." render={(row) => <article className="academic-record" key={row.id}><div className="academic-record-main"><strong>{row.name}</strong><span>{row.is_active ? 'Active' : 'Inactive'}</span></div><button className="small-button" type="button" onClick={() => { setArmEditId(row.id); setArmForm({ name: row.name, description: row.description }) }}>Edit</button><button className="small-button" type="button" disabled={saving} onClick={() => changeStatus(`classes/${classId}/arms/${row.id}/`, 'is_active', !row.is_active, () => refreshClassChildren(classId), `Change ${row.name} active status?`)}>{row.is_active ? 'Deactivate' : 'Activate'}</button></article>} />
                  <form className="academic-form compact" onSubmit={saveArm}><h3>{armEditId ? 'Edit arm' : 'Add arm'}</h3><div className="academic-form-grid"><FormField label="Arm name"><input required maxLength="60" value={armForm.name} onChange={(e) => setArmForm({ ...armForm, name: e.target.value })} placeholder="A or Gold" /></FormField><FormField label="Description"><input value={armForm.description} onChange={(e) => setArmForm({ ...armForm, description: e.target.value })} /></FormField></div><div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : armEditId ? 'Save arm' : 'Add arm'}</button>{armEditId && <button className="secondary-button" type="button" onClick={() => { setArmEditId(null); setArmForm(emptyArm) }}>Cancel</button>}</div></form>
                  <h3 className="academic-subheading">Class subjects</h3><p className="academic-hint">Subjects assigned here are available to students enrolled in this class, across its arms. Assign teachers for each session from Staff &amp; teachers.</p>
                  <EntryList rows={matching(assignments)} empty="No subjects assigned to this class." render={(row) => <article className="academic-record" key={row.id}><div className="academic-record-main"><strong>{row.subject_name}</strong><span>{row.is_active ? 'Active' : 'Inactive'}</span></div><button className="small-button" type="button" disabled={saving} onClick={() => changeStatus(`classes/${classId}/subjects/${row.id}/`, 'is_active', !row.is_active, () => refreshClassChildren(classId), `Change ${row.subject_name} assignment status?`)}>{row.is_active ? 'Deactivate' : 'Activate'}</button></article>} />
                  <form className="academic-form compact" onSubmit={saveAssignment}><h3>Assign a subject</h3><div className="academic-form-grid"><FormField label="Subject"><select required value={assignmentSubject} onChange={(e) => setAssignmentSubject(e.target.value)}><option value="">Select a school subject</option>{subjects.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField><button className="primary-button" disabled={saving || !assignmentSubject}>{saving ? 'Saving…' : 'Assign subject'}</button></div></form>
                </>}
              </div>
            </div>}

            {section === 'subjects' && <section className="academic-panel"><h2>School subjects</h2>
              <EntryList rows={matching(subjects)} empty="No subjects added yet." render={(row) => <article className="academic-record" key={row.id}><div className="academic-record-main"><strong>{row.name}</strong><span>{row.code || 'No code'} · {row.is_active ? 'Active' : 'Inactive'}</span></div><button className="small-button" type="button" onClick={() => { setSubjectEditId(row.id); setSubjectForm({ name: row.name, code: row.code, description: row.description }) }}>Edit</button><button className="small-button" disabled={saving} type="button" onClick={() => changeStatus(`subjects/${row.id}/`, 'is_active', !row.is_active, refreshSubjects, `${row.is_active ? 'Deactivate' : 'Activate'} ${row.name}?`)}>{row.is_active ? 'Deactivate' : 'Activate'}</button></article>} />
              <form className="academic-form" onSubmit={saveSubject}><h3>{subjectEditId ? 'Edit subject' : 'Add subject'}</h3><div className="academic-form-grid"><FormField label="Subject name"><input required maxLength="120" value={subjectForm.name} onChange={(e) => setSubjectForm({ ...subjectForm, name: e.target.value })} placeholder="Mathematics" /></FormField><FormField label="Code (optional)"><input maxLength="30" value={subjectForm.code} onChange={(e) => setSubjectForm({ ...subjectForm, code: e.target.value })} /></FormField></div><FormField label="Description"><textarea rows="2" value={subjectForm.description} onChange={(e) => setSubjectForm({ ...subjectForm, description: e.target.value })} /></FormField><div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : subjectEditId ? 'Save subject' : 'Create subject'}</button>{subjectEditId && <button className="secondary-button" type="button" onClick={() => { setSubjectEditId(null); setSubjectForm(emptySubject) }}>Cancel</button>}</div></form>
            </section>}

            {section === 'grading' && <div className="academic-columns">
              <div className="academic-panel"><h2>Grading scales</h2>
                <EntryList rows={matching(scales)} empty="No grading scales yet. No grade boundaries are assumed by default." render={(row) => <article className={`academic-record ${String(row.id) === String(scaleId) ? 'selected' : ''}`} key={row.id}><button className="academic-record-main" type="button" onClick={() => setScaleId(String(row.id))}><strong>{row.name}</strong><span>Maximum {row.maximum_score} · {row.is_active ? 'Active' : 'Draft'}</span></button><button className="small-button" type="button" onClick={() => { setScaleEditId(row.id); setScaleForm({ name: row.name, maximum_score: row.maximum_score, description: row.description }) }}>Edit</button><button className="small-button" disabled={saving} type="button" onClick={() => changeStatus(`grading-scales/${row.id}/`, 'is_active', !row.is_active, refreshScales, `${row.is_active ? 'Deactivate' : 'Activate'} ${row.name}? An active scale requires complete contiguous bands.`)}>{row.is_active ? 'Deactivate' : 'Activate'}</button></article>} />
                <form className="academic-form" onSubmit={saveScale}><h3>{scaleEditId ? 'Edit scale' : 'Add grading scale'}</h3><div className="academic-form-grid"><FormField label="Scale name"><input required maxLength="100" value={scaleForm.name} onChange={(e) => setScaleForm({ ...scaleForm, name: e.target.value })} /></FormField><FormField label="Maximum score"><input type="number" min="0.01" max="999.99" step="0.01" required value={scaleForm.maximum_score} onChange={(e) => setScaleForm({ ...scaleForm, maximum_score: e.target.value })} /></FormField></div><FormField label="Description"><textarea rows="2" value={scaleForm.description} onChange={(e) => setScaleForm({ ...scaleForm, description: e.target.value })} /></FormField><div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : scaleEditId ? 'Save scale' : 'Create scale'}</button>{scaleEditId && <button className="secondary-button" type="button" onClick={() => { setScaleEditId(null); setScaleForm(emptyScale) }}>Cancel</button>}</div></form>
              </div>
              <div className="academic-panel"><h2>Grade bands{selectedScale ? ` · ${selectedScale.name}` : ''}</h2><p className="academic-hint">Bands use inclusive two-decimal boundaries. A scale can be activated only when active bands cover 0.00 through its maximum without gaps or overlap.</p>
                {!selectedScale ? <p className="academic-empty">Select or create a grading scale to add bands.</p> : <>
                  <EntryList rows={matching(bands)} empty="No grade bands configured." render={(row) => <article className="academic-record" key={row.id}><div className="academic-record-main"><strong>{row.label} · {row.min_score}–{row.max_score}</strong><span>{row.description || (row.grade_point ? `Grade point ${row.grade_point}` : row.is_active ? 'Active' : 'Inactive')}</span></div><button className="small-button" type="button" disabled={selectedScale.is_active} onClick={() => { setBandEditId(row.id); setBandForm({ label: row.label, min_score: row.min_score, max_score: row.max_score, description: row.description, grade_point: row.grade_point || '' }) }}>Edit</button><button className="small-button" type="button" disabled={saving || selectedScale.is_active} onClick={() => changeStatus(`grading-scales/${scaleId}/bands/${row.id}/`, 'is_active', !row.is_active, () => refreshBands(scaleId), 'Change this grade band active status?')}>{row.is_active ? 'Deactivate' : 'Activate'}</button></article>} />
                  {selectedScale.is_active && <p className="academic-hint">Deactivate this scale before changing grade bands.</p>}
                  <form className="academic-form compact" onSubmit={saveBand}><h3>{bandEditId ? 'Edit grade band' : 'Add grade band'}</h3><div className="academic-form-grid"><FormField label="Grade label"><input required maxLength="20" value={bandForm.label} onChange={(e) => setBandForm({ ...bandForm, label: e.target.value })} placeholder="A" /></FormField><FormField label="Minimum score"><input type="number" min="0" step="0.01" required value={bandForm.min_score} onChange={(e) => setBandForm({ ...bandForm, min_score: e.target.value })} /></FormField><FormField label="Maximum score"><input type="number" min="0" step="0.01" required value={bandForm.max_score} onChange={(e) => setBandForm({ ...bandForm, max_score: e.target.value })} /></FormField><FormField label="Grade point (optional)"><input type="number" min="0" step="0.01" value={bandForm.grade_point} onChange={(e) => setBandForm({ ...bandForm, grade_point: e.target.value })} /></FormField></div><FormField label="Description"><input maxLength="200" value={bandForm.description} onChange={(e) => setBandForm({ ...bandForm, description: e.target.value })} /></FormField><div className="form-actions"><button className="primary-button" disabled={saving || selectedScale.is_active}>{saving ? 'Saving…' : bandEditId ? 'Save band' : 'Add band'}</button>{bandEditId && <button className="secondary-button" type="button" onClick={() => { setBandEditId(null); setBandForm(emptyBand) }}>Cancel</button>}</div></form>
                </>}
              </div>
            </div>}
          </>
        )}
      </section>
    </main>
  )
}
