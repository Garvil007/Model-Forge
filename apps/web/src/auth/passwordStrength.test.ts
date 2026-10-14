import { describe, expect, it } from 'vitest'
import { isPasswordValid, passwordStrengthLabel } from './passwordStrength'

describe('passwordStrengthLabel', () => {
  it('rates short simple passwords as weak', () => {
    expect(passwordStrengthLabel('abc')).toBe('weak')
  })

  it('rates a long mixed-case alphanumeric-plus-symbol password as strong', () => {
    expect(passwordStrengthLabel('Str0ng!Password')).toBe('strong')
  })
})

describe('isPasswordValid', () => {
  it('rejects passwords shorter than 8 characters', () => {
    expect(isPasswordValid('short1')).toBe(false)
  })

  it('accepts an 8+ character password', () => {
    expect(isPasswordValid('longenough')).toBe(true)
  })
})
