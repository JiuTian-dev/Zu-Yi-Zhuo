/** PRODUCT 3D — a restrained meeting table placed inside the reused scene. */
import * as THREE from 'three/webgpu'
import { color, uniform } from 'three/tsl'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { Game } from '../Game.js'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'

const SEATS = [
    { angle: -Math.PI * 0.5, color: '#f0c37c' },
    { angle: -Math.PI * 0.1, color: '#c97855' },
    { angle: Math.PI * 0.28, color: '#7b9aa4' },
    { angle: Math.PI * 0.72, color: '#8eaf8d' },
    { angle: Math.PI, color: '#db9c66' },
]

export class TableMeeting
{
    constructor()
    {
        this.game = Game.getInstance()
        this.anchor = this.game.view.focusPoint.position.clone()
        this.group = new THREE.Group()
        this.group.position.set(this.anchor.x, 0.03, this.anchor.z)
        this.group.name = 'product-table-meeting'
        this.game.scene.add(this.group)

        this.addTable()
        this.addSeats()
        this.addTableLight()
    }

    material(hex, options = {})
    {
        return new MeshDefaultMaterial({
            colorNode: uniform(color(hex)),
            hasWater: false,
            ...options,
        })
    }

    addTable()
    {
        const top = new THREE.Mesh(
            new THREE.CylinderGeometry(2.18, 2.2, 0.18, 96),
            this.material('#8f5a42'),
        )
        top.position.y = 1.02
        top.castShadow = true
        top.receiveShadow = true
        this.group.add(top)

        const rim = new THREE.Mesh(
            new THREE.TorusGeometry(2.08, 0.075, 20, 128),
            this.material('#e1a36f'),
        )
        rim.rotation.x = Math.PI * 0.5
        rim.position.y = 1.13
        rim.castShadow = true
        this.group.add(rim)

        const inlay = new THREE.Mesh(
            new THREE.CylinderGeometry(1.88, 1.88, 0.035, 96),
            this.material('#6c443b'),
        )
        inlay.position.y = 1.125
        inlay.receiveShadow = true
        this.group.add(inlay)

        const stem = new THREE.Mesh(
            new THREE.CylinderGeometry(0.27, 0.48, 0.9, 64),
            this.material('#5e4039'),
        )
        stem.position.y = 0.52
        stem.castShadow = true
        this.group.add(stem)

        const foot = new THREE.Mesh(
            new THREE.CylinderGeometry(0.9, 1.08, 0.14, 96),
            this.material('#4d3938'),
        )
        foot.position.y = 0.075
        foot.castShadow = true
        foot.receiveShadow = true
        this.group.add(foot)
    }

    addSeats()
    {
        for(const seat of SEATS)
        {
            const distance = 3.02
            const x = Math.cos(seat.angle) * distance
            const z = Math.sin(seat.angle) * distance
            const chairMaterial = this.material(seat.color)

            // PRODUCT 3D — rounded furniture gives the seat a readable
            // silhouette while staying inside Bruno's material/shadow model.
            const cushion = new THREE.Mesh(
                new RoundedBoxGeometry(0.94, 0.2, 0.78, 10, 0.15),
                chairMaterial,
            )
            cushion.position.set(x, 0.5, z)
            cushion.rotation.y = Math.PI * 0.25 - seat.angle
            cushion.castShadow = true
            cushion.receiveShadow = true
            this.group.add(cushion)

            const backrest = new THREE.Mesh(
                new RoundedBoxGeometry(0.92, 0.76, 0.18, 10, 0.12),
                chairMaterial,
            )
            backrest.position.set(Math.cos(seat.angle) * (distance + 0.25), 0.88, Math.sin(seat.angle) * (distance + 0.25))
            backrest.rotation.y = Math.PI * 0.5 - seat.angle
            backrest.castShadow = true
            backrest.receiveShadow = true
            this.group.add(backrest)
        }
    }

    addTableLight()
    {
        const material = this.game.materials.getFromName('emissiveOrangeRadialGradient')
        const glow = new THREE.Mesh(new THREE.SphereGeometry(0.15, 24, 16), material)
        glow.position.y = 1.4
        glow.scale.set(1.2, 0.8, 1.2)
        this.group.add(glow)
    }
}
