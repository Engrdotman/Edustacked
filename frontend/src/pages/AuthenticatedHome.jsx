import { useState } from 'react'
import { ApiError } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'

const roleLabels = {
  school_owner: 'School owner',
  principal: 'Principal',
  platform_superadmin: 'Platform superadmin',
  school_admin: 'School admin',
  school_manager: 'School manager',
  teacher: 'Teacher',
  accountant: 'Accountant',
  receptionist: 'Receptionist',
  member: 'No assigned permissions',
}

export default function AuthenticatedHome({ navigate }) {
  const { user, schools, selectedSchool, guardianProfile, selectSchool, signOut } = useAuth()
  const [schoolId, setSchoolId] = useState(selectedSchool?.school_id || '')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  async function handleSchoolChange(event) {
    const nextSchoolId = event.target.value
    setSchoolId(nextSchoolId)
    setError('')
    if (!nextSchoolId) return
    setWorking(true)
    try {
      await selectSchool(nextSchoolId)
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : 'School selection failed.')
      setSchoolId(selectedSchool?.school_id || '')
    } finally {
      setWorking(false)
    }
  }

  async function handleSignOut() {
    setWorking(true)
    await signOut()
    setWorking(false)
    navigate('/')
  }

  const currentRole = selectedSchool?.role || (schools.length === 1 ? schools[0].role : null)
  const canViewSchoolProfile = [
    'platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'accountant', 'receptionist',
  ].includes(currentRole)
  const canManageAcademics = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(currentRole)
  const canViewStudents = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'receptionist'].includes(currentRole)
  const canViewStaff = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'receptionist'].includes(currentRole)
  const canManageAttendance = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher'].includes(currentRole)
  const canViewResults = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher'].includes(currentRole)
  const canViewReportCards = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher'].includes(currentRole)
  const canViewBilling = ['platform_superadmin', 'school_owner', 'school_admin', 'accountant'].includes(currentRole)
  const canManageAnnouncements = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(currentRole)
  const canViewReports = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'accountant', 'receptionist'].includes(currentRole)

  return (
    <main className="app-page">
      <header className="app-topbar">
        <BrandMark />
        <button className="text-button" type="button" onClick={handleSignOut} disabled={working}>Sign out</button>
      </header>
      <section className="app-content">
        <p className="eyebrow"><span className="status-dot status-dot-online" /> AUTHENTICATED SESSION</p>
        <h1 className="app-heading">Good to have<br /><em>you here.</em></h1>
        <p className="intro">You’re signed in as <strong>{user?.first_name || user?.email}</strong>.</p>

        {user?.is_superuser && <button className="primary-button profile-link" type="button" onClick={() => navigate('/platform/schools')}>Platform administration</button>}
        {selectedSchool && ['school_owner', 'school_admin', 'school_manager', 'principal'].includes(currentRole) && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/onboarding')}>School onboarding</button>}

        <section className="access-panel" aria-labelledby="school-title">
          <div>
            <p className="panel-kicker">YOUR ACCESS</p>
            <h2 id="school-title">School membership</h2>
          </div>
          {schools.length > 1 ? (
            <label className="school-picker">
              <span>Select an authorized school</span>
              <select value={schoolId} onChange={handleSchoolChange} disabled={working}>
                <option value="">Choose a school…</option>
                {schools.map((school) => (
                  <option key={school.school_id} value={school.school_id}>{school.school_name} · {roleLabels[school.role] || school.role}</option>
                ))}
              </select>
            </label>
          ) : selectedSchool ? (
            <div className="selected-school">
              <strong>{selectedSchool.school_name}</strong>
              <span>{roleLabels[currentRole] || currentRole}</span>
            </div>
          ) : schools.length === 1 ? (
            <div className="selected-school">
              <strong>{schools[0].school_name}</strong>
              <span>{roleLabels[currentRole] || currentRole}</span>
            </div>
          ) : (
            <p className="auth-intro">No active school membership is assigned to this account.</p>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
          {!selectedSchool && schools.length === 1 && schools[0].school_verification_status === 'suspended' && <p className="form-error" role="alert">Your school account is currently suspended. Please contact support.</p>}
          {!selectedSchool && schools.length === 1 && schools[0].school_verification_status === 'rejected' && <p className="school-status school-status-rejected" role="status">Your school is awaiting further information. {schools[0].school_verification_reason}</p>}
          {selectedSchool && <p className="selection-note" role="status">Selected: {selectedSchool.school_name}. School access is verified by the API on every request.</p>}
          {!selectedSchool && guardianProfile && <p className="selection-note" role="status">Your parent portal access is active for the students linked to your account.</p>}
        </section>

        {selectedSchool && canViewSchoolProfile && <button className="primary-button profile-link" type="button" onClick={() => navigate('/app/school')}>
          School profile &amp; settings
        </button>}
        {selectedSchool && canManageAcademics && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/academics')}>
          Academic setup
        </button>}
        {selectedSchool && canViewStudents && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/students')}>
          Student management
        </button>}
        {selectedSchool && canViewStaff && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/staff')}>
          Staff &amp; teacher assignments
        </button>}
        {selectedSchool && canManageAttendance && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/attendance')}>
          Student attendance
        </button>}
        {selectedSchool && canViewResults && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/assessments')}>
          Assessments &amp; results
        </button>}
        {selectedSchool && canViewReportCards && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/report-cards')}>
          Report cards
        </button>}
        {selectedSchool && canViewBilling && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/billing')}>
          Report-card credits &amp; billing
        </button>}
        {selectedSchool && canManageAnnouncements && <button className="secondary-button profile-link" type="button" onClick={() => navigate('/app/announcements')}>
          Parent announcements
        </button>}
        {selectedSchool && canViewReports && <button className="primary-button profile-link" type="button" onClick={() => navigate('/app/reports')}>
          School reports &amp; analytics
        </button>}
        {guardianProfile && <button className="primary-button profile-link" type="button" onClick={() => navigate('/parent')}>
          Parent / guardian portal
        </button>}

        <div className="session-details">
          <div><span>ACCOUNT</span><strong>{user?.email}</strong></div>
          <div><span>ROLE</span><strong>{roleLabels[currentRole] || currentRole || 'No school role'}</strong></div>
        </div>
        <p className="module-note">EDUstacked school access, academic setup, and student admissions are ready for your role.</p>
      </section>
    </main>
  )
}
