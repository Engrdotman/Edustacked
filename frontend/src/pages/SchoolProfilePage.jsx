import { useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  ApiError,
  getSchoolLogo,
  getSchoolProfile,
  getSchoolSettings,
  updateSchoolProfile,
  updateSchoolSettings,
  uploadSchoolLogo,
} from '../services/api.js'

const emptyProfile = {
  name: '', contact_email: '', contact_phone: '', address: '', state: '',
  local_government_area: '', website: '', motto: '', description: '',
}
const emptySettings = {
  default_currency: 'NGN', time_zone: 'Africa/Lagos', date_format: 'DD/MM/YYYY',
  academic_year_label: 'Academic year', contact_preferences: { email: true, phone: true },
  branding_primary_color: '#285744',
}

function errorMessage(error) {
  return error instanceof ApiError ? error.message : 'The request could not be completed.'
}

function FieldError({ errors, name }) {
  const message = errors?.[name]
  return message ? <small className="field-error">{Array.isArray(message) ? message.join(' ') : message}</small> : null
}

export default function SchoolProfilePage({ navigate }) {
  const { selectedSchool, user } = useAuth()
  const canEdit = ['school_owner', 'school_admin', 'platform_superadmin'].includes(selectedSchool?.role)
  const [profile, setProfile] = useState(emptyProfile)
  const [settings, setSettings] = useState(emptySettings)
  const [savedProfile, setSavedProfile] = useState(emptyProfile)
  const [savedSettings, setSavedSettings] = useState(emptySettings)
  const [logoUrl, setLogoUrl] = useState('')
  const [savedLogoUrl, setSavedLogoUrl] = useState('')
  const [logoFile, setLogoFile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})

  useEffect(() => {
    let active = true
    let objectUrl = ''
    async function load() {
      setLoading(true)
      setError('')
      try {
        const [profileData, settingsData] = await Promise.all([getSchoolProfile(), getSchoolSettings()])
        if (!active) return
        const nextProfile = Object.fromEntries(Object.keys(emptyProfile).map((key) => [key, profileData[key] || '']))
        const nextSettings = { ...emptySettings, ...settingsData }
        setProfile(nextProfile)
        setSavedProfile(nextProfile)
        setSettings(nextSettings)
        setSavedSettings(nextSettings)
        if (profileData.logo_present) {
          const blob = await getSchoolLogo()
          if (!active) return
          objectUrl = URL.createObjectURL(blob)
          setLogoUrl(objectUrl)
          setSavedLogoUrl(objectUrl)
        } else {
          setLogoUrl('')
          setSavedLogoUrl('')
        }
      } catch (loadError) {
        if (active) setError(errorMessage(loadError))
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [selectedSchool?.school_id])

  useEffect(() => () => {
    if (logoUrl.startsWith('blob:')) URL.revokeObjectURL(logoUrl)
  }, [logoUrl])

  useEffect(() => {
    const onBeforeUnload = (event) => {
      const dirty = JSON.stringify(profile) !== JSON.stringify(savedProfile)
        || JSON.stringify(settings) !== JSON.stringify(savedSettings) || Boolean(logoFile)
      if (dirty) {
        event.preventDefault()
        event.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [profile, savedProfile, settings, savedSettings, logoFile])

  function cancelProfile() {
    setProfile(savedProfile)
    setLogoFile(null)
    if (logoUrl.startsWith('blob:') && logoUrl !== savedLogoUrl) URL.revokeObjectURL(logoUrl)
    setLogoUrl(savedLogoUrl)
    setFieldErrors({})
    setSuccess('')
  }

  function cancelSettings() {
    setSettings(savedSettings)
    setFieldErrors({})
    setSuccess('')
  }

  async function saveProfile(event) {
    event.preventDefault()
    setSavingProfile(true)
    setError('')
    setSuccess('')
    setFieldErrors({})
    try {
      await updateSchoolProfile(profile)
      if (logoFile) await uploadSchoolLogo(logoFile)
      setSavedProfile(profile)
      setLogoFile(null)
      setSuccess('School profile saved.')
      if (logoUrl.startsWith('blob:')) URL.revokeObjectURL(logoUrl)
      if (logoFile) {
        const blob = await getSchoolLogo()
        const nextLogoUrl = URL.createObjectURL(blob)
        setLogoUrl(nextLogoUrl)
        setSavedLogoUrl(nextLogoUrl)
      }
    } catch (saveError) {
      setError(errorMessage(saveError))
      setFieldErrors(saveError.fields || {})
    } finally {
      setSavingProfile(false)
    }
  }

  async function saveSettings(event) {
    event.preventDefault()
    setSavingSettings(true)
    setError('')
    setSuccess('')
    setFieldErrors({})
    try {
      const next = await updateSchoolSettings(settings)
      setSettings({ ...emptySettings, ...next })
      setSavedSettings({ ...emptySettings, ...next })
      setSuccess('School settings saved.')
    } catch (saveError) {
      setError(errorMessage(saveError))
      setFieldErrors(saveError.fields || {})
    } finally {
      setSavingSettings(false)
    }
  }

  function changeLogo(file) {
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
      setError('Choose a JPG, PNG, or WebP image no larger than 2 MB.')
      return
    }
    setError('')
    setLogoFile(file)
    if (logoUrl.startsWith('blob:')) URL.revokeObjectURL(logoUrl)
    setLogoUrl(URL.createObjectURL(file))
  }

  function back() {
    const dirty = JSON.stringify(profile) !== JSON.stringify(savedProfile)
      || JSON.stringify(settings) !== JSON.stringify(savedSettings) || Boolean(logoFile)
    if (!dirty || window.confirm('Discard unsaved school changes?')) navigate('/app')
  }

  return (
    <main className="app-page profile-page">
      <header className="app-topbar">
        <BrandMark />
        <button className="text-button" type="button" onClick={back}>Back to workspace</button>
      </header>
      <section className="app-content profile-content">
        <p className="eyebrow">SCHOOL WORKSPACE</p>
        <h1 className="app-heading">School profile<br /><em>& settings.</em></h1>
        <p className="intro">Manage the information and display preferences for {selectedSchool?.school_name || 'your selected school'}.</p>
        <div className="session-details profile-overview">
          <div><span>SCHOOL</span><strong>{profile.name || selectedSchool?.school_name || '—'}</strong></div>
          <div><span>SCHOOL CODE</span><strong>{profile.slug || selectedSchool?.school_slug || '—'}</strong></div>
          <div><span>ACCOUNT</span><strong>{user?.email}</strong></div>
        </div>
        {loading ? <p className="loading-message" role="status">Loading school profile…</p> : (
          <>
            {error && <p className="form-error" role="alert">{error}</p>}
            {success && <p className="form-success" role="status">{success}</p>}
            <form className="settings-card" onSubmit={saveProfile}>
              <div className="settings-card-heading"><div><p className="panel-kicker">SCHOOL INFORMATION</p><h2>Profile</h2></div>
                <span className="permission-note">{canEdit ? 'Administrator editing' : 'Read only'}</span></div>
              <div className="logo-field">
                <div className="school-logo-preview">{logoUrl ? <img src={logoUrl} alt="School logo preview" /> : <span aria-label="No logo uploaded">{profile.name?.slice(0, 1) || 'S'}</span>}</div>
                <div><strong>School logo</strong><p>JPG, PNG, or WebP · up to 2 MB</p>
                  {canEdit && <label className="upload-button">Choose image<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => changeLogo(event.target.files?.[0])} /></label>}
                </div>
              </div>
              <div className="form-grid">
                <label>School name<input value={profile.name} disabled={!canEdit} required maxLength={200} onChange={(event) => setProfile({ ...profile, name: event.target.value })} /><FieldError errors={fieldErrors} name="name" /></label>
                <label>School email<input type="email" value={profile.contact_email} disabled={!canEdit} onChange={(event) => setProfile({ ...profile, contact_email: event.target.value })} /><FieldError errors={fieldErrors} name="contact_email" /></label>
                <label>Phone number<input value={profile.contact_phone} disabled={!canEdit} maxLength={30} onChange={(event) => setProfile({ ...profile, contact_phone: event.target.value })} /><FieldError errors={fieldErrors} name="contact_phone" /></label>
                <label>Website<input type="url" value={profile.website} disabled={!canEdit} placeholder="https://example.edu.ng" onChange={(event) => setProfile({ ...profile, website: event.target.value })} /><FieldError errors={fieldErrors} name="website" /></label>
                <label>State<input value={profile.state} disabled={!canEdit} maxLength={100} onChange={(event) => setProfile({ ...profile, state: event.target.value })} /><FieldError errors={fieldErrors} name="state" /></label>
                <label>Local government area<input value={profile.local_government_area} disabled={!canEdit} maxLength={120} onChange={(event) => setProfile({ ...profile, local_government_area: event.target.value })} /><FieldError errors={fieldErrors} name="local_government_area" /></label>
                <label className="field-wide">Address<textarea rows="2" value={profile.address} disabled={!canEdit} onChange={(event) => setProfile({ ...profile, address: event.target.value })} /><FieldError errors={fieldErrors} name="address" /></label>
                <label>Motto<input value={profile.motto} disabled={!canEdit} maxLength={200} onChange={(event) => setProfile({ ...profile, motto: event.target.value })} /><FieldError errors={fieldErrors} name="motto" /></label>
                <label className="field-wide">Description<textarea rows="3" value={profile.description} disabled={!canEdit} onChange={(event) => setProfile({ ...profile, description: event.target.value })} /><FieldError errors={fieldErrors} name="description" /></label>
              </div>
              {canEdit && <div className="form-actions"><button className="primary-button" disabled={savingProfile}>{savingProfile ? 'Saving…' : 'Save profile'}</button><button className="secondary-button" type="button" onClick={cancelProfile}>Cancel</button></div>}
            </form>

            <form className="settings-card" onSubmit={saveSettings}>
              <div className="settings-card-heading"><div><p className="panel-kicker">LOCAL PREFERENCES</p><h2>School settings</h2></div></div>
              <div className="form-grid">
                <label>Default currency<input value={settings.default_currency} disabled={!canEdit} maxLength={3} onChange={(event) => setSettings({ ...settings, default_currency: event.target.value.toUpperCase() })} /><FieldError errors={fieldErrors} name="default_currency" /></label>
                <label>Time zone<select value={settings.time_zone} disabled={!canEdit} onChange={(event) => setSettings({ ...settings, time_zone: event.target.value })}><option value="Africa/Lagos">Africa/Lagos</option><option value="UTC">UTC</option><option value="Africa/Accra">Africa/Accra</option></select><FieldError errors={fieldErrors} name="time_zone" /></label>
                <label>Date display<select value={settings.date_format} disabled={!canEdit} onChange={(event) => setSettings({ ...settings, date_format: event.target.value })}><option>DD/MM/YYYY</option><option>MM/DD/YYYY</option><option>YYYY-MM-DD</option></select><FieldError errors={fieldErrors} name="date_format" /></label>
                <label>Academic year label<input value={settings.academic_year_label} disabled={!canEdit} maxLength={80} onChange={(event) => setSettings({ ...settings, academic_year_label: event.target.value })} /><FieldError errors={fieldErrors} name="academic_year_label" /></label>
                <label>Brand color<input type="color" value={settings.branding_primary_color} disabled={!canEdit} onChange={(event) => setSettings({ ...settings, branding_primary_color: event.target.value.toUpperCase() })} /><FieldError errors={fieldErrors} name="branding_primary_color" /></label>
                <fieldset className="contact-preferences"><legend>Preferred school contact methods</legend>
                  {['email', 'phone'].map((method) => <label key={method}><input type="checkbox" checked={Boolean(settings.contact_preferences?.[method])} disabled={!canEdit} onChange={(event) => setSettings({ ...settings, contact_preferences: { ...settings.contact_preferences, [method]: event.target.checked } })} /> {method === 'email' ? 'Email' : 'Phone'}</label>)}
                </fieldset>
              </div>
              {canEdit && <div className="form-actions"><button className="primary-button" disabled={savingSettings}>{savingSettings ? 'Saving…' : 'Save settings'}</button><button className="secondary-button" type="button" onClick={cancelSettings}>Cancel</button></div>}
            </form>
          </>
        )}
      </section>
    </main>
  )
}
