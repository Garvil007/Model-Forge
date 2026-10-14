import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '../ui/Button/Button'
import styles from './ErrorBoundary.module.css'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info.componentStack)
  }

  handleReload = () => {
    this.setState({ error: null })
    window.location.assign('/')
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <main className={styles.wrap}>
        <h1 className={styles.title}>Something went wrong</h1>
        <p className={styles.message}>
          ModelForge hit an unexpected error. Your work in progress may be unsaved. Try reloading —
          if this keeps happening, let us know what you were doing.
        </p>
        <Button onClick={this.handleReload}>Back to home</Button>
        <details className={styles.details}>
          <summary>Technical details</summary>
          <pre>{error.message}</pre>
        </details>
      </main>
    )
  }
}
