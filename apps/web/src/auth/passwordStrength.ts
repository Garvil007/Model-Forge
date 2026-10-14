export type PasswordStrength = 'weak' | 'fair' | 'good' | 'strong'

export function scorePassword(password: string): number {
  let score = 0
  if (password.length >= 8) score += 1
  if (password.length >= 12) score += 1
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1
  if (/\d/.test(password)) score += 1
  if (/[^a-zA-Z0-9]/.test(password)) score += 1
  return Math.min(score, 4)
}

const LABELS: Record<number, PasswordStrength> = {
  0: 'weak',
  1: 'weak',
  2: 'fair',
  3: 'good',
  4: 'strong',
}

export function passwordStrengthLabel(password: string): PasswordStrength {
  return LABELS[scorePassword(password)]
}

export function isPasswordValid(password: string): boolean {
  return password.length >= 8
}
