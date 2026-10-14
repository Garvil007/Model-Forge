import { useState } from 'react'
import { Button } from '../ui/Button/Button'
import { useAuth } from './useAuth'

export function GoogleButton({ onSuccess }: { onSuccess: () => void }) {
  const { signInWithGoogle } = useAuth()
  const [loading, setLoading] = useState(false)

  async function handleClick() {
    setLoading(true)
    try {
      await signInWithGoogle()
      onSuccess()
    } finally {
      setLoading(false)
    }
  }

  return (
    <Button type="button" variant="secondary" loading={loading} onClick={handleClick}>
      Continue with Google
    </Button>
  )
}
