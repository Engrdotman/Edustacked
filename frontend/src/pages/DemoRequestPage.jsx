import { useState } from 'react'
import { requestSchoolDemo } from '../services/api.js'

export default function DemoRequestPage({ navigate }) {
  const [values, setValues] = useState({ administrator_name: '', school_name: '', email: '', phone_number: '', message: '' })
  const [message, setMessage] = useState('')
  const [error, setError] = useState(false)
  const [working, setWorking] = useState(false)
  async function submit(event) {
    event.preventDefault(); setWorking(true); setError(false); setMessage('')
    try { const result = await requestSchoolDemo(values); setMessage(result.detail) }
    catch (e) { setMessage(e.message || 'Your request could not be sent.'); setError(true) }
    finally { setWorking(false) }
  }
  function update(event) { setValues({ ...values, [event.target.name]: event.target.value }) }
  return <main className="auth-page"><section className="auth-card signup-card"><p className="eyebrow">EDUstacked · PERSONAL WALKTHROUGH</p><h1>Request a demo.</h1><p className="auth-intro">Tell us a little about your school and our team will arrange a walkthrough.</p><form className="auth-form" onSubmit={submit}>
    <label htmlFor="demo-admin">Your name</label><input id="demo-admin" name="administrator_name" required maxLength="150" value={values.administrator_name} onChange={update} />
    <label htmlFor="demo-school">School name</label><input id="demo-school" name="school_name" required maxLength="200" value={values.school_name} onChange={update} />
    <label htmlFor="demo-email">Email</label><input id="demo-email" type="email" name="email" required value={values.email} onChange={update} />
    <label htmlFor="demo-phone">Phone</label><input id="demo-phone" type="tel" name="phone_number" required value={values.phone_number} onChange={update} />
    <label htmlFor="demo-message">What would you like to see? <span>(optional)</span></label><textarea id="demo-message" name="message" rows="3" maxLength="2000" value={values.message} onChange={update} />
    {message && <p className={error ? 'form-error' : 'form-success'} role={error ? 'alert' : 'status'}>{message}</p>}
    <button className="primary-button" disabled={working}>{working ? 'Sending…' : 'Request a demo'}</button>
  </form><button className="text-button back-link" onClick={() => navigate('/')}>Back to home</button></section></main>
}
