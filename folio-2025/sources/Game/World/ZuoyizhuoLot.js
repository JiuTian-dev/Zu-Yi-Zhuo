import * as THREE from 'three/webgpu'
import { vec3 } from 'three/tsl'
import { Game } from '../Game.js'
import { nearestCenterOfType, centersForType } from './ZuoyizhuoTerrainPlan.js'

/**
 * 组一桌 lot: parking lines under the car, lamp facing car,
 * trees → towers, strip benches/crates/lanterns (keep river/water).
 */
export class ZuoyizhuoLot
{
    constructor()
    {
        this.game = Game.getInstance()
        this.group = new THREE.Group()
        this.group.name = 'zuoyizhuoLot'
        this.game.scene.add(this.group)

        // Wait a few frames so VisualVehicle chassis has settled on physics pose.
        this.game.ticker.wait(2, () =>
        {
            this.clearClutter()
            this.setParkingBayUnderCar()
            this.placeLampFacingCar()
            this.placeSignPostAtRearLeft()
            // Building stays off the intro/start screen; placed after click in Reveal step 2.
            this.moveKioskAwayFromBuilding()
        })
    }

    getCircleCenter()
    {
        const p = this.game.respawns.getDefault().position.clone()
        p.y = 0
        return p
    }

    getCarPose()
    {
        const circle = this.getCircleCenter()
        const chassis = this.game.world.visualVehicle?.parts?.chassis
        if(chassis)
        {
            const euler = new THREE.Euler().setFromQuaternion(chassis.quaternion, 'YXZ')
            // Anchor lot to the purple reveal circle center (car sits on it).
            return { center: circle, yaw: euler.y, quaternion: chassis.quaternion.clone() }
        }

        return { center: circle, yaw: 0, quaternion: new THREE.Quaternion() }
    }

    clearClutter()
    {
        const world = this.game.world

        // Grass stays on grassland only (see Grass.js); land uses original slabs except start asphalt pad.

        for(const system of [world.benches, world.explosiveCrates, world.lanterns, world.fences, world.poleLights])
        {
            if(!system)
                continue
            if(system.objects)
            {
                for(const object of system.objects)
                {
                    if(object?.visual?.object3D)
                        object.visual.object3D.visible = false
                    if(object?.physical?.body)
                        object.physical.body.setEnabled(false)
                }
            }
            if(system.instancedGroup?.meshes)
            {
                for(const entry of system.instancedGroup.meshes)
                {
                    if(entry?.instance)
                        entry.instance.visible = false
                }
            }
            if(system.references)
            {
                for(const ref of system.references)
                    ref.visible = false
            }
        }

        if(world.bushes?.mesh)
            world.bushes.mesh.visible = false
        if(world.bushes?.leaves?.mesh)
            world.bushes.leaves.mesh.visible = false
        if(world.flowers?.mesh)
            world.flowers.mesh.visible = false
        if(world.bricks?.mesh)
            world.bricks.mesh.visible = false
    }

    setParkingBayUnderCar()
    {
        // Clear previous lines if any
        if(this.parkingGroup)
            this.parkingGroup.removeFromParent()

        const { center, yaw } = this.getCarPose()
        // Fit inside purple reveal ring (radius ~3.5).
        const stallW = 2.2
        const stallL = 3.6
        const lineW = 0.12
        const y = 0.025

        this.parkingGroup = new THREE.Group()
        this.parkingGroup.name = 'parkingBay'
        this.parkingGroup.position.set(center.x, y, center.z)
        this.parkingGroup.rotation.y = yaw

        const mat = new THREE.MeshBasicNodeMaterial({
            colorNode: vec3(0.95, 0.95, 0.9),
            transparent: true,
            opacity: 0.95,
            depthWrite: false,
        })

        const addLine = (w, l, x, z) =>
        {
            const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, l), mat)
            mesh.rotation.x = -Math.PI * 0.5
            mesh.position.set(x, 0, z)
            this.parkingGroup.add(mesh)
        }

        addLine(lineW, stallL, -stallW * 0.5, 0)
        addLine(lineW, stallL, stallW * 0.5, 0)
        addLine(stallW + lineW, lineW, 0, -stallL * 0.5)
        addLine(stallW + lineW, lineW, 0, stallL * 0.5)
        addLine(stallW * 0.4, lineW, 0, stallL * 0.18)

        this.group.add(this.parkingGroup)
    }

    placeLampFacingCar()
    {
        const { center, yaw } = this.getCarPose()
        const gltf = this.game.resources.zuoyizhuoStreetLamp
        if(!gltf?.scene)
            return

        // Front-right but kept inside the circle.
        const stallW = 2.2
        const stallL = 3.6
        const localX = stallW * 0.5 + 0.7
        const localZ = stallL * 0.5 + 0.2
        const cos = Math.cos(yaw)
        const sin = Math.sin(yaw)
        const lampPos = new THREE.Vector3(
            center.x + localX * cos + localZ * sin,
            0,
            center.z - localX * sin + localZ * cos,
        )

        if(this.lamp)
            this.lamp.removeFromParent()

        const lamp = gltf.scene.clone(true)
        lamp.name = 'zuoyizhuoStreetLamp'
        lamp.traverse((child) =>
        {
            if(child.isMesh)
            {
                child.castShadow = true
                child.receiveShadow = true
            }
        })

        lamp.updateMatrixWorld(true)
        const box = new THREE.Box3().setFromObject(lamp)
        const size = new THREE.Vector3()
        box.getSize(size)
        lamp.scale.setScalar(3.5 / Math.max(size.y, 0.001))

        lamp.position.set(lampPos.x, 0, lampPos.z)
        // Face the vehicle, then clockwise 45°.
        lamp.lookAt(center.x, 0, center.z)
        lamp.rotateY(-Math.PI / 4)

        lamp.updateMatrixWorld(true)
        const box2 = new THREE.Box3().setFromObject(lamp)
        lamp.position.y = -box2.min.y

        this.group.add(lamp)
        this.lamp = lamp
    }

    placeSignPostAtRearLeft()
    {
        const { center, yaw } = this.getCarPose()
        const gltf = this.game.resources.zuoyizhuoSignPost
        if(!gltf?.scene)
            return

        // Right-rear corner of the parking stall (local +X right, -Z rear).
        const stallW = 2.2
        const stallL = 3.6
        const localX = stallW * 0.5 + 0.35
        const localZ = -(stallL * 0.5 + 0.25)
        const cos = Math.cos(yaw)
        const sin = Math.sin(yaw)
        const pos = new THREE.Vector3(
            center.x + localX * cos + localZ * sin,
            0,
            center.z - localX * sin + localZ * cos,
        )

        if(this.signPost)
            this.signPost.removeFromParent()

        const sign = gltf.scene.clone(true)
        sign.name = 'zuoyizhuoSignPost'
        sign.traverse((child) =>
        {
            if(child.isMesh)
            {
                child.castShadow = true
                child.receiveShadow = true
            }
        })

        sign.updateMatrixWorld(true)
        const box = new THREE.Box3().setFromObject(sign)
        const size = new THREE.Vector3()
        box.getSize(size)
        // ~2.2m tall sign post
        sign.scale.setScalar(2.2 / Math.max(size.y, 0.001))
        sign.position.copy(pos)
        sign.rotation.y = yaw

        sign.updateMatrixWorld(true)
        const box2 = new THREE.Box3().setFromObject(sign)
        sign.position.y = -box2.min.y

        this.group.add(sign)
        this.signPost = sign
    }

    placeBuilding(gltf, position, height = 9)
    {
        if(!gltf?.scene)
            return null
        const building = gltf.scene.clone(true)
        building.traverse((child) =>
        {
            if(child.isMesh)
            {
                child.castShadow = true
                child.receiveShadow = true
            }
        })
        building.updateMatrixWorld(true)
        const box = new THREE.Box3().setFromObject(building)
        const size = new THREE.Vector3()
        box.getSize(size)
        building.scale.setScalar(height / Math.max(size.y, 0.001))
        building.position.set(position.x, 0, position.z)
        building.updateMatrixWorld(true)
        const box2 = new THREE.Box3().setFromObject(building)
        building.position.y = -box2.min.y
        building.userData.isBuilding = true
        building.userData.kind = 'building'
        const dressing = this.game.world.zuoyizhuoDressing
        if(dressing?.footprintOnLeftoverAsphalt)
        {
            building.updateMatrixWorld(true)
            const box3 = new THREE.Box3().setFromObject(building)
            if(dressing.footprintOnLeftoverAsphalt(box3) || dressing.onLeftoverAsphalt(position))
                return null
        }
        this.group.add(building)
        return building
    }

    moveKioskAwayFromBuilding()
    {
        const landing = this.game.world.areas?.landing
        if(!landing)
            return

        const { yaw } = this.getCarPose()
        // Page/car right in parking frame (local +X) — 10 units clear of the tower.
        const right = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw)).multiplyScalar(10)

        const ip = landing.references.items.get('kioskInteractivePoint')?.[0]
        const anchor = ip?.position?.clone() ?? null

        const moveRoot = (root) =>
        {
            if(!root)
                return
            root.position.add(right)
            root.updateMatrixWorld?.(true)
        }

        // Move interactive point + any landing visuals near the kiosk.
        if(ip)
            moveRoot(ip)

        if(landing.objects?.items)
        {
            for(const object of landing.objects.items)
            {
                const vis = object.visual?.object3D
                if(!vis)
                    continue

                const nearAnchor = anchor
                    ? vis.position.distanceTo(anchor) < 6
                    : false
                const name = `${vis.name || ''} ${object.visual?.model?.name || ''}`
                const looksLikeKiosk = /kiosk|map|panel|sign/i.test(name)

                if(!nearAnchor && !looksLikeKiosk)
                    continue

                moveRoot(vis)
                if(object.physical?.body)
                {
                    const t = object.physical.body.translation()
                    object.physical.body.setTranslation(
                        { x: t.x + right.x, y: t.y, z: t.z + right.z },
                        true,
                    )
                }
            }
        }

        // Fallback: any reference whose name mentions kiosk (besides the interactive point).
        landing.references.items.forEach((list, name) =>
        {
            if(!/kiosk/i.test(name) || name === 'kioskInteractivePoint')
                return
            for(const ref of list)
            {
                moveRoot(ref)
                const object = ref.userData?.object
                if(object?.physical?.body)
                {
                    const t = object.physical.body.translation()
                    object.physical.body.setTranslation(
                        { x: t.x + right.x, y: t.y, z: t.z + right.z },
                        true,
                    )
                }
            }
        })
    }

    replaceTreesWithBuildings()
    {
        // Keep the intro cherry tree; place two towers behind the stall (staggered heights).
        const { center, yaw } = this.getCarPose()

        const stallL = 3.6
        const backDist = stallL * 0.5 + 3
        const rear = new THREE.Vector3(-Math.sin(yaw), 0, -Math.cos(yaw)).multiplyScalar(backDist)
        const buildingPos = center.clone().add(rear)

        // Right of first tower in parking frame (local +X).
        const gap = 4.5
        const right = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw)).multiplyScalar(gap)
        const buildingPosRight = buildingPos.clone().add(right)

        const tall = this.game.resources.zuoyizhuoBuildingTall
        const narrow = this.game.resources.zuoyizhuoBuildingNarrow
        const snapDistinct = (pos, excludeSerial = null) =>
        {
            const list = centersForType('slab').filter((cell) => cell.serial !== excludeSerial)
            let best = null
            let bestD = Infinity
            for(const cell of list)
            {
                const d = (cell.x - pos.x) ** 2 + (cell.z - pos.z) ** 2
                if(d < bestD)
                {
                    bestD = d
                    best = cell
                }
            }
            return best ? new THREE.Vector3(best.x, 0, best.z) : pos
        }
        const first = nearestCenterOfType('slab', buildingPos.x, buildingPos.z)
        const posA = first ? new THREE.Vector3(first.x, 0, first.z) : buildingPos
        const posB = snapDistinct(buildingPosRight, first?.serial)
        this.placeBuilding(tall || narrow, posA, 4.5)
        this.placeBuilding(narrow || tall, posB, 5.5)
        this.game.world.zuoyizhuoDressing?.stripOnLeftoverAsphalt?.()
    }
}
