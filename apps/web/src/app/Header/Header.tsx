import { NavLink } from 'react-router-dom'
import { ThemeToggle } from '../../ui/theme/ThemeToggle'
import { AccountMenu } from './AccountMenu'
import styles from './Header.module.css'

const NAV_LINKS = [
  { to: '/app', label: 'Tool' },
  { to: '/pricing', label: 'Pricing' },
]

export function Header() {
  return (
    <header className={styles.bar}>
      <div className={styles.inner}>
        <NavLink to="/" className={styles.logo}>
          ModelForge
        </NavLink>
        <nav className={styles.nav} aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                isActive ? `${styles.navLink} ${styles.navLinkActive}` : styles.navLink
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className={styles.right}>
          <ThemeToggle />
          <AccountMenu />
        </div>
      </div>
    </header>
  )
}
