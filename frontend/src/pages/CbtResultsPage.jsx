import { useEffect, useMemo, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { ApiError, apiBlobRequest, apiRequest } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'

const emptyFilters = { academic_session: '', term: '', class_level: '', subject: '', examination: '', student: '', start_date: '', end_date: '' }
const rolesCanManage = ['platform_superadmin', 'school_owner', 'school_admin', 'principal']
const messageFor = (error) => error instanceof ApiError ? error.message : 'The request could not be completed.'
const display = (value, suffix = '') => value === null || value === undefined || value === '' ? '—' : `${value}${suffix}`
const formatDate = (value) => value ? new Date(value).toLocaleDateString() : '—'
const optionLabels = (answer, ids) => (ids || []).map((id) => answer.options?.find((option) => option.id === id)?.text || id).join(', ')

export default function CbtResultsPage({ navigate, resultId = '' }) {
  const { selectedSchool, signOut } = useAuth()
  const [filters, setFilters] = useState(emptyFilters)
  const [dashboard, setDashboard] = useState(null)
  const [detail, setDetail] = useState(null)
  const [marks, setMarks] = useState({})
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const canManage = rolesCanManage.includes(selectedSchool?.role)

  async function loadDashboard(nextFilters = filters, page = 1) {
    const params = new URLSearchParams()
    Object.entries(nextFilters).forEach(([key, value]) => { if (value) params.set(key, value) })
    params.set('page', String(page))
    const data = await apiRequest(`cbt/results/?${params.toString()}`)
    setDashboard(data)
  }

  async function loadDetail() {
    if (!resultId) { setDetail(null); return }
    const data = await apiRequest(`cbt/results/${resultId}/`)
    setDetail(data)
    setMarks(Object.fromEntries(data.answers.map((answer) => [answer.question_id, answer.marks_awarded ?? ''])))
  }

  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    Promise.all([loadDashboard(), loadDetail()])
      .catch((requestError) => { if (active) setError(messageFor(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [resultId])

  const summary = dashboard?.summary || {}
  const analytics = dashboard?.analytics || {}
  const filterOptions = dashboard?.filters || {}
  const rows = dashboard?.results || []
  const maxBin = useMemo(() => Math.max(1, ...(analytics.score_distribution || []).map((item) => item.count)), [analytics.score_distribution])

  async function applyFilters(event) {
    event.preventDefault(); setLoading(true); setError('')
    try { await loadDashboard(filters, 1) } catch (requestError) { setError(messageFor(requestError)) }
    finally { setLoading(false) }
  }

  async function changePage(page) {
    setLoading(true)
    try { await loadDashboard(filters, page) } catch (requestError) { setError(messageFor(requestError)) }
    finally { setLoading(false) }
  }

  async function exportCsv() {
    setWorking(true); setError('')
    try {
      const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value))
      const blob = await apiBlobRequest(`cbt/results/export/?${params.toString()}`)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a'); link.href = url; link.download = 'edustacked-cbt-results.csv'; link.click()
      URL.revokeObjectURL(url)
    } catch (requestError) { setError(messageFor(requestError)) }
    finally { setWorking(false) }
  }

  async function saveMarks(event) {
    event.preventDefault(); setWorking(true); setError(''); setNotice('')
    const updates = Object.fromEntries(Object.entries(marks).filter(([, value]) => value !== ''))
    try {
      await apiRequest(`cbt/results/${resultId}/corrections/`, { method: 'POST', body: { marks: updates, reason } })
      setNotice('Marks saved. The previous and corrected marks were recorded in the audit trail.')
      setReason(''); await loadDetail(); await loadDashboard()
    } catch (requestError) { setError(messageFor(requestError)) }
    finally { setWorking(false) }
  }

  async function handleSignOut() { await signOut(); navigate('/') }

  return <main className="app-page">
    <header className="app-topbar"><BrandMark navigate={navigate} /><nav className="page-actions" aria-label="Page actions"><button className="text-button" onClick={() => navigate('/app')}>Dashboard</button><button className="text-button" onClick={() => navigate('/app/cbt')}>CBT setup</button><button className="text-button" onClick={handleSignOut}>Sign out</button></nav></header>
    <section className="app-content cbt-results-content">
      <p className="eyebrow">{selectedSchool?.school_name} · OFFLINE CBT</p>
      <h1 className="app-heading">Examination <em>results</em></h1>
      <p className="intro">Synchronized attempts are marked against the published question snapshots. Essay responses remain pending until an authorized reviewer grades them.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="form-success" role="status">{notice}</p>}

      {resultId && detail ? <>
        <div className="cbt-results-toolbar"><button className="secondary-button" onClick={() => navigate('/app/cbt/results')}>← All results</button><button className="secondary-button" onClick={() => window.print()}>Print result</button></div>
        <section className="cbt-panel cbt-result-paper">
          <p className="panel-kicker">INDIVIDUAL STUDENT RESULT</p><h2>{detail.student_name}</h2>
          <p className="cbt-results-subtitle">{detail.admission_number} · {detail.class_name} · {detail.subject_name}</p>
          <div className="cbt-result-meta"><span><b>Examination</b>{detail.examination_title}</span><span><b>Exam date</b>{formatDate(detail.exam_date)}</span><span><b>Submitted</b>{formatDate(detail.submitted_at)}</span><span><b>Synchronized</b>{formatDate(detail.synchronized_at)}</span></div>
          <div className="cbt-result-kpis"><article><span>Questions</span><strong>{detail.total_questions}</strong></article><article><span>Attempted</span><strong>{detail.attempted_questions}</strong></article><article><span>Unanswered</span><strong>{detail.unanswered_questions}</strong></article><article><span>Correct</span><strong>{detail.correct_answers}</strong></article><article><span>Incorrect</span><strong>{detail.incorrect_answers}</strong></article><article><span>Score</span><strong>{detail.score == null ? `Marking · ${detail.objective_score}/${detail.maximum_score}` : `${detail.score}/${detail.maximum_score}`}</strong></article><article><span>Percentage</span><strong>{display(detail.percentage, '%')}</strong></article><article><span>Outcome</span><strong>{detail.status === 'needs_marking' ? 'Needs marking' : detail.passed ? 'Passed' : 'Failed'}</strong></article></div>
          {detail.review_allowed && <div className="cbt-answer-review"><h3>Answer review</h3>{detail.answers.map((answer) => <article key={answer.question_id}><div><b>Q{answer.position + 1}. {answer.prompt}</b><span>{answer.attempted ? `Response: ${Array.isArray(answer.response) ? optionLabels(answer, answer.response) : optionLabels(answer, [answer.response]) || answer.response}` : 'Unanswered'}</span>{answer.correct_option_ids?.length > 0 && <span>Correct answer: {optionLabels(answer, answer.correct_option_ids)}</span>}{answer.explanation && <span>Explanation: {answer.explanation}</span>}</div><strong>{answer.marks_awarded == null ? 'Pending manual mark' : `${answer.marks_awarded} / ${answer.marks_possible}`}</strong></article>)}</div>}
          {!detail.review_allowed && <p className="selection-note">Answer explanations and keys are withheld until the examination window ends ({formatDate(detail.answer_release_at)}).</p>}
          {canManage && <form className="cbt-correction-form" onSubmit={saveMarks}><p className="panel-kicker">AUDITED MARKING / CORRECTION</p><h3>Review question marks</h3><p>Enter a mark for each question you are grading or correcting. Original responses remain unchanged.</p>{detail.answers.map((answer) => <label key={answer.question_id}>Q{answer.position + 1} · {answer.prompt}<span className="cbt-mark-input"><input type="number" min="0" max={answer.marks_possible} step="0.01" value={marks[answer.question_id] ?? ''} onChange={(event) => setMarks({ ...marks, [answer.question_id]: event.target.value })} placeholder={answer.attempted ? 'Enter mark' : 'Unanswered'} /><small>out of {answer.marks_possible}</small></span></label>)}<label>Reason for marking/correction<textarea minLength="5" required value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Record why these marks are being entered or changed" /></label><button className="primary-button" disabled={working}>{working ? 'Saving…' : 'Save marks with audit'}</button></form>}
          {detail.corrections?.length > 0 && <div className="cbt-correction-history"><h3>Marking audit</h3>{detail.corrections.map((item, index) => <p key={`${item.created_at}-${index}`}>{formatDate(item.created_at)} · {item.corrected_by} · {item.reason}</p>)}</div>}
        </section>
      </> : <>
        <div className="cbt-results-toolbar"><button className="secondary-button" onClick={() => navigate('/app/cbt')}>Manage exams</button><button className="primary-button" disabled={working} onClick={exportCsv}>{working ? 'Preparing…' : 'Export CSV'}</button><button className="secondary-button" onClick={() => window.print()}>Print report</button></div>
        <form className="cbt-panel cbt-results-filters" onSubmit={applyFilters}><p className="panel-kicker">FILTER RESULTS</p><div className="cbt-form-grid">
          <label>Academic session<select value={filters.academic_session} onChange={(e) => setFilters({ ...filters, academic_session: e.target.value })}><option value="">All sessions</option>{(filterOptions.sessions || []).map((x) => <option key={x.academic_session_id} value={x.academic_session_id}>{x.academic_session__name}</option>)}</select></label>
          <label>Term<select value={filters.term} onChange={(e) => setFilters({ ...filters, term: e.target.value })}><option value="">All terms</option>{(filterOptions.terms || []).map((x) => <option key={x.term_id} value={x.term_id}>{x.term__name}</option>)}</select></label>
          <label>Class<select value={filters.class_level} onChange={(e) => setFilters({ ...filters, class_level: e.target.value })}><option value="">All classes</option>{(filterOptions.classes || []).map((x) => <option key={x.class_level_id} value={x.class_level_id}>{x.class_level__name}</option>)}</select></label>
          <label>Subject<select value={filters.subject} onChange={(e) => setFilters({ ...filters, subject: e.target.value })}><option value="">All subjects</option>{(filterOptions.subjects || []).map((x) => <option key={x.subject_id} value={x.subject_id}>{x.subject__name}</option>)}</select></label>
          <label>Examination<select value={filters.examination} onChange={(e) => setFilters({ ...filters, examination: e.target.value })}><option value="">All examinations</option>{(filterOptions.examinations || []).map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</select></label>
          <label>Student<select value={filters.student} onChange={(e) => setFilters({ ...filters, student: e.target.value })}><option value="">All students</option>{(filterOptions.students || []).map((x) => <option key={x.student_id} value={x.student_id}>{x.student__last_name}, {x.student__first_name} · {x.student__admission_number}</option>)}</select></label>
          <label>Submitted from<input type="date" value={filters.start_date} onChange={(e) => setFilters({ ...filters, start_date: e.target.value })} /></label><label>Submitted to<input type="date" value={filters.end_date} onChange={(e) => setFilters({ ...filters, end_date: e.target.value })} /></label>
        </div><div className="cbt-actions"><button className="primary-button" disabled={loading}>Apply filters</button><button className="text-button" type="button" onClick={() => { setFilters(emptyFilters); loadDashboard(emptyFilters) }}>Clear</button></div></form>
        {loading ? <p className="loading-message">Loading examination results…</p> : dashboard && <>
          <section className="cbt-result-kpis cbt-result-summary"><article><span>Students assigned</span><strong>{summary.total_assigned}</strong></article><article><span>Participated</span><strong>{summary.participated}</strong></article><article><span>Did not participate</span><strong>{summary.not_participated}</strong></article><article><span>Completed exams</span><strong>{summary.completed_examinations}</strong></article><article><span>Average score</span><strong>{display(summary.average_score, '%')}</strong></article><article><span>Highest score</span><strong>{display(summary.highest_score, '%')}</strong></article><article><span>Lowest score</span><strong>{display(summary.lowest_score, '%')}</strong></article><article><span>Pass rate</span><strong>{display(summary.pass_rate, '%')}</strong></article><article><span>Failure rate</span><strong>{display(summary.failure_rate, '%')}</strong></article><article><span>Pending sync review</span><strong>{summary.pending_sync}</strong></article><article><span>Needs manual marking</span><strong>{summary.pending_manual_marking}</strong></article></section>
          {summary.small_sample && <p className="selection-note">Performance rates are based on {summary.sample_size} finalized result(s); treat these figures as preliminary until at least five results are available.</p>}
          <section className="cbt-results-grid"><article className="cbt-panel"><p className="panel-kicker">SCORE DISTRIBUTION</p><h2>Student performance</h2><div className="cbt-chart-bars">{analytics.score_distribution?.map((item) => <div key={item.label}><span>{item.label}</span><i><b style={{ width: `${item.count / maxBin * 100}%` }} /></i><strong>{item.count}</strong></div>)}</div></article><article className="cbt-panel"><p className="panel-kicker">PERFORMANCE TREND</p><h2>Monthly average</h2>{analytics.trend_sufficient ? analytics.trend.map((item) => <p className="cbt-trend-row" key={item.month}><span>{item.month}</span><b>{item.average}%</b><small>{item.attempts} attempts</small></p>) : <p className="selection-note">Trend needs results from at least two different months.</p>}</article></section>
          <section className="cbt-results-grid"><article className="cbt-panel"><p className="panel-kicker">CLASS PERFORMANCE</p><h2>Average score by class</h2>{analytics.class_performance?.map((item) => <p className="cbt-analytics-row" key={item.id}><span>{item.name}</span><b>{item.average}%</b><small>{item.students} students · {item.attempts} attempts{item.students < 5 ? ' · small sample' : ''}</small></p>)}{!analytics.class_performance?.length && <p className="selection-note">No finalized class results yet.</p>}</article><article className="cbt-panel"><p className="panel-kicker">SUBJECT PERFORMANCE</p><h2>Average score by subject</h2>{analytics.subject_performance?.map((item) => <p className="cbt-analytics-row" key={item.id}><span>{item.name}</span><b>{item.average}%</b><small>{item.students} students · {item.attempts} attempts{item.students < 5 ? ' · small sample' : ''}</small></p>)}{!analytics.subject_performance?.length && <p className="selection-note">No finalized subject results yet.</p>}</article></section>
          <section className="cbt-panel"><p className="panel-kicker">QUESTION REVIEW</p><h2>High failure or unanswered rates</h2>{analytics.question_analysis?.map((item) => <p className="cbt-question-analysis" key={item.question_id}><span>{item.prompt}</span><b>{item.failure_rate == null ? '—' : `${item.failure_rate}% failed`}</b><small>{item.unanswered_rate}% unanswered · {item.attempts + item.unanswered} responses{item.small_sample ? ' · small sample' : ''}</small></p>)}{!analytics.question_analysis?.length && <p className="selection-note">Question-level analysis will appear after submissions synchronize.</p>}</section>
          <section className="cbt-panel cbt-results-table-panel"><p className="panel-kicker">EXAMINATION RESULTS</p><h2>Student attempts</h2><div className="cbt-results-table-scroll"><table className="cbt-results-table"><thead><tr><th>Student</th><th>Class</th><th>Subject</th><th>Examination</th><th>Attempted</th><th>Correct</th><th>Score</th><th>Status</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><button className="cbt-result-link" onClick={() => navigate(`/app/cbt/results/${row.id}`)}>{row.student_name}<small>{row.admission_number}</small></button></td><td>{row.class_name}</td><td>{row.subject_name}</td><td>{row.examination_title}<small>{formatDate(row.submitted_at)}</small></td><td>{row.attempted_questions}/{row.total_questions}</td><td>{row.correct_answers}</td><td>{row.score == null ? `Marking · ${row.objective_score}/${row.maximum_score}` : `${row.score}/${row.maximum_score} (${row.percentage}%)`}</td><td>{row.status === 'needs_marking' ? 'Needs marking' : row.passed ? 'Passed' : 'Failed'}</td></tr>)}</tbody></table>{rows.length === 0 && <p className="selection-note">No synchronized results match these filters yet.</p>}</div><div className="cbt-actions"><button className="secondary-button" disabled={!dashboard.previous} onClick={() => changePage((new URL(dashboard.previous).searchParams.get('page') || 1))}>Previous</button><span>Showing {rows.length} of {dashboard.count || 0}</span><button className="secondary-button" disabled={!dashboard.next} onClick={() => changePage(Number(new URL(dashboard.next).searchParams.get('page') || 1))}>Next</button></div></section>
        </>}
      </>}
    </section>
  </main>
}
