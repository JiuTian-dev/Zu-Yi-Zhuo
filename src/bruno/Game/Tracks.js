import * as THREE from 'three'

export class Tracks
{
    constructor()
    {
        // Shim: no vehicle tracks on the table
        const size = 2
        const data = new Uint8Array([255, 255, 255, 255])
        const texture = new THREE.DataTexture(data, 1, 1)
        texture.needsUpdate = true
        this.renderTarget = { texture }
        this.halfSize = size * 0.5
        this.size = size
        this.focusPoint = { x: 0, y: 0 }
    }
}
