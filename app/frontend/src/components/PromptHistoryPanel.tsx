import { getCookie } from '../utils/cookies'

export default function PromptHistoryPanel({
  open
}: {
  open: boolean
}) {
  const userId = getCookie('user_id')

  return (
    <div className={`drawer ${open ? 'open' : ''}`}>
      <div className="drawer-inner">
        {userId ? (
          <div>History coming soon</div>
        ) : (
          <div className="muted">Available only for authorized users</div>
        )}
      </div>
    </div>
  )
}
