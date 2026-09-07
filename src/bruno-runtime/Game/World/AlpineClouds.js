/** @origin ZUOYIZHUO-SCENE — bounded density ray march, no cloud meshes or product effects. */
import * as THREE from 'three/webgpu'
import { Fn, Loop, float, vec3, vec4, positionWorld, positionView, cameraPosition, texture3D, mix, color,
    cameraNear, cameraFar, viewportDepthTexture, perspectiveDepthToViewZ } from 'three/tsl'
import { LANDSCAPE } from '../landscapeLayout.js'
import { ImprovedNoise } from 'three/addons/math/ImprovedNoise.js'

export class AlpineClouds
{
    constructor(game, mountainPosition)
    {
        const centre = new THREE.Vector3(mountainPosition.x + LANDSCAPE.seaDirection.x * 42, 17,
            mountainPosition.z + LANDSCAPE.seaDirection.z * 42)
        const half = new THREE.Vector3(56, 8, 23)
        const steps = game.quality.level === 0 ? 40 : 20
        const stepLength = 124 / steps
        const size = 48
        const data = new Uint8Array(size ** 3)
        const noise = new ImprovedNoise()
        for(let z = 0; z < size; z++)
            for(let y = 0; y < size; y++)
                for(let x = 0; x < size; x++)
                {
                    const u = x / size * 5, v = y / size * 5, w = z / size * 5
                    const density = 0.5 + noise.noise(u, v, w) * 0.55
                        + noise.noise(u * 2, v * 2, w * 2) * 0.18
                        + noise.noise(u * 4, v * 4, w * 4) * 0.07
                    data[x + size * (y + size * z)] = Math.round(THREE.MathUtils.clamp(density, 0, 1) * 255)
                }
        this.densityTexture = new THREE.Data3DTexture(data, size, size, size)
        this.densityTexture.format = THREE.RedFormat
        this.densityTexture.minFilter = this.densityTexture.magFilter = THREE.LinearFilter
        this.densityTexture.unpackAlignment = 1
        this.densityTexture.needsUpdate = true
        const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false })
        material.outputNode = Fn(() =>
        {
            const ray = positionWorld.sub(cameraPosition).normalize()
            // Clip samples against opaque scene depth, so clouds cannot bleed
            // through a peak, the cherry tree, or the foreground architecture.
            const surfaceDistance = positionWorld.sub(cameraPosition).length()
            const viewCosine = positionView.z.negate().div(surfaceDistance).max(0.001)
            const sceneDistance = perspectiveDepthToViewZ(viewportDepthTexture(), cameraNear, cameraFar)
                .negate().div(viewCosine)
            const opacity = float(0).toVar()
            const illumination = float(0).toVar()
            const drift = game.ticker.elapsedUniform.mul(0.002)
            Loop(steps, ({ i }) =>
            {
                const travel = float(i).add(0.5).mul(stepLength)
                const p = positionWorld.add(ray.mul(travel))
                const local = p.sub(vec3(centre)).div(vec3(half))
                const bounds = vec3(1).sub(local.abs()).max(0)
                // Separate billows leave gaps across the ridge; the bounding
                // volume itself must never read as a rectangular fog sheet.
                const lobeA = local.sub(vec3(-0.52, -0.2, 0)).div(vec3(0.47, 0.52, 0.8)).length()
                const lobeB = local.sub(vec3(0.12, 0.25, -0.1)).div(vec3(0.35, 0.58, 0.72)).length()
                const lobeC = local.sub(vec3(0.65, -0.35, 0.1)).div(vec3(0.38, 0.35, 0.7)).length()
                const envelope = lobeA.min(lobeB).min(lobeC).smoothstep(0.3, 1).oneMinus()
                    .mul(bounds.x.mul(bounds.y).mul(bounds.z).smoothstep(0, 0.08))
                const cloudUV = local.mul(0.32).add(0.5)
                    .add(vec3(drift.sin().mul(0.08), 0, drift.cos().mul(0.06)))
                const cloud = texture3D(this.densityTexture, cloudUV).r
                const visible = sceneDistance.sub(surfaceDistance.add(travel)).smoothstep(0, 2)
                const density = cloud.smoothstep(0.35, 0.62)
                    .mul(envelope).mul(visible).mul(stepLength * 0.24).clamp(0, 0.85)
                const contribution = float(1).sub(opacity).mul(density)
                illumination.addAssign(contribution.mul(local.y.mul(0.2).add(0.8)))
                opacity.addAssign(contribution)
            })
            const shade = illumination.div(opacity.max(0.001))
            const tint = mix(game.fog.color, color('#edf2fa').mul(mix(color('#b8c9df'), game.lighting.colorUniform, 0.45))
                .mul(game.lighting.intensityUniform.min(1.2)), 0.82).mul(shade)
                .mul(game.lighting.intensityUniform.max(1.2).reciprocal().mul(1.2))
            return vec4(tint, opacity.mul(0.85))
        })()
        this.mesh = new THREE.Mesh(new THREE.BoxGeometry(half.x * 2, half.y * 2, half.z * 2), material)
        this.mesh.position.copy(centre)
        this.mesh.name = 'product-alpine-volume-clouds'
    }

    destroy()
    {
        this.densityTexture.dispose()
        this.mesh.material.dispose()
    }
}
