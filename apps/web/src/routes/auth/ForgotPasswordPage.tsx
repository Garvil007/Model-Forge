import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import { TextInput } from '../../ui/TextInput/TextInput'
import { AuthApiError } from '../../auth/provider'
import { isPasswordValid } from '../../auth/passwordStrength'
import { useAuth } from '../../auth/useAuth'
import { useToast } from '../../ui/toast/useToast'
import { AuthLayout } from './AuthLayout'
import styles from './AuthLayout.module.css'

export function ForgotPasswordPage() {
  const { forgotPassword, confirmForgotPassword } = useAuth()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [stage, setStage] = useState<'request' | 'reset'>('request')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setFieldError('Enter a valid email address.')
      return
    }
    setFieldError(null)
    setLoading(true)
    try {
      await forgotPassword(email)
      setStage('reset')
    } catch (error) {
      setFormError(error instanceof AuthApiError ? error.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  async function handleReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    if (!/^\d{6}$/.test(code)) {
      setFieldError('Enter the 6-digit code from your email.')
      return
    }
    if (!isPasswordValid(newPassword)) {
      setFieldError('Password must be at least 8 characters.')
      return
    }
    setFieldError(null)
    setLoading(true)
    try {
      await confirmForgotPassword(email, code, newPassword)
      showToast({ message: 'Password reset. Log in with your new password.', variant: 'success' })
      navigate('/login', { replace: true })
    } catch (error) {
      setFormError(error instanceof AuthApiError ? error.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  if (stage === 'reset') {
    return (
      <AuthLayout
        title="Reset your password"
        subtitle={`We sent a code to ${email}.`}
        onSubmit={handleReset}
      >
        {formError && <Notice variant="error">{formError}</Notice>}
        {fieldError && <p className={styles.fieldError}>{fieldError}</p>}
        <TextInput
          label="Verification code"
          inputMode="numeric"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          required
        />
        <TextInput
          label="New password"
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
          autoComplete="new-password"
          help="At least 8 characters"
        />
        <Button type="submit" loading={loading}>
          Reset password
        </Button>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Forgot password"
      subtitle="We'll email you a code to reset it."
      onSubmit={handleRequest}
      footer={<Link to="/login">Back to log in</Link>}
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
      <Button type="submit" loading={loading}>
        Send code
      </Button>
    </AuthLayout>
  )
}
