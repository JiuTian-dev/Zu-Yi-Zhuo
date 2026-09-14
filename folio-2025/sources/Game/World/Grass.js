import * as THREE from 'three/webgpu'
import { Game } from '../Game.js'
import { mul, step, output, color, sin, mix, matcapUV, float, mod, texture, transformNormalToView, uniformArray, varying, vertexIndex, rotateUV, cameraPosition, vec4, atan, vec3, vec2, modelWorldMatrix, Fn, attribute, uniform, normalWorld, abs, dot, smoothstep } from 'three/tsl'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'
import { PLAN_TYPE } from './ZuoyizhuoTerrainPlan.js'

export class Grass
{
    constructor()
    {
        this.game = Game.getInstance()

        this.subdivisions = 280
        const halfExtent = this.game.view.optimalArea.radius
        this.size = halfExtent * 2
        this.count = this.subdivisions * this.subdivisions
        this.fragmentSize = this.size / this.subdivisions

        this.surface = this.size * this.size
        this.surfaceIdeal = 2000
        this.surfaceOverflow = Math.max(0, this.surface - this.surfaceIdeal) / this.surfaceIdeal

        this.setGeometry()
        this.setMaterial()
        this.setMesh()

        this.game.ticker.events.on('tick', () =>
        {
            this.update()
        }, 10)

        // Resize
        this.game.viewport.events.on('throttleChange', () =>
        {
            const halfExtent = this.game.view.optimalArea.radius
            this.size = halfExtent * 2
            this.surface = this.size * this.size
            this.surfaceOverflow = Math.max(0, this.surface - this.surfaceIdeal) / this.surfaceIdeal
            
            this.sizeUniform.value = this.size
            this.bladeWidth.value = 0.1 * (1 + this.surfaceOverflow * 0.4)
            this.bladeHeight.value = 0.6 * (1 + this.surfaceOverflow * 0.4)

            this.geometry.dispose()
            this.setGeometry()
            this.mesh.geometry = this.geometry
        }, 2)
    }

    setGeometry()
    {
        const position = new Float32Array(this.count * 3 * 2)
        const heightRandomness = new Float32Array(this.count * 3)

        for(let iX = 0; iX < this.subdivisions; iX++)
        {
            const fragmentX = (iX / this.subdivisions - 0.5) * this.size + this.fragmentSize * 0.5
            
            for(let iZ = 0; iZ < this.subdivisions; iZ++)
            {
                const fragmentZ = (iZ / this.subdivisions - 0.5) * this.size + this.fragmentSize * 0.5

                const i = (iX * this.subdivisions + iZ)
                const i3 = i * 3
                const i6 = i * 6

                // Center of the blade
                const positionX = fragmentX + (Math.random() - 0.5) * this.fragmentSize
                const positionZ = fragmentZ + (Math.random() - 0.5) * this.fragmentSize

                position[i6    ] = positionX
                position[i6 + 1] = positionZ

                position[i6 + 2] = positionX
                position[i6 + 3] = positionZ

                position[i6 + 4] = positionX
                position[i6 + 5] = positionZ

                // Randomness
                heightRandomness[i3    ] = Math.random()
                heightRandomness[i3 + 1] = Math.random()
                heightRandomness[i3 + 2] = Math.random()
            }
        }
        
        this.geometry = new THREE.BufferGeometry()
        this.geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1)
        this.geometry.setAttribute('position', new THREE.Float32BufferAttribute(position, 2))
        this.geometry.setAttribute('heightRandomness', new THREE.Float32BufferAttribute(heightRandomness, 1))
    }

    setMaterial()
    {
        this.center = uniform(new THREE.Vector2())
        // this.tracksDelta = uniform(new THREE.Vector2())

        const vertexLoopIndex = varying(vertexIndex.toFloat().mod(3))
        const tipness = varying(step(vertexLoopIndex, 0.5))
        const wind = varying(vec2())
        const bladePosition = varying(vec2())

        this.bladeWidth = uniform(0.1 * (1 + this.surfaceOverflow * 0.5))
        this.bladeHeight = uniform(0.6 * (1 + this.surfaceOverflow * 0.5))
        this.bladeHeightRandomness = uniform(0.6)
        this.sizeUniform = uniform(this.size)

        const bladeShape = uniformArray([

                // Tip
                0,
                1,

                // Left side
                1,
                0,

                // Right side
                - 1,
                0,
        ])

        const hiddenThreshold = 0.1
        const terrainData = this.game.terrain.terrainNode(bladePosition)
        const floor = this.game.world.floor

        // Plan soft coverage only (覆盖): grass weight fades at cell edges — no asphalt/terrain.g overlay stack.
        const grassMask = floor?.softTypeWeight
            ? floor.softTypeWeight(bladePosition, PLAN_TYPE.grass)
            : float(0)

        this.roadOrigin = uniform(vec2(0, 0))
        this.roadForward = uniform(vec2(0, -1))
        this.roadRight = uniform(vec2(1, 0))
        this.roadHalfWidth = uniform(6)
        this.roadLength = uniform(200)
        this.roadMaskActive = uniform(0)

        const roadLocal = bladePosition.sub(this.roadOrigin)
        const roadAlong = dot(roadLocal, this.roadForward)
        const roadAcross = abs(dot(roadLocal, this.roadRight))
        const onHighway = this.roadMaskActive.mul(
            step(float(0), roadAlong)
                .mul(step(roadAlong, this.roadLength))
                .mul(step(roadAcross, this.roadHalfWidth))
        )

        // Highway suppress stays as a safety for scenery refRoad; plan types already cover keep/road/water.
        // Original terrain.g is 0 on the Folio bridge/highway — never grow blades there.
        const onBridge = smoothstep(0.28, 0.08, terrainData.g)
        const grassCover = grassMask.mul(onHighway.oneMinus()).mul(onBridge.oneMinus())
        const hidden = step(grassCover, hiddenThreshold)

        // Instance
        const tipnessShadowMix = tipness.oneMinus().mul(grassCover)

        this.material = new MeshDefaultMaterial({
            colorNode: this.game.terrain.colorNode(terrainData),
            normalNode: vec3(0, 1, 0),
            hasWater: false,
            hasLightBounce: false,
            shadowNode: tipnessShadowMix
        })

        this.material.positionNode = Fn(() =>
        {
            // Blade position
            const position = attribute('position')

            const loopPosition = position.sub(this.center)
            const halfSize = this.sizeUniform.mul(0.5)
            loopPosition.x.assign(mod(loopPosition.x.add(halfSize), this.sizeUniform).sub(halfSize))
            loopPosition.y.assign(mod(loopPosition.y.add(halfSize), this.sizeUniform).sub(halfSize))

            const position3 = vec3(loopPosition.x, 0, loopPosition.y).add(vec3(this.center.x, 0, this.center.y))
            const worldPosition = modelWorldMatrix.mul(position3)
            bladePosition.assign(worldPosition.xz)

            // Height — only where grassland mask allows
            const heightVariation = texture(this.game.noises.perlin, bladePosition.mul(0.0321)).r.add(0.5)
            const height = this.bladeHeight
                .mul(this.bladeHeightRandomness.mul(attribute('heightRandomness')).add(this.bladeHeightRandomness.oneMinus()))
                .mul(heightVariation)
                .mul(grassCover)

            // Shape
            const shape = vec3(
                bladeShape.element(vertexLoopIndex.mod(3).mul(2)).mul(this.bladeWidth).mul(grassCover),
                bladeShape.element(vertexLoopIndex.mod(3).mul(2).add(1)).mul(height),
                0
            )

            // Vertex positioning
            const vertexPosition = position3.add(shape)

            // Vertex rotation
            const angleToCamera = atan(worldPosition.z.sub(cameraPosition.z), worldPosition.x.sub(cameraPosition.x)).add(- Math.PI * 0.5)
            vertexPosition.xz.assign(rotateUV(vertexPosition.xz, angleToCamera, worldPosition.xz))

            // Wind
            wind.assign(this.game.wind.offsetNode(worldPosition.xz).mul(tipness).mul(height).mul(2))
            vertexPosition.addAssign(vec3(wind.x, 0, wind.y))

            // Hide (far above)
            vertexPosition.y.addAssign(hidden.mul(100))

            return vertexPosition
        })()

        // Debug
        if(this.game.debug.active)
        {
            const debugPanel = this.game.debug.panel.addFolder({
                title: '🌱 Grass',
                expanded: false,
            })

            debugPanel.addBinding(this.bladeWidth, 'value', { label: 'bladeWidth', min: 0, max: 1, step: 0.001 })
            debugPanel.addBinding(this.bladeHeight, 'value', { label: 'bladeHeight', min: 0, max: 2, step: 0.001 })
            debugPanel.addBinding(this.bladeHeightRandomness, 'value', { label: 'bladeHeightRandomness', min: 0, max: 1, step: 0.001 })
        }
    }

    setMesh()
    {
        this.mesh = new THREE.Mesh(this.geometry, this.material)
        this.mesh.frustumCulled = false
        this.mesh.receiveShadow = true
        // this.mesh.visible = false
        this.game.scene.add(this.mesh)
    }

    /** Hide Folio blades on scenery refRoad pavement. */
    setRoadMask(frame)
    {
        if(!frame || !this.roadOrigin)
            return

        this.roadOrigin.value.set(frame.origin.x, frame.origin.z)
        this.roadForward.value.set(frame.forward.x, frame.forward.z)
        this.roadRight.value.set(frame.right.x, frame.right.z)
        this.roadHalfWidth.value = frame.halfWidth + 4
        this.roadLength.value = frame.length
        this.roadMaskActive.value = 1
    }

    update()
    {
        this.center.value.set(this.game.view.optimalArea.position.x, this.game.view.optimalArea.position.z)
    }
}