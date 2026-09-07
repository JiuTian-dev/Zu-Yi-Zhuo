import * as THREE from 'three/webgpu'
import { Game } from './Game.js'
import MeshGridMaterial, { MeshGridMaterialLine } from './Materials/MeshGridMaterial.js'
import { color, Fn, max, min, mix, round, smoothstep, texture, uniform, uv, vec2 } from 'three/tsl'
import { LANDSCAPE } from './landscapeLayout.js'
import { ALPINE_STREAM } from './alpineStream.js'

export class Terrain
{
    constructor()
    {
        this.game = Game.getInstance()

        this.subdivision = 128
        this.size = 192

        if(this.game.debug.active)
        {
            this.debugPanel = this.game.debug.panel.addFolder({
                title: '🏔️ Terrain Data',
                expanded: false,
            })
        }

        this.setGradient()
        this.setNodes()

        this.game.ticker.events.on('tick', () =>
        {
            this.update()
        }, 10)
    }

    setGradient()
    {
        const height = 16

        const canvas = document.createElement('canvas')
        canvas.width = 1
        canvas.height = height

        this.gradientTexture = new THREE.Texture(canvas)
        this.gradientTexture.colorSpace = THREE.SRGBColorSpace

        const context = canvas.getContext('2d')

        this.colors = [
            { stop: 0.1, value: '#ffa94e' },
            { stop: 0.3, value: '#5bc2b9' },
            { stop: 0.9, value: '#13375f' },
        ]

        const update = () =>
        {
            const gradient = context.createLinearGradient(0, 0, 0, height)
            for(const color of this.colors)
                gradient.addColorStop(color.stop, color.value)

            context.fillStyle = gradient
            context.fillRect(0, 0, 1, height)
            this.gradientTexture.needsUpdate = true
        }

        update()

        // // Debug
        // canvas.style.position = 'fixed'
        // canvas.style.zIndex = 999
        // canvas.style.top = 0
        // canvas.style.left = 0
        // canvas.style.width = '128px'
        // canvas.style.height = `256px`
        // document.body.append(canvas)
        
        if(this.game.debug.active)
        {
            for(const color of this.colors)
            {
                this.debugPanel.addBinding(color, 'stop', { min: 0, max: 1, step: 0.001 }).on('change', update)
                this.debugPanel.addBinding(color, 'value', { view: 'color' }).on('change', update)
            }
        }
    }

    setNodes()
    {
        this.grassColorUniform = uniform(color('#b8b62e'))
        const worldPositionToUvNode = Fn(([position]) =>
        {
            return position.div(this.subdivision).div(1.5).add(0.5)
        })

        // PRODUCT 3D — the table cove is a terrain projection, not a second
        // water renderer. The fixed anchor keeps the mask stable while the
        // camera orbits and the bridge-side opening remains dry.
        this.productWaterAnchor = uniform(new THREE.Vector2(
            this.game.view.focusPoint.position.x,
            this.game.view.focusPoint.position.z,
        ))
        this.seaDepthNode = Fn(([position]) =>
        {
            const local = position.sub(this.productWaterAnchor)
            const distance = local.dot(vec2(LANDSCAPE.seaDirection.x, LANDSCAPE.seaDirection.z))
                .add(local.x.mul(0.12).sin().mul(2.1))
                .add(local.y.mul(0.21).sin().mul(1.2))
            const islandDistance = local.length()
                .add(local.x.mul(0.14).sin().mul(2.5))
                .add(local.y.mul(0.19).sin().mul(1.8))
            return max(smoothstep(LANDSCAPE.coastStart, LANDSCAPE.coastDeep, distance),
                smoothstep(38, 49, islandDistance)).mul(0.94)
        })
        const productWaterCoveNode = Fn(([position]) =>
        {
            const local = position.sub(this.productWaterAnchor)
            // A lateral inlet joins the original river. The foreground and
            // bridge approach remain a broad connected peninsula, not an island.
            const inlet = local.sub(vec2(1.5, -8.8))
            const bend = inlet.x.mul(0.22).sin().mul(0.65)
            const distance = vec2(inlet.x, inlet.y.add(bend)).div(vec2(8.4, 3.4)).length()
            const shorelineNoise = texture(this.game.noises.perlin, local.mul(0.075)).r
                .sub(0.5)
                .mul(0.09)
            const coveMask = smoothstep(0.86, 1.0, distance.add(shorelineNoise)).oneMinus()
            const coveDepth = smoothstep(0.45, 1.0, distance.add(shorelineNoise)).oneMinus().mul(0.72)

            return vec2(coveMask, coveDepth)
        })

        this.terrainNode = Fn(([position]) =>
        {
            const textureUv = worldPositionToUvNode(position)
            const sourceData = texture(this.game.resources.terrainTexture, textureUv)
            const data = sourceData.toVar()
            const productWaterCove = productWaterCoveNode(position)
            const local = position.sub(this.productWaterAnchor)
            const seaDepth = this.seaDepthNode(position)
            const streamX = local.y.negate().sub(9).smoothstep(0, 25).mul(-20).sub(15)
                .add(local.y.add(9).mul(0.13).sin().mul(4))
            const streamDistance = local.x.sub(streamX).abs()
            const bankNoise = texture(this.game.noises.perlin, local.mul(0.16)).r
            const streamWidth = bankNoise.mul(0.65).add(ALPINE_STREAM.width)
            const streamEnds = local.y.smoothstep(ALPINE_STREAM.startZ, ALPINE_STREAM.startZ + 8)
                .mul(local.y.smoothstep(ALPINE_STREAM.endZ - 3, ALPINE_STREAM.endZ).oneMinus())
            const alpineEnabled = new URLSearchParams(location.search).get('landscape') === 'alpine'
            const streamDepth = streamDistance.div(streamWidth).smoothstep(0.12, 1).oneMinus()
                .mul(streamEnds).mul(alpineEnabled ? 0.5 : 0)
            // A soft vegetated bank replaces paving beside the tributary.
            // Fade before its mouth to preserve the existing table/bridge bank.
            const streamBank = streamDistance.div(streamWidth.add(3)).smoothstep(0.45, 1).oneMinus()
                .mul(streamEnds).mul(local.y.smoothstep(-22, -13).oneMinus()).mul(alpineEnabled ? 1 : 0)
            // Short tributary beside the ruin; tapers into the existing cove.
            const creekT = local.y.smoothstep(-18, -8)
            const creekX = creekT.mul(6).sub(6).add(creekT.mul(Math.PI * 2).sin().mul(1.2))
            const creekDistance = local.x.sub(creekX).abs()
            const creekEnds = local.y.smoothstep(-19, -16)
                .mul(local.y.smoothstep(-9, -7).oneMinus())
            const creekDepth = creekDistance.smoothstep(0.25, 1.4).oneMinus().mul(creekEnds).mul(0.55)
            // Keep the recovered landmark footprints clear of grass, including their steps.
            const landmarkMask = (landmark, width, depth) =>
            {
                const offset = local.sub(vec2(landmark.x, landmark.z))
                const cos = Math.cos(landmark.rotation), sin = Math.sin(landmark.rotation)
                const localBox = vec2(offset.x.mul(cos).sub(offset.y.mul(sin)),
                    offset.x.mul(sin).add(offset.y.mul(cos))).abs()
                return max(localBox.x.div(width), localBox.y.div(depth)).smoothstep(0.9, 1.12)
            }
            const landmarkClear = min(
                landmarkMask(LANDSCAPE.landmarks.waterfall, 4.5, 6.0),
                landmarkMask(LANDSCAPE.landmarks.bar, 3.2, 2.2),
            )

            // Preserve the Bruno texture everywhere else. The product mask
            // only adds water depth and removes grass inside the cove.
            data.b.assign(max(sourceData.b, productWaterCove.y, seaDepth, streamDepth, creekDepth))
            data.g.assign(max(sourceData.g, streamBank.mul(0.85)).mul(productWaterCove.x.oneMinus())
                .mul(smoothstep(0, 0.04, max(seaDepth, streamDepth, creekDepth)).oneMinus()).mul(landmarkClear))
            // Paving ends on the dry bank; the riverbed must not look flooded.
            data.r.assign(sourceData.r.mul(smoothstep(0.015, 0.12, data.b).oneMinus())
                .mul(streamBank.oneMinus()))

            return data
        })
        
        this.colorNode = Fn(([terrainData]) =>
        {
            // Dirt and water
            const baseColor = texture(this.gradientTexture, vec2(0, terrainData.b.oneMinus()))

            // Grass
            baseColor.assign(mix(baseColor, this.grassColorUniform, terrainData.g))

            return baseColor.rgb
        })

        if(this.game.debug.active)
        {
            this.game.debug.addThreeColorBinding(this.debugPanel, this.grassColorUniform.value, 'grassColor')
        }
    }
    
    update()
    {
    }
}
