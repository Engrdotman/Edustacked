import { useEffect, useState } from 'react'

export default function PWAControls() {
  const [online, setOnline] = useState(() => navigator.onLine)
  const [installPrompt, setInstallPrompt] = useState(null)
  const [installed, setInstalled] = useState(() => (
    window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true
  ))

  useEffect(() => {
    const updateOnline = () => setOnline(navigator.onLine)
    const captureInstall = (event) => {
      event.preventDefault()
      setInstallPrompt(event)
    }
    const markInstalled = () => {
      setInstalled(true)
      setInstallPrompt(null)
    }
    window.addEventListener('online', updateOnline)
    window.addEventListener('offline', updateOnline)
    window.addEventListener('beforeinstallprompt', captureInstall)
    window.addEventListener('appinstalled', markInstalled)
    if (import.meta.env.PROD && 'serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' }).catch(() => {})
    }
    return () => {
      window.removeEventListener('online', updateOnline)
      window.removeEventListener('offline', updateOnline)
      window.removeEventListener('beforeinstallprompt', captureInstall)
      window.removeEventListener('appinstalled', markInstalled)
    }
  }, [])

  async function installApp() {
    if (!installPrompt) return
    await installPrompt.prompt()
    await installPrompt.userChoice
    setInstallPrompt(null)
  }

  if (online && (installed || !installPrompt)) return null
  return (
    <aside className={`pwa-status-banner${online ? ' pwa-status-install' : ''}`} role={online ? 'region' : 'status'} aria-live="polite">
      <div>
        <strong>{online ? 'Install EDUstacked' : 'You’re offline'}</strong>
        <span>{online
          ? 'Add the workspace to this device for quick access.'
          : 'Previously prepared attendance registers can be marked and saved on this device, then synced when you reconnect. Other live school records need internet. Offline CBT runs through your school’s local CBT server.'}</span>
      </div>
      {installPrompt && <button type="button" className="secondary-button" onClick={installApp}>Install app</button>}
    </aside>
  )
}
