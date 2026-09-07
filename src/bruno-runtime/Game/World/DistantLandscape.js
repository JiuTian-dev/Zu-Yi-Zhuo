/** @origin ZUOYIZHUO-SCENE — forest-side alpine ridges, open seaward horizon. */
import * as THREE from 'three/webgpu'
import { color, mix, normalWorld, positionWorld, texture, vec2, vec3, vec4 } from 'three/tsl'
import { Game } from '../Game.js'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'
import { TABLE_ANCHORS } from '../tableAnchors.js'
import { LANDSCAPE } from '../landscapeLayout.js'
import { AlpineClouds } from './AlpineClouds.js'
import { ALPINE_STREAM, alpineStreamX } from '../alpineStream.js'

// Continuous transverse slopes, tapered into the terrain at both ends.
function ridgeGeometry(centre, radius, depth, height, span, phase)
{
    const segments = 112
    const rows = 18
    const vertices = []
    const indices = []
    const direction = Math.atan2(LANDSCAPE.seaDirection.z, LANDSCAPE.seaDirection.x) + Math.PI
    for(let row = 0; row <= rows; row++)
    {
        const v = row / rows
        for(let i = 0; i <= segments; i++)
        {
            const u = i / segments
            const angle = direction + (u - 0.5) * span
            const r = radius + v * depth + Math.sin(angle * 7 + phase) * 2.5
            const envelope = Math.pow(Math.sin(u * Math.PI), 0.7)
            const peaks = 0.55 + 0.23 * Math.sin(u * 19 + phase) + 0.13 * Math.sin(u * 41 + 0.4)
            const crest = 0.56 + Math.sin(u * 13 + phase) * 0.09
            const slope = Math.max(0, 1 - Math.abs(v - crest) / (v < crest ? crest : 1 - crest))
            const erosion = Math.sin(u * 171 + v * 15) * Math.sin(v * Math.PI) * 0.6
            const x = Math.cos(angle) * r, z = Math.sin(angle) * r
            let y = -2 + Math.pow(slope, 1.25) * (height * peaks + erosion) * envelope
            if(z > ALPINE_STREAM.startZ - 8 && z < ALPINE_STREAM.endZ)
            {
                const bank = THREE.MathUtils.smoothstep(Math.abs(x - alpineStreamX(z)), 2, 10)
                y = THREE.MathUtils.lerp(-2, y, bank)
            }
            vertices.push(centre.x + x, y, centre.z + z)
            if(row < rows && i < segments)
            {
                const a = row * (segments + 1) + i
                const b = a + segments + 1
                indices.push(a, a + 1, b, a + 1, b + 1, b)
            }
        }
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
    geometry.setIndex(indices)
    geometry.computeVertexNormals()
    return geometry
}

export class DistantLandscape
{
    constructor(flowers)
    {
        const game = Game.getInstance()
        const centre = TABLE_ANCHORS.valley
        this.group = new THREE.Group()
        if(new URLSearchParams(location.search).get('landscape') !== 'alpine')
        {
            this.group.name = 'product-island-horizon'
            for(const [x, z, width, height, depth] of [[-74, -88, 17, 3.2, 9], [96, -58, 12, 2.1, 7]])
            {
                const geometry = new THREE.SphereGeometry(1, 32, 12)
                const material = new MeshDefaultMaterial({
                    colorNode: mix(game.terrain.grassColorUniform, game.fog.color, 0.72),
                    hasWater: false, hasReveal: false, hasDropShadows: false,
                    hasLightBounce: false,
                })
                const island = new THREE.Mesh(geometry, material)
                island.name = 'product-distant-island'
                island.scale.set(width, height, depth)
                island.position.set(centre.x + x, -1, centre.z + z)
                this.group.add(island)
            }
            game.scene.add(this.group)
            return
        }
        this.group.name = 'product-mountain-horizon'
        const layers = [
            { radius: 68, depth: 62, height: 28, span: 2.6, phase: 0.3, snow: true, tint: '#707e91' },
            { radius: 48, depth: 65, height: 12, span: 2.85, phase: 1.6, snow: false, tint: '#52752c' },
        ]
        const legacy = new URLSearchParams(location.search).get('alpine') === 'legacy'
        for(const layer of layers.filter(layer => legacy || !layer.snow))
        {
            const noise = texture(game.noises.perlin, positionWorld.xz.mul(0.06)).r
            const rock = mix(game.terrain.grassColorUniform.mul(0.72), game.terrain.grassColorUniform, noise)
            const snowLine = positionWorld.y.add(noise.mul(3)).smoothstep(9, 15)
                .mul(normalWorld.y.smoothstep(0.25, 0.65))
            const material = new MeshDefaultMaterial({
                colorNode: layer.snow ? mix(rock, color('#f1f3f1'), snowLine) : rock,
                hasFog: false, hasWater: false, hasLightBounce: false,
                hasDropShadows: false, hasReveal: false, side: THREE.DoubleSide,
            })
            // Dedicated falloff keeps peaks visible beyond the near-scene fog.
            const lit = material.outputNode
            const distance = positionWorld.xz.sub(vec2(centre.x, centre.z)).length()
            const haze = distance.smoothstep(45, 190).mul(0.4).add(0.08)
            material.outputNode = vec4(mix(lit.rgb, game.fog.color, haze), 1)
            const mesh = new THREE.Mesh(ridgeGeometry(centre, layer.radius, layer.depth,
                layer.height, layer.span, layer.phase), material)
            mesh.name = layer.snow ? 'product-snow-ridge' : 'product-woodland-foothills'
            this.group.add(mesh)
            if(!layer.snow) this.addMeadowFlowers(mesh.geometry, game, flowers)
        }
        if(!legacy)
        {
            const noise = texture(game.noises.perlin, positionWorld.xz.mul(0.045)).r
            const weights = normalWorld.abs().pow(4)
            const blend = weights.div(weights.x.add(weights.y).add(weights.z).max(0.001))
            const detail = texture(game.resources.alpineSnowTexture, positionWorld.zy.mul(0.12)).rgb.mul(blend.x)
                .add(texture(game.resources.alpineSnowTexture, positionWorld.xz.mul(0.12)).rgb.mul(blend.y))
                .add(texture(game.resources.alpineSnowTexture, positionWorld.xy.mul(0.12)).rgb.mul(blend.z))
            // Broad snowfields with a few exposed steep faces, not a rock wall.
            const snow = positionWorld.y.add(noise.mul(4)).smoothstep(-2, 5)
                .mul(normalWorld.y.add(noise.mul(0.16)).smoothstep(-0.1, 0.22).mul(0.22).add(0.78))
            // This material consumes world normals, not tangent/view normals.
            // Project snow micro-relief into the horizontal world plane, then
            // blend gently so the measured ridge normals still define relief.
            const micro = texture(game.resources.alpineSnowNormal, positionWorld.xz.mul(0.07)).xy.mul(2).sub(1)
            const surfaceNormal = normalWorld.add(vec3(micro.x, 0, micro.y.negate()).mul(snow.mul(0.12))).normalize()
            const rock = mix(color('#414d60'), color('#85909e'), noise)
            const baseColor = mix(rock, color('#f4f6fa').mul(detail.r.mul(0.35).add(0.65)), snow)
            const material = new MeshDefaultMaterial({
                colorNode: baseColor,
                normalNode: surfaceNormal,
                hasFog: false, hasWater: false, hasLightBounce: false,
                hasDropShadows: false, hasReveal: false,
            })
            const lit = material.outputNode
            const distance = positionWorld.xz.sub(vec2(centre.x, centre.z)).length()
            const haze = distance.smoothstep(110, 280).mul(0.15).add(0.025)
                .add(positionWorld.y.smoothstep(-5, 12).oneMinus().mul(0.25)).clamp(0, 0.8)
            const alpineLight = surfaceNormal.dot(game.lighting.directionUniform).max(0).mul(0.32).add(0.88)
            const ambient = baseColor.mul(mix(color('#dce6f2'), game.lighting.colorUniform, 0.12))
                .mul(alpineLight)
            // The original night light is deliberately intense for the nearby
            // stylized scene. Snow must stay moonlit rather than bloom like neon.
            const exposure = game.lighting.intensityUniform.max(1.2).reciprocal().mul(1.2)
            material.outputNode = vec4(mix(mix(lit.rgb, ambient, snow.mul(0.94)).mul(exposure), game.fog.color, haze), 1)
            const lod = new THREE.LOD()
            for(const [resource, threshold] of [[game.resources.alpineModel, 0], [game.resources.alpineLodModel, 180]])
            {
                const model = resource.scene
                model.traverse(object => {
                    if(object.isMesh)
                    {
                        object.material.dispose()
                        object.material = material
                    }
                })
                lod.addLevel(model, threshold, 0.05)
            }
            lod.name = 'product-dem-snow-ridge'
            lod.position.set(centre.x - LANDSCAPE.seaDirection.x * 130, -3,
                centre.z - LANDSCAPE.seaDirection.z * 130)
            lod.rotation.y = Math.atan2(LANDSCAPE.seaDirection.x, LANDSCAPE.seaDirection.z)
            this.group.add(lod)
            this.clouds = new AlpineClouds(game, lod.position)
            this.group.add(this.clouds.mesh)
        }
        game.scene.add(this.group)
    }

    // Small flower patches follow actual hillside triangles, never the water
    // or table floor. Instancing keeps this distant dressing to one draw call.
    addMeadowFlowers(geometry, game, flowers)
    {
        const positions = geometry.attributes.position
        const indices = geometry.index
        const material = new MeshDefaultMaterial({ colorNode: color('#ffffff'), side: THREE.DoubleSide,
            hasWater: false, hasDropShadows: false, hasReveal: false })
        const transforms = []
        const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3()
        const object = new THREE.Object3D()
        for(let i = 0; i < indices.count; i += 9)
        {
            a.fromBufferAttribute(positions, indices.getX(i))
            b.fromBufferAttribute(positions, indices.getX(i + 1))
            c.fromBufferAttribute(positions, indices.getX(i + 2))
            const point = a.clone().add(b).add(c).multiplyScalar(1 / 3)
            if(point.y < 0.2 || Math.sin(point.x * 0.45) * Math.cos(point.z * 0.36) < 0.4) continue
            object.position.copy(point).add(new THREE.Vector3(0, 0.16, 0))
            object.scale.setScalar(0.85)
            object.updateMatrix()
            transforms.push(object.matrix.clone())
        }
        const mesh = new THREE.InstancedMesh(flowers.geometry.clone(), material, transforms.length)
        transforms.forEach((matrix, index) => mesh.setMatrixAt(index, matrix))
        mesh.name = 'product-alpine-meadow-flowers'
        this.group.add(mesh)
    }

    destroy()
    {
        this.clouds?.destroy()
        const materials = new Set()
        this.group.traverse(object => {
            if(object.isMesh && object !== this.clouds?.mesh)
            {
                materials.add(object.material)
                object.geometry.dispose()
            }
        })
        materials.forEach(material => material.dispose())
    }
}
