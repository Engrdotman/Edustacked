import { useEffect, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { requestSchoolDemo } from '../services/api.js'
import { companyContent, faqs, getStartedSteps, productFeatures, productScreens } from '../companyContent.js'

function PreviewWindow({ kind = 'dashboard', compact = false }) {
  const title = {
    dashboard: 'School dashboard', teacher: 'Teacher workspace', students: 'Students', attendance: 'Attendance',
    results: 'Assessment results', reports: 'Report cards', signup: 'Register your school', onboarding: 'School setup',
    home: 'EDUstacked homepage', verify: 'Verify your email', status: 'Verification status',
  }[kind] || 'School workspace'
  const rows = kind === 'students' ? [['Amina Bello', 'JSS 2A', 'Active'], ['Chidi Okafor', 'Primary 5', 'Active'], ['Zainab Musa', 'SS 1B', 'Active']] :
    kind === 'attendance' ? [['JSS 1A', 'Present', '32 / 35'], ['Primary 5B', 'Present', '28 / 30'], ['SS 2A', 'Review', '26 / 29']] :
      kind === 'results' || kind === 'reports' ? [['Mathematics', 'Submitted', 'Review'], ['English Language', 'Approved', 'Ready'], ['Basic Science', 'Draft', 'Continue']] :
        [['Academic setup', 'Complete', '›'], ['Classes and subjects', 'In progress', '›'], ['Invite staff', 'Ready', '›']]
  return <div className={`product-preview product-preview-${kind}${compact ? ' product-preview-compact' : ''}`} aria-label={`Illustrative interface preview: ${title}`}>
    <div className="preview-window-bar"><span /><span /><span /><b>{title}</b><i>Admin</i></div>
    <div className="preview-app">
      <aside className="preview-sidebar"><div className="preview-brand"><span className="preview-brand-mark">ES</span><b>EDUstacked</b></div>{['Dashboard', 'Students', 'Staff', 'Classes', 'Attendance', 'Results', 'Report Cards', 'Settings'].map((item, index) => <span key={item} className={(kind === 'students' && index === 1) || (kind === 'attendance' && index === 4) || ((kind === 'results' || kind === 'reports') && index === 5) || (kind === 'dashboard' && index === 0) ? 'active' : ''}>{item}</span>)}</aside>
      {kind === 'signup' ? <div className="preview-form-main"><small>CREATE YOUR SCHOOL WORKSPACE</small><h3>Register your school</h3><div className="preview-form-grid">{['School name', 'Administrator name', 'Email address', 'Phone number', 'School type', 'State'].map((label) => <span key={label}>{label}<i /></span>)}</div><b>Register your school →</b></div> :
        kind === 'verify' ? <div className="preview-state-main"><span className="preview-state-icon" aria-hidden="true" /><small>ACCOUNT VERIFICATION</small><h3>Check your email</h3><p>Use the secure link to verify your email and continue to your school workspace.</p><b>Verification link sent</b></div> :
          kind === 'onboarding' ? <div className="preview-state-main preview-onboarding-main"><small>SCHOOL SETUP</small><h3>Let’s get your school ready.</h3>{['School profile', 'Academic setup', 'Classes and subjects', 'Invite staff'].map((item, index) => <p key={item}><i>{index === 0 ? '✓' : index + 1}</i>{item}<b>{index === 0 ? 'Complete' : 'Continue'}</b></p>)}</div> :
            kind === 'status' ? <div className="preview-state-main"><span className="preview-pending">PENDING VERIFICATION</span><h3>Your school is awaiting review.</h3><p>You can continue setting up your school while verification is pending.</p><b>Email verified · School review pending</b></div> :
              <div className="preview-main"><div className="preview-heading"><div><small>WELCOME TO YOUR SCHOOL</small><h3>{kind === 'teacher' ? 'Good morning, Teacher.' : 'Good morning, Administrator.'}</h3><p>Here’s an overview of your school workspace.</p></div><button>Current session⌄</button></div>
        <div className="preview-metrics"><div><small>Total students</small><strong>248</strong><em>↑ This term</em></div><div><small>Teaching staff</small><strong>28</strong><em>School team</em></div><div><small>Classes</small><strong>12</strong><em>Across levels</em></div></div>
        <div className="preview-panels"><div className="preview-chart"><strong>{kind === 'teacher' ? 'My classes' : 'Academic overview'}</strong><div className="preview-bars">{[66, 88, 58, 76, 92, 69, 84, 61, 77, 93, 68, 82].map((height, i) => <i key={i} style={{ height: `${height}%` }} />)}</div><div className="preview-chart-labels"><span>JSS 1</span><span>JSS 2</span><span>SS 1</span><span>SS 2</span></div></div><div className="preview-activity"><strong>{kind === 'signup' ? 'School details' : 'Recent activity'}</strong>{rows.map((row) => <div key={row[0]}><b>{row[0]}</b><span>{row[1]}</span><small>{row[2]}</small></div>)}</div></div>
      </div>}
    </div>
    <span className="preview-disclaimer">Illustrative interface preview · Sample data only</span>
  </div>
}

function DemoForm() {
  const [values, setValues] = useState({ administrator_name: '', school_name: '', email: '', phone_number: '', message: '' })
  const [notice, setNotice] = useState('')
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)
  function update(event) { setValues((current) => ({ ...current, [event.target.name]: event.target.value })) }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setNotice(''); setError(false)
    try { const response = await requestSchoolDemo(values); setNotice(response.detail); setValues({ administrator_name: '', school_name: '', email: '', phone_number: '', message: '' }) }
    catch (requestError) { setNotice(requestError.message || 'We could not send your request. Please try again.'); setError(true) }
    finally { setBusy(false) }
  }
  return <form className="company-contact-form" onSubmit={submit}>
    <label>Your name<input name="administrator_name" autoComplete="name" required maxLength="150" value={values.administrator_name} onChange={update} /></label>
    <label>School name<input name="school_name" autoComplete="organization" required maxLength="200" value={values.school_name} onChange={update} /></label>
    <label>Email<input name="email" type="email" autoComplete="email" required value={values.email} onChange={update} /></label>
    <label>Phone<input name="phone_number" type="tel" autoComplete="tel" required value={values.phone_number} onChange={update} /></label>
    <label className="contact-message">What would you like to see?<textarea name="message" rows="4" maxLength="2000" value={values.message} onChange={update} /></label>
    {notice && <p className={error ? 'form-error' : 'form-success'} role={error ? 'alert' : 'status'}>{notice}</p>}
    <button className="company-button company-button-primary" disabled={busy}>{busy ? 'Sending request…' : 'Request a demo'}</button>
  </form>
}

export default function WelcomePage({ onLogin, onSignup, onDemo }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [activeScreen, setActiveScreen] = useState(productScreens[0])
  const [openFaq, setOpenFaq] = useState(0)
  const navItems = [['About Us', '#about'], ['Our Inspiration', '#inspiration'], ['Features', '#features'], ['How It Works', '#how-it-works'], ['Contact', '#contact']]
  function goTo(id) { setMenuOpen(false); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }

  useEffect(() => {
    const sections = document.querySelectorAll('.company-section, .company-trust-strip, .company-hero-copy, .company-hero-visual')
    if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        }
      })
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' })
    sections.forEach((section) => { section.classList.add('scroll-reveal'); observer.observe(section) })
    return () => observer.disconnect()
  }, [])

  return <main className="company-site" id="home">
    <header className="company-header"><a className="company-home-brand" href="#home" aria-label="EDUstacked home"><BrandMark /></a>
      <button className="company-menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="company-navigation" onClick={() => setMenuOpen((value) => !value)}><span>{menuOpen ? 'Close' : 'Menu'}</span><b className={menuOpen ? 'menu-icon is-open' : 'menu-icon'} aria-hidden="true"><i /><i /><i /></b></button>
      <nav id="company-navigation" className={menuOpen ? 'company-nav is-open' : 'company-nav'} aria-label="Main navigation">
        <a href="#home" onClick={() => setMenuOpen(false)}>Home</a>{navItems.map(([label, href]) => <a href={href} key={href} onClick={() => setMenuOpen(false)}>{label}</a>)}
        <button className="company-login" type="button" onClick={onLogin}>Login</button><button className="company-button company-button-primary company-nav-cta" type="button" onClick={onSignup}>Register Your School</button>
      </nav>
    </header>

    <section className="company-hero" aria-labelledby="company-hero-title"><div className="company-hero-copy"><p className="company-kicker"><span /> SCHOOL MANAGEMENT, MADE CLEARER</p><h1 id="company-hero-title">More time for the work that <em>moves schools forward.</em></h1><p className="company-hero-description">EDUstacked is a school management workspace for owners, principals, administrators, and teachers across Nigeria. Bring everyday school records and academic workflows into one organized place.</p>
      <div className="company-hero-actions"><button className="company-button company-button-primary" onClick={onSignup}>Register Your School <span aria-hidden="true">↗</span></button><a className="company-button company-button-secondary" href="#explore">Explore the Platform <span aria-hidden="true">↓</span></a></div>
      <button className="company-demo-link" onClick={() => goTo('contact')}>Prefer a walkthrough? <span>Request a demo →</span></button>
      <div className="company-hero-proof"><span>For Nigerian primary and secondary schools</span><span>School-level access controls</span><span>Set up at your own pace</span></div>
    </div><div className="company-hero-visual"><div className="hero-orbit hero-orbit-one"/><div className="hero-orbit hero-orbit-two"/><PreviewWindow /></div></section>

    <div className="company-trust-strip"><span>One school workspace</span><i/><span>Role-based access</span><i/><span>Guided setup</span><i/><span>Built step by step</span></div>

    <section id="about" className="company-section company-about"><div className="company-section-intro"><p className="company-kicker">ABOUT {companyContent.name.toUpperCase()}</p><h2>Tools that make the school day easier to organize.</h2></div><div className="company-about-copy"><p>{companyContent.background}</p><p>{companyContent.whatWeDo}</p><p><strong>Who we serve:</strong> {companyContent.serves}</p></div>
      <div className="company-purpose-grid"><article><span>OUR MISSION</span><h3>{companyContent.mission}</h3></article><article><span>OUR VISION</span><h3>{companyContent.vision}</h3></article><article><span>OUR VALUES</span><div className="company-values">{companyContent.values.map((value) => <b key={value}>{value}</b>)}</div></article></div>
    </section>

    <section id="inspiration" className="company-section company-inspiration"><div className="inspiration-mark" aria-hidden="true">“</div><div><p className="company-kicker">THE STORY BEHIND THE WORK</p><h2>Why We Built This Platform</h2><p className="inspiration-lead">Running a school means balancing many important details. Too often, those details live in paperwork, spreadsheets, and processes that do not speak to one another.</p><p>Student records, staff information, attendance, academic results, and report cards all need careful attention. When information is difficult to find, school leaders have less visibility, and teachers spend more time organizing than supporting learning.</p><p>EDUstacked is being built to bring these school workflows together in a clear, approachable workspace. School owners and principals can make decisions with organized information; teachers can focus on the academic work assigned to them; and administrators can keep everyday operations moving without unnecessary complexity.</p><p className="inspiration-note">We are building this platform incrementally and sharing its capabilities as they become available.</p></div></section>

    <section id="features" className="company-section company-features"><div className="company-section-heading"><div><p className="company-kicker">A CLEARER WAY TO WORK</p><h2>School operations, connected.</h2><p>Explore features currently implemented in the EDUstacked workspace.</p></div><button className="company-text-cta" onClick={onSignup}>Set up a school workspace ↗</button></div><div className="company-feature-grid">{productFeatures.map((feature) => <article className="company-feature-card" key={feature.title}><span className="feature-number">{feature.icon}</span><h3>{feature.title}</h3><p>{feature.text}</p><span className="feature-availability">Available in the school workspace</span></article>)}</div></section>

    <section id="explore" className="company-section company-explore"><div className="company-section-heading"><div><p className="company-kicker">TAKE A CLOSER LOOK</p><h2>Explore the Platform</h2><p>Choose a workspace to see an illustrative preview. These interface illustrations use sample data; they are not screenshots from a live school account.</p></div><span className="preview-legend">Illustrative interface previews</span></div>
      <div className="product-tour"><div className="product-tour-tabs" role="tablist" aria-label="Product interface previews">{productScreens.map((screen) => <button key={screen.key} type="button" role="tab" aria-selected={screen.key === activeScreen.key} onClick={() => setActiveScreen(screen)}>{screen.title}</button>)}</div><div className="product-tour-detail" role="tabpanel"><div className="product-tour-caption"><span>PRODUCT PREVIEW</span><h3>{activeScreen.title}</h3><p>{activeScreen.description}</p></div><PreviewWindow key={activeScreen.key} kind={activeScreen.kind} compact /></div></div>
    </section>

    <section id="how-it-works" className="company-section company-steps"><div className="company-section-heading"><div><p className="company-kicker">SCHOOL ONBOARDING</p><h2>How to Get Started</h2><p>Register independently, verify your account, and build your workspace as you go.</p></div><button className="company-button company-button-primary" onClick={onSignup}>Register Your School</button></div><div className="company-step-grid">{getStartedSteps.map((step, index) => <article className="company-step-card" key={step.title}><div className="step-card-top"><span>{String(index + 1).padStart(2, '0')}</span><i aria-hidden="true">{index < getStartedSteps.length - 1 ? '↘' : '✓'}</i></div><PreviewWindow kind={step.kind} compact /><h3>{step.title}</h3><p>{step.text}</p><div className="step-tip"><b>Helpful tip</b><span>{step.tip}</span></div></article>)}</div><div className="company-verification-note"><span className="security-symbol">✓</span><div><strong>Email verification and school verification are different.</strong><p>Verifying the administrator’s email confirms access to that email account. Platform review separately determines the school’s verification status. Basic school setup can continue while that review is pending.</p></div></div></section>

    <section className="company-section company-security"><div className="security-copy"><p className="company-kicker">ACCESS WITH CARE</p><h2>School information stays in the right school context.</h2><p>EDUstacked applies access checks in the backend so school records are served through an authenticated school membership. School roles determine which actions a user can perform, and sensitive academic workflows have controlled access.</p><p>These are implemented access-control measures. We do not make claims here about certifications, encryption coverage, backups, or regulatory compliance.</p></div><div className="security-cards"><article><span>01</span><h3>School-level data separation</h3><p>Protected school records are scoped to the user's authorized school.</p></article><article><span>02</span><h3>Role-based permissions</h3><p>Owners, administrators, principals, teachers, and other staff receive different access.</p></article><article><span>03</span><h3>Controlled academic actions</h3><p>Assessment review and publication follow authorized workflows.</p></article></div></section>

    <section className="company-section company-faq"><div className="company-section-heading"><div><p className="company-kicker">GOOD TO KNOW</p><h2>Frequently Asked Questions</h2></div></div><div className="faq-list">{faqs.map(([question, answer], index) => <article className={openFaq === index ? 'faq-item open' : 'faq-item'} key={question}><h3><button type="button" aria-expanded={openFaq === index} onClick={() => setOpenFaq((current) => current === index ? -1 : index)}>{question}<span>{openFaq === index ? '−' : '+'}</span></button></h3>{openFaq === index && <p>{answer}</p>}</article>)}</div></section>

    <section id="contact" className="company-section company-contact"><div className="contact-copy"><p className="company-kicker">LET’S TALK ABOUT YOUR SCHOOL</p><h2>See how your school could get started.</h2><p>Tell us what you would like to explore. We’ll use the details you provide to follow up about a product walkthrough.</p><div className="contact-details"><div><span>COMPANY EMAIL</span><strong>{companyContent.email}</strong></div><div><span>SUPPORT PHONE</span><strong>{companyContent.phone}</strong></div><div><span>OFFICE</span><strong>{companyContent.address}</strong></div><div><span>SOCIAL CHANNELS</span><strong>{Object.entries(companyContent.socials).map(([platform, profile]) => `${platform}: ${profile}`).join(' · ')}</strong></div></div><p className="contact-placeholder-note">Official company contact details and social profiles will be added here when confirmed.</p></div><div className="contact-form-wrap"><h3>Request a demo</h3><p>Share a few details and tell us what you want to see.</p><DemoForm /></div></section>

    <footer className="company-footer"><div className="footer-main"><div className="footer-brand-column"><a href="#home" aria-label="EDUstacked home"><BrandMark /></a><p>{companyContent.description}</p></div><div className="footer-link-column"><strong>EXPLORE</strong><a href="#about">About Us</a><a href="#inspiration">Our Inspiration</a><a href="#features">Features</a><a href="#how-it-works">How It Works</a></div><div className="footer-link-column"><strong>GET STARTED</strong><button onClick={onSignup}>Register Your School</button><button onClick={onLogin}>Login</button><button onClick={() => goTo('contact')}>Request a Demo</button></div><div className="footer-link-column"><strong>INFORMATION</strong><a href="/privacy">Privacy Policy <small>Draft</small></a><a href="/terms">Terms of Service <small>Draft</small></a><a href="#contact">Contact</a></div></div><div className="footer-legal"><span>© {new Date().getFullYear()} {companyContent.legalName}. All rights reserved.</span><span>Company registration details will be added when confirmed.</span></div></footer>
  </main>
}
