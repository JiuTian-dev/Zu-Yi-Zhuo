/** @origin ZUOYIZHUO-SCENE — React lifecycle bridge for the single Bruno runtime. */

type RuntimeLike = {
  sceneBridge?: {
    transitionToTable?: (options?: { mode?: 'overview' | 'approach'; reducedMotion?: boolean }) => Promise<void>
    projectAnchor?: (anchorId: string) => { x: number; y: number; visible: boolean } | null
    apply?: (projection: unknown) => void
    setDayCycleMode?: (mode: DayCycleMode) => void
  }
  cameraOrbit?: { setEnabled?: (enabled: boolean) => void }
}

export type DayCycleMode = 'auto' | 'day' | 'night'

let runtime: RuntimeLike | null = null
let pendingTransition: {
  options: { mode?: 'overview' | 'approach'; reducedMotion?: boolean }
  resolve: () => void
} | null = null
const listeners = new Set<() => void>()
let pendingDayCycleMode: DayCycleMode = 'auto'

export function attachRuntime(next: RuntimeLike) {
  runtime = next
  runtime.sceneBridge?.setDayCycleMode?.(pendingDayCycleMode)
  listeners.forEach((listener) => listener())
  if (pendingTransition) {
    const pending = pendingTransition
    pendingTransition = null
    const transition = next.sceneBridge?.transitionToTable?.(pending.options)
    if (transition && typeof transition.then === 'function') {
      void transition.then(pending.resolve)
    } else {
      pending.resolve()
    }
  }
}

export function detachRuntime(next: RuntimeLike) {
  if (runtime !== next) return
  runtime = null
  pendingTransition?.resolve()
  pendingTransition = null
  listeners.forEach((listener) => listener())
}

export function subscribeRuntime(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function transitionTableCamera(options: { mode?: 'overview' | 'approach'; reducedMotion?: boolean } = {}) {
  if (runtime?.sceneBridge?.transitionToTable) return runtime.sceneBridge.transitionToTable(options)
  return new Promise<void>((resolve) => {
    // A rapid sequence of navigation actions should never leave the first
    // caller waiting forever while the runtime is still attaching.
    pendingTransition?.resolve()
    pendingTransition = { options, resolve }
  })
}

export function projectTableAnchor(anchorId: string) {
  return runtime?.sceneBridge?.projectAnchor?.(anchorId) ?? null
}

export function setRuntimeInteraction(enabled: boolean) {
  runtime?.cameraOrbit?.setEnabled?.(enabled)
}

export function setDayCycleMode(mode: DayCycleMode) {
  pendingDayCycleMode = mode
  runtime?.sceneBridge?.setDayCycleMode?.(mode)
}
