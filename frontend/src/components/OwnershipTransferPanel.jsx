import { useEffect, useState } from 'react'
import { apiRequest } from '../services/api.js'

export default function OwnershipTransferPanel({ schoolId }) {
  const [memberships, setMemberships] = useState([])
  const [target, setTarget] = useState('')
  const [password, setPassword] = useState('')
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { apiRequest(`schools/${schoolId}/memberships/`).then((response) => setMemberships(response.results || response || [])).catch((e) => setError(e.message)) }, [schoolId])
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const response = await apiRequest(`schools/${schoolId}/ownership/transfer/`, { method: 'POST', body: { target_membership_id: Number(target), password, reason } })
      setMessage(`${response.detail} Sign out and sign back in to use your updated role.`); setPassword(''); setReason(''); setTarget('')
    } catch (e) { setError(e.message || 'Ownership could not be transferred.') }
    finally { setBusy(false) }
  }
  const candidates = memberships.filter((row) => row.role !== 'school_owner' && row.user_email_verified)
  return <section className="membership-invite ownership-transfer"><div><p className="panel-kicker">ACCOUNT SECURITY</p><h2>Transfer school ownership</h2><p className="auth-intro">This action requires your current password and is recorded in the platform audit history.</p></div><form className="ownership-transfer-form" onSubmit={submit}><label>New owner<select required value={target} onChange={(e) => setTarget(e.target.value)}><option value="">Choose a verified member</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.first_name} {item.last_name} · {item.email} · {item.role.replaceAll('_', ' ')}</option>)}</select></label><label>Your password<input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label><label>Reason<input required maxLength="1000" value={reason} onChange={(e) => setReason(e.target.value)} /></label><button className="secondary-button" disabled={busy || !target}>{busy ? 'Transferring…' : 'Transfer ownership'}</button></form>{error && <p className="form-error" role="alert">{error}</p>}{message && <p className="form-success" role="status">{message}</p>}</section>
}
