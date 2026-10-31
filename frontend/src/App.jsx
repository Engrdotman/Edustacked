import { useCallback, useEffect, useState } from 'react'
import { AuthProvider, useAuth } from './auth/AuthContext.jsx'
import AccessDeniedPage from './pages/AccessDeniedPage.jsx'
import AuthenticatedHome from './pages/AuthenticatedHome.jsx'
import LoginPage from './pages/LoginPage.jsx'
import PasswordResetPage from './pages/PasswordResetPage.jsx'
import SchoolProfilePage from './pages/SchoolProfilePage.jsx'
import AcademicSetupPage from './pages/AcademicSetupPage.jsx'
import WelcomePage from './pages/WelcomePage.jsx'
import StudentManagementPage from './pages/StudentManagementPage.jsx'
import StaffManagementPage from './pages/StaffManagementPage.jsx'
import AttendanceManagementPage from './pages/AttendanceManagementPage.jsx'
import AssessmentResultsPage from './pages/AssessmentResultsPage.jsx'
import ReportCardsPage from './pages/ReportCardsPage.jsx'
import BillingPage from './pages/BillingPage.jsx'
import ParentPortalPage from './pages/ParentPortalPage.jsx'
import GuardianActivationPage from './pages/GuardianActivationPage.jsx'
import AnnouncementsManagementPage from './pages/AnnouncementsManagementPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import SignupPage from './pages/SignupPage.jsx'
import SchoolDashboardPage from './pages/SchoolDashboardPage.jsx'
import VerifyEmailPage from './pages/VerifyEmailPage.jsx'
import DemoRequestPage from './pages/DemoRequestPage.jsx'
import SchoolOnboardingPage from './pages/SchoolOnboardingPage.jsx'
import PlatformSchoolsPage from './pages/PlatformSchoolsPage.jsx'
import PlatformSchoolDetailPage from './pages/PlatformSchoolDetailPage.jsx'
import LegalDraftPage from './pages/LegalDraftPage.jsx'

function AppRoutes() {
  const [location, setLocation] = useState(() => `${window.location.pathname}${window.location.search}`)
  const { user, loading, selectedSchool, guardianProfile } = useAuth()

  useEffect(() => {
    const onPopState = () => setLocation(`${window.location.pathname}${window.location.search}`)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((path) => {
    window.history.pushState({}, '', path)
    setLocation(path)
  }, [])

  const pathname = location.split('?')[0]
  if (pathname === '/privacy') return <LegalDraftPage type="privacy" navigate={navigate} />
  if (pathname === '/terms') return <LegalDraftPage type="terms" navigate={navigate} />
  if (pathname === '/guardian/activate') return <GuardianActivationPage navigate={navigate} />
  if (pathname === '/verify-email') return <VerifyEmailPage navigate={navigate} />
  if (pathname === '/demo') return <DemoRequestPage navigate={navigate} />
  if (pathname === '/signup') return user ? <AuthenticatedHome navigate={navigate} /> : <SignupPage navigate={navigate} />
  if (pathname === '/login') {
    return user ? <AuthenticatedHome navigate={navigate} /> : <LoginPage navigate={navigate} />
  }
  if (pathname === '/forgot-password') {
    return <PasswordResetPage navigate={navigate} mode="request" />
  }
  if (pathname === '/reset-password') {
    return <PasswordResetPage navigate={navigate} />
  }
  if (pathname === '/denied') {
    return <AccessDeniedPage navigate={navigate} signedIn={Boolean(user)} />
  }
  if (pathname === '/platform/schools' || /^\/platform\/schools\/\d+$/.test(pathname)) {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!user.is_superuser) return <AccessDeniedPage navigate={navigate} signedIn />
    const detail = pathname.match(/^\/platform\/schools\/(\d+)$/)
    return detail ? <PlatformSchoolDetailPage schoolId={detail[1]} navigate={navigate} /> : <PlatformSchoolsPage navigate={navigate} />
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
  if (pathname === '/app/students') {
    if (loading) return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    if (!user) return <AccessDeniedPage navigate={navigate} />
    if (!selectedSchool) return <AuthenticatedHome navigate={navigate} />
    if (!['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal', 'teacher', 'receptionist'].includes(selectedSchool.role)) return <AccessDeniedPage navigate={navigate} signedIn />
    return <StudentManagementPage navigate={navigate} />
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
  return <AuthProvider><AppRoutes /></AuthProvider>
}
