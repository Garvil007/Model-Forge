import { Link } from 'react-router-dom'
import { Panel } from '../ui/Panel/Panel'
import styles from './DashboardPage.module.css'

export function DashboardPage() {
  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Your models</h1>
      <Panel>
        <div className={styles.empty}>
          <p>No models yet.</p>
          <Link to="/app">Upload a model</Link>
        </div>
      </Panel>
    </div>
  )
}
