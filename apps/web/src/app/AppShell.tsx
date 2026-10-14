import { Outlet, useLocation } from 'react-router-dom'
import { Footer } from './Footer/Footer'
import { Header } from './Header/Header'
import styles from './AppShell.module.css'

export function AppShell() {
  const location = useLocation()
  return (
    <>
      <a href="#main-content" className={styles.skipLink}>
        Skip to content
      </a>
      <Header />
      <main id="main-content" className={styles.main} key={location.pathname}>
        <Outlet />
      </main>
      <Footer />
    </>
  )
}
