import { useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { ApiError, signupSchool } from '../services/api.js'

export default function SignupPage({ navigate }) {
  const [values, setValues] = useState({ school_name: '', administrator_name: '', email: '', phone_number: '', password: '', password_confirmation: '', school_email: '', school_phone: '', school_type: 'both', country: 'Nigeria', state: '', local_government_area: '', address: '' })
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  function update(event) { setValues({ ...values, [event.target.name]: event.target.value }) }

  async function submit(event) {
    event.preventDefault(); setError(''); setWorking(true)
    try {
      await signupSchool(values)
      navigate('/login?registered=1&email=' + encodeURIComponent(values.email))
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : 'School registration could not be completed. Try again.')
    } finally { setWorking(false) }
  }

  return <main className="auth-page"><header className="auth-topbar"><BrandMark /><button className="text-button" type="button" onClick={() => navigate('/login')}>Sign in</button></header>
    <section className="auth-card signup-card" aria-labelledby="signup-title">
      <p className="eyebrow">EDUstacked · SCHOOL ONBOARDING</p><h1 id="signup-title">Set up your school.</h1>
      <p className="auth-intro">Create your school workspace. We’ll email you a verification link before you can sign in.</p>
      <form className="auth-form" onSubmit={submit}>
        <label htmlFor="school_name">School name</label><input id="school_name" name="school_name" autoComplete="organization" required maxLength="200" value={values.school_name} onChange={update} />
        <label htmlFor="administrator_name">Administrator name</label><input id="administrator_name" name="administrator_name" autoComplete="name" required maxLength="150" value={values.administrator_name} onChange={update} />
        <label htmlFor="signup_email">Work email</label><input id="signup_email" name="email" type="email" autoComplete="email" required value={values.email} onChange={update} />
        <label htmlFor="signup_phone">Administrator phone</label><input id="signup_phone" name="phone_number" type="tel" autoComplete="tel" placeholder="+234 801 234 5678" required value={values.phone_number} onChange={update} />
        <div className="signup-section-title">School details</div>
        <label htmlFor="school_email">School email <span>(optional)</span></label><input id="school_email" name="school_email" type="email" autoComplete="organization" value={values.school_email} onChange={update} />
        <label htmlFor="school_phone">School phone</label><input id="school_phone" name="school_phone" type="tel" required value={values.school_phone} onChange={update} />
        <label htmlFor="school_type">School type</label><select id="school_type" name="school_type" required value={values.school_type} onChange={update}><option value="primary">Primary</option><option value="secondary">Secondary</option><option value="both">Primary and secondary</option></select>
        <label htmlFor="country">Country</label><input id="country" name="country" required value={values.country} onChange={update} />
        <label htmlFor="state">State</label><input id="state" name="state" autoComplete="address-level1" required value={values.state} onChange={update} />
        <label htmlFor="local_government_area">Local Government Area</label><input id="local_government_area" name="local_government_area" required value={values.local_government_area} onChange={update} />
        <label htmlFor="address">School address</label><textarea id="address" name="address" autoComplete="street-address" rows="3" required value={values.address} onChange={update} />
        <div className="signup-section-title">Secure your account</div>
        <label htmlFor="signup_password">Password</label><input id="signup_password" name="password" type="password" autoComplete="new-password" minLength="8" required value={values.password} onChange={update} />
        <label htmlFor="signup_password_confirmation">Confirm password</label><input id="signup_password_confirmation" name="password_confirmation" type="password" autoComplete="new-password" minLength="8" required value={values.password_confirmation} onChange={update} />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button" type="submit" disabled={working || values.password !== values.password_confirmation}>{working ? 'Creating workspace…' : 'Register your school'}</button>
      </form>
      <button className="text-button back-link" type="button" onClick={() => navigate('/')}>Back to home</button>
    </section>
  </main>
}
