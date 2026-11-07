import { useNavigate } from 'react-router-dom'
import { useBillingPlans, useCreateCheckoutSession, useUsage } from '../api/hooks'
import { Button } from '../ui/Button/Button'
import { Notice } from '../ui/Notice/Notice'
import { Panel } from '../ui/Panel/Panel'
import { Skeleton } from '../ui/Skeleton/Skeleton'
import styles from './PricingPage.module.css'

function formatPrice(monthlyPriceUsdCents: number): string {
  return monthlyPriceUsdCents === 0 ? '$0' : `$${(monthlyPriceUsdCents / 100).toFixed(0)}/mo`
}

export function PricingPage() {
  const navigate = useNavigate()
  const { data: plans, isLoading, isError } = useBillingPlans()
  const { data: usage } = useUsage()
  const checkout = useCreateCheckoutSession()

  function handlePlanAction(planId: string) {
    if (planId === 'free') {
      navigate('/signup')
      return
    }
    checkout.mutate(undefined, { onSuccess: ({ url }) => (window.location.href = url) })
  }

  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Pricing</h1>
      <p className={styles.subtitle}>Start free. Upgrade when you need GPU methods.</p>

      {isLoading && (
        <div className={styles.grid}>
          <Skeleton height="320px" />
          <Skeleton height="320px" />
        </div>
      )}
      {isError && <Notice variant="error">Couldn't load plans — try again shortly.</Notice>}
      {checkout.isError && (
        <Notice variant="error">Couldn't start checkout — try again shortly.</Notice>
      )}

      {plans && (
        <div className={styles.grid}>
          {plans.map((plan) => {
            const isCurrentPlan = usage?.plan === plan.id
            return (
              <Panel key={plan.id} className={styles.plan}>
                <h2>{plan.name}</h2>
                <p className={styles.price}>{formatPrice(plan.monthlyPriceUsdCents)}</p>
                <p className={styles.tagline}>{plan.tagline}</p>
                <ul className={styles.features}>
                  {plan.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
                <Button
                  disabled={isCurrentPlan}
                  loading={plan.id !== 'free' && checkout.isPending}
                  onClick={() => handlePlanAction(plan.id)}
                >
                  {isCurrentPlan ? 'Current plan' : plan.id === 'free' ? 'Get started' : 'Upgrade'}
                </Button>
              </Panel>
            )
          })}
        </div>
      )}

      <Panel className={styles.workings}>
        <h2>How we priced this</h2>
        <p>
          Every job runs on AWS Spot capacity, so the cost math is real, not a guess — see{' '}
          <code>docs/COSTS.md</code> for the full derivation. The short version, worst case (every
          user maxes out their monthly quota every month):
        </p>
        <table className={styles.workingsTable}>
          <thead>
            <tr>
              <th>Plan</th>
              <th>Infra cost</th>
              <th>Stripe fee</th>
              <th>Total cost</th>
              <th>Margin</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Free</td>
              <td>$0.13/mo</td>
              <td>$0 (no card)</td>
              <td>$0.13/mo</td>
              <td>loss-leader, capped low on purpose</td>
            </tr>
            <tr>
              <td>Pro ($29/mo)</td>
              <td>$1.46/mo</td>
              <td>$1.14/mo</td>
              <td>$2.60/mo</td>
              <td>≈91% ($26.40/mo)</td>
            </tr>
          </tbody>
        </table>
        <p className={styles.workingsNote}>
          Pro stays profitable even if every user saturates CPU and GPU quota every single month —
          in practice most jobs are CPU-only, so real margins run higher than this worst case.
        </p>
      </Panel>
    </div>
  )
}
