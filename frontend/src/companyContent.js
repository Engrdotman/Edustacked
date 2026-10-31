// Replace these clearly marked placeholders when official company details are approved.
export const companyContent = {
  name: 'EDUstacked',
  legalName: '[Official company name to be confirmed]',
  description: 'A thoughtful digital workspace for the people who keep schools moving.',
  background: 'EDUstacked is being built around a practical belief: school administration should be easier to understand, easier to organize, and more useful in the decisions schools make every day.',
  whatWeDo: 'We are developing a school management platform that brings student records, staff, academic organization, attendance, results, and report cards into one school workspace.',
  serves: 'Primary and secondary schools in Nigeria, including school owners, principals, administrators, teachers, and authorized staff.',
  mission: 'Make dependable school management tools easier for Nigerian schools to use, one useful workflow at a time.',
  vision: 'A future where every school can make confident decisions with organized, accessible information.',
  values: ['Clarity', 'Practical progress', 'Responsible access', 'Respect for school communities'],
  email: '[Company email to be added]',
  phone: '[Support phone to be added]',
  address: '[Office address, if applicable]',
  socials: {
    LinkedIn: '[Official LinkedIn profile to be added]',
    Instagram: '[Official Instagram profile to be added]',
  },
}

export const productFeatures = [
  { icon: '01', title: 'Student records', text: 'Keep student profiles, admission details, guardians, and class enrollment organized in the school workspace.', href: '/app/students' },
  { icon: '02', title: 'Staff and teachers', text: 'Maintain staff profiles, teacher roles, and class or subject assignments with role-based access.', href: '/app/staff' },
  { icon: '03', title: 'Academic structure', text: 'Set up sessions, terms, classes, arms, subjects, and grading configuration for your school.', href: '/app/academics' },
  { icon: '04', title: 'Attendance', text: 'Record attendance by class and review school attendance activity.', href: '/app/attendance' },
  { icon: '05', title: 'Assessments and results', text: 'Plan assessments, record scores, and use a controlled review and approval workflow.', href: '/app/assessments' },
  { icon: '06', title: 'Report cards', text: 'Generate, review, and publish student report cards from approved academic records.', href: '/app/report-cards' },
  { icon: '07', title: 'School administration', text: 'Manage school profile, settings, and staff permissions from a school-scoped workspace.', href: '/app/school' },
  { icon: '08', title: 'Reports and insights', text: 'Review role-scoped enrollment, attendance, academic, and report-card summaries.', href: '/app/reports' },
]

export const productScreens = [
  { key: 'dashboard', title: 'School administrator dashboard', description: 'A school-level overview with practical links into everyday school workflows.', kind: 'dashboard' },
  { key: 'teacher', title: 'Teacher workspace', description: 'Teaching staff use their authorized school tools and assigned academic tasks.', kind: 'teacher' },
  { key: 'students', title: 'Student management', description: 'Student records and enrollment are managed within the active school.', kind: 'students' },
  { key: 'attendance', title: 'Attendance', description: 'School staff can record and review class attendance.', kind: 'attendance' },
  { key: 'results', title: 'Results management', description: 'Assessment scores follow a submission and approval workflow.', kind: 'results' },
  { key: 'reports', title: 'Report cards', description: 'Approved results can be assembled into term report cards for review.', kind: 'reports' },
  { key: 'signup', title: 'School registration', description: 'A school representative can start a workspace using the public signup form.', kind: 'signup' },
  { key: 'onboarding', title: 'School setup wizard', description: 'Owners can save their place and return to setup steps later.', kind: 'onboarding' },
]

export const getStartedSteps = [
  { title: 'Visit the website', text: 'Choose Register Your School from the navigation or the main call to action.', tip: 'You do not need to contact the company before starting registration.', kind: 'home' },
  { title: 'Enter your details', text: 'Provide an administrator name, email and phone, plus your school name, type, and location.', tip: 'Use an email address you can open to complete verification.', kind: 'signup' },
  { title: 'Verify your account', text: 'Open the one-time email link. Phone verification fields are prepared for future OTP integration; SMS verification is not currently enabled.', tip: 'Email verification confirms the account contact, not the legitimacy of the school.', kind: 'verify' },
  { title: 'Set up your school', text: 'Work through school profile, academic setup, classes and subjects, and staff invitations.', tip: 'Progress is saved, and optional setup steps can be completed later.', kind: 'onboarding' },
  { title: 'Open your dashboard', text: 'Continue into your workspace and explore the school tools available to your role.', tip: 'Invite staff from the school workspace and assign only the access they need.', kind: 'dashboard' },
  { title: 'School verification', text: 'Basic school setup can continue while platform review is pending. School verification is a separate decision from email verification.', tip: 'Higher-trust capabilities can require verified-school status.', kind: 'status' },
]

export const faqs = [
  ['Who can register?', 'A school owner, principal, administrator, or authorized representative can start a school workspace.'],
  ['Can a school register without contacting the company?', 'Yes. School registration is self-service. A valid administrator email must be verified before sign-in.'],
  ['Does registration require immediate manual approval?', 'No. Schools can begin basic setup after account email verification while platform verification is pending.'],
  ['What happens after registration?', 'The first registrant becomes the initial school owner. Verify the email, sign in, and follow the onboarding wizard.'],
  ['Can a school invite teachers?', 'School owners and authorized administrators can add staff and assign school roles.'],
  ['Can a school update its information?', 'Authorized school administrators can manage the school profile and configuration.'],
  ['How is school data separated?', 'School API access is scoped on the backend to an authenticated user’s active membership and selected school.'],
  ['Is there a monthly subscription?', 'Subscription billing is not currently available. The planned approach is free access to core features within reasonable limits.'],
  ['How do report-card credits work?', 'Schools can buy one-time packages: 100 credits for ₦30,000, 300 for ₦45,000, or 500 for ₦50,000. One credit is charged the first time a student’s approved report card is finalized for a school, session, and term. A successful Paystack payment must be verified by the server before credits are added.'],
  ['Can a school preview report cards for free?', 'Yes. Drafts, review, approval, preview, download, reprint, and later corrections do not use another credit. One credit is charged only for the first finalization in that student’s school, session, and term.'],
  ['How can a school contact support?', 'Use Request a Demo to leave contact details. Official support email and phone details will be published when confirmed.'],
]
