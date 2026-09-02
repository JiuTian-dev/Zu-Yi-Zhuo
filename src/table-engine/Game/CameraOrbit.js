import * as THREE from 'three/webgpu'

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

/**
 * A quiet, table-first camera: the pointer changes the viewpoint, never the
 * world. This is the only navigation model used inside a table.
 */
export class CameraOrbit
{
    constructor(game, camera, target)
    {
        this.camera = camera
        this.target = target
        this.azimuth = 0.65
        this.elevation = 0.38
        this.radius = 10.6
        this.goalAzimuth = this.azimuth
        this.goalElevation = this.elevation
        this.goalRadius = this.radius
        this.dragging = false
        this.pointerId = null
        this.lastX = 0
        this.lastY = 0
        this.domElement = game.domElement

        this.onPointerDown = this.onPointerDown.bind(this)
        this.onPointerMove = this.onPointerMove.bind(this)
        this.onPointerUp = this.onPointerUp.bind(this)
        this.onWheel = this.onWheel.bind(this)

        this.domElement?.addEventListener('pointerdown', this.onPointerDown)
        this.domElement?.addEventListener('pointermove', this.onPointerMove)
        this.domElement?.addEventListener('pointerup', this.onPointerUp)
        this.domElement?.addEventListener('pointercancel', this.onPointerUp)
        this.domElement?.addEventListener('wheel', this.onWheel, { passive: false })
    }

    onPointerDown(event)
    {
        if(event.button !== 0 || !this.domElement) return
        this.dragging = true
        this.pointerId = event.pointerId
        this.lastX = event.clientX
        this.lastY = event.clientY
        this.domElement.setPointerCapture?.(event.pointerId)
        this.domElement.classList.add('is-orbiting')
    }

    onPointerMove(event)
    {
        if(!this.dragging || event.pointerId !== this.pointerId) return
        const dx = event.clientX - this.lastX
        const dy = event.clientY - this.lastY
        this.lastX = event.clientX
        this.lastY = event.clientY
        this.goalAzimuth -= dx * 0.006
        this.goalElevation = clamp(this.goalElevation + dy * 0.004, 0.08, 1.08)
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
        event.preventDefault()
        this.goalRadius = clamp(this.goalRadius + event.deltaY * 0.008, 7.8, 15)
    }

    update(delta)
    {
        const easing = 1 - Math.exp(-6 * Math.min(delta || 0.016, 0.1))
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
    }

    destroy()
    {
        this.domElement?.removeEventListener('pointerdown', this.onPointerDown)
        this.domElement?.removeEventListener('pointermove', this.onPointerMove)
        this.domElement?.removeEventListener('pointerup', this.onPointerUp)
        this.domElement?.removeEventListener('pointercancel', this.onPointerUp)
        this.domElement?.removeEventListener('wheel', this.onWheel)
        this.domElement?.classList.remove('is-orbiting')
    }
}
