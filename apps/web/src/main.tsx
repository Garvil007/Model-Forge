import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { createQueryClient } from './api/queryClient.ts'
import App from './App.tsx'
import { ErrorBoundary } from './app/ErrorBoundary.tsx'
import { AuthProvider } from './auth/AuthProvider.tsx'
import { ThemeProvider } from './ui/theme/ThemeProvider.tsx'
import { ToastProvider } from './ui/toast/ToastProvider.tsx'
import './styles/tokens.css'

const queryClient = createQueryClient()

async function enableMocking(): Promise<void> {
  if (import.meta.env.VITE_USE_MOCKS !== 'true') return
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledFrame: 'bypass' })
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ToastProvider>
              <BrowserRouter>
                <AuthProvider>
                  <App />
                </AuthProvider>
              </BrowserRouter>
            </ToastProvider>
          </ThemeProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </StrictMode>,
  )
})
