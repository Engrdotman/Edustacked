import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { flushSync } from 'react-dom'
import { AuthProvider, useAuth } from './auth/AuthContext.jsx'

const AccessDeniedPage = lazy(() => import('./pages/AccessDeniedPage.jsx'))
const AuthenticatedHome = lazy(() => import('./pages/AuthenticatedHome.jsx'))
const LoginPage = lazy(() => import('./pages/LoginPage.jsx'))
const PlatformLoginPage = lazy(() => import('./pages/PlatformLoginPage.jsx'))
const PasswordResetPage = lazy(() => import('./pages/PasswordResetPage.jsx'))
const SchoolProfilePage = lazy(() => import('./pages/SchoolProfilePage.jsx'))
const AcademicSetupPage = lazy(() => import('./pages/AcademicSetupPage.jsx'))
const PromotionPlanningPage = lazy(() => import('./pages/PromotionPlanningPage.jsx'))
const WelcomePage = lazy(() => import('./pages/WelcomePage.jsx'))
const StudentManagementPage = lazy(() => import('./pages/StudentManagementPage.jsx'))
const StaffManagementPage = lazy(() => import('./pages/StaffManagementPage.jsx'))
const AttendanceManagementPage = lazy(() => import('./pages/AttendanceManagementPage.jsx'))
const AssessmentResultsPage = lazy(() => import('./pages/AssessmentResultsPage.jsx'))
const ReportCardsPage = lazy(() => import('./pages/ReportCardsPage.jsx'))
const BillingPage = lazy(() => import('./pages/BillingPage.jsx'))
const ParentPortalPage = lazy(() => import('./pages/ParentPortalPage.jsx'))
const GuardianActivationPage = lazy(() => import('./pages/GuardianActivationPage.jsx'))
const AnnouncementsManagementPage = lazy(() => import('./pages/AnnouncementsManagementPage.jsx'))
const ReportsPage = lazy(() => import('./pages/ReportsPage.jsx'))
const SignupPage = lazy(() => import('./pages/SignupPage.jsx'))
const SchoolDashboardPage = lazy(() => import('./pages/SchoolDashboardPage.jsx'))
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage.jsx'))
const DemoRequestPage = lazy(() => import('./pages/DemoRequestPage.jsx'))
const SchoolOnboardingPage = lazy(() => import('./pages/SchoolOnboardingPage.jsx'))
const PlatformSchoolsPage = lazy(() => import('./pages/PlatformSchoolsPage.jsx'))
const PlatformSchoolDetailPage = lazy(() => import('./pages/PlatformSchoolDetailPage.jsx'))
const PlatformAdminDashboardPage = lazy(() => import('./pages/PlatformAdminDashboardPage.jsx'))
const LegalDraftPage = lazy(() => import('./pages/LegalDraftPage.jsx'))
const CbtManagementPage = lazy(() => import('./pages/CbtManagementPage.jsx'))
const CbtResultsPage = lazy(() => import('./pages/CbtResultsPage.jsx'))
const ServicesPage = lazy(() => import('./pages/ServicesPage.jsx'))

function AppRoutes() {
  const [location, setLocation] = useState(() => `${window.location.pathname}${window.location.search}`)
  const { user, loading, selectedSchool, guardianProfile } = useAuth()

  useEffect(() => {
    const onPopState = () => setLocation(`${window.location.pathname}${window.location.search}`)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((path) => {
    const from = window.location.pathname
    const to = new URL(path, window.location.origin).pathname
    const isAuthFlip = from !== to && ['/login', '/signup'].includes(from) && ['/login', '/signup'].includes(to)
    const updateRoute = () => {
      window.history.pushState({}, '', path)
      flushSync(() => setLocation(path))
    }
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

    if (isAuthFlip && !reduceMotion && typeof document.startViewTransition === 'function') {
      document.startViewTransition(updateRoute)
      return
    }
    updateRoute()
  }, [])

  const pathname = location.split('?')[0]
  useEffect(() => {
    if (!loading && user?.is_superuser && ['/platform/login', '/login', '/signup'].includes(pathname)) navigate('/platform')
  }, [loading, pathname, user, navigate])

  if (pathname === '/privacy') return <LegalDraftPage type="privacy" navigate={navigate} />
  if (pathname === '/terms') return <LegalDraftPage type="terms" navigate={navigate} />
  if (pathname === '/guardian/activate') return <GuardianActivationPage navigate={navigate} />
  if (pathname === '/verify-email') return <VerifyEmailPage navigate={navigate} />
  if (pathname === '/demo') return <DemoRequestPage navigate={navigate} />
  if (pathname === '/platform/login') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Checking platform session…</p></main>
    return <PlatformLoginPage navigate={navigate} />
  }
  if (pathname === '/signup') {
    if (user?.is_superuser) return <main className="auth-page"><p className="loading-message" role="status">Opening platform administration…</p></main>
    return user ? <AuthenticatedHome navigate={navigate} /> : <SignupPage navigate={navigate} />
  }
  if (pathname === '/login') {
    if (user?.is_superuser) return <main className="auth-page"><p className="loading-message" role="status">Opening platform administration…</p></main>
    return user ? <AuthenticatedHome navigate={navigate} /> : <LoginPage navigate={navigate} />
  }
  if (pathname === '/forgot-password') {
    return <PasswordResetPage navigate={navigate} mode="request" />
  }
  if (pathname === '/reset-password') {
    return <PasswordResetPage navigate={navigate} />
  }
  if ((pathname === '/app' || pathname.startsWith('/app/')) && !loading && !user) {
    return <LoginPage navigate={navigate} sessionRequired />
  }
  if (pathname === '/denied') {
    return <AccessDeniedPage navigate={navigate} signedIn={Boolean(user)} />
  }
  if (pathname === '/platform' || pathname === '/platform/schools' || /^\/platform\/schools\/\d+$/.test(pathname)) {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <PlatformLoginPage navigate={navigate} />
    if (!user.is_superuser) return <AccessDeniedPage navigate={navigate} signedIn />
    const detail = pathname.match(/^\/platform\/schools\/(\d+)$/)
    if (detail) return <PlatformSchoolDetailPage schoolId={detail[1]} navigate={navigate} />
    if (pathname === '/platform/schools') return <PlatformSchoolsPage navigate={navigate} />
    return <PlatformAdminDashboardPage navigate={navigate} />
  }
  if (pathname === '/app') {
    if (loading) {
      return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    }
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool && guardianProfile) return <ParentPortalPage navigate={navigate} />
    return selectedSchool ? <SchoolDashboardPage navigate={navigate} /> : <AuthenticatedHome navigate={navigate} />
  }
  if (pathname === '/app/school') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (selectedSchool.role === 'teacher') return <AccessDeniedPage navigate={navigate} signedIn />
    return <SchoolProfilePage navigate={navigate} />
  }
  if (pathname === '/app/onboarding') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['school_owner', 'school_admin', 'school_manager', 'principal'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <SchoolOnboardingPage navigate={navigate} />
  }
  if (pathname === '/app/academics') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(selectedSchool.role)) {
      return <AccessDeniedPage navigate={navigate} signedIn />
    }
    return <AcademicSetupPage navigate={navigate} />
  }
  if (pathname === '/app/promotions') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <PromotionPlanningPage navigate={navigate} />
  }
  if (pathname === '/app/students') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'receptionist'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <StudentManagementPage navigate={navigate} />
  }
  if (pathname === '/app/cbt' || pathname === '/app/cbt/results' || /^\/app\/cbt\/results\/[0-9a-f-]+$/i.test(pathname)) {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool || !['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    if (pathname === '/app/cbt') return <CbtManagementPage navigate={navigate} />
    const resultId = pathname.match(/^\/app\/cbt\/results\/([0-9a-f-]+)$/i)?.[1] || ''
    return <CbtResultsPage navigate={navigate} resultId={resultId} />
  }
  if (pathname === '/app/services') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool || !['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <ServicesPage navigate={navigate} />
  }
  if (pathname === '/app/staff') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'receptionist'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <StaffManagementPage navigate={navigate} />
  }
  if (pathname === '/app/attendance') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <AttendanceManagementPage navigate={navigate} />
  }
  if (pathname === '/app/assessments') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <AssessmentResultsPage navigate={navigate} />
  }
  if (pathname === '/app/report-cards') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <ReportCardsPage navigate={navigate} />
  }
  if (pathname === '/app/billing') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'accountant'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <BillingPage navigate={navigate} />
  }
  if (pathname === '/app/announcements') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool || !['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <AnnouncementsManagementPage navigate={navigate} />
  }
  if (pathname === '/app/reports') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool || !['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'accountant', 'receptionist'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <ReportsPage navigate={navigate} />
  }
  if (pathname === '/parent') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user || !guardianProfile) return <AccessDeniedPage navigate={navigate} signedIn={Boolean(user)} />
    return <ParentPortalPage navigate={navigate} />
  }
  return <WelcomePage onLogin={() => navigate('/login')} onSignup={() => navigate('/signup')} onDemo={() => navigate('/demo')} />
}

export default function App() {
  return <AuthProvider><Suspense fallback={<main className="auth-page"><p className="loading-message" role="status">Loading EDUstacked…</p></main>}><AppRoutes /></Suspense></AuthProvider>
}
