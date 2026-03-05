import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import styles from './ChatPage.module.css'

export default function ChatPage() {
  const [goal, setGoal] = useState('')
  const [startUrl, setStartUrl] = useState('https://www.google.com')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    if (!goal.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal.trim(), start_url: startUrl.trim() }),
      })
      if (!res.ok) throw new Error('Server error')
      const { task_id } = await res.json()
      navigate(`/run?task_id=${task_id}&goal=${encodeURIComponent(goal.trim())}`)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="var(--accent)" strokeWidth="1.5"/>
            <path d="M8 12h8M12 8l4 4-4 4" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <h1 className={styles.title}>VoiceNav</h1>
        <p className={styles.subtitle}>Tell me what you'd like to do on the web</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.inputGroup}>
            <label className={styles.label}>Your goal</label>
            <textarea
              className={styles.textarea}
              placeholder="e.g. Find the cheapest flights from NYC to LA next month"
              value={goal}
              onChange={e => setGoal(e.target.value)}
              rows={3}
              onKeyDown={e => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit(e)
              }}
              autoFocus
            />
          </div>

          <div className={styles.inputGroup}>
            <label className={styles.label}>Start URL <span className={styles.optional}>(optional)</span></label>
            <input
              className={styles.input}
              type="url"
              placeholder="https://www.google.com"
              value={startUrl}
              onChange={e => setStartUrl(e.target.value)}
            />
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <button
            type="submit"
            className={styles.button}
            disabled={!goal.trim() || loading}
          >
            {loading ? (
              <span className={styles.spinner} />
            ) : (
              <>
                Start
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </>
            )}
          </button>
        </form>

        <p className={styles.hint}>Tip: Press ⌘↵ to submit</p>
      </div>
    </div>
  )
}
