import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { apiRequest, login as apiLogin, logout as apiLogout, refreshSession, setAccessToken, setSelectedSchoolId, verifySchoolEmail } from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [schools, setSchools] = useState([])
  const [selectedSchool, setSelectedSchool] = useState(null)
  const [guardianProfile, setGuardianProfile] = useState(null)
  const [loading, setLoading] = useState(true)

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
        await loadIdentity()
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
