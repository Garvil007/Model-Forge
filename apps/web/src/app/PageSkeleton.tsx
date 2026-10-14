import { Skeleton } from '../ui/Skeleton/Skeleton'

export function PageSkeleton() {
  return (
    <div style={{ maxWidth: 1180, margin: '0 auto', padding: 'var(--space-9)' }} aria-busy="true">
      <Skeleton height="2em" width="40%" />
      <div style={{ marginTop: 'var(--space-8)' }}>
        <Skeleton height="1.2em" />
      </div>
      <div style={{ marginTop: 'var(--space-5)' }}>
        <Skeleton height="1.2em" width="80%" />
      </div>
      <div style={{ marginTop: 'var(--space-5)' }}>
        <Skeleton height="1.2em" width="60%" />
      </div>
    </div>
  )
}
