import { Link } from 'react-router-dom'
import styles from './DashboardPage.module.css'

export function NotFoundPage() {
  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Page not found</h1>
      <p>
        <Link to="/">Back to home</Link>
      </p>
    </div>
  )
}
