import BrandMark from '../components/BrandMark.jsx'
import { companyContent } from '../companyContent.js'

const privacySections = [
  ['1. Status of this draft', 'This draft describes the intended privacy approach for EDUstacked and is not final legal advice or a complete privacy notice. It must be reviewed and updated by qualified counsel before the service is commercially launched.'],
  ['2. Information handled', 'Depending on the features a school uses, the platform may handle account and contact details, school profile information, staff records, student records, guardians, attendance, academic results, and report-card information. Schools should only enter information they are authorized to manage.'],
  ['3. Account and school verification', 'Email verification confirms control of an email address. It does not establish that a school is legitimate. Platform school review is a separate process. Phone verification by SMS is not currently enabled.'],
  ['4. School access and separation', 'The application enforces school membership and role checks on protected API access. The final policy must describe all processors, hosting locations, retention periods, security controls, and school responsibilities after these have been formally established.'],
  ['5. Children’s educational information', 'Student records may include information about children. Schools should use the service only with an appropriate legal basis and required notices or permissions. Specific procedures for access, correction, retention, export, and deletion must be confirmed before commercial launch.'],
  ['6. Contact and requests', `The official privacy contact has not yet been supplied: ${companyContent.email}. Replace this placeholder and define a verified process for privacy requests before publication.`],
]

const termsSections = [
  ['1. Status of this draft', 'These draft terms are a product-planning document, not a binding agreement. They require review by qualified counsel before commercial launch.'],
  ['2. Accounts and school authority', 'A person registering a school represents that they are authorized to create and administer its workspace. The first registrant becomes the initial school owner. Account access should be protected and staff access assigned according to school responsibilities.'],
  ['3. School records', 'Schools remain responsible for the accuracy and lawful handling of the student, staff, attendance, and academic records they enter. Users should not access records outside their authorized school membership.'],
  ['4. Verification and access', 'Email verification is separate from school verification. A school may begin basic setup while its status is pending. Platform verification, rejection, suspension, and reactivation follow the platform’s review process.'],
  ['5. Service availability and features', 'Features may change as the platform is developed. Payment, credits, support commitments, service levels, data retention, and termination terms must be finalized before commercial use. The credit model described on the website is planned and is not presented as an active subscription service.'],
  ['6. Company details and contact', `The official contracting entity and contact details have not yet been provided. Current placeholders: ${companyContent.legalName}; ${companyContent.email}; ${companyContent.address}. Replace and validate these details before publication.`],
]

export default function LegalDraftPage({ type, navigate }) {
  const isPrivacy = type === 'privacy'
  const title = isPrivacy ? 'Privacy Policy' : 'Terms of Service'
  const sections = isPrivacy ? privacySections : termsSections
  return <main className="legal-draft-page"><header className="legal-header"><a href="/" onClick={(event) => { event.preventDefault(); navigate('/') }}><BrandMark /></a><button className="text-button" onClick={() => navigate('/')}>Back to website</button></header><article className="legal-draft-content"><p className="company-kicker">{companyContent.name.toUpperCase()} · DRAFT FOR REVIEW</p><h1>{title}</h1><div className="legal-draft-alert"><strong>Draft — not approved for commercial publication</strong><p>This page contains working product language. It needs legal review and verified company details before it can serve as a final policy or agreement.</p></div><p className="legal-draft-updated">Working draft · {companyContent.legalName}</p>{sections.map(([heading, content]) => <section key={heading}><h2>{heading}</h2><p>{content}</p></section>)}<button className="company-button company-button-primary" onClick={() => navigate('/')}>Return to EDUstacked</button></article><footer className="legal-footer">© {new Date().getFullYear()} {companyContent.legalName}. Draft content is subject to review.</footer></main>
}
