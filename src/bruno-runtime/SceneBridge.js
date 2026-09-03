/** @origin ZUOYIZHUO-SCENE — backend projection into the single Bruno runtime. */
import { CAMERA_PRESETS } from './Game/tableAnchors.js'

export class SceneBridge
{
    constructor(game)
    {
        this.game = game
    }

    apply({ tableState = null, hostAction = null, speakingId = null, closeState = 'idle', viewerId = null } = {})
    {
        const tableMeeting = this.game.world?.tableMeeting
        if(!tableMeeting) return

        tableMeeting.setTableState?.(tableState, speakingId, viewerId)
        tableMeeting.setHostAction?.(hostAction, closeState)
    }

    transitionToTable({ mode = 'overview', reducedMotion = false } = {})
    {
        const target = this.game.world?.tableMeeting?.getFocusTarget?.()
        if(!target) return Promise.resolve()
        const preset = CAMERA_PRESETS[mode] ?? CAMERA_PRESETS.overview
        return this.game.cameraOrbit.transitionTo(target, {
            ...preset,
            duration: reducedMotion ? 1 : mode === 'approach' ? 1450 : 900,
        })
    }

    projectAnchor(anchorId)
    {
        const tableMeeting = this.game.world?.tableMeeting
        if(!tableMeeting || !this.game.viewport) return null
        const point = tableMeeting.getAnchorWorld?.(anchorId)
        if(!point) return null
        this.game.view.camera.updateMatrixWorld()
        const projected = point.project(this.game.view.camera)
        return {
            x: (projected.x * 0.5 + 0.5) * this.game.viewport.width,
            y: (-projected.y * 0.5 + 0.5) * this.game.viewport.height,
            visible: projected.z > -1 && projected.z < 1 && projected.x > -1.15 && projected.x < 1.15 && projected.y > -1.15 && projected.y < 1.15,
        }
    }

    destroy()
    {
        this.game = null
    }
}
