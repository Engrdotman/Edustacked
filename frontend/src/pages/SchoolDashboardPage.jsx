import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'
import { apiRequest } from '../services/api.js'

const actions = [
  ['Students', '/app/students', ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'receptionist']],
  ['Staff', '/app/staff', ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal']],
  ['Classes & subjects', '/app/academics', ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal']],
  ['Attendance', '/app/attendance', ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher']],
  ['Assessments & results', '/app/assessments', ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher']],
  ['Report cards', '/app/report-cards', ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher']],
  ['Reports & analytics', '/app/reports', ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'accountant', 'receptionist']],
  ['Billing & credits', '/app/billing', ['platform_superadmin', 'school_owner', 'school_admin', 'accountant']],
  ['School settings', '/app/school', ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'accountant', 'receptionist']],
]

export default function SchoolDashboardPage({ navigate }) {
  const { user, selectedSchool, signOut } = useAuth()
  const role = selectedSchool?.role
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    apiRequest('reports/dashboard/')
      .then((report) => { if (active) setData(report) })
      .catch((e) => { if (active) setError(e.message || 'Dashboard data could not be loaded.') })
    return () => { active = false }
  }, [])
  async function exit() { await signOut(); navigate('/') }
  const metrics = data?.metrics || {}
  const cards = [
    metrics.currently_enrolled != null && ['Currently enrolled', metrics.currently_enrolled, 'Active student records', '/app/students?status=active'],
    metrics.active_staff != null && ['Active staff', metrics.active_staff, 'Current staff records', '/app/staff?status=active'],
    metrics.report_cards && ['Report cards', metrics.report_cards.published, 'Published this session'],
    metrics.results && ['Average result', metrics.results.average_approved_percentage != null ? `${metrics.results.average_approved_percentage}%` : '—', 'Approved assessments'],
    metrics.credit_balance != null && ['Report-card credits', metrics.credit_balance, 'Available balance'],
  ].filter(Boolean)
  const permittedActions = actions.filter(([, , roles]) => roles.includes(role))
  const activity = [
    metrics.results?.submitted != null && [`${metrics.results.submitted} result submissions awaiting review`, '/app/assessments'],
    metrics.report_cards?.review != null && [`${metrics.report_cards.review} report cards in review`, '/app/report-cards'],
  ].filter(Boolean)
  return <main className="school-dashboard">
    <aside className="dashboard-sidebar"><BrandMark /><nav aria-label="School workspace">{[['Dashboard', '/app'], ...permittedActions].map(([label, path]) => <button key={path} className={path === '/app' ? 'dashboard-nav active' : 'dashboard-nav'} onClick={() => navigate(path)}>{label}</button>)}{user?.is_superuser && <button className="dashboard-nav" onClick={() => navigate('/platform/schools')}>Platform administration</button>}</nav><div className="dashboard-user"><strong>{user?.first_name || user?.email}</strong><span>{role?.replaceAll('_', ' ')}</span></div></aside>
    <section className="dashboard-main"><header className="dashboard-topbar"><strong>{selectedSchool?.school_name || 'School workspace'}</strong><div><span>{data?.session?.name || 'No active session'}</span><button className="text-button" onClick={exit}>Sign out</button></div></header>
      <div className="dashboard-content"><p className="panel-kicker">SCHOOL OVERVIEW</p><h1>Good morning, {user?.first_name || 'there'}.</h1><p className="dashboard-subtitle">Here’s a snapshot of your school’s current activity.</p>
        {selectedSchool?.school_verification_status && <div className={`school-status school-status-${selectedSchool.school_verification_status}`} role="status">{selectedSchool.school_verification_status === 'pending_verification' ? 'Your school is awaiting verification. You can continue setting it up while verification is pending.' : selectedSchool.school_verification_status === 'under_review' ? 'Your school is under review. You can continue using the workspace.' : selectedSchool.school_verification_status === 'rejected' ? `Your school registration needs attention. ${selectedSchool.school_verification_reason || 'Contact support for next steps.'}` : selectedSchool.school_verification_status === 'verified' ? 'Your school has been successfully verified.' : 'Your school account is currently suspended. Please contact support.'}</div>}
        {['school_owner', 'school_admin', 'school_manager', 'principal'].includes(role) && selectedSchool?.school_verification_status !== 'suspended' && <button className="dashboard-onboarding-link" onClick={() => navigate('/app/onboarding')}>Continue school setup →</button>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dashboard-kpis">{cards.map(([label, value, note, path]) => path ? <button type="button" className="dashboard-kpi dashboard-kpi-link" key={label} onClick={() => navigate(path)}><span>{label}</span><strong>{value}</strong><small>{note} · View records →</small></button> : <article className="dashboard-kpi" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div>
        <div className="dashboard-columns"><article className="dashboard-panel"><div className="dashboard-panel-heading"><h2>Academic overview</h2><button className="text-button" onClick={() => navigate('/app/reports')}>View reports</button></div>
          {metrics.class_performance?.length ? <div className="dashboard-performance">{metrics.class_performance.map((item) => <div key={item.class_name}><span>{item.class_name}</span><span className="dashboard-bar"><i style={{ width: `${Math.min(100, item.average_percentage)}%` }} /></span><strong>{item.average_percentage}%</strong></div>)}</div> : data?.filters?.classes?.length ? <div className="dashboard-class-list">{data.filters.classes.slice(0, 8).map((item) => <button key={item.id} onClick={() => navigate('/app/academics')}><span>{item.name}</span><span>Manage class →</span></button>)}</div> : <p className="dashboard-empty">Class overview will appear when there is academic structure available to your role.</p>}
        </article><article className="dashboard-panel"><h2>Needs attention</h2>{activity.length ? activity.map(([label, path]) => <button className="dashboard-activity" key={label} onClick={() => navigate(path)}>{label} <span>→</span></button>) : <p className="dashboard-empty">No pending review items are available for this account.</p>}<h2 className="dashboard-actions-title">Quick actions</h2><div className="dashboard-quick-actions">{permittedActions.slice(0, 4).map(([label, path]) => <button key={path} onClick={() => navigate(path)}>{label} →</button>)}</div></article></div>
        <p className="dashboard-footer">EDUstacked · {selectedSchool?.school_name}</p>
      </div>
    </section>
  </main>
}
