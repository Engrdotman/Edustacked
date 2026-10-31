import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'

const emptyForm = { title: '', message: '', expires_at: '' }

export default function AnnouncementsManagementPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [editing, setEditing] = useState(null)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = useCallback(async () => setRows(await apiRequest('parent/staff/announcements/')), [])
  useEffect(() => { load().catch((requestError) => setError(requestError.message)) }, [load])

  function edit(row) {
    setEditing(row.id)
    setForm({ title: row.title, message: row.message, expires_at: row.expires_at ? new Date(row.expires_at).toISOString().slice(0, 16) : '' })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function submit(event) {
    event.preventDefault(); setWorking(true); setError(''); setSuccess('')
    const body = { ...form, expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null }
    try {
      await apiRequest(editing ? `parent/staff/announcements/${editing}/` : 'parent/staff/announcements/', { method: editing ? 'PATCH' : 'POST', body })
      setForm(emptyForm); setEditing(null); setSuccess(editing ? 'Announcement updated.' : 'Draft announcement created.')
      await load()
    } catch (requestError) { setError(requestError.message) }
    finally { setWorking(false) }
  }

  async function action(row, kind) {
    setWorking(true); setError(''); setSuccess('')
    try {
      await apiRequest(`parent/staff/announcements/${row.id}/${kind}/`, { method: 'POST', body: {} })
      setSuccess(kind === 'publish' ? 'Announcement published to linked families.' : 'Announcement archived.')
      await load()
    } catch (requestError) { setError(requestError.message) }
    finally { setWorking(false) }
  }

  return <main className="app-page"><header className="app-topbar"><BrandMark /><button className="text-button" onClick={() => navigate('/app')}>Back to dashboard</button></header>
    <section className="app-content announcement-admin-page"><p className="eyebrow">{selectedSchool?.school_name} · FAMILY COMMUNICATION</p><h1 className="app-heading">Parent <em>announcements.</em></h1><p className="intro">Create school updates that become visible to guardians only after publication.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}
      <form className="parent-panel announcement-form" onSubmit={submit}><h2>{editing ? 'Edit announcement' : 'New announcement draft'}</h2><label>Title<input required maxLength="180" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label>Message<textarea required maxLength="10000" rows="6" value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} /></label><label>Optional expiry date<input type="datetime-local" value={form.expires_at} onChange={(event) => setForm({ ...form, expires_at: event.target.value })} /></label><div className="report-card-actions"><button className="primary-button" disabled={working}>{editing ? 'Save changes' : 'Create draft'}</button>{editing && <button type="button" className="text-button" onClick={() => { setEditing(null); setForm(emptyForm) }}>Cancel edit</button>}</div></form>
      <section className="parent-panel"><h2>School announcements</h2>{rows.length ? <div className="announcement-admin-list">{rows.map((row) => <article key={row.id}><div><span className={`announcement-status ${row.status}`}>{row.status}</span><h3>{row.title}</h3><p>{row.message}</p>{row.published_at && <small>Published {new Date(row.published_at).toLocaleString()}</small>}</div><div className="announcement-admin-actions"><button className="text-button" type="button" onClick={() => edit(row)}>Edit</button>{row.status === 'draft' && <button className="secondary-button" type="button" disabled={working} onClick={() => action(row, 'publish')}>Publish</button>}{row.status === 'published' && <button className="text-button" type="button" disabled={working} onClick={() => action(row, 'archive')}>Archive</button>}</div></article>)}</div> : <p>No announcements have been created yet.</p>}</section>
    </section>
  </main>
}
