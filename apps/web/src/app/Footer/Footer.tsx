import { Link } from 'react-router-dom'
import styles from './Footer.module.css'

export function Footer() {
  return (
    <footer className={styles.bar}>
      <div className={styles.inner}>
        <span>© {new Date().getFullYear()} ModelForge</span>
        <nav className={styles.links} aria-label="Footer">
          <Link to="/pricing">Pricing</Link>
          <a href="mailto:support@modelforge.dev">Support</a>
        </nav>
      </div>
    </footer>
  )
}
