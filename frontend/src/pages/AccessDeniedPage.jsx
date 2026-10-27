export default function AccessDeniedPage({ navigate, signedIn = false }) {
  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="denied-title">
        <p className="eyebrow">ACCESS CHECK</p>
        <h1 id="denied-title">This page is unavailable.</h1>
        <p className="auth-intro">
          {signedIn
            ? 'Your account does not have access to this page.'
            : 'Sign in with an account that has been provisioned for your school.'}
        </p>
        <button className="primary-button" type="button" onClick={() => navigate(signedIn ? '/app' : '/login')}>
          {signedIn ? 'Return to your account' : 'Go to sign in'}
        </button>
      </section>
    </main>
  )
}
