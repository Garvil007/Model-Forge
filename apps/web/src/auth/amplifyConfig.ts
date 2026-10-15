import { Amplify } from 'aws-amplify'

let configured = false

/** Configures Amplify from Vite env vars — see .env.example for what each one is and where
 * `cdk deploy` prints the value (infra/stacks/auth_stack.py's CfnOutputs). Idempotent: Amplify
 * itself isn't, so this provider only ever calls it once per page load. */
export function configureAmplify(): void {
  if (configured) return
  configured = true

  const redirectSignIn = import.meta.env.VITE_COGNITO_REDIRECT_SIGN_IN ?? 'http://localhost:5173/'
  const redirectSignOut =
    import.meta.env.VITE_COGNITO_REDIRECT_SIGN_OUT ?? 'http://localhost:5173/login'

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID ?? '',
        userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID ?? '',
        loginWith: {
          oauth: {
            domain: import.meta.env.VITE_COGNITO_DOMAIN ?? '',
            scopes: ['openid', 'email', 'profile'],
            redirectSignIn: [redirectSignIn],
            redirectSignOut: [redirectSignOut],
            responseType: 'code',
          },
        },
      },
    },
  })
}
