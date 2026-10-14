import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppShell } from './app/AppShell'
import { PageSkeleton } from './app/PageSkeleton'
import { RouteGuard } from './auth/RouteGuard'

const LandingPage = lazy(() => import('./routes/LandingPage').then((m) => ({ default: m.LandingPage })))
const ToolPage = lazy(() => import('./routes/ToolPage').then((m) => ({ default: m.ToolPage })))
const PricingPage = lazy(() => import('./routes/PricingPage').then((m) => ({ default: m.PricingPage })))
const DashboardPage = lazy(() =>
  import('./routes/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const SettingsPage = lazy(() =>
  import('./routes/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const NotFoundPage = lazy(() =>
  import('./routes/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
)
const LoginPage = lazy(() => import('./routes/auth/LoginPage').then((m) => ({ default: m.LoginPage })))
const SignupPage = lazy(() =>
  import('./routes/auth/SignupPage').then((m) => ({ default: m.SignupPage })),
)
const VerifyPage = lazy(() =>
  import('./routes/auth/VerifyPage').then((m) => ({ default: m.VerifyPage })),
)
const ForgotPasswordPage = lazy(() =>
  import('./routes/auth/ForgotPasswordPage').then((m) => ({ default: m.ForgotPasswordPage })),
)

function App() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<LandingPage />} />
          <Route
            path="/app"
            element={
              <RouteGuard>
                <ToolPage />
              </RouteGuard>
            }
          />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/verify" element={<VerifyPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route
            path="/dashboard"
            element={
              <RouteGuard>
                <DashboardPage />
              </RouteGuard>
            }
          />
          <Route
            path="/settings"
            element={
              <RouteGuard>
                <SettingsPage />
              </RouteGuard>
            }
          />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default App
