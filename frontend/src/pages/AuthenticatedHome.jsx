import { useState } from 'react'
import { ApiError } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'

const roleLabels = {
  platform_superadmin: 'Platform superadmin',
  school_admin: 'School admin',
  school_manager: 'School manager',
  teacher: 'Teacher',
  accountant: 'Accountant',
  receptionist: 'Receptionist',
  member: 'No assigned permissions',
}

export default function AuthenticatedHome({ navigate }) {
  const { user, schools, selectedSchool, selectSchool, signOut } = useAuth()
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
          {selectedSchool && <p className="selection-note" role="status">Selected: {selectedSchool.school_name}. School access is verified by the API on every request.</p>}
        </section>

        <div className="session-details">
          <div><span>ACCOUNT</span><strong>{user?.email}</strong></div>
          <div><span>ROLE</span><strong>{roleLabels[currentRole] || currentRole || 'No school role'}</strong></div>
        </div>
        <p className="module-note">Authentication and school access are ready. School workflows will be added in later modules.</p>
      </section>
    </main>
  )
}
