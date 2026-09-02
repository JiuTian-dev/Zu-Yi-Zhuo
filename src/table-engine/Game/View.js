import * as THREE from 'three/webgpu'
import { Game } from './Game.js'
import { Events } from './Events.js'
import { CameraOrbit } from './CameraOrbit.js'

export class View
{
    constructor()
    {
        this.game = Game.getInstance()
        this.events = new Events()

        const aspect = (this.game.viewport.width || 16) / (this.game.viewport.height || 9)

        this.camera = new THREE.PerspectiveCamera(38, aspect, 0.1, 160)
        this.camera.position.set(7.5, 4.6, 9.5)

        // The table is the stable visual anchor for lighting, fog and orbit.
        this.focusPoint = {
            position: new THREE.Vector3(0, 0.4, 0),
            smoothedPosition: new THREE.Vector3(0, 0.4, 0),
        }

        this.optimalArea = {
            needsUpdate: false,
            radius: 6.5,
            nearDistance: 9,
            farDistance: 30,
            position: this.focusPoint.position,
        }

        this.cameraOrbit = new CameraOrbit(this.game, this.camera, this.focusPoint.position)
        this.game.ticker.events.on('tick', () => { this.update() }, 900)
        this.events.trigger('change')
    }

    update()
    {
        this.cameraOrbit.update(this.game.ticker.delta)
    }

    destroy()
    {
        this.cameraOrbit.destroy()
    }
}
