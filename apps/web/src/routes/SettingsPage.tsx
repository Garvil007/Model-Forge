import { Panel } from '../ui/Panel/Panel'
import { useAuth } from '../auth/useAuth'
import styles from './DashboardPage.module.css'

export function SettingsPage() {
  const { user } = useAuth()
  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Settings</h1>
      <Panel>
        <div className={styles.empty}>
          <p>Signed in as {user?.email}.</p>
          <p>No settings yet — plan and billing controls land in a later milestone.</p>
        </div>
      </Panel>
    </div>
  )
}
