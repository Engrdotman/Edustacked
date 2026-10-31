import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiBlobRequest, apiRequest, ApiError } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'

const sectionLabels = {
  enrollment: 'Enrollment', attendance: 'Attendance', academics: 'Academic performance',
  report_cards: 'Report cards', finance: 'Credits & payments',
}
const sectionPaths = {
  enrollment: 'reports/enrollment/', attendance: 'reports/attendance/', academics: 'reports/academics/',
  report_cards: 'reports/report-cards/', finance: 'reports/finance/',
}

function formatPercent(value) {
  return value === null || value === undefined ? 'No recorded data' : `${Number(value).toFixed(2)}%`
}

function formatMoney(value) {
  if (value === null || value === undefined) return 'Not configured'
  return new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 2 }).format(value)
}

function queryString(filters, extra = {}) {
  const params = new URLSearchParams()
  Object.entries({ ...filters, ...extra }).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) params.set(key, value)
  })
  return params.toString()
}

function StatCard({ label, value, note }) {
  return <article className="reports-stat"><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</article>
}

function Table({ columns, rows, empty = 'No records match these filters.' }) {
  if (!rows?.length) return <p className="reports-empty">{empty}</p>
  return <div className="reports-table-wrap"><table><thead><tr>{columns.map((column) => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id || row.plan_id || `${index}-${row.date || row.class_name || ''}`}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : (row[column.key] ?? '—')}</td>)}</tr>)}</tbody></table></div>
}

export default function ReportsPage({ navigate }) {
  const { selectedSchool, signOut } = useAuth()
  const [dashboard, setDashboard] = useState(null)
  const [filters, setFilters] = useState({ session: '', term: '', class_level: '', arm: '', start_date: '', end_date: '' })
  const [activeTab, setActiveTab] = useState('overview')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [reportLoading, setReportLoading] = useState(false)
  const [error, setError] = useState('')
  const [showStudentRows, setShowStudentRows] = useState(false)
  const [search, setSearch] = useState('')

  const available = dashboard?.available_sections || []
  const sections = useMemo(() => ['overview', ...available], [available.join(',')])
  const terms = dashboard?.filters?.terms || []
  const arms = (dashboard?.filters?.arms || []).filter((arm) => !filters.class_level || String(arm.class_level_id) === String(filters.class_level))
  const financeOnly = activeTab === 'finance'

  const loadDashboard = useCallback(async (query = {}) => {
    const suffix = queryString(query)
    return apiRequest(`reports/dashboard/${suffix ? `?${suffix}` : ''}`)
  }, [])

  useEffect(() => {
    let active = true
    setLoading(true)
    loadDashboard().then((data) => {
      if (!active) return
      setDashboard(data)
      setFilters({
        session: data.session?.id || '', term: data.term?.id || '', class_level: '', arm: '',
        start_date: data.date_range?.start || '', end_date: data.date_range?.end || '',
      })
    }).catch((requestError) => {
      if (active) setError(requestError instanceof ApiError ? requestError.message : 'Reports could not be loaded.')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [loadDashboard])

  async function applyFilters(event) {
    event?.preventDefault()
    setError('')
    setLoading(true)
    try {
      const next = await loadDashboard(filters)
      setDashboard(next)
      if (activeTab !== 'overview') await loadReport(activeTab, filters)
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : 'The report could not be refreshed.')
    } finally { setLoading(false) }
  }

  async function loadReport(section, activeFilters = filters, options = {}) {
    if (!sectionPaths[section]) return
    setReportLoading(true)
    setError('')
    try {
      const path = sectionPaths[section]
      const suffix = queryString(activeFilters, options)
      const data = await apiRequest(`${path}?${suffix}`)
      setReport(data)
    } catch (requestError) {
      setReport(null)
      setError(requestError instanceof ApiError ? requestError.message : 'The requested report could not be loaded.')
    } finally { setReportLoading(false) }
  }

  async function selectTab(section) {
    setActiveTab(section)
    setReport(null)
    setShowStudentRows(false)
    setSearch('')
    if (section !== 'overview') await loadReport(section)
  }

  async function exportReport(section, extra = {}) {
    setError('')
    try {
      const suffix = queryString(filters, { ...extra, export: 'csv' })
      const blob = await apiBlobRequest(`${sectionPaths[section]}?${suffix}`)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${section}-${filters.start_date || 'all'}-${filters.end_date || 'all'}.csv`
      document.body.append(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : 'The CSV export could not be created.')
    }
  }

  const metrics = dashboard?.metrics || {}
  const attendance = metrics.attendance
  const resultStats = metrics.results
  const cardStats = metrics.report_cards

  async function handleSignOut() {
    await signOut()
    navigate('/')
  }

  return (
    <main className="app-page reports-page">
      <header className="app-topbar"><BrandMark /><div className="reports-header-actions"><span>{selectedSchool?.school_name}</span><button className="text-button" type="button" onClick={handleSignOut}>Sign out</button></div></header>
      <section className="reports-content">
        <p className="eyebrow"><span className="status-dot status-dot-online" /> SCHOOL REPORTS</p>
        <h1 className="reports-heading">Decisions with<br /><em>clear numbers.</em></h1>
        <p className="reports-intro">Summaries use this school’s enrollment, finalized attendance, approved results, published reports, and verified credit ledger.</p>
        <form className="reports-filter-panel" onSubmit={applyFilters}>
          {!financeOnly && <>
            <label>Academic session<select value={filters.session} onChange={(event) => setFilters((old) => ({ ...old, session: event.target.value, term: '' }))}><option value="">All sessions</option>{dashboard?.filters?.sessions?.map((item) => <option key={item.id} value={item.id}>{item.name}{item.status === 'active' ? ' · Active' : ''}</option>)}</select></label>
            <label>Term<select value={filters.term} onChange={(event) => setFilters((old) => ({ ...old, term: event.target.value }))}><option value="">All terms</option>{terms.filter((term) => !filters.session || String(term.academic_session_id) === String(filters.session)).map((term) => <option key={term.id} value={term.id}>{term.name}</option>)}</select></label>
            <label>Class<select value={filters.class_level} onChange={(event) => setFilters((old) => ({ ...old, class_level: event.target.value, arm: '' }))}><option value="">All classes</option>{dashboard?.filters?.classes?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label>Arm<select value={filters.arm} onChange={(event) => setFilters((old) => ({ ...old, arm: event.target.value }))}><option value="">All arms</option>{arms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          </>}
          <label>From<input type="date" value={filters.start_date} onChange={(event) => setFilters((old) => ({ ...old, start_date: event.target.value }))} /></label>
          <label>To<input type="date" value={filters.end_date} onChange={(event) => setFilters((old) => ({ ...old, end_date: event.target.value }))} /></label>
          <button className="primary-button" type="submit" disabled={loading}>Apply filters</button>
        </form>
        <nav className="reports-tabs" aria-label="Report sections">
          {sections.map((section) => <button type="button" key={section} className={activeTab === section ? 'active' : ''} onClick={() => selectTab(section)}>{section === 'overview' ? 'Overview' : sectionLabels[section]}</button>)}
        </nav>
        {error && <p className="form-error" role="alert">{error}</p>}
        {loading && !dashboard ? <p className="loading-message" role="status">Loading school reports…</p> : (
          <>
            {activeTab === 'overview' && <section className="reports-panel" aria-labelledby="overview-title">
              <div className="reports-panel-heading"><div><p className="panel-kicker">{dashboard?.session?.name || 'No active session'}</p><h2 id="overview-title">School overview</h2></div><span className="reports-date-range">{dashboard?.date_range?.start} – {dashboard?.date_range?.end}</span></div>
              <div className="reports-stat-grid">
                {metrics.currently_enrolled !== undefined && <StatCard label="Currently enrolled" value={metrics.currently_enrolled} note="Active student enrollments in the selected session" />}
                {metrics.new_admissions !== undefined && <StatCard label="New admissions" value={metrics.new_admissions} note="Admission dates within the selected period" />}
                {attendance && <StatCard label="Recorded attendance" value={attendance.has_records ? `${attendance.total} marks` : 'No records'} note={attendance.has_records ? `Attendance rate ${formatPercent(attendance.attendance_percentage)}` : 'No finalized attendance records in this range'} />}
                {resultStats && <StatCard label="Approved results" value={resultStats.approved} note={`${resultStats.submitted} submitted · ${resultStats.draft} draft`} />}
                {resultStats && <StatCard label="Average approved result" value={formatPercent(resultStats.average_approved_percentage)} note="Mean approved assessment percentage" />}
                {cardStats && <StatCard label="Published report cards" value={cardStats.published} note={`${cardStats.review} awaiting review · ${cardStats.approved} approved`} />}
                {metrics.credit_balance !== undefined && <StatCard label="Available credits" value={metrics.credit_balance === null ? 'Not set up' : metrics.credit_balance} note="Current school balance from the Module 10 account" />}
              </div>
              {attendance && <p className="reports-policy">Attendance rate is (present + late) ÷ explicitly marked records in finalized registers. Excused and absent records remain in the denominator; missing registers and unmarked students do not.</p>}
            </section>}
            {activeTab !== 'overview' && <section className="reports-panel">
              <div className="reports-panel-heading"><div><p className="panel-kicker">{sectionLabels[activeTab]}</p><h2>{sectionLabels[activeTab]} report</h2></div><div className="reports-actions">{activeTab !== 'finance' && <button className="secondary-button" type="button" onClick={() => exportReport(activeTab, activeTab === 'enrollment' ? { view: 'students', search } : activeTab === 'attendance' ? { view: 'students', search } : {})}>Export CSV</button>}{activeTab === 'finance' && <button className="secondary-button" type="button" onClick={() => exportReport(activeTab)}>Export payment CSV</button>}</div></div>
              {reportLoading && <p className="loading-message" role="status">Loading report…</p>}
              {!reportLoading && activeTab === 'enrollment' && report && <>
                <div className="reports-stat-grid"><StatCard label="Admissions in period" value={report.admissions} /><StatCard label="Withdrawals" value={report.outcomes.withdrawn} /><StatCard label="Transfers" value={report.outcomes.transferred} /></div>
                <h3>Enrollment by historical class placement</h3><p className="reports-policy">Each row counts a non-pending enrollment record in the selected session. Transfers preserve separate historical class placements.</p>
                <Table columns={[{ key: 'class_level__name', label: 'Class' }, { key: 'class_arm__name', label: 'Arm' }, { key: 'status', label: 'Status' }, { key: 'count', label: 'Students' }]} rows={report.distribution} />
                <div className="reports-roster-tools"><h3>Student list</h3><input aria-label="Search students" placeholder="Search name or admission number" value={search} onChange={(event) => setSearch(event.target.value)} /><button className="secondary-button" type="button" onClick={() => { setShowStudentRows(true); loadReport('enrollment', filters, { view: 'students', search }) }}>Search roster</button></div>
                {showStudentRows && report.students && <><Table columns={[{ key: 'admission_number', label: 'Admission no.' }, { key: 'name', label: 'Student' }, { key: 'class_name', label: 'Class' }, { key: 'arm_name', label: 'Arm' }, { key: 'status', label: 'Enrollment' }]} rows={report.students.results} />{(report.students.previous || report.students.next) && <div className="reports-pagination"><button type="button" disabled={!report.students.previous} onClick={() => loadReport('enrollment', filters, { view: 'students', search, page: Math.max(1, Number(report.students.previous?.match(/[?&]page=(\d+)/)?.[1] || 2) - 1) })}>Previous</button><span>{report.students.count} records</span><button type="button" disabled={!report.students.next} onClick={() => loadReport('enrollment', filters, { view: 'students', search, page: Number(report.students.next?.match(/[?&]page=(\d+)/)?.[1] || 2) })}>Next</button></div>}</>}
              </>}
              {!reportLoading && activeTab === 'attendance' && report?.summary && <>
                <div className="reports-stat-grid"><StatCard label="Marked records" value={report.summary.total} note={report.summary.has_records ? 'Finalized registers only' : 'No finalized attendance records'} /><StatCard label="Attendance rate" value={formatPercent(report.summary.attendance_percentage)} note="Present and late ÷ marked records" /><StatCard label="Present / late" value={`${report.summary.present} / ${report.summary.late}`} /><StatCard label="Absent / excused" value={`${report.summary.absent} / ${report.summary.excused}`} /></div>
                <p className="reports-policy">{report.summary.policy}</p>
                <h3>By date, class, and arm</h3><Table columns={[{ key: 'register__attendance_date', label: 'Date' }, { key: 'register__class_level__name', label: 'Class' }, { key: 'register__class_arm__name', label: 'Arm' }, { key: 'present', label: 'Present' }, { key: 'absent', label: 'Absent' }, { key: 'late', label: 'Late' }, { key: 'excused', label: 'Excused' }]} rows={report.rows} />
                <div className="reports-roster-tools"><h3>By student</h3><input aria-label="Search attendance students" placeholder="Search name or admission number" value={search} onChange={(event) => setSearch(event.target.value)} /><button className="secondary-button" type="button" onClick={() => { setShowStudentRows(true); loadReport('attendance', filters, { view: 'students', search }) }}>View students</button></div>
              </>}
              {!reportLoading && activeTab === 'attendance' && report?.results && <><p className="reports-policy">{report.policy}</p><Table columns={[{ key: 'student__admission_number', label: 'Admission no.' }, { key: 'student__first_name', label: 'First name' }, { key: 'register__class_level__name', label: 'Class' }, { key: 'register__class_arm__name', label: 'Arm' }, { key: 'total', label: 'Marked records' }, { key: 'present', label: 'Present' }, { key: 'absent', label: 'Absent' }, { key: 'late', label: 'Late' }, { key: 'excused', label: 'Excused' }]} rows={report.results} /><div className="reports-pagination"><button type="button" disabled={!report.previous} onClick={() => loadReport('attendance', filters, { view: 'students', search, page: Math.max(1, Number(report.previous?.match(/[?&]page=(\d+)/)?.[1] || 2) - 1) })}>Previous</button><span>{report.count} students</span><button type="button" disabled={!report.next} onClick={() => loadReport('attendance', filters, { view: 'students', search, page: Number(report.next?.match(/[?&]page=(\d+)/)?.[1] || 2) })}>Next</button></div></>}
              {!reportLoading && activeTab === 'academics' && report && <><p className="reports-policy">Averages and grade distributions include approved results only. Draft and submitted values appear as workflow counts and are not included in official performance figures.</p><Table columns={[{ key: 'class_name', label: 'Class' }, { key: 'arm_name', label: 'Arm' }, { key: 'subject', label: 'Subject' }, { key: 'plan_status', label: 'Plan' }, { key: 'approved', label: 'Approved' }, { key: 'submitted', label: 'Submitted' }, { key: 'draft', label: 'Draft' }, { key: 'average_approved_percentage', label: 'Average', render: (row) => formatPercent(row.average_approved_percentage) }, { key: 'grade_distribution', label: 'Approved grades', render: (row) => row.grade_distribution.map((grade) => `${grade.approved_grade || 'Unspecified'}: ${grade.count}`).join(' · ') || 'No approved grades' }]} rows={report.plans} /></>}
              {!reportLoading && activeTab === 'report_cards' && report && <><div className="reports-stat-grid">{Object.entries(report.statuses).map(([key, value]) => <StatCard key={key} label={key === 'published' ? 'Published' : key.replaceAll('_', ' ')} value={value} />)}</div><p className="reports-policy">Expected students are non-pending enrollment records in the selected session and class placement. Completion is published report cards ÷ expected students. Zero expected students has no percentage.</p><Table columns={[{ key: 'class_name', label: 'Class' }, { key: 'arm_name', label: 'Arm' }, { key: 'expected_students', label: 'Expected' }, { key: 'draft', label: 'Draft' }, { key: 'review', label: 'Review' }, { key: 'approved', label: 'Approved' }, { key: 'published', label: 'Published' }, { key: 'publication_percentage', label: 'Completion', render: (row) => formatPercent(row.publication_percentage) }]} rows={report.classes} /></>}
              {!reportLoading && activeTab === 'finance' && report && <><div className="reports-stat-grid"><StatCard label="Current credits" value={report.credit_balance ?? 'No account'} /><StatCard label="Successful purchases" value={report.successful_purchases} /><StatCard label="Gross verified purchases" value={formatMoney(report.gross_successful_purchases_ngn)} note="Successful payment records only; pending and failed payments excluded" /><StatCard label="Open reconciliation issues" value={report.reconciliation_issues.open} /></div><h3>Payments by status</h3><Table columns={[{ key: 'status', label: 'Payment status' }, { key: 'currency', label: 'Currency' }, { key: 'count', label: 'Payments' }, { key: 'amount_minor', label: 'Total amount (minor units)' }, { key: 'credits', label: 'Credits' }]} rows={report.payments_by_status} /><h3>Credit ledger movement</h3><Table columns={[{ key: 'kind', label: 'Transaction type' }, { key: 'count', label: 'Entries' }, { key: 'credit_change', label: 'Net credit change' }]} rows={report.ledger_by_kind} /><p className="reports-policy">Gross purchase totals use successful payment records in NGN. Reversals remain visible under their own payment status. Credit movements come from the append-only ledger; balances are not treated as revenue.</p></>}
              {!reportLoading && report && activeTab !== 'enrollment' && activeTab !== 'attendance' && activeTab !== 'academics' && activeTab !== 'report_cards' && activeTab !== 'finance' && <p className="reports-empty">No report is available for this section.</p>}
              {!reportLoading && !report && !error && <p className="reports-empty">Choose filters and load a report.</p>}
            </section>}
          </>
        )}
        <button className="reports-back" type="button" onClick={() => navigate('/app')}>Back to dashboard</button>
      </section>
    </main>
  )
}
