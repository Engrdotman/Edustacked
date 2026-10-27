import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { apiRequest, login as apiLogin, logout as apiLogout, refreshSession, setSelectedSchoolId } from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [schools, setSchools] = useState([])
  const [selectedSchool, setSelectedSchool] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadIdentity = useCallback(async () => {
    const [profile, memberships] = await Promise.all([
      apiRequest('auth/me/'),
      apiRequest('auth/schools/'),
    ])
    setUser(profile)
    setSchools(memberships)
    setSelectedSchoolId(null)
    setSelectedSchool(null)
    if (memberships.length === 1) {
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
    setSelectedSchool(null)
    setSelectedSchoolId(null)
    if (memberships.length === 1) {
      const selection = await apiRequest('auth/schools/select/', {
        method: 'POST',
        body: { school_id: memberships[0].school_id },
      })
      setSelectedSchoolId(selection.school_id)
      setSelectedSchool(selection)
    }
    return profile
  }, [])

  const signOut = useCallback(async () => {
    try {
      await apiLogout()
    } finally {
      setUser(null)
      setSchools([])
      setSelectedSchool(null)
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
    loading,
    signIn,
    signOut,
    selectSchool,
  }), [user, schools, selectedSchool, loading, signIn, signOut, selectSchool])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
