/** @origin BRUNO-ADAPTED — product camera view; no player, keyboard or gamepad state. */
import * as THREE from 'three/webgpu'
import { Game } from './Game.js'
import { Events } from './Events.js'

export class View
{
    constructor()
    {
        this.game = Game.getInstance()
        this.events = new Events()
        this.delta = new THREE.Vector3()
        this.camera = new THREE.PerspectiveCamera(38, this.game.viewport.ratio, 0.1, 220)
        const defaultRespawn = this.game.respawns?.getDefault?.()
        const focus = new THREE.Vector3(defaultRespawn?.position.x ?? 0, 0.35, defaultRespawn?.position.z ?? 0)
        this.focusPoint = {
            position: focus,
            smoothedPosition: focus.clone(),
        }
        this.optimalArea = {
            needsUpdate: false,
            radius: 18,
            nearDistance: 7,
            farDistance: 42,
            position: this.focusPoint.position,
        }
        this.spherical = {
            offset: new THREE.Vector3(8, 6, 10),
            radius: { current: 13 },
        }
        this.camera.position.copy(focus).add(new THREE.Vector3(8, 5.2, 11))
        this.camera.lookAt(this.focusPoint.position)
        this.game.viewport.events.on('change', () => this.resize())
        this.events.trigger('change')
    }

    setTarget(target)
    {
        this.focusPoint.position.copy(target)
        this.focusPoint.smoothedPosition.copy(target)
        this.optimalArea.position = this.focusPoint.position
    }

    resize()
    {
        this.camera.aspect = this.game.viewport.ratio
        this.camera.updateProjectionMatrix()
        this.events.trigger('change')
    }

    update()
    {
        this.spherical.offset.copy(this.camera.position).sub(this.focusPoint.position)
        this.spherical.radius.current = this.spherical.offset.length()
    }

    destroy()
    {
        // View has no independent input listeners; CameraOrbit owns input cleanup.
    }
}
