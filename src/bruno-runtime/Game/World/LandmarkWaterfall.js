/** @origin BRUNO-ADAPTED — AchievementsArea.setWaterfall from folio-2025.
 * Original water/foam shaders and spray trajectory; all coordinates stay inside
 * the authored landmark root. No achievements, triggers or audio dependencies. */
import * as THREE from 'three/webgpu'
import { color, cos, float, Fn, instancedArray, instanceIndex, min, mix, positionGeometry, sin, texture, uniform, uv, vec2, vec3 } from 'three/tsl'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'

export class LandmarkWaterfall
{
    constructor(game, root)
    {
        this.game = game
        this.root = root
        this.references = { items: new Map() }
        for(const key of ['waterfallStill', 'waterfallDrop', 'waterfallParticles'])
        {
            const mesh = root.getObjectByName('product-' + key)
            if(!mesh) throw new Error('Missing original waterfall mesh: ' + key)
            this.references.items.set(key, [mesh])
        }
        this.setWaterfall()
    }
    setWaterfall()
    {
        const waterColorA = uniform(color(this.game.terrain.colors[1].value))
        const waterColorB = uniform(color(this.game.terrain.colors[2].value))

        // Still color and foam
        {
            const colorNode = Fn(() =>
            {
                const baseUv = uv().toVar()
                const baseColor = color()

                // Water color
                {
                    const xMix = baseUv.x.sub(0.5).mul(2).abs().pow3().max(0)
                    
                    const waterColor = mix(waterColorB, waterColorA, xMix)
                    baseColor.assign(waterColor)
                }

                // Foam
                {
                    const newUv = baseUv.toVar()
                    newUv.x.assign(newUv.x.sub(0.5).abs().mul(2))
                    const uv3 = newUv.sub(vec2(this.game.ticker.elapsedScaledUniform.mul(0.05), 0)).mul(vec2(0.35, 0.96))
                    const noise3 = texture(this.game.noises.voronoi, uv3).r

                    const uv4 = newUv.sub(vec2(this.game.ticker.elapsedScaledUniform.mul(0.041), 0)).mul(vec2(0.75, 1.28))
                    const noise4 = texture(this.game.noises.voronoi, uv4).r

                    const noiseFinal = min(noise3, noise4)
                    const stepTreshold = baseUv.x.sub(0.5).abs().mul(2).add(0.5).mul(0.5).oneMinus()
                    const foamMix = noiseFinal.step(stepTreshold)

                    baseColor.assign(mix(baseColor, color('#ffffff'), foamMix))
                }

                return vec3(baseColor)
            })()
            const material = new MeshDefaultMaterial({
                colorNode: colorNode,
                hasLightBounce: false,
                hasWater: false,
                hasReveal: false,
                side: THREE.DoubleSide
            })
            const mesh = this.references.items.get('waterfallStill')[0]
            mesh.material = material
        }

        // Drop foam
        {
            const colorNode = Fn(() =>
            {
                const baseUv = uv().toVar()

                // Foam
                {
                    const uv3 = baseUv.sub(vec2(0, this.game.ticker.elapsedScaledUniform.mul(0.11))).mul(vec2(0.7, 0.6))
                    const noise3 = texture(this.game.noises.voronoi, uv3).r

                    const uv4 = baseUv.sub(vec2(0, this.game.ticker.elapsedScaledUniform.mul(0.085))).mul(vec2(1.5, 0.8))
                    const noise4 = texture(this.game.noises.voronoi, uv4).r

                    const noiseFinal = min(noise3, noise4)
                    const stepTreshold = baseUv.y.sub(0.5).abs().mul(2).add(0.5).mul(0.5)
                    noiseFinal.lessThan(stepTreshold).discard()
                }


                return vec3(1)
            })()
            const material = new MeshDefaultMaterial({
                colorNode: colorNode,
                hasLightBounce: false,
                hasWater: false,
                hasReveal: false,
                side: THREE.DoubleSide
            })
            const mesh = this.references.items.get('waterfallDrop')[0]
            mesh.material = material
        }

        // Particles
        {
            const reference = this.references.items.get('waterfallParticles')[0]
            reference.removeFromParent()
            
            const origin = new THREE.Vector3(
                reference.geometry.attributes.position.array[0],
                reference.geometry.attributes.position.array[1],
                reference.geometry.attributes.position.array[2]
            )
            const destination = new THREE.Vector3(
                reference.geometry.attributes.position.array[3],
                reference.geometry.attributes.position.array[4],
                reference.geometry.attributes.position.array[5]
            )
            origin.applyMatrix4(reference.matrix)
            destination.applyMatrix4(reference.matrix)

            const length = origin.distanceTo(destination)
            const delta = destination.clone().sub(origin)

            const count = 100
            const positions = new Float32Array(count * 3)
            const angles = new Float32Array(count)

            for(let i = 0; i < count; i++)
            {
                positions[i * 3 + 0] = 0
                positions[i * 3 + 1] = 0
                positions[i * 3 + 2] = length * Math.random()

                angles[i] = Math.PI - Math.PI * 0.5 * Math.random()
            }

            const positionAttribute = instancedArray(positions, 'vec3').toAttribute()
            const angleAttribute = instancedArray(angles, 'float').toAttribute()
            
            const material = new MeshDefaultMaterial({
                hasLightBounce: false,
                hasWater: false,
                hasReveal: false,
                side: THREE.DoubleSide,
                alphaTest: 0.1,
            
            })

            material.positionNode = Fn(() =>
            {
                const progress = this.game.ticker.elapsedScaledUniform.mul(0.2).add(float(instanceIndex).div(count)).fract()
                
                const scale = progress.oneMinus().mul(0.4)
                const newPositionGeometry = positionGeometry.toVar().mul(scale)

                const finalPosition = newPositionGeometry.add(positionAttribute).toVar()

                const distance = progress.oneMinus().pow2().oneMinus()
                finalPosition.y.addAssign(sin(angleAttribute).mul(distance).mul(2))
                finalPosition.x.addAssign(cos(angleAttribute).mul(distance).mul(1.5))
                return finalPosition
            })()

            material._alphaNode = Fn(() =>
            {
                const distanceToCenter = uv().sub(0.5).length().oneMinus().sub(0.5)
                return distanceToCenter
            })()

            const geometry = new THREE.PlaneGeometry(1, 1)
            geometry.rotateY(-Math.PI * 0.5)
            geometry.rotateZ(-Math.PI * 0.25)

            const mesh = new THREE.InstancedMesh(
                geometry,
                material,
                count
            )
            mesh.receiveShadow = true
            mesh.castShadow = true
            mesh.lookAt(delta.multiplyScalar(-1))
            mesh.position.copy(destination)
            mesh.count = count
            this.root.add(mesh)
            mesh.name = 'product-waterfall-spray'
            mesh.frustumCulled = false
        }
    }

}
