import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import { TextInput } from '../../ui/TextInput/TextInput'
import { AuthApiError } from '../../auth/provider'
import { GoogleButton } from '../../auth/GoogleButton'
import { useAuth } from '../../auth/useAuth'
import { AuthLayout } from './AuthLayout'
import styles from './AuthLayout.module.css'

export function LoginPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const from = (location.state as { from?: Location })?.from?.pathname ?? '/app'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setFieldError('Enter a valid email address.')
      return
    }
    if (!password) {
      setFieldError('Enter your password.')
      return
    }
    setFieldError(null)
    setLoading(true)
    try {
      await signIn(email, password)
      navigate(from, { replace: true })
    } catch (error) {
      setFormError(error instanceof AuthApiError ? error.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Log in"
      onSubmit={handleSubmit}
      footer={
        <>
          No account? <Link to="/signup">Sign up</Link> · <Link to="/forgot-password">Forgot password?</Link>
        </>
      }
    >
      {formError && <Notice variant="error">{formError}</Notice>}
      {fieldError && <p className={styles.fieldError}>{fieldError}</p>}
      <TextInput
        label="Email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        autoComplete="email"
      />
      <TextInput
        label="Password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        autoComplete="current-password"
      />
      <Button type="submit" loading={loading}>
        Log in
      </Button>
      <GoogleButton onSuccess={() => navigate(from, { replace: true })} />
    </AuthLayout>
  )
}
