export const PASSWORD_REQUIREMENTS = 'Use at least 8 characters, including an uppercase letter (A-Z), a digit (0-9), and a special character (e.g. !@#$%).'

// ASCII punctuation, matching Python's string.punctuation on the backend.
const SPECIAL_CHARACTERS = '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'

export function validateRegistrationPassword(password: string): string | undefined {
  if (
    Array.from(password).length < 8 ||
    !/[A-Z]/.test(password) ||
    !/[0-9]/.test(password) ||
    !Array.from(password).some(char => SPECIAL_CHARACTERS.includes(char))
  ) return PASSWORD_REQUIREMENTS
  if (new TextEncoder().encode(password).length > 72) return 'Password must not exceed 72 UTF-8 bytes.'
  return undefined
}
