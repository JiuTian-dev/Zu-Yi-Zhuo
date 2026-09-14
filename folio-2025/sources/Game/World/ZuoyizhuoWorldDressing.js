import * as THREE from 'three/webgpu'
import { Game } from '../Game.js'
import { centersForType, findRoadCrossings } from './ZuoyizhuoTerrainPlan.js'
import { Trees } from './Trees.js'

/**
 * City / transition / nature dressing along scenery refRoad.
 * Does not move the intro vehicle, lamp, sign, or parking bay.
 * Kit megameshes (~65MB each) are avoided; uses home/* + already-loaded kit clones.
 */
export class ZuoyizhuoWorldDressing
{
    constructor()
    {
        this.game = Game.getInstance()
        this.group = new THREE.Group()
        this.group.name = 'zuoyizhuoWorldDressing'
        this.group.visible = false
        this.game.scene.add(this.group)

        this.cache = new Map()
        this.placed = false
        this.introRadius = 18
        this.roadHalfWidth = 4.2

        this.rngState = 0xC0FFEE ^ 0x5A17
        this.loadPromise = this.preload()
        this.mainRoadFrame = null

        // Kill Folio grass on the highway as soon as scenery exists (before reveal).
        this.game.ticker.wait(3, () =>
        {
            const frame = this.getRoadFrame()
            this.game.world.grass?.setRoadMask?.(frame)
            this.game.world.floor?.setRoadMask?.(frame)
        })
    }

    /** Mulberry32 */
    rand()
    {
        let t = this.rngState += 0x6D2B79F5
        t = Math.imul(t ^ (t >>> 15), t | 1)
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }

    randRange(a, b)
    {
        return a + (b - a) * this.rand()
    }

    async preload()
    {
        const files = [
            // City buildings (light Kenney)
            ...['a','b','c','d','e','f','g','h','i','j','k','l','m','n'].map((id) =>
                [`bldg_${id}`, `zuoyizhuo/home/buildings/building-${id}.glb`, 'gltf']),
            ...['a','b','c','d','e'].map((id) =>
                [`sky_${id}`, `zuoyizhuo/home/buildings/building-skyscraper-${id}.glb`, 'gltf']),
            ...['a','b','c','d','e','f','g','h','i','j','k','l','m','n'].map((id) =>
                [`low_${id}`, `zuoyizhuo/home/buildings/low-detail-building-${id}.glb`, 'gltf']),
            ['low_wide_a', 'zuoyizhuo/home/buildings/low-detail-building-wide-a.glb', 'gltf'],
            ['low_wide_b', 'zuoyizhuo/home/buildings/low-detail-building-wide-b.glb', 'gltf'],
            // Props
            ['dumpster', 'zuoyizhuo/home/props/dumpster.glb', 'gltf'],
            ['trafficLight', 'zuoyizhuo/home/props/traffic-light.glb', 'gltf'],
            ['roadSignStop', 'zuoyizhuo/home/props/road-sign-stop.glb', 'gltf'],
            ['roadSignWarn', 'zuoyizhuo/home/props/road-sign-warning.glb', 'gltf'],
            ['roadSignStreet', 'zuoyizhuo/home/props/road-sign-street.glb', 'gltf'],
            ['signHighway', 'zuoyizhuo/home/props/sign-highway.glb', 'gltf'],
            ['cone', 'zuoyizhuo/home/props/construction-cone.glb', 'gltf'],
            ['barrier', 'zuoyizhuo/home/props/construction-barrier.glb', 'gltf'],
            ['constFence', 'zuoyizhuo/home/props/construction-fence.glb', 'gltf'],
            // Parked cars (not Vehicle_SUV)
            ['car_sedan', 'zuoyizhuo/home/vehicle/sedan.glb', 'gltf'],
            ['car_suv', 'zuoyizhuo/home/vehicle/suv.glb', 'gltf'],
            ['car_van', 'zuoyizhuo/home/vehicle/van.glb', 'gltf'],
            ['car_taxi', 'zuoyizhuo/home/vehicle/taxi.glb', 'gltf'],
            ['car_hatch', 'zuoyizhuo/home/vehicle/hatchback-sports.glb', 'gltf'],
            // Nature props only — trees come from Folio birch/oak/cherry, not custom GLBs.
            ['rock_l', 'zuoyizhuo/home/trees/rock_largeA.glb', 'gltf'],
            ['rock_s', 'zuoyizhuo/home/trees/rock_smallA.glb', 'gltf'],
            ['bush', 'zuoyizhuo/home/trees/plant_bush.glb', 'gltf'],
            ['bushD', 'zuoyizhuo/home/trees/plant_bushDetailed.glb', 'gltf'],
            ['bushS', 'zuoyizhuo/home/trees/plant_bushSmall.glb', 'gltf'],
            ['grassL', 'zuoyizhuo/home/trees/grass_large.glb', 'gltf'],
            ['grassS', 'zuoyizhuo/home/trees/grass.glb', 'gltf'],
        ]

        // Load one-by-one so a missing file does not abort the whole dressing set.
        for(const file of files)
        {
            try
            {
                const loaded = await this.game.resourcesLoader.load([file])
                for(const [key, value] of Object.entries(loaded))
                    this.cache.set(key, value)
            }
            catch(err)
            {
                console.warn('[ZuoyizhuoWorldDressing] skip', file[1], err)
            }
        }
    }

    getScene(key)
    {
        const fromCache = this.cache.get(key)
        if(fromCache?.scene)
            return fromCache.scene
        const fromGame = this.game.resources[key]
        if(fromGame?.scene)
            return fromGame.scene
        return null
    }

    /**
     * Folio 樱花（碎叶片粉紫），不是自制绿叶 GLB，也不是 cherry visual 的原叶网格.
     */
    plantFolioCherries()
    {
        const spots = this.cherryPlantSpots || []
        const visual = this.game.resources.cherryTreesVisualModel?.scene
        if(!spots.length || !visual)
            return

        const refs = []
        for(const spot of spots)
        {
            if(this.onLeftoverAsphalt(spot.pos) || this.onRoadSurface(this.mainRoadFrame, spot.pos))
                continue
            const obj = new THREE.Object3D()
            obj.position.copy(spot.pos)
            obj.rotation.y = this.randRange(0, Math.PI * 2)
            obj.scale.setScalar((spot.height || 8) / 8)
            obj.updateMatrix()
            obj.updateMatrixWorld(true)
            refs.push(obj)
        }
        if(!refs.length)
            return

        this.plantedCherries = new Trees('Cherry Planted', visual, refs, '#ff6d6d', '#ff9990')
        this.plantedCherries.bodies.removeFromParent()
        this.plantedCherries.leaves?.mesh?.removeFromParent()
        this.group.add(this.plantedCherries.bodies)
        if(this.plantedCherries.leaves?.mesh)
            this.group.add(this.plantedCherries.leaves.mesh)
    }

    stripCustomTreeClones()
    {
        for(const child of [...this.group.children])
        {
            if(child.userData?.kind === 'tree')
                child.removeFromParent()
        }
    }

    /**
     * Road frame from scenery `refRoad` meshes.
     * Samples mesh vertices (not fat AABB) so curb width tracks the pavement,
     * not the river / world bounds.
     */
    getRoadFrame()
    {
        const meshes = this.game.world.scenery?.references?.items?.get('road') || []
        const samples = []
        const _v = new THREE.Vector3()

        for(const mesh of meshes)
        {
            mesh.updateWorldMatrix?.(true, true)
            const geom = mesh.geometry
            const posAttr = geom?.attributes?.position
            if(!posAttr)
            {
                const box = new THREE.Box3().setFromObject(mesh)
                if(!box.isEmpty())
                {
                    const c = box.getCenter(new THREE.Vector3())
                    samples.push(c.x, c.z)
                }
                continue
            }

            const step = Math.max(1, Math.floor(posAttr.count / 800))
            for(let i = 0; i < posAttr.count; i += step)
            {
                _v.fromBufferAttribute(posAttr, i)
                _v.applyMatrix4(mesh.matrixWorld)
                samples.push(_v.x, _v.z)
            }
        }

        const spawn = this.game.respawns.getDefault().position.clone()
        spawn.y = 0

        if(samples.length < 4)
        {
            return {
                origin: new THREE.Vector3(spawn.x, 0, spawn.z),
                forward: new THREE.Vector3(0, 0, -1),
                right: new THREE.Vector3(1, 0, 0),
                length: 120,
                halfWidth: this.roadHalfWidth,
                center: spawn.clone(),
                spawn,
            }
        }

        // Mean center
        let meanX = 0
        let meanZ = 0
        const n = samples.length / 2
        for(let i = 0; i < samples.length; i += 2)
        {
            meanX += samples[i]
            meanZ += samples[i + 1]
        }
        meanX /= n
        meanZ /= n

        // Covariance → principal axis (road forward)
        let cxx = 0
        let czz = 0
        let cxz = 0
        for(let i = 0; i < samples.length; i += 2)
        {
            const dx = samples[i] - meanX
            const dz = samples[i + 1] - meanZ
            cxx += dx * dx
            czz += dz * dz
            cxz += dx * dz
        }
        cxx /= n
        czz /= n
        cxz /= n

        // Largest eigenvector of [[cxx,cxz],[cxz,czz]]
        const diff = cxx - czz
        const disc = Math.sqrt(Math.max(0, diff * diff + 4 * cxz * cxz))
        let forward = new THREE.Vector3(
            2 * cxz,
            0,
            czz - cxx + disc,
        )
        if(forward.lengthSq() < 1e-8)
            forward.set(cxx >= czz ? 1 : 0, 0, cxx >= czz ? 0 : 1)
        forward.normalize()

        // Orient city → nature using spawn as transition anchor.
        const center = new THREE.Vector3(meanX, 0, meanZ)
        const toSpawn = spawn.clone().sub(center)
        if(toSpawn.dot(forward) > 0)
            forward.multiplyScalar(-1)

        const right = new THREE.Vector3(-forward.z, 0, forward.x)

        // Project samples → along / across
        const alongVals = []
        const acrossAbs = []
        for(let i = 0; i < samples.length; i += 2)
        {
            const dx = samples[i] - meanX
            const dz = samples[i + 1] - meanZ
            alongVals.push(dx * forward.x + dz * forward.z)
            acrossAbs.push(Math.abs(dx * right.x + dz * right.z))
        }

        alongVals.sort((a, b) => a - b)
        acrossAbs.sort((a, b) => a - b)

        const alongMin = alongVals[Math.floor(alongVals.length * 0.02)]
        const alongMax = alongVals[Math.min(alongVals.length - 1, Math.floor(alongVals.length * 0.98))]
        const length = Math.max(alongMax - alongMin, 40)

        const p70 = acrossAbs[Math.min(acrossAbs.length - 1, Math.floor(acrossAbs.length * 0.7))]
        const p95 = acrossAbs[Math.min(acrossAbs.length - 1, Math.floor(acrossAbs.length * 0.95))]
        const halfWidth = Math.min(8, Math.max(this.roadHalfWidth, p70))
        const blockHalfWidth = Math.min(18, Math.max(halfWidth + 3.5, p95)) + 2

        const origin = center.clone().addScaledVector(forward, alongMin)

        return { origin, forward, right, length, halfWidth, blockHalfWidth, center, spawn, alongMin, alongMax }
    }

    /** t∈[0,1] along road; side = signed lateral meters (road center = 0). */
    roadPoint(frame, t, side = 0)
    {
        return frame.origin.clone()
            .addScaledVector(frame.forward, t * frame.length)
            .addScaledVector(frame.right, side)
    }

    bandOf(t)
    {
        if(t < 0.33)
            return 'city'
        if(t < 0.53)
            return 'transition'
        return 'nature'
    }

    inIntroPad(pos)
    {
        const c = this.game.respawns.getDefault().position
        const dx = pos.x - c.x
        const dz = pos.z - c.z
        return dx * dx + dz * dz < this.introRadius * this.introRadius
    }

    /** True if xz is on the paved road band (never place props here). */
    onRoadSurface(frame, pos, extra = 0)
    {
        if(!frame)
            return false
        const delta = new THREE.Vector3(pos.x - frame.origin.x, 0, pos.z - frame.origin.z)
        const along = delta.dot(frame.forward)
        const across = Math.abs(delta.dot(frame.right))
        const half = (frame.blockHalfWidth ?? frame.halfWidth) + extra
        return along >= -2 && along <= frame.length + 2 && across <= half
    }

    footprintOnRoad(frame, box)
    {
        if(!frame || !box)
            return false
        const corners = [
            new THREE.Vector3(box.min.x, 0, box.min.z),
            new THREE.Vector3(box.max.x, 0, box.min.z),
            new THREE.Vector3(box.min.x, 0, box.max.z),
            new THREE.Vector3(box.max.x, 0, box.max.z),
            new THREE.Vector3((box.min.x + box.max.x) * 0.5, 0, (box.min.z + box.max.z) * 0.5),
        ]
        return corners.some((p) => this.onRoadSurface(frame, p, 0.6) || this.onLeftoverAsphalt(p))
    }

    /**
     * Folio 原公路网格（规划没覆盖到的残余沥青），开场圈除外。
     */
    buildLeftoverAsphaltMask()
    {
        this.asphaltCells = new Set()
        this.asphaltMeshes = []
        const refs = this.game.world.scenery?.references?.items
        if(!refs)
            return

        refs.forEach((list, name) =>
        {
            if(!/road/i.test(name))
                return
            for(const mesh of list)
            {
                if(mesh)
                    this.asphaltMeshes.push(mesh)
            }
        })

        const va = new THREE.Vector3()
        const vb = new THREE.Vector3()
        const vc = new THREE.Vector3()

        for(const mesh of this.asphaltMeshes)
        {
            mesh.updateWorldMatrix?.(true, true)
            const geom = mesh.geometry
            if(!geom?.attributes?.position)
            {
                const box = new THREE.Box3().setFromObject(mesh)
                if(!box.isEmpty())
                    this.markAsphaltBox(box)
                continue
            }

            const pos = geom.attributes.position
            const index = geom.index
            const triCount = index ? index.count / 3 : pos.count / 3
            for(let t = 0; t < triCount; t++)
            {
                const ia = index ? index.getX(t * 3) : t * 3
                const ib = index ? index.getX(t * 3 + 1) : t * 3 + 1
                const ic = index ? index.getX(t * 3 + 2) : t * 3 + 2
                va.fromBufferAttribute(pos, ia).applyMatrix4(mesh.matrixWorld)
                vb.fromBufferAttribute(pos, ib).applyMatrix4(mesh.matrixWorld)
                vc.fromBufferAttribute(pos, ic).applyMatrix4(mesh.matrixWorld)
                this.markAsphaltTriangle(va, vb, vc)
            }
        }
    }

    markAsphaltBox(box)
    {
        const minX = Math.floor(box.min.x)
        const maxX = Math.ceil(box.max.x)
        const minZ = Math.floor(box.min.z)
        const maxZ = Math.ceil(box.max.z)
        if(maxX - minX > 80 || maxZ - minZ > 80)
            return
        for(let x = minX; x <= maxX; x++)
        {
            for(let z = minZ; z <= maxZ; z++)
                this.markAsphaltCell(x, z)
        }
    }

    markAsphaltTriangle(a, b, c)
    {
        const minX = Math.floor(Math.min(a.x, b.x, c.x))
        const maxX = Math.ceil(Math.max(a.x, b.x, c.x))
        const minZ = Math.floor(Math.min(a.z, b.z, c.z))
        const maxZ = Math.ceil(Math.max(a.z, b.z, c.z))
        if(maxX - minX > 40 || maxZ - minZ > 40)
            return

        for(let x = minX; x <= maxX; x++)
        {
            for(let z = minZ; z <= maxZ; z++)
            {
                if(this.pointInTriangleXZ(x + 0.5, z + 0.5, a, b, c))
                    this.markAsphaltCell(x, z)
            }
        }
    }

    markAsphaltCell(x, z)
    {
        this.asphaltCells.add(`${x}_${z}`)
    }

    pointInTriangleXZ(x, z, a, b, c)
    {
        const v0x = c.x - a.x
        const v0z = c.z - a.z
        const v1x = b.x - a.x
        const v1z = b.z - a.z
        const v2x = x - a.x
        const v2z = z - a.z
        const dot00 = v0x * v0x + v0z * v0z
        const dot01 = v0x * v1x + v0z * v1z
        const dot02 = v0x * v2x + v0z * v2z
        const dot11 = v1x * v1x + v1z * v1z
        const dot12 = v1x * v2x + v1z * v2z
        const denom = dot00 * dot11 - dot01 * dot01
        if(Math.abs(denom) < 1e-8)
            return false
        const u = (dot11 * dot02 - dot01 * dot12) / denom
        const v = (dot00 * dot12 - dot01 * dot02) / denom
        return u >= -0.05 && v >= -0.05 && u + v <= 1.05
    }

    onLeftoverAsphalt(pos)
    {
        if(!pos || !this.asphaltCells)
            return false
        const x = Math.round(pos.x)
        const z = Math.round(pos.z)
        for(let dx = -1; dx <= 1; dx++)
        {
            for(let dz = -1; dz <= 1; dz++)
            {
                if(this.asphaltCells.has(`${x + dx}_${z + dz}`))
                    return true
            }
        }
        return false
    }

    footprintOnLeftoverAsphalt(box)
    {
        if(!box || box.isEmpty())
            return false
        const step = 0.8
        for(let x = box.min.x; x <= box.max.x; x += step)
        {
            for(let z = box.min.z; z <= box.max.z; z += step)
            {
                if(this.onLeftoverAsphalt(new THREE.Vector3(x, 0, z)))
                    return true
            }
        }
        return this.onLeftoverAsphalt(new THREE.Vector3(
            (box.min.x + box.max.x) * 0.5,
            0,
            (box.min.z + box.max.z) * 0.5,
        ))
    }

    stripOnLeftoverAsphalt()
    {
        if(!this.asphaltCells)
            this.buildLeftoverAsphaltMask()

        const keep = /StreetLamp|SignPost|Parking|parking/i
        const visit = (root) =>
        {
            if(!root)
                return
            for(const child of [...root.children])
            {
                if(keep.test(child.name || ''))
                    continue
                const kind = child.userData?.kind || (child.userData?.isBuilding ? 'building' : '')
                if(kind !== 'building' && kind !== 'tree')
                    continue
                const box = new THREE.Box3().setFromObject(child)
                if(this.footprintOnLeftoverAsphalt(box))
                    child.removeFromParent()
            }
        }

        visit(this.group)
        visit(this.game.world.zuoyizhuoLot?.group)

        const onAsphalt = (pos) => this.onLeftoverAsphalt(pos) || this.onRoadSurface(this.mainRoadFrame, pos)
        for(const trees of [
            this.game.world.cherryTrees,
            this.game.world.birchTrees,
            this.game.world.oakTrees,
        ])
            trees?.hideWhere?.((pos) => onAsphalt(new THREE.Vector3(pos.x, 0, pos.z)))
    }

    /** Lateral offset always clear of the pavement. */
    offRoadSide(frame, minExtra = 2, maxExtra = 10)
    {
        const sign = this.rand() > 0.5 ? 1 : -1
        return sign * (frame.halfWidth + this.randRange(minExtra, maxExtra))
    }

    groundY(pos)
    {
        // Flat physical floor; terrain visual may differ slightly.
        return 0
    }

    placeClone(scene, position, opts = {})
    {
        if(!scene || (!opts.allowIntroPad && this.inIntroPad(position)))
            return null
        const roadFrame = opts.frame || this.mainRoadFrame
        if(roadFrame && this.onRoadSurface(roadFrame, position) && !opts.allowOnRoad)
            return null
        if(opts.kind === 'building' && this.onLeftoverAsphalt(position))
            return null
        if(opts.kind === 'tree' && this.onLeftoverAsphalt(position))
            return null

        const root = scene.clone(true)
        root.traverse((child) =>
        {
            if(child.isMesh)
            {
                child.castShadow = true
                child.receiveShadow = true
            }
        })

        root.updateMatrixWorld(true)
        const box = new THREE.Box3().setFromObject(root)
        const size = new THREE.Vector3()
        box.getSize(size)

        if(opts.height != null && size.y > 0.001)
            root.scale.setScalar(opts.height / size.y)
        else if(opts.scale != null)
            root.scale.setScalar(opts.scale)
        else if(opts.uniformScale != null)
            root.scale.multiplyScalar(opts.uniformScale)

        if(opts.yaw != null)
            root.rotation.y = opts.yaw

        root.position.set(position.x, this.groundY(position), position.z)
        root.updateMatrixWorld(true)
        const box2 = new THREE.Box3().setFromObject(root)
        root.position.y = -box2.min.y + (opts.yOffset || 0)
        root.updateMatrixWorld(true)
        const box3 = new THREE.Box3().setFromObject(root)

        if(roadFrame && !opts.allowOnRoad && this.footprintOnRoad(roadFrame, box3))
            return null
        if(opts.kind === 'building' && this.footprintOnLeftoverAsphalt(box3))
            return null
        if(opts.kind === 'tree' && this.footprintOnLeftoverAsphalt(box3))
            return null

        if(opts.kind)
            root.userData.kind = opts.kind

        this.group.add(root)
        return root
    }

    yawAlongRoad(frame, jitter = 0.35)
    {
        return Math.atan2(frame.forward.x, frame.forward.z) + this.randRange(-jitter, jitter)
    }

    yawFaceRoad(frame, side)
    {
        // Face toward road center from lateral offset.
        const face = frame.right.clone().multiplyScalar(side > 0 ? -1 : 1)
        return Math.atan2(face.x, face.z) + this.randRange(-0.15, 0.15)
    }

    /** Clockwise 90° (right) for non-intro city buildings. */
    buildingYaw(baseYaw)
    {
        return baseYaw - Math.PI * 0.5
    }

    async placeAll()
    {
        if(this.placed)
            return
        await this.loadPromise
        this.rngState = 0xC0FFEE ^ 0x5A17

        const frame = this.getRoadFrame()
        this.mainRoadFrame = frame
        this.game.world.grass?.setRoadMask?.(frame)
        this.game.world.floor?.setRoadMask?.(frame)
        this.placeStreetLampsOnMainRoad(frame)
        this.placeTrafficLightsAtCrossings()
        this.buildLeftoverAsphaltMask()
        this.placeCity(frame)
        this.placeResidentialOfficeBehindCar(frame)
        this.placeSoftGroundProps()
        this.cherryPlantSpots = []
        this.placeTreesOnGrass()
        this.placeTreesOppositeCar(frame)
        this.plantFolioCherries()
        this.stripCustomTreeClones()
        this.stripOnLeftoverAsphalt()
        this.placed = true
    }

    /**
     * 车后方住宅 + 办公区。开场车 / 灯 / 牌 / 车位不动；只占车尾一侧。
     */
    placeResidentialOfficeBehindCar(frame)
    {
        const pose = this.game.world.zuoyizhuoLot?.getCarPose?.()
        if(!pose)
            return

        const { center, yaw } = pose
        const forward = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw))
        const right = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw))
        const rear = forward.clone().multiplyScalar(-1)
        const faceYaw = yaw

        const houseKeys = [
            'low_a','low_b','low_c','low_d','low_e','low_f','low_g','low_h',
            'low_wide_a','low_wide_b',
        ]
        const officeKeys = [
            'low_i','low_j','low_k','low_l','low_m','low_n',
            'sky_a','sky_b','sky_c',
        ]
        // 用户建模的单栋（不含连排）
        const customSingles = [
            this.game.resources.zuoyizhuoBuildingTall?.scene,
            this.game.resources.zuoyizhuoBuildingNarrow?.scene,
        ].filter(Boolean)

        const stepAlong = 3.15
        const stepSide = 3.05
        const startBack = 6.4
        const rows = 5
        const cols = 6

        const stallKeep = (pos) =>
        {
            const rel = pos.clone().sub(center)
            const localX = rel.dot(right)
            const localZ = rel.dot(forward)
            // Parking stall + lamp (front-right) + sign (rear-right).
            return localZ > -3.4 && localZ < 5.2 && localX > -3.4 && localX < 4.2
        }

        let n = 0
        for(let row = 0; row < rows; row++)
        {
            const office = row >= 2
            const keys = office ? officeKeys : houseKeys

            for(let col = 0; col < cols; col++)
            {
                const side = (col - (cols - 1) * 0.5) * stepSide
                const pos = center.clone()
                    .addScaledVector(rear, startBack + row * stepAlong)
                    .addScaledVector(right, side)

                if(stallKeep(pos) || this.onRoadSurface(frame, pos) || this.onLeftoverAsphalt(pos))
                    continue

                // ~2/3 → 用户单栋随机；其余保留白色低模
                const useCustom = customSingles.length > 0 && this.rand() < (2 / 3)
                if(useCustom)
                {
                    const scene = customSingles[Math.floor(this.rand() * customSingles.length)]
                    this.placeClone(scene, pos, {
                        height: office
                            ? this.randRange(5.0, 8.0)
                            : this.randRange(3.2, 5.2),
                        yaw: faceYaw + this.randRange(-0.08, 0.08),
                        allowIntroPad: true,
                        frame,
                        kind: 'building',
                    })
                }
                else
                {
                    const key = keys[n % keys.length]
                    n++
                    this.placeClone(this.getScene(key), pos, {
                        height: office
                            ? this.randRange(4.2, 7.2)
                            : this.randRange(2.0, 3.4),
                        yaw: faceYaw,
                        allowIntroPad: true,
                        frame,
                        kind: 'building',
                    })
                }
            }
        }
    }

    /** 主路路沿：对向错位、一侧顺时针 90°、一侧逆时针 90°. */
    placeStreetLampsOnMainRoad(frame)
    {
        const lampScene = this.game.resources.zuoyizhuoStreetLamp?.scene
        if(!lampScene)
            return

        const spacing = 12
        const curb = frame.halfWidth + 0.55
        const start = 2.5
        const end = Math.max(start + spacing, frame.length - 2.5)

        let index = 0
        for(let dist = start; dist <= end; dist += spacing)
        {
            const t = dist / frame.length
            const side = (index % 2 === 0) ? 1 : -1
            const pos = this.roadPoint(frame, t, side * curb)
            const face = frame.right.clone().multiplyScalar(side > 0 ? -1 : 1)
            const baseYaw = Math.atan2(face.x, face.z)
            const turn = side > 0 ? -1 : 1
            this.placeClone(lampScene, pos, {
                allowOnRoad: true,
                height: 5.4,
                yaw: baseYaw + turn * Math.PI * 0.5,
            })
            index++
        }
    }

    /** 十字路口：一路口四个红绿灯（四角朝向交叉中心）. */
    placeTrafficLightsAtCrossings()
    {
        const scene = this.getScene('trafficLight')
        if(!scene)
            return

        const corner = 3.2
        for(const cross of findRoadCrossings())
        {
            // Four corners, yaw axis-aligned so the housing sits parallel to a road
            // (N / E / S / W) — not the previous 45° diagonal toward the center.
            const corners = [
                { dx: -corner, dz: -corner, yaw: 0 },
                { dx:  corner, dz: -corner, yaw: Math.PI * 0.5 },
                { dx: -corner, dz:  corner, yaw: -Math.PI * 0.5 },
                { dx:  corner, dz:  corner, yaw: Math.PI },
            ]
            for(const { dx, dz, yaw } of corners)
            {
                const pos = new THREE.Vector3(cross.x + dx, 0, cross.z + dz)
                this.placeClone(scene, pos, {
                    allowOnRoad: true,
                    height: 4.0,
                    yaw,
                })
            }
        }
    }

    /**
     * 草 / 花 / 落叶堆 / 石头 / 悬崖 → 仅草地+泥土格.
     */
    placeSoftGroundProps()
    {
        const dirtSerials = new Set(centersForType('dirt').map((c) => c.serial))
        const plots = [
            ...centersForType('grass'),
            ...centersForType('dirt'),
        ].filter((cell) => !this.inIntroPad(new THREE.Vector3(cell.x, 0, cell.z)))

        for(const cell of plots)
        {
            const isDirt = dirtSerials.has(cell.serial)
            const density = cell.serial % 3 === 0 ? 4 : 3
            for(let i = 0; i < density; i++)
            {
                const pos = new THREE.Vector3(
                    cell.x + this.randRange(-3.8, 3.8),
                    0,
                    cell.z + this.randRange(-3.8, 3.8),
                )
                if(this.inIntroPad(pos))
                    continue

                const roll = this.rand()
                if(roll < 0.28)
                {
                    // 草
                    this.placeClone(this.getScene(this.rand() > 0.45 ? 'grassL' : 'grassS'), pos, {
                        scale: this.randRange(0.7, 1.5),
                        yaw: this.randRange(0, Math.PI * 2),
                    })
                }
                else if(roll < 0.48)
                {
                    // 花（小灌木 / 扁花）
                    const flower = this.getScene('flower') || this.getScene(this.rand() > 0.5 ? 'bushS' : 'bush')
                    this.placeClone(flower, pos, {
                        scale: this.randRange(0.6, 1.2),
                        yaw: this.randRange(0, Math.PI * 2),
                    })
                }
                else if(roll < 0.62)
                {
                    // 落叶堆：矮丛 + 小石（或 debris）
                    const pile = this.getScene('debris') || this.getScene('bushS')
                    this.placeClone(pile, pos, {
                        scale: this.randRange(0.4, 0.9),
                        yaw: this.randRange(0, Math.PI * 2),
                        yOffset: -0.05,
                    })
                    this.placeClone(this.getScene('rock_s'), pos.clone().add(new THREE.Vector3(this.randRange(-0.4, 0.4), 0, this.randRange(-0.4, 0.4))), {
                        scale: this.randRange(0.25, 0.55),
                        yaw: this.randRange(0, Math.PI * 2),
                        yOffset: 0.02,
                    })
                }
                else if(roll < 0.86)
                {
                    // 石头
                    this.placeClone(this.getScene(this.rand() > 0.4 ? 'rock_s' : 'rock_l'), pos, {
                        scale: this.randRange(0.45, 1.35),
                        yaw: this.randRange(0, Math.PI * 2),
                    })
                }
                else
                {
                    // 悬崖 / 大岩立面（泥土格更常见）
                    if(!isDirt && this.rand() > 0.35)
                        continue
                    const cliff = this.getScene('cliff') || this.getScene('rock_l')
                    this.placeClone(cliff, pos, {
                        scale: this.randRange(2.2, 4.2),
                        yaw: this.randRange(0, Math.PI * 2),
                    })
                }
            }
        }
    }

    placeTreesOnGrass()
    {
        const plots = centersForType('grass').filter((cell) =>
            !this.inIntroPad(new THREE.Vector3(cell.x, 0, cell.z)))

        for(let i = 0; i < plots.length; i++)
        {
            const cell = plots[i]
            const count = cell.serial % 3 === 0 ? 2 : 1
            for(let k = 0; k < count; k++)
            {
                const pos = new THREE.Vector3(
                    cell.x + this.randRange(-3.2, 3.2),
                    0,
                    cell.z + this.randRange(-3.2, 3.2),
                )
                if(this.inIntroPad(pos) || this.onLeftoverAsphalt(pos))
                    continue
                this.cherryPlantSpots.push({ pos, height: this.randRange(5, 11) })
            }
        }
    }

    /**
     * 车头对面（与后方住宅区相对）种树；避开车位 / 沥青 / 水面.
     */
    placeTreesOppositeCar(frame)
    {
        const pose = this.game.world.zuoyizhuoLot?.getCarPose?.()
        if(!pose)
            return

        const { center, yaw } = pose
        const forward = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw))
        const right = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw))
        const water = centersForType('water')
        const onWater = (pos) => water.some((c) =>
        {
            const dx = c.x - pos.x
            const dz = c.z - pos.z
            return dx * dx + dz * dz < 25
        })

        const stallKeep = (pos) =>
        {
            const rel = pos.clone().sub(center)
            const localX = rel.dot(right)
            const localZ = rel.dot(forward)
            return localZ > -3.4 && localZ < 5.2 && localX > -3.4 && localX < 4.2
        }

        const startFront = 6.2
        const rows = 5
        const cols = 7
        const stepAlong = 3.35
        const stepSide = 3.15

        for(let row = 0; row < rows; row++)
        {
            for(let col = 0; col < cols; col++)
            {
                const side = (col - (cols - 1) * 0.5) * stepSide + this.randRange(-0.4, 0.4)
                const pos = center.clone()
                    .addScaledVector(forward, startFront + row * stepAlong + this.randRange(-0.3, 0.3))
                    .addScaledVector(right, side)

                if(stallKeep(pos) || this.onRoadSurface(frame, pos) || this.onLeftoverAsphalt(pos) || onWater(pos))
                    continue

                this.cherryPlantSpots.push({ pos, height: this.randRange(5, 12) })
            }
        }
    }

    placeCity(frame)
    {
        const bldgKeys = [
            'bldg_a','bldg_b','bldg_c','bldg_d','bldg_e','bldg_f','bldg_g',
            'bldg_h','bldg_i','bldg_j','bldg_k','bldg_l','bldg_m','bldg_n',
        ]
        const lowKeys = ['low_a','low_b','low_c','low_d','low_e','low_f']
        const skyKeys = ['sky_a','sky_b','sky_c','sky_d','sky_e']

        const slabs = centersForType('slab').filter((cell) =>
        {
            const pos = new THREE.Vector3(cell.x, 0, cell.z)
            return !this.inIntroPad(pos) && !this.onRoadSurface(frame, pos, 2)
        })

        // Single towers only — no Building_Row_Thin chain.
        const narrow = this.game.resources.zuoyizhuoBuildingNarrow?.scene
        const tall = this.game.resources.zuoyizhuoBuildingTall?.scene

        const pickBuilding = (i) =>
        {
            if(i % 17 === 2 && tall)
                return { scene: tall, height: this.randRange(5.5, 7.5) }
            if(i % 17 === 8 && narrow)
                return { scene: narrow, height: this.randRange(3.8, 5) }

            const near = i % 3 === 0
            const sky = i % 5 === 0
            const key = near
                ? lowKeys[i % lowKeys.length]
                : (sky ? skyKeys[i % skyKeys.length] : bldgKeys[i % bldgKeys.length])
            const height = near
                ? this.randRange(1.7, 2.6)
                : (sky ? this.randRange(4.5, 7) : this.randRange(2.7, 4.3))
            return { scene: this.getScene(key), height }
        }

        // 3×3 packed singles per 石板 cell — 一栋挨一栋, skip 主路.
        let buildIndex = 0
        const grid = 3
        const stepM = 3.05
        for(let i = 0; i < slabs.length; i++)
        {
            const cell = slabs[i]
            const yaw = this.buildingYaw(this.yawAlongRoad(frame, 0.08))

            for(let gx = 0; gx < grid; gx++)
            {
                for(let gz = 0; gz < grid; gz++)
                {
                    const pos = new THREE.Vector3(
                        cell.x + (gx - (grid - 1) * 0.5) * stepM,
                        0,
                        cell.z + (gz - (grid - 1) * 0.5) * stepM,
                    )
                    if(this.inIntroPad(pos) || this.onRoadSurface(frame, pos))
                        continue

                    const pick = pickBuilding(buildIndex++)
                    this.placeClone(pick.scene, pos, { height: pick.height, yaw, frame, kind: 'building' })
                }
            }

            if(i % 11 === 0)
            {
                const propPos = new THREE.Vector3(cell.x + 4.4, 0, cell.z - 4.4)
                if(!this.onRoadSurface(frame, propPos))
                {
                    this.placeClone(this.getScene('dumpster'), propPos, {
                        scale: 1,
                        yaw: this.randRange(0, Math.PI * 2),
                        frame,
                    })
                }
            }
        }

        // Road signs 4–6
        const signs = ['roadSignStop', 'roadSignWarn', 'roadSignStreet', 'signHighway', 'roadSignStreet', 'signHighway']
        for(let i = 0; i < signs.length; i++)
        {
            const t = 0.05 + i * 0.045 + this.randRange(-0.01, 0.01)
            const side = i % 2 === 0 ? 1 : -1
            const pos = this.roadPoint(frame, t, side * (frame.halfWidth + 1.6))
            this.placeClone(this.getScene(signs[i]), pos, {
                height: this.randRange(2.4, 3.2),
                yaw: this.yawAlongRoad(frame, 0.1),
            })
        }

        // Parked cars 4–8 curb-side
        const cars = ['car_sedan', 'car_suv', 'car_van', 'car_taxi', 'car_hatch', 'car_sedan', 'car_suv']
        for(let i = 0; i < cars.length; i++)
        {
            const t = 0.06 + i * 0.035 + this.randRange(-0.008, 0.008)
            const side = i % 2 === 0 ? 1 : -1
            const pos = this.roadPoint(frame, t, side * (frame.halfWidth + 2.6))
            this.placeClone(this.getScene(cars[i]), pos, {
                height: 1.55,
                yaw: this.yawAlongRoad(frame, 0.06) + (side > 0 ? 0 : Math.PI),
            })
        }
    }

    placeTransition(frame)
    {
        // Gravel / debris stand-ins: low rock patches (kit gravel GLBs are ~65MB)
        for(let i = 0; i < 8; i++)
        {
            const t = 0.34 + this.randRange(0, 0.18)
            const pos = this.roadPoint(frame, t, this.offRoadSide(frame, 2.5, 10))
            this.placeClone(this.getScene(this.rand() > 0.5 ? 'rock_s' : 'rock_l'), pos, {
                frame,
                scale: this.randRange(0.4, 1.1),
                yaw: this.randRange(0, Math.PI * 2),
                yOffset: 0.02,
            })
        }

        // One Prop_Sign_Post at transition entrance facing city (extra instance; intro sign untouched)
        {
            const sign = this.game.resources.zuoyizhuoSignPost?.scene
            const pos = this.roadPoint(frame, 0.35, frame.halfWidth + 2.2)
            this.placeClone(sign, pos, {
                frame,
                height: 2.4,
                yaw: this.yawAlongRoad(frame, 0) + Math.PI,
            })
        }

        // Fence segments stand-in: construction fence along sides
        for(let i = 0; i < 8; i++)
        {
            const t = 0.36 + i * 0.02 + this.randRange(-0.005, 0.005)
            const side = i % 2 === 0 ? 1 : -1
            const pos = this.roadPoint(frame, t, side * (frame.halfWidth + 3.5))
            this.placeClone(this.getScene('constFence'), pos, {
                frame,
                height: 1.8,
                yaw: this.yawAlongRoad(frame, 0.08),
            })
        }

        // Flowers / bushes / grass — never on asphalt
        for(let i = 0; i < 20; i++)
        {
            const t = 0.34 + this.randRange(0, 0.18)
            const pos = this.roadPoint(frame, t, this.offRoadSide(frame, 3.5, 14))
            const key = this.rand() > 0.4 ? 'bush' : (this.rand() > 0.5 ? 'bushD' : 'grassL')
            this.placeClone(this.getScene(key), pos, {
                frame,
                scale: this.randRange(0.8, 1.6),
                yaw: this.randRange(0, Math.PI * 2),
            })
        }

        // Short trees 6–10, spacing ~8–12m irregular
        const shortTrees = ['tree_small', 'tree_thin', 'tree_pineR', 'tree_fat']
        for(let i = 0; i < 9; i++)
        {
            const t = 0.35 + (i / 9) * 0.16 + this.randRange(-0.015, 0.015)
            const side = (i % 2 === 0 ? 1 : -1) * (frame.halfWidth + this.randRange(6, 14))
            const pos = this.roadPoint(frame, t, side)
            this.placeClone(this.getScene(shortTrees[i % shortTrees.length]), pos, {
                height: this.randRange(3.5, 6),
                yaw: this.randRange(0, Math.PI * 2),
            })
        }
    }

    placeNature(frame)
    {
        // Large rock stand-ins as boundary / midground clusters
        for(let i = 0; i < 28; i++)
        {
            const t = 0.55 + this.randRange(0, 0.42)
            const lateral = this.randRange(8, 42) * (this.rand() > 0.5 ? 1 : -1)
            // Keep off road surface
            const side = Math.sign(lateral) * Math.max(Math.abs(lateral), frame.halfWidth + 5)
            const pos = this.roadPoint(frame, t, side)
            const big = this.rand() > 0.55
            this.placeClone(this.getScene(big ? 'rock_l' : 'rock_s'), pos, {
                scale: big ? this.randRange(1.2, 2.8) : this.randRange(0.6, 1.4),
                yaw: this.randRange(0, Math.PI * 2),
            })
        }

        // Outer rim blockers
        for(let i = 0; i < 16; i++)
        {
            const t = 0.7 + this.randRange(0, 0.28)
            const side = (i % 2 === 0 ? 1 : -1) * this.randRange(36, 55)
            const pos = this.roadPoint(frame, t, side)
            this.placeClone(this.getScene('rock_l'), pos, {
                scale: this.randRange(2.2, 4),
                yaw: this.randRange(0, Math.PI * 2),
            })
            this.placeClone(this.getScene(this.rand() > 0.5 ? 'tree_pine' : 'tree_tall'), pos.clone().add(
                new THREE.Vector3(this.randRange(-3, 3), 0, this.randRange(-3, 3))
            ), {
                height: this.randRange(10, 16),
                yaw: this.randRange(0, Math.PI * 2),
            })
        }

        // Canopy trees mid/near
        const canopy = ['tree_oak', 'tree_plat', 'tree_fat', 'tree_tall']
        for(let i = 0; i < 22; i++)
        {
            const t = 0.56 + this.randRange(0, 0.35)
            const side = (this.rand() > 0.5 ? 1 : -1) * (frame.halfWidth + this.randRange(8, 28))
            const pos = this.roadPoint(frame, t, side)
            this.placeClone(this.getScene(canopy[i % canopy.length]), pos, {
                height: this.randRange(6, 12),
                yaw: this.randRange(0, Math.PI * 2),
            })
        }

        // Conifer / columnar stand-ins in depth
        for(let i = 0; i < 12; i++)
        {
            const t = 0.72 + this.randRange(0, 0.25)
            const side = (i % 2 === 0 ? 1 : -1) * (frame.halfWidth + this.randRange(14, 36))
            const pos = this.roadPoint(frame, t, side)
            this.placeClone(this.getScene('tree_pine'), pos, {
                height: this.randRange(9, 15),
                yaw: this.randRange(0, Math.PI * 2),
            })
        }

        // Small trees at transition↔nature edge
        for(let i = 0; i < 8; i++)
        {
            const t = 0.52 + this.randRange(0, 0.08)
            const side = (i % 2 === 0 ? 1 : -1) * (frame.halfWidth + this.randRange(5, 12))
            const pos = this.roadPoint(frame, t, side)
            this.placeClone(this.getScene('tree_small'), pos, {
                height: this.randRange(3, 5),
                yaw: this.randRange(0, Math.PI * 2),
            })
        }

        // Plants at roots
        for(let i = 0; i < 12; i++)
        {
            const t = 0.58 + this.randRange(0, 0.35)
            const side = (this.rand() > 0.5 ? 1 : -1) * (frame.halfWidth + this.randRange(6, 22))
            const pos = this.roadPoint(frame, t, side)
            this.placeClone(this.getScene('bushD'), pos, {
                scale: this.randRange(0.7, 1.3),
                yaw: this.randRange(0, Math.PI * 2),
            })
        }

        // “Crystal / platform” landmarks: use scaled rock + low platform rock
        {
            const landmark = this.roadPoint(frame, 0.82, -18)
            this.placeClone(this.getScene('rock_l'), landmark, {
                scale: 3.2,
                yaw: this.randRange(0, Math.PI),
            })
            this.placeClone(this.getScene('rock_s'), this.roadPoint(frame, 0.78, 16), {
                scale: 2.5,
                yaw: 0,
            })
        }

        // folio birch/oak/cherry matrices intentionally untouched
    }

    async reveal()
    {
        await this.placeAll()
        this.group.visible = true
        // Keep folio bushes/flowers hidden — they often sit on/near the highway.
    }
}
