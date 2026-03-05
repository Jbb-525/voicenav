import { useEffect, useRef } from 'react'
import styles from './ThinkingPanel.module.css'

export default function ThinkingPanel({ events, summary }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  return (
    <aside className={styles.panel}>
      <div className={styles.header}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <path d="M12 2a7 7 0 0 1 7 7c0 2.5-1.3 4.7-3.3 6l-.7.4V17a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2v-1.6l-.7-.4A7 7 0 0 1 12 2z" stroke="var(--accent)" strokeWidth="1.5"/>
          <path d="M10 21h4" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
        Agent Thinking
      </div>

      <div className={styles.log}>
        {events.length === 0 && (
          <p className={styles.empty}>Waiting for agent to start…</p>
        )}

        {events.map((ev, i) => (
          <EventRow key={i} ev={ev} />
        ))}

        <div ref={bottomRef} />
      </div>

      {summary?.final_url && (
        <div className={styles.resultFooter}>
          <div className={styles.resultLabel}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
              <path d="M20 6L9 17l-5-5" stroke="var(--green)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Final URL
          </div>
          <a
            href={summary.final_url}
            target="_blank"
            rel="noreferrer"
            className={styles.resultUrl}
            title={summary.final_url}
          >
            {summary.final_url}
          </a>
        </div>
      )}
    </aside>
  )
}

function EventRow({ ev }) {
  if (ev.type === 'thinking') {
    return (
      <div className={styles.entry}>
        <div className={styles.stepLabel}>Step {ev.step}</div>
        <div className={styles.thought}>{ev.thought}</div>
        {ev.plan_adjustment && (
          <div className={styles.adjustment}>↻ {ev.plan_adjustment}</div>
        )}
      </div>
    )
  }

  if (ev.type === 'action') {
    return (
      <div className={`${styles.entry} ${styles.actionEntry}`}>
        <span className={styles.actionIcon}>→</span>
        <span className={styles.actionText}>{formatAction(ev.action)}</span>
      </div>
    )
  }

  if (ev.type === 'result') {
    return (
      <div className={`${styles.entry} ${styles.resultEntry}`} data-ok={ev.success}>
        <span className={styles.resultIcon}>{ev.success ? '✓' : '✗'}</span>
        <span className={styles.resultText}>{ev.message || (ev.success ? 'Success' : 'Failed')}</span>
      </div>
    )
  }

  if (ev.type === 'done') {
    return (
      <div className={`${styles.entry} ${styles.doneEntry}`} data-ok={ev.success}>
        <div className={styles.doneLabel}>
          {ev.success ? '✅ Task complete' : '⚠ Task stopped'}
        </div>
        {ev.error && <div className={styles.doneError}>{ev.error}</div>}
        {ev.steps && <div className={styles.doneMeta}>{ev.steps} steps taken</div>}
      </div>
    )
  }

  if (ev.type === 'captcha') {
    return (
      <div className={`${styles.entry} ${styles.captchaEntry}`}>
        ⚠ CAPTCHA detected — click the browser stream to solve it
      </div>
    )
  }

  if (ev.type === 'error') {
    return (
      <div className={`${styles.entry} ${styles.errorEntry}`}>
        <span className={styles.resultIcon}>✗</span>
        <span>{ev.message}</span>
      </div>
    )
  }

  return null
}

function formatAction(action) {
  if (!action) return '?'
  const t = action.type
  if (t === 'goto')   return `Navigate → ${action.url}`
  if (t === 'click')  return `Click "${action.target}"`
  if (t === 'type')   return `Type "${action.text}" in "${action.target}"${action.submit ? ' ↵' : ''}`
  if (t === 'scroll') return `Scroll ${action.direction}`
  if (t === 'select') return `Select "${action.option}" from "${action.dropdown}"`
  if (t === 'done')   return 'Mark as done'
  return JSON.stringify(action)
}
