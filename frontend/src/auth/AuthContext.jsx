import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { apiRequest, login as apiLogin, logout as apiLogout, refreshSession, setAccessToken, setSelectedSchoolId, verifySchoolEmail } from '../services/api.js'

const AuthContext = createContext(null)
const IDLE_TIMEOUT_MS = 30 * 60 * 1000
const SESSION_REFRESH_INTERVAL_MS = 4 * 60 * 1000
const SESSION_CHECK_INTERVAL_MS = 30 * 1000

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [schools, setSchools] = useState([])
  const [selectedSchool, setSelectedSchool] = useState(null)
  const [guardianProfile, setGuardianProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const lastActivityAt = useRef(Date.now())
  const lastSessionRefreshAt = useRef(Date.now())
  const refreshInProgress = useRef(false)

  const loadIdentity = useCallback(async () => {
    const [profile, memberships] = await Promise.all([
      apiRequest('auth/me/'),
      apiRequest('auth/schools/'),
    ])
    setUser(profile)
    setSchools(memberships)
    const portalProfile = await apiRequest('parent/profile/').catch(() => null)
    setGuardianProfile(portalProfile)
    setSelectedSchoolId(null)
    setSelectedSchool(null)
    if (memberships.length === 1 && memberships[0].school_accessible !== false) {
      const selection = await apiRequest('auth/schools/select/', {
        method: 'POST',
        body: { school_id: memberships[0].school_id },
      })
      setSelectedSchoolId(selection.school_id)
      setSelectedSchool(selection)
    }
  }, [])

  useEffect(() => {
    let active = true
    async function restoreSession() {
      try {
        await refreshSession()
        lastSessionRefreshAt.current = Date.now()
        await loadIdentity()
        lastActivityAt.current = Date.now()
      } catch {
        if (active) {
          setUser(null)
          setSchools([])
          setSelectedSchool(null)
          setGuardianProfile(null)
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    restoreSession()
    return () => { active = false }
  }, [loadIdentity])

  const signIn = useCallback(async (email, password) => {
    const profile = await apiLogin(email, password)
    lastActivityAt.current = Date.now()
    lastSessionRefreshAt.current = Date.now()
    const memberships = await apiRequest('auth/schools/')
    setUser(profile)
    setSchools(memberships)
    const portalProfile = await apiRequest('parent/profile/').catch(() => null)
    setGuardianProfile(portalProfile)
    setSelectedSchool(null)
    setSelectedSchoolId(null)
    if (memberships.length === 1 && memberships[0].school_accessible !== false) {
      const selection = await apiRequest('auth/schools/select/', {
        method: 'POST',
        body: { school_id: memberships[0].school_id },
      })
      setSelectedSchoolId(selection.school_id)
      setSelectedSchool(selection)
    }
    return { ...profile, guardian_portal: Boolean(portalProfile) }
  }, [])

  const completeEmailVerification = useCallback(async (selector, token) => {
    const result = await verifySchoolEmail({ selector, token })
    setAccessToken(result.access)
    await loadIdentity()
    return result
  }, [loadIdentity])

  const signOut = useCallback(async () => {
    try {
      await apiLogout()
    } finally {
      setUser(null)
      setSchools([])
      setSelectedSchool(null)
      setGuardianProfile(null)
    }
  }, [])

  useEffect(() => {
    if (!user) return undefined

    const markActivity = () => {
      lastActivityAt.current = Date.now()
    }
    const activityEvents = ['pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll']
    activityEvents.forEach((eventName) => window.addEventListener(eventName, markActivity, { passive: true }))

    const checkSession = async () => {
      const now = Date.now()
      if (now - lastActivityAt.current >= IDLE_TIMEOUT_MS) {
        await signOut()
        return
      }
      if (document.visibilityState !== 'visible'
        || refreshInProgress.current
        || now - lastSessionRefreshAt.current < SESSION_REFRESH_INTERVAL_MS) return

      refreshInProgress.current = true
      lastSessionRefreshAt.current = now
      try {
        await refreshSession()
      } catch (error) {
        if ([401, 403].includes(error.statusCode)) {
          await signOut()
        } else {
          // A temporary network/server failure should not end an active session.
          lastSessionRefreshAt.current = Date.now() - SESSION_REFRESH_INTERVAL_MS + SESSION_CHECK_INTERVAL_MS
        }
      } finally {
        refreshInProgress.current = false
      }
    }

    const interval = window.setInterval(checkSession, SESSION_CHECK_INTERVAL_MS)
    return () => {
      window.clearInterval(interval)
      activityEvents.forEach((eventName) => window.removeEventListener(eventName, markActivity))
    }
  }, [user, signOut])

  const selectSchool = useCallback(async (schoolId) => {
    const selection = await apiRequest('auth/schools/select/', {
      method: 'POST',
      body: { school_id: Number(schoolId) },
    })
    setSelectedSchoolId(selection.school_id)
    setSelectedSchool(selection)
    return selection
  }, [])

  const value = useMemo(() => ({
    user,
    schools,
    selectedSchool,
    guardianProfile,
    loading,
    signIn,
    signOut,
    selectSchool,
    completeEmailVerification,
  }), [user, schools, selectedSchool, guardianProfile, loading, signIn, signOut, selectSchool, completeEmailVerification])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
