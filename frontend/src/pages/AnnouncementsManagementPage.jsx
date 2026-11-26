import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'
import BrandMark from '../components/BrandMark.jsx'

const emptyForm = { title: '', message: '', expires_at: '', send_sms: false }

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
    setForm({ title: row.title, message: row.message, expires_at: row.expires_at ? new Date(row.expires_at).toISOString().slice(0, 16) : '', send_sms: Boolean(row.send_sms) })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function submit(event) {
    event.preventDefault(); setWorking(true); setError(''); setSuccess('')
    const body = { ...form, expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null }
    try {
      await apiRequest(editing ? `parent/staff/announcements/${editing}/` : 'parent/staff/announcements/', { method: editing ? 'PATCH' : 'POST', body: { ...body, send_sms: Boolean(form.send_sms) } })
      setForm(emptyForm); setEditing(null); setSuccess(editing ? 'Announcement updated.' : 'Draft announcement created.')
      await load()
    } catch (requestError) { setError(requestError.message) }
    finally { setWorking(false) }
  }

  async function action(row, kind) {
    setWorking(true); setError(''); setSuccess('')
    try {
      await apiRequest(`parent/staff/announcements/${row.id}/${kind}/`, { method: 'POST', body: {} })
      setSuccess(kind === 'publish' ? (row.send_sms ? 'Announcement published. SMS submission status is shown with the announcement below.' : 'Announcement published to the school’s linked families.') : 'Announcement archived.')
      await load()
    } catch (requestError) { setError(requestError.message) }
    finally { setWorking(false) }
  }

  return <main className="app-page"><header className="app-topbar"><BrandMark navigate={navigate} /><button className="text-button" onClick={() => navigate('/app')}>Back to dashboard</button></header>
    <section className="app-content announcement-admin-page"><p className="eyebrow">{selectedSchool?.school_name} · FAMILY COMMUNICATION</p><h1 className="app-heading">Parent <em>announcements.</em></h1><p className="intro">Publishing sends the notice to parent portal accounts linked to this school. If SMS is selected, it also texts the unique phone numbers of active students’ guardians whose student links allow school communications. This is a school-wide audience; choose recipients by updating guardian links under Students.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}
      <form className="parent-panel announcement-form" onSubmit={submit}><h2>{editing ? 'Edit announcement' : 'New announcement draft'}</h2><label>Title<input required maxLength="180" placeholder="e.g. Mid-term break dates" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label>Message<textarea required maxLength={form.send_sms ? 5000 : 10000} rows="6" placeholder="Write the update families need to know." value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} /></label><label>Optional expiry date<input type="datetime-local" value={form.expires_at} onChange={(event) => setForm({ ...form, expires_at: event.target.value })} /></label><label className="announcement-sms-toggle"><input type="checkbox" checked={form.send_sms} disabled={Boolean(editing && rows.find((row) => row.id === editing)?.status === 'published')} onChange={(event) => setForm({ ...form, send_sms: event.target.checked })} /><span><strong>Also send this announcement by SMS</strong><small>Uses this school’s SMS wallet or monthly allowance. You’ll see the number submitted and any delivery issue below.</small></span></label><div className="report-card-actions"><button className="primary-button" disabled={working}>{editing ? 'Save changes' : 'Create draft'}</button>{editing && <button type="button" className="text-button" onClick={() => { setEditing(null); setForm(emptyForm) }}>Cancel edit</button>}</div></form>
      <section className="parent-panel"><h2>School announcements</h2>{rows.length ? <div className="announcement-admin-list">{rows.map((row) => <article key={row.id}><div><span className={`announcement-status ${row.status}`}>{row.status}</span><h3>{row.title}</h3><p>{row.message}</p>{row.published_at && <small>Published {new Date(row.published_at).toLocaleString()}</small>}{row.send_sms && <p className={`announcement-sms-result ${row.sms_status}`}><strong>SMS: {row.sms_status.replace('_', ' ')}</strong>{row.sms_recipient_count > 0 && ` · ${row.sms_submitted_count} of ${row.sms_recipient_count} numbers submitted`}{row.sms_error && <span>{row.sms_error}</span>}</p>}</div><div className="announcement-admin-actions"><button className="text-button" type="button" onClick={() => edit(row)}>Edit</button>{row.status === 'draft' && <button className="secondary-button" type="button" disabled={working} onClick={() => action(row, 'publish')}>Publish</button>}{row.status === 'published' && <button className="text-button" type="button" disabled={working} onClick={() => action(row, 'archive')}>Archive</button>}</div></article>)}</div> : <p>No announcements have been created yet.</p>}</section>
    </section>
  </main>
}
