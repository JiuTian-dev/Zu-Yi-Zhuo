/** @origin ZUOYIZHUO-SCENE — mouse-only camera input; never writes table state. */
import * as THREE from 'three/webgpu'

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

export class CameraOrbit
{
    constructor(game, camera, target)
    {
        this.game = game
        this.camera = camera
        this.target = target
        this.domElement = game.domElement
        this.azimuth = 0.62
        this.elevation = 0.42
        this.radius = 12.8
        this.goalAzimuth = this.azimuth
        this.goalElevation = this.elevation
        this.goalRadius = this.radius
        this.dragging = false
        this.pointerId = null
        this.lastX = 0
        this.lastY = 0

        this.onPointerDown = this.onPointerDown.bind(this)
        this.onPointerMove = this.onPointerMove.bind(this)
        this.onPointerUp = this.onPointerUp.bind(this)
        this.onWheel = this.onWheel.bind(this)
        this.onTick = () => this.update(this.game.ticker.delta)
        this.domElement?.addEventListener('pointerdown', this.onPointerDown)
        this.domElement?.addEventListener('pointermove', this.onPointerMove, { passive: false })
        this.domElement?.addEventListener('pointerup', this.onPointerUp)
        this.domElement?.addEventListener('pointercancel', this.onPointerUp)
        this.domElement?.addEventListener('wheel', this.onWheel, { passive: false })
        this.game.ticker.events.on('tick', this.onTick, 5)
    }

    isUiTarget(target)
    {
        return target instanceof Element && !!target.closest('button,a,input,textarea,select,[role="dialog"],[data-ui-interactive]')
    }

    onPointerDown(event)
    {
        if(event.button !== 0 || this.isUiTarget(event.target)) return
        this.dragging = true
        this.pointerId = event.pointerId
        this.lastX = event.clientX
        this.lastY = event.clientY
        this.domElement?.setPointerCapture?.(event.pointerId)
        this.domElement?.classList.add('is-orbiting')
    }

    onPointerMove(event)
    {
        if(!this.dragging || event.pointerId !== this.pointerId) return
        const dx = event.clientX - this.lastX
        const dy = event.clientY - this.lastY
        this.lastX = event.clientX
        this.lastY = event.clientY
        this.goalAzimuth -= dx * 0.006
        this.goalElevation = clamp(this.goalElevation + dy * 0.004, 0.12, 1.04)
        event.preventDefault()
    }

    onPointerUp(event)
    {
        if(this.pointerId !== null && event.pointerId !== this.pointerId) return
        this.dragging = false
        this.pointerId = null
        this.domElement?.classList.remove('is-orbiting')
    }

    onWheel(event)
    {
        if(this.isUiTarget(event.target)) return
        event.preventDefault()
        this.goalRadius = clamp(this.goalRadius + event.deltaY * 0.008, 7.2, 20)
    }

    update(delta = 0.016)
    {
        const easing = 1 - Math.exp(-7 * Math.min(delta || 0.016, 0.1))
        this.azimuth = THREE.MathUtils.lerp(this.azimuth, this.goalAzimuth, easing)
        this.elevation = THREE.MathUtils.lerp(this.elevation, this.goalElevation, easing)
        this.radius = THREE.MathUtils.lerp(this.radius, this.goalRadius, easing)
        const horizontal = Math.cos(this.elevation) * this.radius
        this.camera.position.set(
            this.target.x + Math.sin(this.azimuth) * horizontal,
            this.target.y + Math.sin(this.elevation) * this.radius,
            this.target.z + Math.cos(this.azimuth) * horizontal,
        )
        this.camera.lookAt(this.target)
        this.game.view.spherical.offset.copy(this.camera.position).sub(this.target)
        this.game.view.spherical.radius.current = this.radius
    }

    reset()
    {
        this.goalAzimuth = 0.62
        this.goalElevation = 0.42
        this.goalRadius = 12.8
    }

    setTarget(target)
    {
        this.target.copy(target)
        this.reset()
    }

    destroy()
    {
        this.game.ticker?.events?.off?.('tick', this.onTick)
        this.domElement?.removeEventListener('pointerdown', this.onPointerDown)
        this.domElement?.removeEventListener('pointermove', this.onPointerMove)
        this.domElement?.removeEventListener('pointerup', this.onPointerUp)
        this.domElement?.removeEventListener('pointercancel', this.onPointerUp)
        this.domElement?.removeEventListener('wheel', this.onWheel)
        this.domElement?.classList.remove('is-orbiting')
    }
}
