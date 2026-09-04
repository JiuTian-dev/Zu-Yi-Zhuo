import * as THREE from 'three/webgpu'
import { Game } from './Game.js'
import MeshGridMaterial, { MeshGridMaterialLine } from './Materials/MeshGridMaterial.js'
import { color, Fn, max, mix, round, smoothstep, texture, uniform, uv, vec2 } from 'three/tsl'

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
        const coveInnerRadius = vec2(4.28, 3.72)
        const coveOuterRadius = vec2(10.8, 8.85)
        const bridgeDirection = vec2(Math.cos(2.36), Math.sin(2.36))
        const productWaterCoveNode = Fn(([position]) =>
        {
            const local = position.sub(this.productWaterAnchor)
            const innerDistance = local.div(coveInnerRadius).length()
            const outerDistance = local.div(coveOuterRadius).length()
            const shorelineNoise = texture(this.game.noises.perlin, local.mul(0.075)).r
                .sub(0.5)
                .mul(0.055)

            // Keep a soft, irregular annulus around the table island.
            const outerInside = smoothstep(0.87, 1.0, outerDistance.add(shorelineNoise)).oneMinus()
            const innerOutside = smoothstep(0.94, 1.05, innerDistance.add(shorelineNoise.mul(0.6)))
            const radialLength = local.length().max(0.001)
            const bridgeAlignment = local.dot(bridgeDirection).div(radialLength)
            const bridgeGap = smoothstep(0.59, 0.73, bridgeAlignment)
            const coveMask = outerInside.mul(innerOutside).mul(bridgeGap.oneMinus())

            // B is the same depth channel consumed by Floor and WaterSurface.
            // The shallow inner edge crosses the native shore threshold, then
            // deepens toward the outer bank without hard color bands.
            const depthGradient = smoothstep(0.42, 0.98, outerDistance)
            const coveDepth = mix(0.12, 0.74, depthGradient).mul(coveMask)

            return vec2(coveMask, coveDepth)
        })

        this.terrainNode = Fn(([position]) =>
        {
            const textureUv = worldPositionToUvNode(position)
            const sourceData = texture(this.game.resources.terrainTexture, textureUv)
            const data = sourceData.toVar()
            const productWaterCove = productWaterCoveNode(position)

            // Preserve the Bruno texture everywhere else. The product mask
            // only adds water depth and removes grass inside the cove.
            data.b.assign(max(sourceData.b, productWaterCove.y))
            data.g.assign(sourceData.g.mul(productWaterCove.x.oneMinus()))

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
