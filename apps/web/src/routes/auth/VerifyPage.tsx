import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import { TextInput } from '../../ui/TextInput/TextInput'
import { AuthApiError } from '../../auth/provider'
import { useAuth } from '../../auth/useAuth'
import { useToast } from '../../ui/toast/useToast'
import { AuthLayout } from './AuthLayout'
import styles from './AuthLayout.module.css'

export function VerifyPage() {
  const { confirmSignUp, resendConfirmationCode } = useAuth()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [searchParams] = useSearchParams()
  const email = searchParams.get('email') ?? ''
  const [code, setCode] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    if (!/^\d{6}$/.test(code)) {
      setFieldError('Enter the 6-digit code from your email.')
      return
    }
    setFieldError(null)
    setLoading(true)
    try {
      await confirmSignUp(email, code)
      navigate('/app', { replace: true })
    } catch (error) {
      setFormError(error instanceof AuthApiError ? error.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    await resendConfirmationCode(email)
    showToast({ message: 'Sent a new code to ' + email, variant: 'success' })
  }

  return (
    <AuthLayout
      title="Verify your email"
      subtitle={email ? `We sent a code to ${email}.` : 'Enter the code we sent you.'}
      onSubmit={handleSubmit}
      footer={<Button variant="link" onClick={handleResend}>Resend code</Button>}
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
      <Button type="submit" loading={loading}>
        Verify
      </Button>
    </AuthLayout>
  )
}
