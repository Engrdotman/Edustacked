import { useCallback, useEffect, useMemo, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { academicList, apiBlobRequest, apiRequest } from '../services/api.js'

const emptyFilters = { academic_session: '', term: '', class_level: '', class_arm: '', status: '', search: '' }
const messageFor = (error) => {
  if (error?.fields && typeof error.fields === 'object') return Object.values(error.fields).flat().map((item) => typeof item === 'string' ? item : '').filter(Boolean).join(' ')
  return error?.message || 'The request could not be completed.'
}

export default function ReportCardsPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const role = selectedSchool?.role
  const canGenerate = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(role)
  const canReview = canGenerate
  const canApprove = ['platform_superadmin', 'school_owner', 'school_admin'].includes(role)
  const [sessions, setSessions] = useState([])
  const [terms, setTerms] = useState([])
  const [classes, setClasses] = useState([])
  const [arms, setArms] = useState([])
  const [filters, setFilters] = useState(emptyFilters)
  const [cards, setCards] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [card, setCard] = useState(null)
  const [remarks, setRemarks] = useState({ teacher: '', head_teacher: '', conduct: '', effort: '', class_teacher_signature_name: '', head_teacher_signature_name: '' })
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [generation, setGeneration] = useState(null)

  const query = useMemo(() => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value) })
    return params.toString()
  }, [filters])

  const loadCards = useCallback(async () => {
    const data = await apiRequest(`report-cards/${query ? `?${query}` : ''}`)
    setCards(data.results || [])
    setSelectedId((current) => data.results?.some((item) => String(item.id) === String(current)) ? current : String(data.results?.[0]?.id || ''))
  }, [query])

  const loadCard = useCallback(async (id = selectedId) => {
    if (!id) { setCard(null); return }
    const data = await apiRequest(`report-cards/${id}/`)
    setCard(data)
    const content = data.current?.snapshot || {}
    setRemarks({
      teacher: content.remarks?.teacher || '', head_teacher: content.remarks?.head_teacher || '',
      conduct: content.remarks?.conduct || '', effort: content.remarks?.effort || '',
      class_teacher_signature_name: content.signatures?.class_teacher || '', head_teacher_signature_name: content.signatures?.head_teacher || '',
    })
  }, [selectedId])

  useEffect(() => {
    let live = true
    Promise.all([academicList('academic-sessions/'), academicList('classes/')])
      .then(([sessionData, classData]) => { if (live) { setSessions(sessionData); setClasses(classData) } })
      .catch((e) => live && setError(messageFor(e)))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [])

  useEffect(() => {
    if (!filters.academic_session) { setTerms([]); return }
    academicList(`terms/?academic_session=${filters.academic_session}`).then(setTerms).catch((e) => setError(messageFor(e)))
  }, [filters.academic_session])
  useEffect(() => {
    if (!filters.class_level) { setArms([]); return }
    academicList(`classes/${filters.class_level}/arms/`).then(setArms).catch((e) => setError(messageFor(e)))
  }, [filters.class_level])
  useEffect(() => { loadCards().catch((e) => setError(messageFor(e))) }, [loadCards])
  useEffect(() => { if (selectedId) loadCard(selectedId).catch((e) => setError(messageFor(e))); else setCard(null) }, [selectedId, loadCard])

  async function run(action, doneMessage) {
    setWorking(true); setError(''); setSuccess('')
    try { const result = await action(); if (doneMessage) setSuccess(typeof result === 'string' ? result : doneMessage) }
    catch (e) { setError(messageFor(e)) }
    finally { setWorking(false) }
  }

  async function generateClass() {
    if (!filters.academic_session || !filters.term || !filters.class_level || !filters.class_arm) {
      setError('Choose a session, term, class, and arm to generate report cards.'); return
    }
    await run(async () => {
      const result = await apiRequest('report-cards/generate-class/', { method: 'POST', body: { academic_session: Number(filters.academic_session), term: Number(filters.term), class_level: Number(filters.class_level), class_arm: Number(filters.class_arm) } })
      setGeneration(result); await loadCards()
    }, 'Class report-card generation finished. Check validation messages below.')
  }

  async function cardAction(action) {
    const reason = ['return', 'correct'].includes(action) ? window.prompt(action === 'correct' ? 'Reason for creating a correction revision:' : 'Reason for returning this report card:') : ''
    if (['return', 'correct'].includes(action) && !reason?.trim()) return
    await run(async () => { const result = await apiRequest(`report-cards/${card.id}/${action}/`, { method: 'POST', body: { reason } }); await loadCard(card.id); await loadCards(); if (action === 'finalize' && result.billing) return result.billing.credit_charged ? `Published. One credit used; ${result.billing.credit_balance} remain.` : `Published. This student and term were already billed; no credit used. ${result.billing.credit_balance} remain.` }, ({ review: 'Report card submitted for review.', approve: 'Report card approved.', finalize: 'Official report card finalized.', return: 'Report card returned for correction.', correct: 'New correction revision started.' })[action])
  }

  async function saveRemarks(event) {
    event.preventDefault()
    await run(async () => { await apiRequest(`report-cards/${card.id}/`, { method: 'PATCH', body: remarks }); await loadCard(card.id) }, 'Remarks saved to the current draft.')
  }

  async function openPdf(preview) {
    const previewWindow = preview ? window.open('', '_blank') : null
    if (preview && !previewWindow) { setError('Allow pop-up windows to preview the PDF.'); return }
    if (previewWindow) previewWindow.opener = null
    await run(async () => {
      const blob = await apiBlobRequest(`report-cards/${card.id}/pdf/${preview ? '?preview=true' : ''}`)
      const url = URL.createObjectURL(blob)
      if (previewWindow) previewWindow.location.href = url
      else {
        const link = document.createElement('a'); link.href = url; link.download = `${card.identifier}-${(card.student_name || 'student').replaceAll(' ', '-')}-v${card.current_revision}.pdf`; link.click()
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    }, preview ? 'PDF preview opened.' : 'PDF downloaded.')
  }

  const current = card?.current
  const snapshot = current?.snapshot
  const currentCardRow = cards.find((item) => String(item.id) === String(card?.id))

  return <main className="app-page"><header className="app-topbar"><BrandMark /><button className="text-button" onClick={() => navigate('/app')}>Back to home</button></header>
    <section className="app-content report-cards-page"><p className="eyebrow">{selectedSchool?.school_name} · REPORT CARDS</p><h1 className="app-heading">Report <em>cards</em></h1><p className="intro">Generate report-card drafts from approved results, review them, and publish a preserved official version.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}{loading && <p className="loading-message" role="status">Loading report cards…</p>}
      <section className="report-card-panel"><div className="report-card-panel-heading"><div><p className="panel-kicker">REPORT CARD REGISTER</p><h2>Find or generate report cards</h2></div></div>
        <div className="report-card-filters"><label>Session<select value={filters.academic_session} onChange={(e) => setFilters({ ...filters, academic_session: e.target.value, term: '' })}><option value="">All sessions</option>{sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Term<select value={filters.term} onChange={(e) => setFilters({ ...filters, term: e.target.value })}><option value="">All terms</option>{terms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Class<select value={filters.class_level} onChange={(e) => setFilters({ ...filters, class_level: e.target.value, class_arm: '' })}><option value="">All classes</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Arm<select value={filters.class_arm} onChange={(e) => setFilters({ ...filters, class_arm: e.target.value })}><option value="">All arms</option>{arms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Status<select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option>{[['draft', 'Draft'], ['review', 'Ready for review'], ['approved', 'Approved'], ['finalized', 'Finalized']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Search<input value={filters.search} placeholder="Student or report ID" onChange={(e) => setFilters({ ...filters, search: e.target.value })} /></label>{canGenerate && <button className="primary-button" onClick={generateClass} disabled={working}>Generate class report cards</button>}</div>
        <div className="report-card-list">{cards.map((item) => <button key={item.id} className={`report-card-list-row ${String(item.id) === String(selectedId) ? 'report-card-list-row-active' : ''}`} onClick={() => setSelectedId(String(item.id))}><span><strong>{item.student_name}</strong><small>{item.admission_number} · {item.class_name} {item.arm_name}</small></span><span className={`report-card-state report-card-state-${item.status}`}>{item.status.replaceAll('_', ' ')}</span><small>{item.term_name} · Rev {item.current_revision}</small></button>)}{!cards.length && <p className="academic-empty">No report cards match these filters.</p>}</div>
      </section>
      {generation && <section className="report-card-panel"><h2>Generation results</h2><p>{generation.generated} generated · {generation.failed} failed</p>{generation.results?.map((item) => <p key={item.report_card_id}><strong>{item.identifier}</strong> · {item.status}{item.validation_errors?.length ? ` · ${item.validation_errors.join(' ')}` : ' · Ready to review'} <button className="text-button" onClick={() => setSelectedId(String(item.report_card_id))}>Open</button></p>)}{generation.failures?.map((item) => <p className="form-error" key={item.student_id}>{item.admission_number}: {item.errors.join?.(' ') || item.errors}</p>)}</section>}

      {card && snapshot && <section className="report-card-panel"><div className="report-card-panel-heading"><div><p className="panel-kicker">{card.identifier} · REVISION {card.current_revision}</p><h2>{snapshot.student.name}</h2><p>{snapshot.student.admission_number} · {snapshot.student.class_name} {snapshot.student.arm_name} · {snapshot.academic.session} · {snapshot.academic.term}</p></div><span className={`report-card-state report-card-state-${card.status}`}>{card.status.replaceAll('_', ' ')}</span></div>
        {current.validation_errors?.length > 0 && <div className="report-card-validation"><strong>Action required before review</strong><ul>{current.validation_errors.map((item) => <li key={item}>{item}</li>)}</ul></div>}
        <div className="report-card-subjects"><h3>Academic performance</h3><div className="report-card-table-wrap"><table><thead><tr><th>Subject</th><th>Components</th><th>Total</th><th>Percentage</th><th>Grade</th></tr></thead><tbody>{snapshot.subjects.map((subject) => <tr key={subject.subject_id}><td>{subject.subject_name}</td><td>{subject.components.map((component) => `${component.name}: ${component.score ?? '—'} / ${component.max_score}`).join(' · ')}</td><td>{subject.total} / {subject.maximum}</td><td>{subject.percentage}%</td><td><strong>{subject.grade}</strong><small>{subject.grade_description}</small></td></tr>)}{!snapshot.subjects.length && <tr><td colSpan="5">No approved subject results are available.</td></tr>}</tbody></table></div></div>
        <div className="report-card-attendance"><h3>Attendance · finalized registers only</h3><p>{snapshot.attendance.present} present · {snapshot.attendance.absent} absent · {snapshot.attendance.late} late · {snapshot.attendance.excused} excused · {snapshot.attendance.register_days_with_record} days with recorded attendance</p><small>{snapshot.attendance.attendance_percentage ? `${snapshot.attendance.attendance_percentage}% attendance among recorded finalized statuses.` : 'Attendance percentage unavailable; no finalized attendance records were found.'} Missing registers are excluded, not counted as absences.</small></div>
        <div className="report-card-actions"><button className="secondary-button" onClick={() => openPdf(true)} disabled={working}>Preview PDF</button><button className="secondary-button" onClick={() => openPdf(false)} disabled={working}>Download / reprint PDF</button>{canReview && card.status === 'draft' && <button className="secondary-button" onClick={() => cardAction('review')} disabled={working || current.validation_errors?.length > 0}>Submit for review</button>}{canApprove && card.status === 'review' && <button className="primary-button" onClick={() => cardAction('approve')} disabled={working}>Approve</button>}{canApprove && card.status === 'approved' && <button className="primary-button" onClick={() => cardAction('finalize')} disabled={working}>Finalize and publish</button>}{canReview && ['review', 'approved'].includes(card.status) && <button className="text-button" onClick={() => cardAction('return')} disabled={working}>Return for correction</button>}{canApprove && card.status === 'finalized' && <button className="text-button" onClick={() => cardAction('correct')} disabled={working}>Create correction revision</button>}</div>
        {canReview && card.status === 'draft' && <form className="report-card-remarks" onSubmit={saveRemarks}><h3>Remarks and sign-off names</h3><div className="report-card-remarks-grid"><label>Teacher remark<textarea rows="3" maxLength="1000" value={remarks.teacher} onChange={(e) => setRemarks({ ...remarks, teacher: e.target.value })} /></label><label>Head-teacher remark<textarea rows="3" maxLength="1000" value={remarks.head_teacher} onChange={(e) => setRemarks({ ...remarks, head_teacher: e.target.value })} /></label><label>Conduct<input maxLength="300" value={remarks.conduct} onChange={(e) => setRemarks({ ...remarks, conduct: e.target.value })} /></label><label>Effort<input maxLength="300" value={remarks.effort} onChange={(e) => setRemarks({ ...remarks, effort: e.target.value })} /></label><label>Class-teacher sign-off name<input maxLength="150" value={remarks.class_teacher_signature_name} onChange={(e) => setRemarks({ ...remarks, class_teacher_signature_name: e.target.value })} /></label><label>Head-teacher sign-off name<input maxLength="150" value={remarks.head_teacher_signature_name} onChange={(e) => setRemarks({ ...remarks, head_teacher_signature_name: e.target.value })} /></label></div><button className="secondary-button" disabled={working}>Save draft remarks</button><p className="report-card-note">Names are displayed as sign-off labels only. No signature is claimed or fabricated.</p></form>}
        <section className="report-card-history"><h3>Revision and audit history</h3>{card.revisions.map((revision) => <div key={revision.id}><strong>Revision {revision.revision_number} · {revision.status}</strong><span>{revision.reason || (revision.finalized_at ? `Published ${new Date(revision.finalized_at).toLocaleString()}` : '')}</span></div>)}{card.audit_events.map((event) => <div key={`audit-${event.id}`}><strong>{event.action.replaceAll('_', ' ')}</strong><span>{event.actor_name} · {new Date(event.created_at).toLocaleString()}{event.reason ? ` · ${event.reason}` : ''}</span></div>)}</section>
      </section>}
      {currentCardRow && <p className="report-card-note">Current official report-card snapshot: {currentCardRow.status === 'finalized' ? 'published' : 'not finalized'} · Preview, download, and reprint do not change lifecycle status.</p>}
    </section>
  </main>
}
