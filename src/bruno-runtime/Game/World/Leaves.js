import * as THREE from 'three/webgpu'
import { Game } from '../Game.js'
import { color, float, Fn, hash, instancedArray, instanceIndex, materialNormal, max, mix, mod, modelViewMatrix, normalWorld, positionGeometry, remapClamp, rotateUV, sin, smoothstep, step, texture, uniform, vec2, vec3, vec4 } from 'three/tsl'
import { remap } from '../utilities/maths.js'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'

export class Leaves
{
    constructor()
    {
        this.game = Game.getInstance()

        // if(this.game.yearCycles.properties.leaves.value < 0.25)
        //     return

        const power = Math.round(remap((this.game.yearCycles.properties.leaves.value), 0.25, 1, 7, 11))
        this.count = Math.pow(2, power)
        // this.count = Math.pow(2, 12)

        // Debug
        if(this.game.debug.active)
        {
            this.debugPanel = this.game.debug.panel.addFolder({
                title: '🍃 Leaves',
                expanded: false,
            })
        }

        this.setGeometry()
        this.setMaterial()
        this.setMesh()

        this.game.ticker.events.on('tick', () =>
        {
            this.update()
        }, 10)
    }

    setGeometry()
    {
        this.geometry = new THREE.PlaneGeometry(1, 1)

        const positionsArray = this.geometry.attributes.position.array

        positionsArray[0] += 0.15
        positionsArray[3] += 0.15
        positionsArray[6] -= 0.15
        positionsArray[9] -= 0.15

        this.geometry.rotateX(- Math.PI * 0.5)
    }

    setMaterial()
    {
        // Uniforms
        this.focusPoint = uniform(vec2())
        this.scale = uniform(0.25)
        this.rotationFrequency = uniform(3)
        this.rotationElevationMultiplier = uniform(1)
        this.pushSidewaysMultiplier = uniform(20)
        this.pushMultiplier = uniform(100)
        this.windFrequency = uniform(0.005)
        this.windMultiplier = uniform(0.5)
        this.upwardMultiplier = uniform(1)
        this.defaultDamping = uniform(1.5)
        this.waterDamping = uniform(0.75)
        this.gravity = uniform(9.807)

        // Buffers
        this.positionBuffer = instancedArray(this.count, 'vec3')
        this.velocityBuffer = instancedArray(this.count, 'vec3')

        // Base rotation buffer
        const baseRotationArray = new Float32Array(this.count)
        for(let i = 0; i < this.count; i++)
            baseRotationArray[i] = Math.random() * Math.PI * 2
        const baseRotationBuffer = instancedArray(baseRotationArray, 'float').toAttribute()
        
        // Scale
        const scaleArray = new Float32Array(this.count)
        for(let i = 0; i < this.count; i++)
            scaleArray[i] = Math.random() * 0.5 + 0.5
        const scaleBuffer = instancedArray(scaleArray, 'float').toAttribute()
        
        // Weight
        const weightArray = new Float32Array(this.count)
        for(let i = 0; i < this.count; i++)
            weightArray[i] = Math.random() * 0.1 + 0.1
        const weightBuffer = instancedArray(weightArray, 'float')

        // Color buffer
        const colorA = uniform(color(0x95513a))// 0x999257
        const colorB = uniform(color(0xf56a3a))// 0xcc8214
        const colorNode = Fn(() =>
        {
            const mixStrength = hash(instanceIndex.add(99))
            return vec3(mix(colorA, colorB, mixStrength))
        })()

        // Normal buffer
        const normalArray = new Float32Array(this.count * 3)
        for(let i = 0; i < this.count; i++)
        {
            const normal = new THREE.Vector3(0, 1, 0)
            normal.applyAxisAngle(new THREE.Vector3(1, 0, 0), (Math.random() - 0.5) * 2)
            normal.applyAxisAngle(new THREE.Vector3(0, 0, 1), (Math.random() - 0.5) * 2)
            normal.toArray(normalArray, i * 3)
        }
        const normalBuffer = instancedArray(normalArray, 'vec3').toAttribute()

        this.material = new MeshDefaultMaterial({
            side: THREE.DoubleSide,
            colorNode: colorNode,
            normalNode: normalWorld,
            hasWater: false,
            transparent: true
        })

        // Position
        this.material.positionNode = Fn(() =>
        {
            // Normal
            materialNormal.assign(modelViewMatrix.mul(vec4(normalBuffer, 0)))

            // Position
            const leavePosition = this.positionBuffer.toAttribute()

            const newPosition = positionGeometry.mul(scaleBuffer).mul(this.scale)

            const rotationMultiplier = max(leavePosition.y.mul(this.rotationElevationMultiplier), 0)
            
            const rotationZ = sin(leavePosition.x.mul(this.rotationFrequency)).mul(rotationMultiplier)
            const rotationX = sin(leavePosition.z.mul(this.rotationFrequency)).mul(rotationMultiplier)
            const rotationY = baseRotationBuffer

            newPosition.xy.assign(rotateUV(newPosition.xy, rotationZ, vec2(0)))
            newPosition.yz.assign(rotateUV(newPosition.yz, rotationX, vec2(0)))
            newPosition.xz.assign(rotateUV(newPosition.xz, rotationY, vec2(0)))

            return newPosition.add(leavePosition)
        })()

        this.size = float(this.game.view.optimalArea.radius * 2)

        // Init
        const init = Fn(() =>
        {
            // Position
            const position = this.positionBuffer.element(instanceIndex)
            
            position.assign(vec3(
                hash(instanceIndex).sub(0.5).mul(this.size),
                0,
                hash(instanceIndex.add(1)).sub(0.5).mul(this.size)
            ))

            const noiseUv = position.xz.mul(0.02)
            const noise = texture(this.game.noises.perlin, noiseUv).r
            position.x.addAssign(noise.mul(15))
        })()
        const initCompute = init.compute(this.count)

        this.game.rendering.renderer.computeAsync(initCompute)

        // Update
        const update = Fn(() =>
        {
            const position = this.positionBuffer.element(instanceIndex)
            const velocity = this.velocityBuffer.element(instanceIndex)
            const weight = weightBuffer.element(instanceIndex)

            // Terrain
            // const terrainUv = this.game.terrain.worldPositionToUvNode(position.xz)
            const terrainData = this.game.terrain.terrainNode(position.xz)
            
            // Wind
            const noiseUv = position.xz.mul(this.windFrequency).add(this.game.wind.direction.mul(this.game.wind.localTime)).xy
            const noise = texture(this.game.noises.perlin, noiseUv).r

            const windStrength = this.game.wind.strength.sub(noise).mul(weight).mul(this.windMultiplier).max(0)
            velocity.x.addAssign(this.game.wind.direction.x.mul(windStrength))
            velocity.z.addAssign(this.game.wind.direction.y.mul(windStrength))

            // Upward fly
            const upwardDim = position.y.remapClamp(0, 6, 1, 0)
            velocity.y = velocity.xz.length().min(2).mul(this.upwardMultiplier).mul(upwardDim)

            // Damping
            const groundDamping = terrainData.b.remapClamp(0.4, 0, this.waterDamping, this.defaultDamping) // Low on water
            const inTheAirDamping = step(0.05, position.y).mul(this.defaultDamping) // High in the air
            const damping = max(groundDamping, inTheAirDamping).mul(this.game.ticker.deltaScaledUniform)
            velocity.mulAssign(float(1).sub(damping))

            // Gravity
            velocity.y = velocity.y.sub(this.gravity.mul(weight))

            // Apply velocity
            position.addAssign(velocity.mul(this.game.ticker.deltaScaledUniform))

            // Clamp to floor / water
            const floorY = terrainData.b.remapClamp(0.02, 0.13, 0, this.game.water.surfaceElevationUniform).add(0.02)
            position.y.assign(max(position.y, floorY))

            // Loop
            const halfSize = this.size.mul(0.5)
            position.x.assign(mod(position.x.add(halfSize).sub(this.focusPoint.x), this.size).sub(halfSize).add(this.focusPoint.x))
            position.z.assign(mod(position.z.add(halfSize).sub(this.focusPoint.y), this.size).sub(halfSize).add(this.focusPoint.y))
        })()
        this.updateCompute = update.compute(this.count)

        // Debug
        if(this.game.debug.active)
        {
            this.game.debug.addThreeColorBinding(this.debugPanel, colorA.value, 'colorA')
            this.game.debug.addThreeColorBinding(this.debugPanel, colorB.value, 'colorB')
            this.debugPanel.addBinding(this.scale, 'value', { label: 'scale', min: 0, max: 1, step: 0.001 })
            this.debugPanel.addBinding(this.scale, 'value', { label: 'scale', min: 0, max: 1, step: 0.001 })
            this.debugPanel.addBinding(this.rotationFrequency, 'value', { label: 'rotationFrequency', min: 0, max: 20, step: 0.001 })
            this.debugPanel.addBinding(this.rotationElevationMultiplier, 'value', { label: 'rotationElevationMultiplier', min: 0, max: 2, step: 0.001 })
            this.debugPanel.addBinding(this.pushSidewaysMultiplier, 'value', { label: 'pushSidewaysMultiplier', min: 0, max: 300, step: 1 })
            this.debugPanel.addBinding(this.pushMultiplier, 'value', { label: 'pushMultiplier', min: 0, max: 300, step: 1 })
            this.debugPanel.addBinding(this.windFrequency, 'value', { label: 'windFrequency', min: 0, max: 0.02, step: 0.00001 })
            this.debugPanel.addBinding(this.windMultiplier, 'value', { label: 'windMultiplier', min: 0, max: 10, step: 0.0001 })
            this.debugPanel.addBinding(this.upwardMultiplier, 'value', { label: 'upwardMultiplier', min: 0, max: 10, step: 0.01 })
            this.debugPanel.addBinding(this.defaultDamping, 'value', { label: 'defaultDamping', min: 0, max: 10, step: 0.01 })
            this.debugPanel.addBinding(this.waterDamping, 'value', { label: 'waterDamping', min: 0, max: 10, step: 0.01 })
            this.debugPanel.addBinding(this.gravity, 'value', { label: 'gravity', min: 0, max: 20, step: 0.01 })
        }
    }

    setMesh()
    {
        this.mesh = new THREE.Mesh(this.geometry, this.material)
        this.mesh.count = this.count
        this.mesh.frustumCulled = false
        this.mesh.castShadow = true
        this.mesh.receiveShadow = true
        this.mesh.renderOrder = 2
        this.game.scene.add(this.mesh)
    }

    update()
    {
        this.focusPoint.value.set(this.game.view.optimalArea.position.x, this.game.view.optimalArea.position.z)

        this.game.rendering.renderer.computeAsync(this.updateCompute)

    }
}
