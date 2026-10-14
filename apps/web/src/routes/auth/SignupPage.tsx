import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import { TextInput } from '../../ui/TextInput/TextInput'
import { AuthApiError } from '../../auth/provider'
import { GoogleButton } from '../../auth/GoogleButton'
import { isPasswordValid, passwordStrengthLabel } from '../../auth/passwordStrength'
import { useAuth } from '../../auth/useAuth'
import { AuthLayout } from './AuthLayout'
import styles from './AuthLayout.module.css'

export function SignupPage() {
  const { signUp } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setFieldError('Enter a valid email address.')
      return
    }
    if (!isPasswordValid(password)) {
      setFieldError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirmPassword) {
      setFieldError('Passwords do not match.')
      return
    }
    setFieldError(null)
    setLoading(true)
    try {
      await signUp(email, password)
      navigate(`/verify?email=${encodeURIComponent(email)}`)
    } catch (error) {
      setFormError(error instanceof AuthApiError ? error.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Sign up"
      onSubmit={handleSubmit}
      footer={
        <>
          Already have an account? <Link to="/login">Log in</Link>
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
        autoComplete="new-password"
        help={password ? `Strength: ${passwordStrengthLabel(password)}` : 'At least 8 characters'}
      />
      <TextInput
        label="Confirm password"
        type="password"
        value={confirmPassword}
        onChange={(e) => setConfirmPassword(e.target.value)}
        required
        autoComplete="new-password"
      />
      <Button type="submit" loading={loading}>
        Create account
      </Button>
      <GoogleButton onSuccess={() => navigate('/app')} />
    </AuthLayout>
  )
}
