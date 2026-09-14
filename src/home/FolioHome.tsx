import { useCallback, useEffect, useRef } from 'react'
import AccountMenu from './AccountMenu'
import FriendsDock from './FriendsDock'
import { fetchDiscovery } from '../live/api'
import './folioHome.css'

const FOLIO_HOME_URL = import.meta.env.VITE_FOLIO_HOME_URL ?? 'http://127.0.0.1:5175/'

interface FolioHomeProps {
  onOpenProfile(): void
  onEnterMatch(): void
  onOpenLogin(): void
  onPreciseMatch(): void
  onHostTable(): void
  onOpenTable(tableId: string): void
}

type DiscoveryPayload = {
  type: 'zuoyizhuo:discovery'
  status: 'loading' | 'ready' | 'error'
  items?: Array<{
    table_id: string
    core_question: string
    participant_count: number
    available_seats: number
    status?: string
  }>
  message?: string
}

/**
 * PRODUCT HOME — folio intro + world (original click animation).
 * Map button opens Folio map modal (same animation); embed content is match/host UI.
 */
export default function FolioHome({
  onOpenProfile,
  onEnterMatch,
  onOpenLogin,
  onPreciseMatch,
  onHostTable,
  onOpenTable,
}: FolioHomeProps) {
  const frameRef = useRef<HTMLIFrameElement>(null)

  const postToFolio = useCallback((payload: DiscoveryPayload) => {
    frameRef.current?.contentWindow?.postMessage(payload, '*')
  }, [])

  const pushDiscovery = useCallback(async () => {
    postToFolio({ type: 'zuoyizhuo:discovery', status: 'loading', items: [] })
    try {
      const items = await fetchDiscovery()
      postToFolio({
        type: 'zuoyizhuo:discovery',
        status: 'ready',
        items: items.map((item) => ({
          table_id: item.table_id,
          core_question: item.core_question,
          participant_count: item.participant_count,
          available_seats: item.available_seats,
          status: item.status,
        })),
      })
    } catch (error) {
      postToFolio({
        type: 'zuoyizhuo:discovery',
        status: 'error',
        items: [],
        message: error instanceof Error ? error.message : '后端暂时不可用',
      })
    }
  }, [postToFolio])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || typeof data !== 'object') return

      if (data.type === 'zuoyizhuo:enter-match') {
        onEnterMatch()
        return
      }
      if (data.type === 'zuoyizhuo:request-discovery') {
        void pushDiscovery()
        return
      }
      if (data.type === 'zuoyizhuo:precise-match') {
        onPreciseMatch()
        return
      }
      if (data.type === 'zuoyizhuo:host-table') {
        onHostTable()
        return
      }
      if (data.type === 'zuoyizhuo:enter-table' && typeof data.tableId === 'string' && data.tableId) {
        onOpenTable(data.tableId)
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [onEnterMatch, onHostTable, onOpenTable, onPreciseMatch, pushDiscovery])

  return (
    <main className="folio-home" aria-label="组一桌首页">
      <iframe
        ref={frameRef}
        className="folio-home-frame"
        title="首页世界"
        src={FOLIO_HOME_URL}
        allow="autoplay; fullscreen; gamepad"
      />

      <header className="folio-home-chrome">
        <p className="folio-home-brand">组一桌</p>
        <AccountMenu onOpenProfile={onOpenProfile} onOpenLogin={onOpenLogin} />
      </header>

      <FriendsDock />
    </main>
  )
}
