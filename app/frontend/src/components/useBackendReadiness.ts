import { useSyncExternalStore } from 'react'
import { getBackendState, subscribeBackend } from '@/services/requests'

export function useBackendReadiness() {
  return useSyncExternalStore(subscribeBackend, getBackendState, getBackendState)
}
