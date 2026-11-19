import { useCallback, useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { academicList, apiRequest, ApiError } from '../services/api.js'

function messageFor(error) {
  if (error instanceof ApiError) {
    if (error.fields && typeof error.fields === 'object') {
      const details = Object.values(error.fields).flat().filter((value) => typeof value === 'string')
      if (details.length) return details.join(' ')
    }
    return error.message
  }
  return 'The promotion review could not be loaded. Please try again.'
}

const decisionLabels = {
  promote: 'Meets promotion criteria',
  repeat: 'Repeat recommended',
  manual_review: 'Needs manual review',
}

export default function PromotionPlanningPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const [sessions, setSessions] = useState([])
  const [terms, setTerms] = useState([])
  const [classes, setClasses] = useState([])
  const [arms, setArms] = useState([])
  const [filters, setFilters] = useState({ academic_session: '', term: '', class_level: '', class_arm: '' })
  const [page, setPage] = useState(1)
  const [review, setReview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    Promise.all([academicList('academic-sessions/'), academicList('classes/')])
      .then(([sessionRows, classRows]) => {
        if (!live) return
        const eligibleSessions = sessionRows.filter((row) => row.status !== 'draft')
        setSessions(eligibleSessions)
        setClasses(classRows.filter((row) => row.is_active))
        setFilters((current) => ({
          ...current,
          academic_session: eligibleSessions.some((row) => String(row.id) === current.academic_session)
            ? current.academic_session : String(eligibleSessions[0]?.id || ''),
          class_level: classRows.some((row) => String(row.id) === current.class_level)
            ? current.class_level : String(classRows.find((row) => row.is_active)?.id || ''),
        }))
      })
      .catch((loadError) => { if (live) setError(messageFor(loadError)) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [selectedSchool?.school_id])

  useEffect(() => {
    let live = true
    if (!filters.academic_session) { setTerms([]); setFilters((current) => ({ ...current, term: '' })); return () => { live = false } }
    academicList(`terms/?academic_session=${filters.academic_session}`)
      .then((rows) => {
        if (!live) return
        const completed = rows.filter((row) => row.status === 'completed').sort((a, b) => b.sequence - a.sequence)
        setTerms(completed)
        setFilters((current) => ({
          ...current,
          term: completed.some((row) => String(row.id) === current.term) ? current.term : String(completed[0]?.id || ''),
        }))
      })
      .catch((loadError) => { if (live) setError(messageFor(loadError)) })
    return () => { live = false }
  }, [filters.academic_session])

  useEffect(() => {
    let live = true
    if (!filters.class_level) { setArms([]); setFilters((current) => ({ ...current, class_arm: '' })); return () => { live = false } }
    academicList(`classes/${filters.class_level}/arms/`)
      .then((rows) => {
        if (!live) return
        const active = rows.filter((row) => row.is_active)
        setArms(active)
        setFilters((current) => ({ ...current, class_arm: active.some((row) => String(row.id) === current.class_arm) ? current.class_arm : String(active[0]?.id || '') }))
      })
      .catch((loadError) => { if (live) setError(messageFor(loadError)) })
    return () => { live = false }
  }, [filters.class_level])

  const loadReview = useCallback(async () => {
    if (!filters.academic_session || !filters.term || !filters.class_level || !filters.class_arm) {
      setReview(null)
      return
    }
    setLoading(true)
    setError('')
    try {
      const query = new URLSearchParams({
        academic_session: filters.academic_session,
        term: filters.term,
        class_arm: filters.class_arm,
        page: String(page),
        page_size: '100',
      })
      setReview(await apiRequest(`academics/classes/${filters.class_level}/promotion-review/?${query}`))
    } catch (loadError) {
      setReview(null)
      setError(messageFor(loadError))
    } finally {
      setLoading(false)
    }
  }, [filters, page])

  useEffect(() => { loadReview() }, [loadReview])

  function updateFilter(field, value) {
    setPage(1)
    setError('')
    setFilters((current) => ({ ...current, [field]: value }))
  }

  const rows = review?.results || []
  const summary = review?.review
  const counts = summary?.decision_counts || {}

  return (
    <main className="app-page academic-page">
      <header className="app-topbar"><BrandMark navigate={navigate} /><button className="text-button" type="button" onClick={() => navigate('/app')}>Back to dashboard</button></header>
      <section className="app-content academic-content">
        <p className="eyebrow">{selectedSchool?.school_name || 'SELECTED SCHOOL'} · PROMOTION PLANNING</p>
        <h1 className="app-heading">Promotion<br /><em>review.</em></h1>
        <p className="intro">Review each student against this class’s promotion rule using approved results from the final completed term. This page recommends a decision; it never changes enrollment or class placement automatically.</p>

        <section className="academic-panel">
          <h2>Choose the completed session and class</h2>
          <div className="academic-form-grid">
            <label className="academic-field">Academic session<select value={filters.academic_session} onChange={(event) => updateFilter('academic_session', event.target.value)}><option value="">Choose session</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
            <label className="academic-field">Final completed term<select value={filters.term} onChange={(event) => updateFilter('term', event.target.value)}><option value="">Choose completed term</option>{terms.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
            <label className="academic-field">Class<select value={filters.class_level} onChange={(event) => updateFilter('class_level', event.target.value)}><option value="">Choose class</option>{classes.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
            <label className="academic-field">Arm<select value={filters.class_arm} onChange={(event) => updateFilter('class_arm', event.target.value)}><option value="">Choose arm</option>{arms.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          </div>
          {error && <p className="form-error" role="alert">{error}{error.toLowerCase().includes('criteria') && <> <button className="text-button" type="button" onClick={() => navigate('/app/academics')}>Set class criteria in Academic setup.</button></>}</p>}
          {loading && <p className="loading-message" role="status">Preparing the promotion review…</p>}
          {!loading && !error && !terms.length && <p className="academic-empty">Promotion review becomes available after the session’s final term is completed.</p>}
        </section>

        {summary && <>
          <section className="academic-panel">
            <p className="eyebrow">PROMOTION RULE</p>
            <h2>{summary.class_name} · {summary.arm_name}</h2>
            <p>Pass at least <strong>{summary.minimum_subjects_passed} of {summary.active_subjects} subjects</strong>, with a score of <strong>{summary.pass_mark}% or higher</strong> in each passed subject.</p>
            <div className="academic-form-grid">
              <p><strong>{review.count}</strong><br />Students reviewed</p>
              <p><strong>{counts.promote || 0}</strong><br />Meet promotion criteria</p>
              <p><strong>{counts.repeat || 0}</strong><br />Repeat recommended</p>
              <p><strong>{counts.manual_review || 0}</strong><br />Need manual review</p>
            </div>
          </section>
          <section className="academic-panel">
            <h2>Student recommendations</h2>
            <p className="academic-hint">Students with missing or conflicting approved results are marked for manual review; they are not automatically classed as repeats.</p>
            {rows.length ? <div className="academic-record-list">{rows.map((row) => <article className="academic-record" key={row.enrollment_id}>
              <div className="academic-record-main">
                <strong>{row.student_name} · {row.admission_number}</strong>
                <span>{row.subjects_passed} of {row.subjects_total} subjects passed · {decisionLabels[row.decision]}</span>
                {row.missing_subjects.length > 0 && <span>Awaiting approved results: {row.missing_subjects.join(', ')}</span>}
                {row.multiple_approved_results.length > 0 && <span>More than one approved result: {row.multiple_approved_results.join(', ')}</span>}
              </div>
              <details><summary>View subject results</summary><ul>{row.subject_results.map((result) => <li key={result.subject}>{result.subject}: {result.percentage}% · Grade {result.grade} · {result.passed ? 'Pass' : 'Below pass mark'}</li>)}</ul></details>
            </article>)}</div> : <p className="academic-empty">No active enrollments were found for this class, arm, and session.</p>}
            <div className="form-actions">
              <button className="secondary-button" type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>Previous</button>
              <span>Page {page} · {review.count} students</span>
              <button className="secondary-button" type="button" disabled={!review.next || loading} onClick={() => setPage((value) => value + 1)}>Next</button>
            </div>
            <p className="academic-hint">After the school confirms each recommendation, record the next session’s placement from <button className="text-button" type="button" onClick={() => navigate('/app/students')}>Student management</button>. Select the next class for promotion or the same class for repetition.</p>
          </section>
        </>}
      </section>
    </main>
  )
}
