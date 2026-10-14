import { useNavigate } from 'react-router-dom'
import { Button } from '../ui/Button/Button'
import { Panel } from '../ui/Panel/Panel'
import styles from './PricingPage.module.css'

const PLANS = [
  { name: 'Free', price: '$0', features: ['CPU methods', '3 jobs / day', 'Community support'] },
  { name: 'Pro', price: '$29/mo', features: ['GPU methods', 'Unlimited jobs', 'Priority support'] },
  { name: 'Team', price: 'Contact us', features: ['Shared workspaces', 'SSO', 'SLA'] },
]

export function PricingPage() {
  const navigate = useNavigate()
  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Pricing</h1>
      <p className={styles.subtitle}>Start free. Upgrade when you need GPU methods.</p>
      <div className={styles.grid}>
        {PLANS.map((plan) => (
          <Panel key={plan.name} className={styles.plan}>
            <h2>{plan.name}</h2>
            <p className={styles.price}>{plan.price}</p>
            <ul className={styles.features}>
              {plan.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <Button onClick={() => navigate('/signup')}>Get started</Button>
          </Panel>
        ))}
      </div>
    </div>
  )
}
