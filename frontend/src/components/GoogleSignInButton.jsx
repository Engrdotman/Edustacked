import { useEffect, useRef } from 'react'
import { ApiError } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'

const GOOGLE_SCRIPT_URL = 'https://accounts.google.com/gsi/client'

export default function GoogleSignInButton({ portal = 'school', onSuccess, onError, onBusy }) {
  const containerRef = useRef(null)
  const portalRef = useRef(portal)
  const onSuccessRef = useRef(onSuccess)
  const onErrorRef = useRef(onError)
  const onBusyRef = useRef(onBusy)
  const { signInWithGoogle, getGoogleLoginChallenge } = useAuth()
  const clientId = (import.meta.env.VITE_GOOGLE_CLIENT_ID || '').trim()

  useEffect(() => { portalRef.current = portal }, [portal])
  useEffect(() => { onSuccessRef.current = onSuccess }, [onSuccess])
  useEffect(() => { onErrorRef.current = onError }, [onError])
  useEffect(() => { onBusyRef.current = onBusy }, [onBusy])

  useEffect(() => {
    if (!clientId || !containerRef.current) return undefined
    let active = true
    let retrying = false

    const renderGoogleButton = async () => {
      try {
        const { nonce } = await getGoogleLoginChallenge()
        if (!active || !window.google?.accounts?.id || !containerRef.current) return
        containerRef.current.replaceChildren()
        window.google.accounts.id.initialize({
          client_id: clientId,
          nonce,
          auto_select: false,
          callback: async (credentialResponse) => {
            if (!credentialResponse?.credential) {
              onErrorRef.current?.('Google did not return a sign-in credential. Try again.')
              return
            }
            onErrorRef.current?.('')
            onBusyRef.current?.(true)
            try {
              const profile = await signInWithGoogle(
                credentialResponse.credential,
                nonce,
                { portal: portalRef.current },
              )
              onSuccessRef.current?.(profile)
            } catch (error) {
              onErrorRef.current?.(error instanceof ApiError
                ? error.message
                : error?.message || 'Google sign-in could not be completed. Try again.')
              onBusyRef.current?.(false)
              if (!retrying && active) {
                retrying = true
                window.setTimeout(() => {
                  retrying = false
                  if (active) renderGoogleButton()
                }, 500)
              }
            }
          },
        })
        window.google.accounts.id.renderButton(containerRef.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          shape: 'rectangular',
          text: 'continue_with',
          logo_alignment: 'left',
          width: Math.min(440, Math.max(240, containerRef.current.clientWidth || 360)),
        })
      } catch (error) {
        if (active) onErrorRef.current?.(error?.message || 'Google sign-in is not available right now.')
      }
    }

    const loadGoogle = () => {
      if (window.google?.accounts?.id) {
        renderGoogleButton()
        return () => {}
      }
      let script = document.querySelector(`script[src="${GOOGLE_SCRIPT_URL}"]`)
      const addedHere = !script
      if (!script) {
        script = document.createElement('script')
        script.src = GOOGLE_SCRIPT_URL
        script.async = true
        script.defer = true
        document.head.appendChild(script)
      }
      const onLoad = () => renderGoogleButton()
      const onScriptError = () => onErrorRef.current?.('Could not load Google sign-in. Check your connection and try again.')
      script.addEventListener('load', onLoad)
      script.addEventListener('error', onScriptError)
      if (window.google?.accounts?.id) onLoad()
      return () => {
        script.removeEventListener('load', onLoad)
        script.removeEventListener('error', onScriptError)
        if (addedHere && !window.google?.accounts?.id) script.remove()
      }
    }

    const cleanupScript = loadGoogle()
    return () => {
      active = false
      containerRef.current?.replaceChildren()
      cleanupScript?.()
    }
  }, [clientId, getGoogleLoginChallenge, signInWithGoogle])

  if (!clientId) return null
  return <div className="google-signin-wrap" aria-label="Sign in with Google">
    <div className="google-signin-divider"><span>or continue with</span></div>
    <div ref={containerRef} className="google-signin-button" />
  </div>
}
