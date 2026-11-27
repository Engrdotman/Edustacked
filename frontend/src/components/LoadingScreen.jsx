import BrandMark from './BrandMark.jsx'

export default function LoadingScreen({ message = 'Getting your workspace ready…' }) {
  return (
    <main className="loading-screen" role="status" aria-live="polite" aria-atomic="true">
      <section className="loading-card" aria-label="EDUstacked is loading">
        <div className="loading-brand-wrap" aria-hidden="true">
          <span className="loading-orbit" />
          <BrandMark className="loading-brand" />
        </div>
        <p className="loading-message">{message}</p>
      </section>
    </main>
  )
}
