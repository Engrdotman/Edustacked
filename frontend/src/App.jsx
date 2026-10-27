import { useCallback, useEffect, useState } from 'react'
import { AuthProvider, useAuth } from './auth/AuthContext.jsx'
import AccessDeniedPage from './pages/AccessDeniedPage.jsx'
import AuthenticatedHome from './pages/AuthenticatedHome.jsx'
import LoginPage from './pages/LoginPage.jsx'
import PasswordResetPage from './pages/PasswordResetPage.jsx'
import WelcomePage from './pages/WelcomePage.jsx'

function AppRoutes() {
  const [location, setLocation] = useState(() => `${window.location.pathname}${window.location.search}`)
  const { user, loading } = useAuth()

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
  if (pathname === '/app') {
    if (loading) {
      return <main className="auth-page"><p className="loading-message" role="status">Restoring your secure session…</p></main>
    }
    if (!user) return <AccessDeniedPage navigate={navigate} />
    return <AuthenticatedHome navigate={navigate} />
  }
  return <WelcomePage onLogin={() => navigate('/login')} />
}

export default function App() {
  return <AuthProvider><AppRoutes /></AuthProvider>
}
