/** @origin ZUOYIZHUO-SCENE — product table inside the reused Bruno world. */
import * as THREE from 'three/webgpu'
import { color, uniform } from 'three/tsl'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { Game } from '../Game.js'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'

const SEATS = [
    { participantId: 'shen-zhiyao', angle: -Math.PI * 0.5, color: '#e8dfca' },
    { participantId: 'zhou-mo', angle: -Math.PI * 0.1, color: '#d87843' },
    { participantId: 'lin-zhou', angle: Math.PI * 0.28, color: '#59698c' },
    { participantId: 'xu-qing', angle: Math.PI * 0.72, color: '#739d94' },
    { participantId: 'viewer', angle: Math.PI, color: '#ffd58c' },
]

const ACTION_COLORS = {
    SILENCE: '#9eb5a9',
    PASS: '#ffd58c',
    PROBE: '#f2a36e',
    REFRAME: '#b6c9ff',
    GROUND: '#9ed4c1',
    CLOSE: '#f28c74',
}

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
        this.seatSlots = []
        this.currentState = null
        this.currentSpeakingId = null

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
            const seatColor = uniform(color(seat.color))
            const chairMaterial = new MeshDefaultMaterial({
                colorNode: seatColor,
                hasWater: false,
            })
            const seatGroup = new THREE.Group()
            seatGroup.position.set(x, 0, z)
            seatGroup.rotation.y = Math.PI * 0.25 - seat.angle

            const cushion = new THREE.Mesh(
                new RoundedBoxGeometry(0.94, 0.2, 0.78, 10, 0.15),
                chairMaterial,
            )
            cushion.position.y = 0.5
            cushion.castShadow = true
            cushion.receiveShadow = true
            seatGroup.add(cushion)

            const backrest = new THREE.Mesh(
                new RoundedBoxGeometry(0.92, 0.76, 0.18, 10, 0.12),
                chairMaterial,
            )
            backrest.position.set(0.25, 0.88, 0)
            backrest.castShadow = true
            backrest.receiveShadow = true
            seatGroup.add(backrest)

            const haloColor = uniform(color(seat.color))
            const halo = new THREE.Mesh(
                new THREE.TorusGeometry(0.38, 0.028, 8, 32),
                new MeshDefaultMaterial({ colorNode: haloColor, hasWater: false }),
            )
            halo.rotation.x = Math.PI * 0.5
            halo.position.y = 0.17
            halo.visible = false
            halo.castShadow = false
            seatGroup.add(halo)

            const marker = new THREE.Mesh(
                new THREE.SphereGeometry(0.105, 16, 12),
                new MeshDefaultMaterial({ colorNode: haloColor, hasWater: false }),
            )
            marker.position.set(0.25, 1.28, 0)
            marker.visible = false
            seatGroup.add(marker)

            this.group.add(seatGroup)
            this.seatSlots.push({ participantId: seat.participantId, baseColor: seat.color, seatColor, haloColor, halo, marker })
        }
    }

    addTableLight()
    {
        const material = this.game.materials.getFromName('emissiveOrangeRadialGradient')
        this.tableLight = new THREE.Mesh(new THREE.SphereGeometry(0.15, 24, 16), material)
        this.tableLight.position.y = 1.4
        this.tableLight.scale.set(1.2, 0.8, 1.2)
        this.group.add(this.tableLight)

        this.actionColor = uniform(color(ACTION_COLORS.SILENCE))
        this.actionMarker = new THREE.Mesh(
            new THREE.TorusGeometry(0.34, 0.024, 8, 40),
            new MeshDefaultMaterial({ colorNode: this.actionColor, hasWater: false }),
        )
        this.actionMarker.rotation.x = Math.PI * 0.5
        this.actionMarker.position.y = 1.22
        this.actionMarker.visible = false
        this.group.add(this.actionMarker)
    }

    setTableState(state, speakingId = null)
    {
        this.currentState = state
        this.currentSpeakingId = speakingId
        const participants = state?.participants ?? {}

        this.seatSlots.forEach((slot) =>
        {
            if(!state)
            {
                slot.seatColor.value.set(slot.baseColor)
                slot.halo.visible = false
                slot.marker.visible = false
                return
            }
            const participant = participants[slot.participantId]
            const occupied = Boolean(participant)
            const speaking = occupied && speakingId === slot.participantId
            const colorValue = speaking ? '#fff0b0' : participant ? slot.baseColor : '#63544d'
            slot.seatColor.value.set(colorValue)
            slot.haloColor.value.set(speaking ? '#fff0b0' : slot.baseColor)
            slot.halo.visible = occupied
            slot.marker.visible = speaking
            slot.halo.scale.setScalar(speaking ? 1.25 : 1)
            slot.marker.scale.setScalar(speaking ? 1.2 : 1)
        })
    }

    setHostAction(hostAction = null, closeState = 'idle')
    {
        const action = closeState === 'started' ? 'CLOSE' : hostAction?.action ?? null
        this.actionMarker.visible = Boolean(action)
        if(!action)
        {
            this.tableLight.scale.set(1.2, 0.8, 1.2)
            return
        }
        this.actionColor.value.set(ACTION_COLORS[action] ?? ACTION_COLORS.SILENCE)
        this.actionMarker.scale.setScalar(action === 'SILENCE' ? 0.82 : 1.15)
        this.tableLight.scale.setScalar(action === 'SILENCE' ? 0.8 : 1.15)
    }

    setAnchor(target)
    {
        this.anchor.copy(target)
        this.group.position.set(this.anchor.x, 0.03, this.anchor.z)
    }
}
