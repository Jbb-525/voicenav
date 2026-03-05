import { useEffect, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import BrowserView from '../components/BrowserView'
import ThinkingPanel from '../components/ThinkingPanel'
import styles from './ExecutionPage.module.css'

// Persist task result into localStorage so ChatPage can show history
function saveHistory(taskId, patch) {
  const raw = localStorage.getItem('voicenav_history') || '[]'
  const hist = JSON.parse(raw)
  const idx = hist.findIndex(h => h.taskId === taskId)
  if (idx >= 0) Object.assign(hist[idx], patch)
  else hist.unshift({ taskId, ...patch })
  localStorage.setItem('voicenav_history', JSON.stringify(hist.slice(0, 50)))
}

export default function ExecutionPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const taskId = searchParams.get('task_id')
  const goal = searchParams.get('goal') || ''

  const [frame, setFrame] = useState(null)
  const [events, setEvents] = useState([])
  const [status, setStatus] = useState('connecting')
  const [summary, setSummary] = useState(null)
  const [captcha, setCaptcha] = useState(false)
  const [currentPlan, setCurrentPlan] = useState([])
  const [currentPlanStep, setCurrentPlanStep] = useState(0)
  const [currentUrl, setCurrentUrl] = useState('')

  const wsRef = useRef(null)

  useEffect(() => {
    if (!taskId) { navigate('/'); return }
    // Record task as running
    saveHistory(taskId, { goal, status: 'running', timestamp: Date.now() })

    const ws = new WebSocket(`ws://${window.location.host}/ws/${taskId}`)
    wsRef.current = ws

    ws.onopen = () => setStatus('running')

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)

      if (msg.type === 'frame') { setFrame(msg.data); return }

      if (msg.type === 'thinking') {
        if (msg.overall_plan?.length) setCurrentPlan(msg.overall_plan)
        if (msg.current_step) setCurrentPlanStep(msg.current_step)
        setCaptcha(false)
      }

      if (msg.type === 'result' && msg.url) setCurrentUrl(msg.url)

      if (msg.type === 'captcha') setCaptcha(true)

      if (msg.type === 'done') {
        setStatus('done')
        const s = { success: msg.success, steps: msg.steps, error: msg.error, final_url: msg.final_url }
        setSummary(s)
        if (msg.final_url) setCurrentUrl(msg.final_url)
        setCaptcha(false)
        // Persist result so ChatPage can display it
        saveHistory(taskId, {
          status: msg.success ? 'done' : 'stopped',
          final_url: msg.final_url,
          steps: msg.steps,
          error: msg.error,
        })
      }

      if (msg.type === 'error') {
        setStatus('error')
        setSummary({ success: false, error: msg.message })
        setCaptcha(false)
        saveHistory(taskId, { status: 'error', error: msg.message })
      }

      setEvents(prev => [...prev, { ...msg, ts: Date.now() }])
    }

    ws.onerror = () => setStatus('error')
    ws.onclose = () => {
      if (status !== 'done' && status !== 'error') setStatus('done')
    }

    return () => ws.close()
  }, [taskId]) // eslint-disable-line react-hooks/exhaustive-deps

  function sendWsMessage(msg) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }

  return (
    <div className={styles.page}>
      {/* Top bar */}
      <header className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M19 12H5M11 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Chat
        </button>
        <div className={styles.goalText} title={goal}>{goal}</div>
        <StatusBadge status={status} summary={summary} />
      </header>

      {/* Plan milestones bar */}
      {currentPlan.length > 0 && (
        <div className={styles.planBar}>
          {currentPlan.map((step, i) => (
            <div
              key={i}
              className={[
                styles.milestone,
                i + 1 < currentPlanStep ? styles.done : '',
                i + 1 === currentPlanStep ? styles.active : '',
              ].join(' ')}
            >
              <span className={styles.milestoneNum}>{i + 1}</span>
              <span className={styles.milestoneText}>{step}</span>
            </div>
          ))}
        </div>
      )}

      {/* Main content */}
      <div className={styles.body}>
        <BrowserView
          frame={frame}
          onInput={sendWsMessage}
          captcha={captcha}
          currentUrl={currentUrl}
          finalUrl={summary?.final_url}
        />
        <ThinkingPanel events={events} summary={summary} />
      </div>
    </div>
  )
}

function StatusBadge({ status, summary }) {
  const map = {
    connecting: { label: 'Connecting…', color: 'var(--text-dim)' },
    running:    { label: 'Running',     color: 'var(--yellow)' },
    done:       { label: summary?.success ? 'Done ✓' : 'Stopped', color: summary?.success ? 'var(--green)' : 'var(--red)' },
    error:      { label: 'Error',       color: 'var(--red)' },
  }
  const { label, color } = map[status] || map.connecting
  return (
    <div className={styles.badge} style={{ '--c': color }}>
      {status === 'running' && <span className={styles.pulse} />}
      {label}
    </div>
  )
}
