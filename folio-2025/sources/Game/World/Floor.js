import * as THREE from 'three/webgpu'
import { Game } from '../Game.js'
import { abs, clamp, color, float, floor, Fn, fract, If, max, min, mix, positionLocal, positionWorld, smoothstep, step, texture, uniform, uv, vec2, vec3, dot } from 'three/tsl'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'
import { createPlanTexture, PLAN_CELL, PLAN_N, PLAN_ORIGIN, PLAN_SPAN, PLAN_TYPE } from './ZuoyizhuoTerrainPlan.js'

export class Floor
{
    constructor()
    {
        this.game = Game.getInstance()

        // Debug
        if(this.game.debug.active)
        {
            this.debugPanel = this.game.debug.panel.addFolder({
                title: '⏥ Floor',
                expanded: false,
            })
        }
        this.geometry = this.game.resources.terrainModel.scene.children[0].geometry
        this.subdivision = this.game.terrain.subdivision

        const spawn = this.game.respawns.getDefault().position
        this.asphaltCenter = uniform(vec2(spawn.x, spawn.z))
        this.asphaltRadius = uniform(16)

        // Soft edge width as fraction of a cell (10m). 0.28 ≈ 2.8m feather.
        this.planSoft = uniform(0.28)

        this.planTexture = createPlanTexture()

        this.roadOrigin = uniform(vec2(0, 0))
        this.roadForward = uniform(vec2(0, -1))
        this.roadRight = uniform(vec2(1, 0))
        this.roadHalfWidth = uniform(6)
        this.roadLength = uniform(200)
        this.roadMaskActive = uniform(0)

        this.setVisual()
        this.setPhysical()
        this.setBedRock()

        this.game.ticker.events.on('tick', () =>
        {
            this.update()
        }, 10)
    }

    planUvNode(xz)
    {
        return vec2(
            xz.x.sub(PLAN_ORIGIN).div(PLAN_SPAN),
            xz.y.sub(PLAN_ORIGIN).div(PLAN_SPAN),
        )
    }

    /**
     * Continuous cell-space sample with soft bilinear weights between cell centers.
     * Returns { c00,c10,c01,c11, wx, wz } — type codes at four neighbors + soft mix.
     */
    planCornerSample(xz)
    {
        const n = float(PLAN_N)
        const cell = float(PLAN_CELL)
        const gx = xz.x.sub(PLAN_ORIGIN).div(cell).sub(0.5)
        const gz = xz.y.sub(PLAN_ORIGIN).div(cell).sub(0.5)

        const ix = floor(gx)
        const iz = floor(gz)
        const fx = fract(gx)
        const fz = fract(gz)

        const soft = this.planSoft
        const wx = smoothstep(float(0.5).sub(soft), float(0.5).add(soft), fx)
        const wz = smoothstep(float(0.5).sub(soft), float(0.5).add(soft), fz)

        const sampleAt = (i, j) =>
        {
            const ci = clamp(i, float(0), n.sub(1))
            const cj = clamp(j, float(0), n.sub(1))
            const u = ci.add(0.5).div(n)
            const v = cj.add(0.5).div(n)
            return texture(this.planTexture, vec2(u, v)).r
        }

        return {
            c00: sampleAt(ix, iz),
            c10: sampleAt(ix.add(1), iz),
            c01: sampleAt(ix, iz.add(1)),
            c11: sampleAt(ix.add(1), iz.add(1)),
            wx,
            wz,
        }
    }

    /** Soft coverage weight of one plan type at xz (0–1). Coverage only — no overlay stack. */
    softTypeWeight(xz, typeCode)
    {
        const s = this.planCornerSample(xz)
        const match = (code) => abs(code.sub(typeCode)).lessThan(0.05).select(float(1), float(0))
        return mix(
            mix(match(s.c00), match(s.c10), s.wx),
            mix(match(s.c01), match(s.c11), s.wx),
            s.wz,
        )
    }

    highwayWeight(xz)
    {
        const roadLocal = xz.sub(this.roadOrigin)
        const roadAlong = dot(roadLocal, this.roadForward)
        const roadAcross = abs(dot(roadLocal, this.roadRight))
        return this.roadMaskActive.mul(
            step(float(0), roadAlong)
                .mul(step(roadAlong, this.roadLength))
                .mul(step(roadAcross, this.roadHalfWidth))
        )
    }

    /** Hide plan coverage on scenery 主路 — highway always wins. */
    setRoadMask(frame)
    {
        if(!frame || !this.roadOrigin)
            return

        this.roadOrigin.value.set(frame.origin.x, frame.origin.z)
        this.roadForward.value.set(frame.forward.x, frame.forward.z)
        this.roadRight.value.set(frame.right.x, frame.right.z)
        this.roadHalfWidth.value = frame.halfWidth + 0.75
        this.roadLength.value = frame.length
        this.roadMaskActive.value = 1
    }

    setVisual()
    {
        this.size = Math.round(this.game.view.optimalArea.radius * 2) + 1
        this.halfSize = this.size * 0.5
        this.cellSize = 1.5
        this.subdivisions = this.size / this.cellSize

        // Geometry
        let geometry = new THREE.PlaneGeometry(this.size, this.size, this.subdivisions, this.subdivisions)
        geometry.rotateX(-Math.PI * 0.5)
        geometry.deleteAttribute('normal')

        const terrainData = this.game.terrain.terrainNode(positionWorld.xz)
        const slabHighColor = uniform(color('#ffcf8b'))
        const slabLowColor = uniform(color('#a87762'))
        const slabTextureFrequency = uniform(0.175)
        const slabNoiseFrequency = uniform(0.03)
        const dirtColor = uniform(color('#6b4a32'))
        const gravelColor = uniform(color('#8b8174'))
        const grassTint = uniform(color('#7a9a3a'))
        const asphaltMap = this.game.resources.zuoyizhuoAsphaltColor
        const roadMap = this.game.resources.zuoyizhuoRoadAsphalt || asphaltMap
        const asphaltFreq = uniform(0.14)
        const roadFreq = uniform(0.08)
        const asphaltTint = uniform(color('#2e2e32'))

        const isType = (code, target) => abs(code.sub(target)).lessThan(0.05)

        const colorFromCode = Fn(([code]) =>
        {
            const detailUv = positionWorld.xz.mul(asphaltFreq)
            const roadUv = positionWorld.xz.mul(roadFreq)

            // Land palette is plan-driven only (覆盖). Water tint still uses Folio water look.
            const waterColor = this.game.terrain.colorNode(terrainData)
            const slabNoise = texture(this.game.noises.perlin, positionWorld.xz.mul(slabNoiseFrequency)).r
            const slabsTexture = texture(this.game.resources.floorSlabsTexture, positionWorld.xz.mul(slabTextureFrequency)).r
            const slabColor = mix(slabLowColor, slabHighColor, slabsTexture)
            const gravelMix = mix(gravelColor, slabLowColor, slabNoise.mul(0.45))
            const grassColor = mix(waterColor, grassTint, 0.55)
            const padAsphalt = mix(texture(asphaltMap, detailUv).rgb, asphaltTint, 0.2)
            const sideRoad = mix(texture(roadMap, roadUv).rgb, asphaltTint, 0.08)
            const dirtMix = mix(dirtColor, slabLowColor, slabNoise.mul(0.25))
            const slabMix = mix(slabColor, slabHighColor, slabNoise.mul(0.2))

            const outColor = dirtMix.toVar()
            If(isType(code, PLAN_TYPE.grass), () => { outColor.assign(grassColor) })
            If(isType(code, PLAN_TYPE.water), () => { outColor.assign(waterColor) })
            If(isType(code, PLAN_TYPE.road), () => { outColor.assign(sideRoad) })
            If(isType(code, PLAN_TYPE.dirt), () => { outColor.assign(dirtMix) })
            If(isType(code, PLAN_TYPE.gravel), () => { outColor.assign(gravelMix) })
            If(isType(code, PLAN_TYPE.slab), () => { outColor.assign(slabMix) })
            If(isType(code, PLAN_TYPE.keep), () => { outColor.assign(padAsphalt) })

            return outColor
        })

        const colorNode = Fn(() =>
        {
            const s = this.planCornerSample(positionWorld.xz)
            const c00 = colorFromCode(s.c00)
            const c10 = colorFromCode(s.c10)
            const c01 = colorFromCode(s.c01)
            const c11 = colorFromCode(s.c11)
            // Soft coverage blend between adjacent cells (not layered overlays).
            const planColor = mix(
                mix(c00, c10, s.wx),
                mix(c01, c11, s.wx),
                s.wz,
            )
            // 主路 wins: keep original Folio terrain color, ignore plan.
            const onHighway = this.highwayWeight(positionWorld.xz)
            return mix(planColor, this.game.terrain.colorNode(terrainData), onHighway)
        })()

        const material = new MeshDefaultMaterial({
            colorNode: colorNode,
            normalNode: vec3(0, 1, 0),
            shadowNode: terrainData.g,
            hasWater: false,
            hasLightBounce: false,
            wireframe: false
        })

        material.positionNode = Fn(() =>
        {
            const uvDim = min(min(uv().x, uv().y).mul(20), 1)
            // Water dip from plan coverage only — do not max/stack with old terrain.b river mask.
            const planWater = this.softTypeWeight(positionWorld.xz, PLAN_TYPE.water)
                .mul(this.highwayWeight(positionWorld.xz).oneMinus())

            const newPosition = positionLocal
            newPosition.y.addAssign(planWater.mul(-1.5).mul(uvDim))

            return newPosition
        })()

        this.mesh = new THREE.Mesh(geometry, material)
        this.mesh.receiveShadow = true
        this.game.scene.add(this.mesh)

        this.game.viewport.events.on('throttleChange', () =>
        {
            this.size = Math.round(this.game.view.optimalArea.radius * 2) + 1
            this.halfSize = this.size * 0.5
            this.subdivisions = this.size
            
            geometry.dispose()
            
            geometry = new THREE.PlaneGeometry(this.size, this.size, this.subdivisions, this.subdivisions)
            geometry.rotateX(-Math.PI * 0.5)
            geometry.deleteAttribute('normal')

            this.mesh.geometry = geometry
        }, 2)

        if(this.game.debug.active)
        {
            this.debugPanel.addBinding(asphaltFreq, 'value', { label: 'asphaltFreq', min: 0.01, max: 0.5, step: 0.001 })
            this.debugPanel.addBinding(this.asphaltRadius, 'value', { label: 'asphaltRadius', min: 4, max: 40, step: 0.5 })
            this.debugPanel.addBinding(this.planSoft, 'value', { label: 'planSoft', min: 0.05, max: 0.48, step: 0.01 })
            this.game.debug.addThreeColorBinding(this.debugPanel, asphaltTint.value, 'asphaltTint')
            this.game.debug.addThreeColorBinding(this.debugPanel, slabHighColor.value, 'slabHighColor')
            this.game.debug.addThreeColorBinding(this.debugPanel, slabLowColor.value, 'slabLowColor')
        }
    }

    setPhysical()
    {
        // Extract heights from geometry
        const positionAttribute = this.geometry.attributes.position
        const totalCount = positionAttribute.count
        const rowsCount = Math.sqrt(totalCount)
        const heights = new Float32Array(totalCount)
        const halfExtent = this.game.terrain.size / 2

        for(let i = 0; i < totalCount; i++)
        {
            const x = positionAttribute.array[i * 3 + 0]
            const y = positionAttribute.array[i * 3 + 1]
            const z = positionAttribute.array[i * 3 + 2]
            const indexX = Math.round(((x / (halfExtent * 2)) + 0.5) * (rowsCount - 1))
            const indexZ = Math.round(((z / (halfExtent * 2)) + 0.5) * (rowsCount - 1))
            const index = indexZ + indexX * rowsCount

            heights[index] = y
        }

        const object = this.game.objects.add(
            null,
            {
                type: 'fixed',
                friction: 0.2,
                restitution: 0.15,
                colliders: [
                    { shape: 'heightfield', parameters: [ rowsCount - 1, rowsCount - 1, heights, { x: this.game.terrain.size, y: 1, z: this.game.terrain.size } ], category: 'floor' }
                ]
            }
        )
        this.physical = object.physical
    }

    setBedRock()
    {
        this.bedRock = {}
        this.bedRock.halfHeight = 0.5
        this.bedRock.halfWidth = 6
        this.bedRock.enabled = false

        this.bedRock.physical = this.game.physics.getPhysical({
            type: 'kinematicPositionBased',
            position: new THREE.Vector3(0, this.game.water.depthElevation - this.bedRock.halfHeight, 0),
            frictionRule: 'min',
            friction: 0.5,
            enabled: true,
            colliders:
            [
                { shape: 'cuboid', parameters: [ this.bedRock.halfWidth, this.bedRock.halfHeight, this.bedRock.halfWidth ] },
            ]
        })
    }

    update()
    {
        this.mesh.position.x = Math.round(this.game.view.optimalArea.position.x / this.cellSize) * this.cellSize
        this.mesh.position.z = Math.round(this.game.view.optimalArea.position.z / this.cellSize) * this.cellSize

        // Bedrock
        if(
            Math.abs(this.game.player.position.x) > this.game.terrain.size / 2 - this.bedRock.halfWidth ||
            Math.abs(this.game.player.position.z) > this.game.terrain.size / 2 - this.bedRock.halfWidth
        )
        {
            if(!this.bedRock.enabled)
            {
                this.bedRock.enabled = true
                this.bedRock.physical.body.setEnabled(true)
            }
            const x = Math.round(this.game.player.position.x)
            const z = Math.round(this.game.player.position.z)
            this.bedRock.physical.body.setNextKinematicTranslation({
                x,
                y: this.game.water.depthElevation - this.bedRock.halfHeight,
                z
            })
            this.bedRock.physical.body.setLinvel({ x: 0, y: 0, z: 0 })
        }
        else
        {
            if(this.bedRock.enabled)
            {
                this.bedRock.enabled = false
                this.bedRock.physical.body.setEnabled(false)
            }
        }
    }
}
