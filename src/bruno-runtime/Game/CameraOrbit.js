/** @origin ZUOYIZHUO-SCENE — mouse-only camera input; never writes table state. */
import * as THREE from 'three/webgpu'
import { CAMERA_PRESETS } from './tableAnchors.js'

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

export class CameraOrbit
{
    constructor(game, camera, target)
    {
        this.game = game
        this.camera = camera
        this.target = target
        this.goalTarget = target.clone()
        this.domElement = game.domElement
        this.azimuth = 0.62
        this.elevation = 0.42
        this.radius = CAMERA_PRESETS.overview.radius
        this.goalAzimuth = this.azimuth
        this.goalElevation = this.elevation
        this.goalRadius = this.radius
        this.transition = null
        this.enabled = true
        this.renderElevation = this.elevation
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
        if(!(target instanceof Element)) return false
        if(target.closest('button,a,input,textarea,select,[role="dialog"],[data-ui-interactive]')) return true
        // Product DOM sits above the persistent canvas. Text, cards and status
        // surfaces must never become accidental camera drag targets.
        return Boolean(this.domElement && !this.domElement.contains(target))
    }

    onPointerDown(event)
    {
        if(!this.enabled || event.button !== 0 || this.isUiTarget(event.target)) return
        this.cancelTransition()
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
        if(!this.enabled || this.isUiTarget(event.target)) return
        event.preventDefault()
        this.goalRadius = clamp(this.goalRadius + event.deltaY * 0.008, 7.2, 34)
    }

    update(delta = 0.016)
    {
        if(this.transition)
        {
            this.transition.elapsed += Math.min(delta || 0.016, 0.1) * 1000
            const progress = clamp(this.transition.elapsed / this.transition.duration, 0, 1)
            const eased = progress * progress * (3 - 2 * progress)
            this.target.lerpVectors(this.transition.startTarget, this.transition.target, eased)
            this.azimuth = THREE.MathUtils.lerp(this.transition.startAzimuth, this.transition.azimuth, eased)
            this.elevation = THREE.MathUtils.lerp(this.transition.startElevation, this.transition.elevation, eased)
            this.radius = THREE.MathUtils.lerp(this.transition.startRadius, this.transition.radius, eased)
            if(progress >= 1)
            {
                const resolve = this.transition.resolve
                this.transition = null
                resolve?.()
            }
        }
        else
        {
            this.target.lerp(this.goalTarget ?? this.target, 1 - Math.exp(-8 * Math.min(delta || 0.016, 0.1)))
            const easing = 1 - Math.exp(-7 * Math.min(delta || 0.016, 0.1))
            this.azimuth = THREE.MathUtils.lerp(this.azimuth, this.goalAzimuth, easing)
            this.elevation = THREE.MathUtils.lerp(this.elevation, this.goalElevation, easing)
            this.radius = THREE.MathUtils.lerp(this.radius, this.goalRadius, easing)
        }
        // A fixed user-controlled elevation avoids discontinuous canopy-solver
        // targets when rotating past overlapping crowns.
        const clearElevation = this.elevation
        this.renderElevation = THREE.MathUtils.lerp(this.renderElevation, clearElevation,
            1 - Math.exp(-6 * Math.min(delta || 0.016, 0.1)))
        const horizontal = Math.cos(this.renderElevation) * this.radius
        this.camera.position.set(
            this.target.x + Math.sin(this.azimuth) * horizontal,
            this.target.y + Math.sin(this.renderElevation) * this.radius,
            this.target.z + Math.cos(this.azimuth) * horizontal,
        )
        this.camera.lookAt(this.target)
        this.game.view.spherical.offset.copy(this.camera.position).sub(this.target)
        this.game.view.spherical.radius.current = this.radius
    }


    reset()
    {
        this.goalAzimuth = CAMERA_PRESETS.overview.azimuth
        this.goalElevation = CAMERA_PRESETS.overview.elevation
        this.goalRadius = CAMERA_PRESETS.overview.radius
        this.goalTarget?.copy(this.target)
    }

    setTarget(target)
    {
        this.target.copy(target)
        this.goalTarget = target.clone()
        this.reset()
    }

    focusTable(target, options = {})
    {
        return this.transitionTo(target, options)
    }

    setEnabled(enabled)
    {
        this.enabled = enabled
        if(!enabled)
        {
            this.cancelTransition()
            this.dragging = false
            this.pointerId = null
            this.domElement.classList.remove('is-orbiting')
        }
    }

    transitionTo(target, { azimuth = this.goalAzimuth, elevation = this.goalElevation, radius = this.goalRadius, duration = 1100 } = {})
    {
        this.cancelTransition()
        if(duration <= 0)
        {
            this.target.copy(target)
            this.goalTarget = target.clone()
            this.azimuth = this.goalAzimuth = azimuth
            this.elevation = this.goalElevation = elevation
            this.radius = this.goalRadius = radius
            return Promise.resolve()
        }
        return new Promise((resolve) =>
        {
            this.transition = {
                elapsed: 0,
                duration,
                startTarget: this.target.clone(),
                target: target.clone(),
                startAzimuth: this.azimuth,
                azimuth,
                startElevation: this.elevation,
                elevation,
                startRadius: this.radius,
                radius,
                resolve,
            }
            this.goalTarget = target.clone()
            this.goalAzimuth = azimuth
            this.goalElevation = elevation
            this.goalRadius = radius
        })
    }

    cancelTransition()
    {
        if(!this.transition) return
        const resolve = this.transition.resolve
        this.transition = null
        resolve?.()
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
