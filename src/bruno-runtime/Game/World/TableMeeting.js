/** @origin ZUOYIZHUO-SCENE — project-owned product furniture inside the
 * reused Bruno world. This file owns geometry and visual state only; it never
 * reads REST/WS data directly. */
import * as THREE from 'three/webgpu'
import { color, float, uniform } from 'three/tsl'
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

function lathe(points, segments = 72)
{
    return new THREE.LatheGeometry(points.map(([radius, height]) => new THREE.Vector2(radius, height)), segments)
}

function roundedSeat(width, height, depth, radius)
{
    return new RoundedBoxGeometry(width, height, depth, 12, radius)
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
        this.viewerId = null
        this.participantSeatMap = new Map()

        this.addWaterCove()
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

    addWaterCove()
    {
        // PRODUCT 3D — the Bruno water system remains the world-scale source
        // of truth. This small cove only restores the missing table/island
        // composition after the vehicle was removed; it is deliberately a
        // quiet transparent surface with the same lighting and fog pipeline.
        const shore = new THREE.Shape()
        shore.moveTo(-10.8, -2.2)
        shore.bezierCurveTo(-9.2, -7.1, -3.7, -9.4, 1.9, -8.2)
        shore.bezierCurveTo(7.2, -7.1, 10.8, -3.4, 10.2, 1.7)
        shore.bezierCurveTo(9.7, 6.4, 4.6, 8.9, -1.5, 8.6)
        shore.bezierCurveTo(-7.4, 8.3, -11.4, 3.4, -10.8, -2.2)

        const island = new THREE.Path()
        island.absellipse(0, 0, 4.28, 3.72, 0, Math.PI * 2, false, 0)
        shore.holes.push(island)

        const coveMaterial = new MeshDefaultMaterial({
            colorNode: color('#2c7887'),
            alphaNode: uniform(float(0.72)),
            transparent: true,
            hasCoreShadows: false,
            hasDropShadows: false,
            hasLightBounce: false,
            hasWater: false,
        })
        const cove = new THREE.Mesh(new THREE.ShapeGeometry(shore, 24), coveMaterial)
        cove.rotation.x = -Math.PI * 0.5
        cove.position.y = 0.018
        cove.renderOrder = 0
        cove.receiveShadow = true
        cove.name = 'product-table-water-cove'
        this.group.add(cove)

        const shorelineMaterial = new MeshDefaultMaterial({
            colorNode: color('#c8e8d5'),
            alphaNode: uniform(float(0.62)),
            transparent: true,
            hasCoreShadows: false,
            hasDropShadows: false,
            hasLightBounce: false,
            hasWater: false,
        })
        const shoreline = new THREE.Mesh(new THREE.TorusGeometry(4.27, 0.065, 8, 128), shorelineMaterial)
        shoreline.rotation.x = Math.PI * 0.5
        shoreline.scale.z = 0.87
        shoreline.position.y = 0.06
        shoreline.name = 'product-table-water-shoreline'
        this.group.add(shoreline)

        const rippleMaterial = new MeshDefaultMaterial({
            colorNode: color('#a9dcd0'),
            alphaNode: uniform(float(0.28)),
            transparent: true,
            hasCoreShadows: false,
            hasDropShadows: false,
            hasLightBounce: false,
            hasWater: false,
        })
        for(const [radius, y, scale] of [[5.4, 0.052, 0.86], [7.2, 0.048, 0.77]])
        {
            const ripple = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.026, 6, 128), rippleMaterial)
            ripple.rotation.x = Math.PI * 0.5
            ripple.scale.z = scale
            ripple.position.y = y
            ripple.name = 'product-table-water-ripple'
            this.group.add(ripple)
        }
    }

    addTable()
    {
        // A hand-authored lathed profile keeps the Bruno rounded, toy-like
        // language while avoiding a naked cylinder as the product asset.
        const top = new THREE.Mesh(lathe([
            [0, 1.02], [1.78, 1.02], [2.0, 1.04], [2.13, 1.09],
            [2.19, 1.16], [2.16, 1.23], [2.06, 1.28], [1.92, 1.3], [0, 1.3],
        ]), this.material('#8f5a42'))
        top.castShadow = true
        top.receiveShadow = true
        this.group.add(top)

        const inlay = new THREE.Mesh(lathe([
            [0, 1.292], [1.78, 1.292], [1.88, 1.31], [1.9, 1.34], [0, 1.34],
        ]), this.material('#523c3a'))
        inlay.receiveShadow = true
        this.group.add(inlay)

        const rim = new THREE.Mesh(
            new THREE.TorusGeometry(2.08, 0.055, 16, 128),
            this.material('#e1a36f'),
        )
        rim.rotation.x = Math.PI * 0.5
        rim.position.y = 1.31
        rim.castShadow = true
        this.group.add(rim)

        const base = new THREE.Mesh(lathe([
            [0, 0.08], [0.62, 0.08], [0.86, 0.14], [0.94, 0.22],
            [0.78, 0.3], [0.42, 0.43], [0.31, 0.62], [0.26, 0.92], [0, 1.02],
        ]), this.material('#4d3938'))
        base.castShadow = true
        base.receiveShadow = true
        this.group.add(base)

        const baseInset = new THREE.Mesh(lathe([
            [0, 0.23], [0.72, 0.23], [0.76, 0.27], [0.6, 0.32], [0.26, 0.48], [0, 0.52],
        ]), this.material('#6b4940'))
        baseInset.castShadow = true
        this.group.add(baseInset)
    }

    addSeats()
    {
        for(const seat of SEATS)
        {
            const distance = 3.02
            const x = Math.cos(seat.angle) * distance
            const z = Math.sin(seat.angle) * distance
            const seatColor = uniform(color(seat.color))
            const chairMaterial = new MeshDefaultMaterial({ colorNode: seatColor, hasWater: false })
            const detailMaterial = this.material('#f2c88f')
            const seatGroup = new THREE.Group()
            seatGroup.position.set(x, 0, z)
            seatGroup.rotation.y = Math.PI * 0.25 - seat.angle
            seatGroup.name = `product-seat-${seat.participantId}`

            const pedestal = new THREE.Mesh(lathe([
                [0, 0.05], [0.3, 0.05], [0.48, 0.11], [0.5, 0.18],
                [0.37, 0.24], [0.25, 0.34], [0.2, 0.52], [0, 0.58],
            ]), chairMaterial)
            pedestal.castShadow = true
            pedestal.receiveShadow = true
            seatGroup.add(pedestal)

            const cushion = new THREE.Mesh(roundedSeat(1.06, 0.18, 0.86, 0.16), chairMaterial)
            cushion.position.y = 0.62
            cushion.castShadow = true
            cushion.receiveShadow = true
            seatGroup.add(cushion)

            const cushionInset = new THREE.Mesh(roundedSeat(0.78, 0.045, 0.58, 0.08), detailMaterial)
            cushionInset.position.set(0.06, 0.73, 0)
            cushionInset.castShadow = true
            seatGroup.add(cushionInset)

            const backrest = new THREE.Mesh(roundedSeat(0.98, 0.86, 0.18, 0.16), chairMaterial)
            backrest.position.set(0.38, 0.99, 0)
            backrest.rotation.z = -0.1
            backrest.castShadow = true
            backrest.receiveShadow = true
            seatGroup.add(backrest)

            const backInset = new THREE.Mesh(roundedSeat(0.7, 0.58, 0.045, 0.06), detailMaterial)
            backInset.position.set(0.28, 1.0, 0)
            backInset.rotation.z = -0.1
            seatGroup.add(backInset)

            const haloColor = uniform(color(seat.color))
            const halo = new THREE.Mesh(
                new THREE.TorusGeometry(0.42, 0.026, 8, 32),
                new MeshDefaultMaterial({ colorNode: haloColor, hasWater: false }),
            )
            halo.rotation.x = Math.PI * 0.5
            halo.position.y = 0.08
            halo.visible = false
            seatGroup.add(halo)

            const marker = new THREE.Mesh(
                new THREE.SphereGeometry(0.105, 16, 12),
                new MeshDefaultMaterial({ colorNode: haloColor, hasWater: false }),
            )
            marker.position.set(0.38, 1.55, 0)
            marker.visible = false
            seatGroup.add(marker)

            this.group.add(seatGroup)
            this.seatSlots.push({ participantId: seat.participantId, seatGroup, baseColor: seat.color, seatColor, haloColor, halo, marker })
        }
    }

    addTableLight()
    {
        const material = this.game.materials.getFromName('emissiveOrangeRadialGradient')
        this.tableLight = new THREE.Mesh(new THREE.SphereGeometry(0.15, 24, 16), material)
        this.tableLight.position.y = 1.48
        this.tableLight.scale.set(1.2, 0.8, 1.2)
        this.group.add(this.tableLight)

        this.actionColor = uniform(color(ACTION_COLORS.SILENCE))
        this.actionMarker = new THREE.Mesh(
            new THREE.TorusGeometry(0.34, 0.024, 8, 40),
            new MeshDefaultMaterial({ colorNode: this.actionColor, hasWater: false }),
        )
        this.actionMarker.rotation.x = Math.PI * 0.5
        this.actionMarker.position.y = 1.39
        this.actionMarker.visible = false
        this.group.add(this.actionMarker)
    }

    participantIdForSlot(slot)
    {
        for(const [participantId, seatId] of this.participantSeatMap)
            if(seatId === slot.participantId) return participantId
        return null
    }

    refreshParticipantSeatMap(state)
    {
        this.participantSeatMap.clear()
        if(!state?.participants) return

        const participantIds = Object.keys(state.participants)
        const occupiedSeats = new Set()
        const assign = (participantId, seatId) =>
        {
            if(!participantId || !seatId || !state.participants[participantId] || occupiedSeats.has(seatId)) return false
            this.participantSeatMap.set(participantId, seatId)
            occupiedSeats.add(seatId)
            return true
        }

        // Keep the authored Bruno seat identities stable when the backend has
        // them. Any other backend participant is assigned to the next open
        // visual seat, so public IDs never fall back to the viewer marker.
        for(const seat of SEATS)
            if(seat.participantId !== 'viewer') assign(seat.participantId, seat.participantId)

        const viewerParticipantId = this.viewerId && state.participants[this.viewerId]
            ? this.viewerId
            : state.participants.viewer ? 'viewer' : null
        assign(viewerParticipantId, 'viewer')

        const freeSeatIds = SEATS
            .map((seat) => seat.participantId)
            .filter((seatId) => seatId !== 'viewer' && !occupiedSeats.has(seatId))
        participantIds
            .filter((participantId) => !this.participantSeatMap.has(participantId))
            .forEach((participantId, index) => assign(participantId, freeSeatIds[index]))
    }

    participantForSlot(slot)
    {
        const id = this.participantIdForSlot(slot)
        return id ? this.currentState?.participants?.[id] : null
    }

    setTableState(state, speakingId = null, viewerId = null)
    {
        this.currentState = state
        this.currentSpeakingId = speakingId
        this.viewerId = viewerId
        this.refreshParticipantSeatMap(state)

        this.seatSlots.forEach((slot) =>
        {
            if(!state)
            {
                slot.seatColor.value.set(slot.baseColor)
                slot.halo.visible = false
                slot.marker.visible = false
                return
            }
            const participantId = this.participantIdForSlot(slot)
            const participant = participantId ? state.participants?.[participantId] : null
            const occupied = Boolean(participant)
            const speaking = occupied && speakingId === participantId
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

    getFocusTarget()
    {
        return this.anchor.clone().setY(0.55)
    }

    getAnchorWorld(anchorId)
    {
        let slot = null
        const mappedSeatId = anchorId === 'viewer' && this.participantSeatMap.has('viewer')
            ? 'viewer'
            : this.participantSeatMap.get(anchorId)
        if(mappedSeatId) slot = this.seatSlots.find((item) => item.participantId === mappedSeatId)
        if(!slot && anchorId === 'viewer') slot = this.seatSlots.find((item) => item.participantId === 'viewer')
        if(!slot && anchorId === 'table-host') return this.group.localToWorld(new THREE.Vector3(0, 1.62, 0))
        if(!slot) return null
        return slot.seatGroup.localToWorld(new THREE.Vector3(0.38, 1.52, 0))
    }

    setAnchor(target)
    {
        this.anchor.copy(target)
        this.group.position.set(this.anchor.x, 0.03, this.anchor.z)
    }
}
