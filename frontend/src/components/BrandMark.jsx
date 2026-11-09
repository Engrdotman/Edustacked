export default function BrandMark({ navigate, ...props }) {
  const handleClick = (e) => {
    if (navigate) {
      e.preventDefault()
      navigate('/')
    }
  }

  const className = navigate ? 'brand brand-clickable' : 'brand'

  return (
    <div 
      className={className} 
      aria-label="EDUstacked"
      onClick={handleClick}
      role={navigate ? 'button' : undefined}
      tabIndex={navigate ? 0 : undefined}
      onKeyDown={navigate ? (e) => e.key === 'Enter' && handleClick(e) : undefined}
      {...props}
    >
      <span className="brand-mark" aria-hidden="true">
        <span className="brand-letter-e">E</span>
        <span className="brand-letter-s">S</span>
      </span>

      <span className="brand-name">EDU<span>stacked</span></span>
    </div>
  )
}
