import { useRef, type KeyboardEvent } from 'react'
import { cx } from '../cx'
import styles from './Tabs.module.css'

export interface TabItem {
  id: string
  label: string
}

export interface TabsProps {
  tabs: TabItem[]
  activeId: string
  onChange: (id: string) => void
  'aria-label'?: string
}

export function Tabs({ tabs, activeId, onChange, ...rest }: TabsProps) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})

  const focusAndSelect = (id: string) => {
    onChange(id)
    refs.current[id]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.findIndex((t) => t.id === activeId)
    if (event.key === 'ArrowRight') focusAndSelect(tabs[(index + 1) % tabs.length].id)
    else if (event.key === 'ArrowLeft')
      focusAndSelect(tabs[(index - 1 + tabs.length) % tabs.length].id)
    else if (event.key === 'Home') focusAndSelect(tabs[0].id)
    else if (event.key === 'End') focusAndSelect(tabs[tabs.length - 1].id)
    else return
    event.preventDefault()
  }

  return (
    <div className={styles.tabs} role="tablist" onKeyDown={onKeyDown} {...rest}>
      {tabs.map((tab) => {
        const active = tab.id === activeId
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el
            }}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className={cx(styles.tab, active && styles.tabActive)}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
