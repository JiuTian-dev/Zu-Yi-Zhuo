import './threejs-override.js'
import * as THREE from 'three/webgpu'

import { Debug } from './Debug.js'
import { Rendering } from './Rendering.js'
import { Ticker } from './Ticker.js'
import { Time } from './Time.js'
import { View } from './View.js'
import { Viewport } from './Viewport.js'
import { Lighting } from './Ligthing.js'
import { Materials } from './Materials.js'
import { Fog } from './Fog.js'
import { DayCycles } from './Cycles/DayCycles.js'
import { Noises } from './Noises.js'
import { Wind } from './Wind.js'
import { Terrain } from './Terrain.js'
import { Quality } from './Quality.js'
import { Water } from './Water.js'
import { Reveal } from './Reveal.js'
import { Weather } from './Weather.js'
import { TableWorld } from './World/World.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

export class Game
{
    static getInstance()
    {
        return Game.instance
    }

    constructor()
    {
        if(Game.instance)
            return Game.instance

        Game.instance = this
        this.destroyed = false

        this.init()
    }

    async init()
    {
        this.domElement = document.querySelector('.table-world-canvas')
        this.canvasElement = this.domElement?.querySelector('.js-canvas')

        this.scene = new THREE.Scene()
        this.debug = new Debug()
        this.quality = new Quality()
        this.ticker = new Ticker()
        this.time = new Time()
        this.dayCycles = new DayCycles()
        this.viewport = new Viewport(this.domElement)
        this.rendering = new Rendering()
        await this.rendering.setRenderer()
        if(this.destroyed)
        {
            this.rendering.renderer?.setAnimationLoop?.(null)
            this.rendering.renderer?.dispose?.()
            return
        }

        // Resources generated locally (palette + terrain data textures)
        this.resources = await this.buildResources()
        if(this.destroyed)
        {
            this.disposeResources()
            return
        }

        this.view = new View()
        this.rendering.setPostprocessing()
        this.rendering.start()
        this.reveal = new Reveal()
        this.noises = new Noises()
        this.weather = new Weather()
        this.wind = new Wind()
        this.lighting = new Lighting()
        this.fog = new Fog()
        this.water = new Water()
        this.materials = new Materials()
        this.terrain = new Terrain()
        this.world = new TableWorld()

        this.ticker.wait(2, () =>
        {
            this.reveal.updateStep?.(0)
        })
    }

    async buildResources()
    {
        // Project palette, sampled with nearest filtering for graphic color blocks.
        const paletteTexture = await new Promise((resolve) => {
            const image = new Image()
            image.onload = () => {
                const texture = new THREE.Texture(image)
                texture.colorSpace = THREE.SRGBColorSpace
                texture.minFilter = THREE.NearestFilter
                texture.magFilter = THREE.NearestFilter
                texture.generateMipmaps = false
                texture.needsUpdate = true
                resolve(texture)
            }
            image.src = '/assets/table-world/palette.png'
        })

        // Terrain data: R = spare, G = grass coverage, B = height/water
        const size = 256
        const data = new Uint8Array(size * size * 4)
        const cx = 0.5, cz = 0.5
        for(let y = 0; y < size; y++)
        {
            for(let x = 0; x < size; x++)
            {
                const i = (y * size + x) * 4
                const dx = (x / size - cx)
                const dz = (y / size - cz)
                const dist = Math.sqrt(dx * dx + dz * dz) * 2
                const noise = Math.sin(x * 0.11) * Math.cos(y * 0.13) * 0.08
                // meadow plateau: B high = warm ground, edges B low = water blue
                const meadow = Math.max(0, Math.min(1, 0.86 + noise - Math.max(0, dist - 0.62) * 2.2))
                const grass = meadow * (0.72 + noise * 0.5)
                data[i] = Math.round(grass * 255)
                data[i + 1] = Math.round(grass * 255)
                data[i + 2] = Math.round((1 - meadow) * 255)
                data[i + 3] = 255
            }
        }
        const terrainTexture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat)
        terrainTexture.needsUpdate = true
        terrainTexture.minFilter = THREE.LinearFilter
        terrainTexture.magFilter = THREE.LinearFilter
        terrainTexture.generateMipmaps = false

        const flowersReferencesModel = await new Promise((resolve) => {
            new GLTFLoader().load('/assets/table-world/flowers.glb', (gltf) => resolve(gltf), undefined, () => resolve({ scene: { children: [] } }))
        })

        return { paletteTexture, terrainTexture, floorSlabsTexture: paletteTexture, flowersReferencesModel }
    }

    disposeResources()
    {
        this.resources?.paletteTexture?.dispose?.()
        this.resources?.terrainTexture?.dispose?.()
        this.resources = null
    }

    destroy()
    {
        this.destroyed = true
        this.view?.destroy?.()
        this.viewport?.destroy?.()
        this.rendering?.renderer?.setAnimationLoop?.(null)
        this.rendering?.renderer?.dispose?.()
        this.scene?.traverse((object) =>
        {
            object.geometry?.dispose?.()
            if(Array.isArray(object.material))
                object.material.forEach((material) => material.dispose?.())
            else
                object.material?.dispose?.()
        })
        this.disposeResources()
        Game.instance = null
    }
}
