import * as THREE from 'three/webgpu'
import { Game } from './Game.js'
import { Events } from './Events.js'

export class View
{
    constructor()
    {
        this.game = Game.getInstance()
        this.events = new Events()

        const aspect = (this.game.viewport.width || 16) / (this.game.viewport.height || 9)

        this.camera = new THREE.PerspectiveCamera(38, aspect, 0.1, 160)
        this.camera.position.set(7.5, 4.6, 9.5)

        // Focused area the lighting/shadows/fog systems orbit around
        this.focusPoint = {
            position: new THREE.Vector3(0, 0.4, 0),
            trackedPosition: new THREE.Vector3(0, 0.4, 0),
            smoothedPosition: new THREE.Vector3(0, 0.4, 0),
        }

        this.optimalArea = {
            needsUpdate: false,
            radius: 6.5,
            nearDistance: 9,
            farDistance: 30,
            position: this.focusPoint.position,
        }

        this.time = 0
        this.game.ticker.events.on('tick', () => { this.update() }, 900)
        this.events.trigger('change')
    }

    update()
    {
        this.time += this.game.ticker.delta
        // Gentle breathing around the table (Bruno-style focus area drift)
        const t = this.time
        this.focusPoint.position.set(
            Math.sin(t * 0.1) * 0.35,
            0.4 + Math.sin(t * 0.16) * 0.06,
            Math.cos(t * 0.08) * 0.35,
        )
        this.camera.position.x = THREE.MathUtils.damp(this.camera.position.x, 7.5 + Math.sin(t * 0.07) * 0.8, 2, this.game.ticker.delta)
        this.camera.position.y = THREE.MathUtils.damp(this.camera.position.y, 4.6 + Math.sin(t * 0.1) * 0.2, 2, this.game.ticker.delta)
        this.camera.position.z = THREE.MathUtils.damp(this.camera.position.z, 9.5 + Math.cos(t * 0.06) * 0.6, 2, this.game.ticker.delta)
        this.camera.lookAt(this.focusPoint.position)
    }
}
