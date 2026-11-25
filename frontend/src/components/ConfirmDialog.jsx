import { useEffect, useId, useRef, useState } from 'react'

export default function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Yes, continue',
  cancelLabel = 'No, cancel',
  confirmTone = 'primary',
  requireReason = false,
  reasonLabel = 'Reason',
  reasonPlaceholder = 'Enter a reason',
  busy = false,
  onConfirm,
  onCancel,
}) {
  const headingId = useId()
  const messageId = useId()
  const reasonId = useId()
  const dialogRef = useRef(null)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState('')

  useEffect(() => {
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const target = dialogRef.current?.querySelector('textarea, .confirm-dialog-cancel')
    target?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
    }
  }, [])

  function confirm() {
    if (requireReason && !reason.trim()) {
      setReasonError('Please enter a reason to continue.')
      return
    }
    onConfirm?.(reason.trim())
  }

  function handleKeyDown(event) {
    if (event.key === 'Escape' && !busy) {
      event.preventDefault()
      onCancel?.()
    }
    if (event.key === 'Tab') {
      const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled), textarea:not(:disabled)')]
      if (!controls.length) return
      const first = controls[0]
      const last = controls.at(-1)
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
  }

  return (
    <div className="confirm-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onCancel?.()}>
      <section
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={headingId}
        aria-describedby={messageId}
        ref={dialogRef}
        onKeyDown={handleKeyDown}
      >
        <span className="confirm-dialog-mark" aria-hidden="true">?</span>
        <p className="confirm-dialog-kicker">PLEASE CONFIRM</p>
        <h2 id={headingId}>{title}</h2>
        <p className="confirm-dialog-message" id={messageId}>{message}</p>
        {requireReason && (
          <label className="confirm-dialog-reason" htmlFor={reasonId}>
            {reasonLabel}
            <textarea
              id={reasonId}
              rows="3"
              value={reason}
              placeholder={reasonPlaceholder}
              aria-invalid={Boolean(reasonError)}
              aria-describedby={reasonError ? `${reasonId}-error` : undefined}
              onChange={(event) => { setReason(event.target.value); setReasonError('') }}
            />
            {reasonError && <span className="confirm-dialog-error" id={`${reasonId}-error`} role="alert">{reasonError}</span>}
          </label>
        )}
        <div className="confirm-dialog-actions">
          <button className="confirm-dialog-cancel" type="button" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            className={`confirm-dialog-accept confirm-dialog-accept-${confirmTone}`}
            type="button"
            disabled={busy}
            onClick={confirm}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  )
}
