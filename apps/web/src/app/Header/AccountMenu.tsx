import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../../ui/Button/Button'
import { useAuth } from '../../auth/useAuth'
import styles from './AccountMenu.module.css'

export function AccountMenu() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (!user) {
    return (
      <Link to="/login" className={styles.item}>
        Log in
      </Link>
    )
  }

  async function handleSignOut() {
    setOpen(false)
    await signOut()
    navigate('/')
  }

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <button
        type="button"
        className={styles.trigger}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {user.email}
      </button>
      {open && (
        <div className={styles.menu} role="menu">
          <Link className={styles.item} role="menuitem" to="/dashboard" onClick={() => setOpen(false)}>
            Dashboard
          </Link>
          <Link className={styles.item} role="menuitem" to="/settings" onClick={() => setOpen(false)}>
            Settings
          </Link>
          <Button variant="link" role="menuitem" className={styles.item} onClick={handleSignOut}>
            Log out
          </Button>
        </div>
      )}
    </div>
  )
}
