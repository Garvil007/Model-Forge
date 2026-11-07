import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useClearHfToken,
  useDeleteAccount,
  useSetHfToken,
  useSettings,
  useUpdateNotifications,
  useUsage,
} from '../api/hooks'
import { useAuth } from '../auth/useAuth'
import { Button } from '../ui/Button/Button'
import { Notice } from '../ui/Notice/Notice'
import { Panel } from '../ui/Panel/Panel'
import { TextInput } from '../ui/TextInput/TextInput'
import { Toggle } from '../ui/Toggle/Toggle'
import { useToast } from '../ui/toast/useToast'
import styles from './DashboardPage.module.css'
import settingsStyles from './SettingsPage.module.css'

const DELETE_CONFIRM_WORD = 'DELETE'

export function SettingsPage() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const { data: usage } = useUsage()
  const { data: settings, isLoading: settingsLoading, isError: settingsError } = useSettings()
  const updateNotifications = useUpdateNotifications()
  const setHfToken = useSetHfToken()
  const clearHfToken = useClearHfToken()
  const deleteAccount = useDeleteAccount()

  const [hfTokenInput, setHfTokenInput] = useState('')
  const [deleteConfirmText, setDeleteConfirmText] = useState('')

  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Settings</h1>

      <Panel className={settingsStyles.section}>
        <h2 className={settingsStyles.heading}>Profile</h2>
        <p>Signed in as {user?.email}.</p>
        {usage && <p className={settingsStyles.plan}>Plan: {usage.plan}</p>}
      </Panel>

      <Panel className={settingsStyles.section}>
        <h2 className={settingsStyles.heading}>Notifications</h2>
        {settingsLoading && <p>Loading…</p>}
        {settingsError && <Notice variant="error">Couldn't load your notification settings.</Notice>}
        {settings && (
          <div className={settingsStyles.toggles}>
            <Toggle
              label="Email me when a job finishes"
              checked={settings.notifications.jobCompleteEmail}
              onChange={(e) =>
                updateNotifications.mutate({
                  ...settings.notifications,
                  jobCompleteEmail: e.target.checked,
                })
              }
            />
            <Toggle
              label="Weekly usage digest"
              checked={settings.notifications.weeklyDigestEmail}
              onChange={(e) =>
                updateNotifications.mutate({
                  ...settings.notifications,
                  weeklyDigestEmail: e.target.checked,
                })
              }
            />
          </div>
        )}
      </Panel>

      <Panel className={settingsStyles.section}>
        <h2 className={settingsStyles.heading}>Hugging Face token</h2>
        <p className={settingsStyles.note}>
          Used to import gated repositories. {settings?.hasHfToken ? 'A token is on file.' : 'No token on file.'}
        </p>
        <div className={settingsStyles.hfRow}>
          <TextInput
            label="Access token"
            type="password"
            value={hfTokenInput}
            onChange={(e) => setHfTokenInput(e.target.value)}
            placeholder="hf_..."
          />
          <Button
            loading={setHfToken.isPending}
            disabled={!hfTokenInput}
            onClick={() =>
              setHfToken.mutate(hfTokenInput, {
                onSuccess: () => {
                  setHfTokenInput('')
                  showToast({ message: 'Hugging Face token saved.', variant: 'success' })
                },
              })
            }
          >
            Save
          </Button>
          {settings?.hasHfToken && (
            <Button
              variant="secondary"
              loading={clearHfToken.isPending}
              onClick={() =>
                clearHfToken.mutate(undefined, {
                  onSuccess: () => showToast({ message: 'Hugging Face token removed.' }),
                })
              }
            >
              Remove
            </Button>
          )}
        </div>
      </Panel>

      <Panel className={settingsStyles.section}>
        <h2 className={settingsStyles.heading}>Delete account</h2>
        <Notice variant="warning">
          This permanently deletes every model, job and result you own — all S3 objects and
          DynamoDB items — and cannot be undone.
        </Notice>
        <TextInput
          label={`Type ${DELETE_CONFIRM_WORD} to confirm`}
          value={deleteConfirmText}
          onChange={(e) => setDeleteConfirmText(e.target.value)}
        />
        <Button
          variant="secondary"
          className={settingsStyles.dangerButton}
          disabled={deleteConfirmText !== DELETE_CONFIRM_WORD}
          loading={deleteAccount.isPending}
          onClick={() =>
            deleteAccount.mutate(undefined, {
              onSuccess: async () => {
                await signOut()
                navigate('/')
              },
            })
          }
        >
          Delete my account
        </Button>
        {deleteAccount.isError && (
          <Notice variant="error">Couldn't delete your account. Try again.</Notice>
        )}
      </Panel>
    </div>
  )
}
