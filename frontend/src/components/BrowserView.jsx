import { useRef } from 'react'
import styles from './BrowserView.module.css'

const BROWSER_W = 1280
const BROWSER_H = 720

export default function BrowserView({ frame, onInput, captcha, currentUrl, finalUrl }) {
  const imgRef = useRef(null)

  function handleClick(e) {
    if (!onInput || !imgRef.current) return
    const img = imgRef.current
    const rect = img.getBoundingClientRect()
    const scale = Math.min(rect.width / BROWSER_W, rect.height / BROWSER_H)
    const renderedW = BROWSER_W * scale
    const renderedH = BROWSER_H * scale
    const ox = (rect.width - renderedW) / 2
    const oy = (rect.height - renderedH) / 2
    const bx = Math.round((e.clientX - rect.left - ox) / scale)
    const by = Math.round((e.clientY - rect.top - oy) / scale)
    if (bx >= 0 && bx <= BROWSER_W && by >= 0 && by <= BROWSER_H) {
      onInput({ type: 'input_click', x: bx, y: by })
      imgRef.current.focus()
    }
  }

  function handleKeyDown(e) {
    if (!onInput) return
    e.preventDefault()
    if (e.key.length === 1) {
      onInput({ type: 'input_key', text: e.key })
    } else if (e.key === 'Enter') {
      onInput({ type: 'input_key', text: '\r' })
    } else if (e.key === 'Backspace') {
      onInput({ type: 'input_key', text: '\b' })
    }
  }

  const isHttps = currentUrl?.startsWith('https://')
  const displayUrl = currentUrl || '—'

  return (
    <div className={styles.container}>
      {/* Browser chrome */}
      <div className={styles.chrome}>
        {/* Traffic lights (decorative) */}
        <div className={styles.dots}>
          <span className={styles.dot} style={{background:'#ff5f57'}} />
          <span className={styles.dot} style={{background:'#febc2e'}} />
          <span className={styles.dot} style={{background:'#28c840'}} />
        </div>

        {/* Address bar */}
        <div className={styles.urlBar}>
          {currentUrl ? (
            isHttps
              ? <svg className={styles.lockIcon} width="11" height="11" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="11" width="18" height="11" rx="2" stroke="var(--green)" strokeWidth="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" stroke="var(--green)" strokeWidth="2"/>
                </svg>
              : <svg className={styles.lockIcon} width="11" height="11" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="var(--text-dim)" strokeWidth="2"/>
                  <path d="M12 8v4M12 16h.01" stroke="var(--text-dim)" strokeWidth="2" strokeLinecap="round"/>
                </svg>
          ) : null}
          <span className={styles.urlText} title={currentUrl}>{displayUrl}</span>
        </div>

        {/* Reload button */}
        <button
          className={styles.reloadBtn}
          title="Reload"
          onClick={() => onInput?.({ type: 'input_reload' })}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
            <path d="M1 4v6h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M3.51 15a9 9 0 1 0 .49-5.66L1 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      {/* Page content */}
      <div className={styles.viewport}>
        {frame ? (
          // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
          <img
            ref={imgRef}
            className={`${styles.screen} ${captcha ? styles.captchaActive : ''}`}
            src={`data:image/jpeg;base64,${frame}`}
            alt="Browser view"
            onClick={handleClick}
            onKeyDown={handleKeyDown}
            tabIndex={0}
          />
        ) : (
          <div className={styles.placeholder}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" opacity="0.2">
              <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M8 21h8M12 17v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <span>Waiting for browser…</span>
          </div>
        )}

        {/* Overlays */}
        {captcha && (
          <div className={styles.overlay} data-type="captcha">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            CAPTCHA detected — click on the browser to solve it
          </div>
        )}

        {finalUrl && !captcha && (
          <div className={styles.overlay} data-type="done">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Final URL:&nbsp;
            <a href={finalUrl} target="_blank" rel="noreferrer" className={styles.urlLink}>
              {finalUrl}
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
