import { useState, type DragEvent, type InputHTMLAttributes } from 'react'
import { cx } from '../cx'
import styles from './FileInput.module.css'

export interface DropZoneProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  title: string
  hint?: string
}

export function DropZone({ title, hint, onDragOver, onDragLeave, onDrop, ...rest }: DropZoneProps) {
  const [over, setOver] = useState(false)

  return (
    <label
      className={cx(styles.drop, over && styles.dropOver)}
      onDragOver={(event: DragEvent<HTMLLabelElement>) => {
        event.preventDefault()
        setOver(true)
        onDragOver?.(event as unknown as DragEvent<HTMLInputElement>)
      }}
      onDragLeave={(event: DragEvent<HTMLLabelElement>) => {
        setOver(false)
        onDragLeave?.(event as unknown as DragEvent<HTMLInputElement>)
      }}
      onDrop={(event: DragEvent<HTMLLabelElement>) => {
        setOver(false)
        onDrop?.(event as unknown as DragEvent<HTMLInputElement>)
      }}
    >
      <strong className={styles.dropStrong}>{title}</strong>
      {hint}
      <input type="file" className={styles.hiddenInput} {...rest} />
    </label>
  )
}

export interface FileInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
  help?: string
  required?: boolean
}

export function FileInput({ label, help, required, id, ...rest }: FileInputProps) {
  const inputId = id ?? `file-${label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <label className={styles.field} htmlFor={inputId}>
      {label}
      {required ? ' (required)' : ''}
      <input id={inputId} type="file" className={styles.plainInput} {...rest} />
      {help && <small className={styles.help}>{help}</small>}
    </label>
  )
}
