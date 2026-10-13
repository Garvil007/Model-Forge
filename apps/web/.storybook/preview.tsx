import type { Preview } from '@storybook/react-vite'
import { useEffect, type ReactElement } from 'react'
import '../src/styles/tokens.css'

const VIEWPORTS = {
  desktop: {
    name: 'Desktop 1280',
    styles: { width: '1280px', height: '800px' },
    type: 'desktop' as const,
  },
  mobile: {
    name: 'Mobile 390',
    styles: { width: '390px', height: '844px' },
    type: 'mobile' as const,
  },
}

// eslint-disable-next-line react-refresh/only-export-components -- Storybook config file, not an app component module.
function ThemeDecorator(Story: () => ReactElement, context: { globals: { theme?: string } }) {
  const theme = context.globals.theme ?? 'light'
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    return () => document.documentElement.removeAttribute('data-theme')
  }, [theme])
  return <Story />
}

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    viewport: {
      options: VIEWPORTS,
    },
    backgrounds: { disable: true },
    a11y: {
      test: 'todo',
    },
  },
  globalTypes: {
    theme: {
      name: 'Theme',
      description: 'Light / dark theme',
      defaultValue: 'light',
      toolbar: {
        icon: 'circlehollow',
        items: [
          { value: 'light', title: 'Light' },
          { value: 'dark', title: 'Dark' },
        ],
        dynamicTitle: true,
      },
    },
  },
  decorators: [ThemeDecorator],
}

export default preview
