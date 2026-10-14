import { useState } from 'react'
import { useImportHf } from '../../api/hooks'
import { ApiError } from '../../api/client'
import type { ApiModel } from '../../api/types'
import { Button } from '../../ui/Button/Button'
import { Notice } from '../../ui/Notice/Notice'
import { TextInput } from '../../ui/TextInput/TextInput'
import styles from './HfImportForm.module.css'

const REPO_ID_PATTERN = /^[\w.-]+\/[\w.-]+$/

export interface HfImportFormProps {
  onImported: (model: ApiModel) => void
}

/** The dropzone's second tab (prototype doesn't have this — it's new for the real backend): a
 * repo id input with inline format validation, an optional access token for gated repos, and a
 * clear error when the repo is gated and no token (or the wrong one) was given. */
export function HfImportForm({ onImported }: HfImportFormProps) {
  const [repoId, setRepoId] = useState('')
  const [token, setToken] = useState('')
  const [touched, setTouched] = useState(false)
  const importHf = useImportHf()

  const repoIdValid = REPO_ID_PATTERN.test(repoId)
  const showFormatError = touched && repoId.length > 0 && !repoIdValid

  const gated = importHf.error instanceof ApiError && importHf.error.code === 'gated_repo'
  const notFound = importHf.error instanceof ApiError && importHf.error.code === 'repo_not_found'

  const handleSubmit = () => {
    setTouched(true)
    if (!repoIdValid) return
    importHf.mutate(
      { repoId, token: token || undefined },
      { onSuccess: (model) => onImported(model) },
    )
  }

  return (
    <div className={styles.form}>
      <TextInput
        label="Hugging Face repo id"
        placeholder="owner/model-name"
        value={repoId}
        onChange={(e) => setRepoId(e.target.value)}
        onBlur={() => setTouched(true)}
        help={showFormatError ? undefined : 'e.g. microsoft/resnet-50'}
        aria-invalid={showFormatError || undefined}
      />
      {showFormatError && (
        <Notice variant="error">
          That doesn't look like a repo id — it should be "owner/model-name".
        </Notice>
      )}

      <TextInput
        label="Access token (optional)"
        type="password"
        placeholder="hf_..."
        value={token}
        onChange={(e) => setToken(e.target.value)}
        help="Only needed for gated or private repositories."
      />

      {gated && (
        <Notice variant="error">
          This repository is gated. Provide an access token with permission to use it.
        </Notice>
      )}
      {notFound && (
        <Notice variant="error">No repository "{repoId}" was found on Hugging Face.</Notice>
      )}

      <Button loading={importHf.isPending} onClick={handleSubmit}>
        Import from Hugging Face
      </Button>
    </div>
  )
}
