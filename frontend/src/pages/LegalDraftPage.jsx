import BrandMark from '../components/BrandMark.jsx'
import { companyContent } from '../companyContent.js'

const privacySections = [
  {
    heading: '1. Who this notice covers',
    paragraphs: [
      `This working notice covers EDUstacked’s public website, school workspaces, teacher tools, report cards, and parent portal. EDUstacked is currently presented as the product name; its full legal contracting entity and business address still need confirmation.`,
      `A school decides why it collects and uses its students’ and families’ records. EDUstacked provides the software to manage those records. EDUstacked may separately handle account, support, security, and billing information to operate its own service. The exact legal roles of EDUstacked and each school must be confirmed in the final documents.`,
    ],
  },
  {
    heading: '2. Information the service can hold',
    paragraphs: [
      'Depending on what a school enters and which features it uses, the workspace can contain:',
    ],
    bullets: [
      'Account and access details: names, email addresses, phone numbers, password hashes, school memberships, staff roles, invitations, and account verification or security status.',
      'School details: school name, contact details, location, school type, website, motto, logo, principal signature, and school verification records.',
      'Student and enrollment details: names, admission numbers, date of birth, gender, optional photo and contact details, address, class, arm, session, and enrollment history.',
      'Family and parent-portal details: guardian name, phone, email, address, relationship to a student, invitations, announcements, and portal notifications.',
      'School activity and academic records: attendance, assessment plans and component scores, grading, approved results, report-card remarks, psychomotor and behaviour ratings, and audit history of changes.',
      'Billing and service details: credit balances, package and payment references, payment status, and separately licensed service or CBT entitlement details. Card and bank payment credentials are handled by the selected payment provider, not stored as EDUstacked payment credentials.',
      'Demo and onboarding requests: the contact details and message a school submits when requesting a product walkthrough or one-time assisted onboarding.',
      'Basic technical and security information needed to run and protect the service, such as authentication and CSRF cookies, failed sign-in counters, and records of administrative actions.',
    ],
  },
  {
    heading: '3. Why information is used',
    paragraphs: [
      'EDUstacked uses information to create and protect accounts; connect staff to the right school and role; support admissions, enrollment, attendance, assessments, results, report cards, and parent communications; administer school verification and separately licensed services; process and reconcile credit purchases; respond to demo, onboarding, and support requests; and detect misuse or protect the service.',
      'EDUstacked does not use school academic records to target advertising. Access is intended to be limited by school membership and user role. The final policy will state the lawful bases that apply to each use after legal review.',
    ],
  },
  {
    heading: '4. Children’s information and school responsibilities',
    paragraphs: [
      'Student records may relate to children. A school must have authority to enter and use those records, give any notices, and obtain any permissions or guardian involvement required by applicable law. Schools should enter only information needed for school administration and should keep it accurate.',
      'A parent or guardian portal account is created through a school invitation and is limited to the linked student information the school authorizes. Parents should contact the school first to correct a student record managed by that school.',
    ],
  },
  {
    heading: '5. Service providers and sharing',
    paragraphs: [
      'Information may be processed by service providers that help host and deliver EDUstacked. The current deployment uses Netlify for the web interface and Railway for the backend and database. SendGrid may deliver verification, password setup, and staff invitation email. When a school starts a payment, the selected provider may be Flutterwave, Bachs, or Paystack and receives the information needed to complete and verify that transaction.',
      'Those providers handle information under their own terms and privacy notices. Their processing locations, international-transfer safeguards, and current contractual arrangements must be confirmed and listed before this draft is published as the final notice. EDUstacked does not sell student records.',
    ],
  },
  {
    heading: '6. Sign-in cookies and browser storage',
    paragraphs: [
      'The sign-in flow uses essential security cookies, including an HttpOnly refresh cookie and a CSRF cookie. They help keep accounts signed in and protect requests that change information. They are not advertising cookies. Blocking or clearing them can prevent sign-in or end a session. The service does not require a custom EDUstacked domain to work, though the hosting and cookie configuration must remain compatible.',
    ],
  },
  {
    heading: '7. Security and access',
    paragraphs: [
      'EDUstacked uses account authentication, role and school-membership checks, secure cookies in production, login rate limits and temporary lockouts, and audit records for certain school actions. These controls reduce risk but cannot guarantee that every system or transmission is completely secure. Schools are responsible for issuing appropriate access, protecting their users’ sign-in details, and removing access when a person leaves.',
    ],
  },
  {
    heading: '8. Retention, export, and deletion',
    paragraphs: [
      'EDUstacked has not yet published a complete retention schedule or a self-service school-data export and deletion workflow. Do not treat this draft as promising a particular deletion deadline. Schools and data subjects can write to the contact below to ask about access, correction, export, restriction, or deletion; identity and authority may need to be checked, and some records may need to be retained for security, audit, payment, or legal reasons.',
      'A fixed retention schedule, school-closure process, backup-deletion process, and documented request-handling time must be approved before this page becomes a final privacy notice.',
    ],
  },
  {
    heading: '9. Your privacy requests',
    paragraphs: [
      `For a privacy question or request, email ${companyContent.email} with “Privacy request” in the subject. A parent or guardian may also contact the school that manages the student record. EDUstacked may ask for enough information to verify the requester and protect another person’s records. Data-subject rights and response timelines are subject to applicable law. You may also contact the Nigeria Data Protection Commission where the law allows.`,
    ],
  },
  {
    heading: '10. Changes and contact',
    paragraphs: [
      `We will revise this notice as the service and its providers change. Material changes should be dated and made available to affected users. Company inquiries and privacy requests: ${companyContent.email}.`,
    ],
  },
]

const termsSections = [
  {
    heading: '1. Scope and acceptance',
    paragraphs: [
      'These working terms describe the intended rules for using the EDUstacked website and school workspace. They are a draft for review, not an approved customer contract. The full legal entity, business address, governing-law wording, liability terms, and dispute process must be confirmed before users are asked to accept final terms.',
    ],
  },
  {
    heading: '2. School accounts and staff access',
    paragraphs: [
      'The person registering a school must be authorized to represent it and becomes its initial school owner. A school owner or authorized administrator can invite staff, connect each login to the correct staff profile, assign a school role, and create teaching assignments for a session, class, arm, and subject. A teacher’s access depends on the linked school membership and assigned responsibilities. An invitation email alone does not create a teaching assignment.',
      'Users must provide accurate contact details, keep sign-in credentials private, use their own account, and tell the school administrator if an account may be compromised. Email verification confirms control of an email address; school verification is a separate EDUstacked review. A school may complete basic setup while verification is pending, subject to available access controls.',
    ],
  },
  {
    heading: '3. School data and acceptable use',
    paragraphs: [
      'The school is responsible for the records it enters, its authority to use them, and the permissions given to its staff and families. This includes student, guardian, attendance, assessment, report-card, behaviour, and psychomotor information. Users must follow applicable law and school policies, enter only appropriate information, and not access or disclose records outside their role.',
      'Users must not attempt to bypass access controls, interfere with the service, upload malicious content, impersonate another person, or use the platform for unlawful purposes. Schools must promptly remove access for staff who no longer need it.',
    ],
  },
  {
    heading: '4. Academic records and parent access',
    paragraphs: [
      'EDUstacked provides tools for school staff to configure grading scales, record component scores, submit and review results, record attendance, and prepare report cards. The school remains responsible for checking grading rules, dates, student enrollment, marks, comments, positions, psychomotor ratings, signatures, and final reports before approval or publication. The software does not replace the school’s academic judgment.',
      'A parent portal is made available through an invitation from the school and shows only records linked and released by the school. Schools are responsible for keeping guardian relationships and communication permissions accurate.',
    ],
  },
  {
    heading: '5. Credits, payments, and separately licensed services',
    paragraphs: [
      'The current core billing model is a one-time purchase of report-card credits, not a recurring school subscription. One credit is used the first time a student’s report card is finalized for a particular school, academic session, and term. Previewing, downloading, reprinting, or revising that already-published report card does not consume another credit under the current implementation. Credit balances and purchases are recorded by EDUstacked after the payment provider verifies a successful transaction.',
      'Schools may choose Flutterwave, Bachs, or Paystack where the checkout option is available. The selected provider processes the payment under its own terms. Prices, tax treatment, cancellations, refunds, and any future recurring subscription rules still need to be finalized and displayed before commercial terms are approved.',
      'Optional one-time assisted onboarding includes training school staff to use the workspace. The current fee is ₦15,000 for remote training or ₦30,000 for on-site training; the school covers on-site transport. This service is separate from report-card credits and does not create a recurring subscription. Booking dates, transport arrangements, payment instructions, and any applicable tax treatment should be confirmed before booking.',
      'Offline CBT is an optional, separately licensed service. It has its own entitlement and capacity. Self-service checkout and license activation are not currently available from the public website; access may be granted administratively while that flow is being completed. Report-card credits do not purchase an Offline CBT license.',
    ],
  },
  {
    heading: '6. Service availability and support',
    paragraphs: [
      'EDUstacked is under active development. Features, integrations, and availability may change, and no uptime commitment or service-level guarantee is currently stated here. Planned maintenance, provider outages, connectivity problems, or security events may temporarily affect access. Contact support at the email below if an issue affects school records or access.',
    ],
  },
  {
    heading: '7. Suspension and ending access',
    paragraphs: [
      'EDUstacked may restrict or suspend an account or school workspace where reasonably necessary to protect users, investigate suspected abuse, comply with law, or respond to a serious breach of these terms. Where practical, EDUstacked should explain the reason and a route to request review. The final agreement must specify notice, appeal, school departure, data export, retention, and deletion procedures before this section is relied on commercially.',
    ],
  },
  {
    heading: '8. Privacy and changes to these terms',
    paragraphs: [
      'Use of personal information is described in EDUstacked’s Privacy Policy. These terms and the privacy notice will be updated as the product and company arrangements are confirmed. The effective date and method for notifying customers of material changes must be set in the final agreement.',
      `Questions: ${companyContent.email}.`,
    ],
    privacyLink: true,
  },
]

function LegalSection({ section }) {
  return (
    <section key={section.heading}>
      <h2>{section.heading}</h2>
      {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      {section.bullets && <ul>{section.bullets.map((item) => <li key={item}>{item}</li>)}</ul>}
      {section.privacyLink && <p><a href="/privacy">Read the Privacy Policy</a></p>}
    </section>
  )
}

export default function LegalDraftPage({ type, navigate }) {
  const isPrivacy = type === 'privacy'
  const title = isPrivacy ? 'Privacy Policy' : 'Terms of Service'
  const sections = isPrivacy ? privacySections : termsSections

  return (
    <main className="legal-draft-page">
      <header className="legal-header">
        <a href="/" onClick={(event) => { event.preventDefault(); navigate('/') }} aria-label="EDUstacked home"><BrandMark navigate={navigate} /></a>
        <button className="text-button" onClick={() => navigate('/')}>Back to website</button>
      </header>
      <article className="legal-draft-content">
        <p className="company-kicker">{companyContent.name.toUpperCase()} · WORKING DRAFT</p>
        <h1>{title}</h1>
        <div className="legal-draft-alert" role="note">
          <strong>Working draft — not yet approved for commercial publication</strong>
          <p>This version reflects the product currently implemented. It still needs review by a Nigerian privacy and commercial lawyer and confirmation of EDUstacked’s legal entity, business address, data-retention schedule, provider locations and contracts, and final billing/refund rules.</p>
        </div>
        <p className="legal-draft-updated">Updated 17 November 2026 · Contact: <a href={`mailto:${companyContent.email}`}>{companyContent.email}</a></p>
        {sections.map((section) => <LegalSection key={section.heading} section={section} />)}
        {isPrivacy && <p className="legal-source-link">Reference: <a href="https://ndpc.gov.ng/wp-content/uploads/2024/03/Nigeria_Data_Protection_Act_2023.pdf" target="_blank" rel="noreferrer">Nigeria Data Protection Act, 2023</a> (Nigeria Data Protection Commission).</p>}
        <button className="company-button company-button-primary" onClick={() => navigate('/')}>Return to EDUstacked</button>
      </article>
      <footer className="legal-footer">© {new Date().getFullYear()} {companyContent.legalName}. Working draft; subject to legal and company review.</footer>
    </main>
  )
}
