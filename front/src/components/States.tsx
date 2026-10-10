import type { ReactNode } from 'react'
import { ApiError, UnreachableError } from '../api/client'
import { useSource } from '../api/source'

/** Honest progress for slow first calls: what is running and how long it usually takes. */
export function Pending({ title, eta }: { title: string; eta?: string }) {
  return (
    <div className="flex max-w-[560px] flex-col gap-4" role="status">
      <p className="text-body font-normal text-chalk">{title}</p>
      <div className="relative h-[2px] w-full overflow-hidden bg-surface2">
        <div className="absolute inset-y-0 left-0 w-2/5 bg-accent animate-progress" />
      </div>
      {eta && <p className="text-caption font-normal text-neutral1">{eta}</p>}
    </div>
  )
}

/** Nothing was recorded for this request: say so, and say how to get it. */
export function Unrecorded({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex max-w-[620px] flex-col gap-4">
      <p className="text-body font-normal text-chalk">{children}</p>
      <p className="text-caption font-normal text-neutral1">
        Live, the API analyses any pocket of any holder.
      </p>
      {action}
    </div>
  )
}

export function Failure({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { setMode } = useSource()
  const message =
    error instanceof ApiError
      ? `The API answered ${error.status}: ${error.message}`
      : error instanceof UnreachableError
        ? error.message
        : error instanceof Error
          ? error.message
          : 'Unknown error.'
  return (
    <div className="flex max-w-[620px] flex-col gap-4" role="alert">
      <p className="text-body font-normal text-chalk">{message}</p>
      {error instanceof ApiError && error.status === 503 && (
        <p className="text-caption font-normal text-neutral1">
          The backend has no RPC node: set ETH_RPC_URL in the .env file at the root of the repository.
        </p>
      )}
      <div className="flex flex-wrap gap-6">
        {onRetry && (
          <button type="button" onClick={onRetry} className="text-body font-semibold text-accent hover:opacity-80">
            Retry
          </button>
        )}
        <button
          type="button"
          onClick={() => setMode('recorded')}
          className="text-body font-normal text-neutral1 hover:text-chalk"
        >
          Back to the recorded data
        </button>
      </div>
    </div>
  )
}
