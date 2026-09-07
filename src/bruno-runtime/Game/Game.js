/** @origin BRUNO-ADAPTED — folio-2025@41046b5 environment composition. */
import './threejs-override.js'
import * as THREE from 'three/webgpu'
import { color, uniform } from 'three/tsl'
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
import { YearCycles } from './Cycles/YearCycles.js'
import { Noises } from './Noises.js'
import { Wind } from './Wind.js'
import { Weather } from './Weather.js'
import { Terrain } from './Terrain.js'
import { Water } from './Water.js'
import { Quality } from './Quality.js'
import { World } from './World/World.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { KTX2Loader } from 'three/examples/jsm/loaders/KTX2Loader.js'
import { CameraOrbit } from './CameraOrbit.js'
import { SceneBridge } from '../SceneBridge.js'

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
        this.ready = this.init()
    }

    async init()
    {
        this.domElement = document.querySelector('.bruno-runtime-canvas')
        this.canvasElement = this.domElement?.querySelector('.js-canvas')
        if(!this.domElement || !this.canvasElement)
            throw new Error('BrunoRuntime requires .bruno-runtime-canvas and .js-canvas')

        this.scene = new THREE.Scene()
        this.debug = new Debug()
        this.quality = new Quality()
        this.ticker = new Ticker()
        this.time = new Time()
        this.dayCycles = new DayCycles()
        this.yearCycles = new YearCycles()
        this.viewport = new Viewport(this.domElement)
        this.rendering = new Rendering()
        await this.rendering.setRenderer()

        if(this.destroyed)
            return

        // BRUNO ASSET PIPELINE — areas-compressed.glb uses KTX2/Basis textures.
        // Keep the decoder local to the runtime; no product state or gameplay
        // dependency is introduced by this asset compatibility layer.
        this.ktx2Loader = new KTX2Loader()
        this.ktx2Loader.setTranscoderPath('/assets/bruno-runtime/basis/')
        this.ktx2Loader.detectSupport(this.rendering.renderer)

        this.resources = await this.loadResources()
        if(this.destroyed)
        {
            this.disposeResources()
            return
        }

        this.view = new View()
        this.cameraOrbit = new CameraOrbit(this, this.view.camera, this.view.focusPoint.position)

        // Reveal is kept as a render-system input only. It has no product behavior.
        this.reveal = {
            position2Uniform: uniform(new THREE.Vector2()),
            // The original intro Reveal started at -1 during boot. Product
            // runtime has no intro gate, so all scene pixels
            // must be visible from the first frame.
            distance: uniform(9999),
            thickness: uniform(0),
            color: uniform(color('#ffffff')),
            intensity: uniform(0),
        }
        this.noises = new Noises()
        this.weather = new Weather()
        this.wind = new Wind()
        this.lighting = new Lighting()
        this.fog = new Fog()
        this.water = new Water()
        this.materials = new Materials()
        this.terrain = new Terrain()
        this.rendering.setPostprocessing()
        this.rendering.start()
        this.world = new World()
        this.sceneBridge = new SceneBridge(this)

        this.initialized = true
        this.domElement.dataset.runtimeState = 'ready'
    }

    loadTexture(path, { colorSpace = THREE.NoColorSpace, repeat = false, flipY = true, mipmaps = false } = {})
    {
        return new Promise((resolve, reject) =>
        {
            new THREE.TextureLoader().load(path, (texture) =>
            {
                texture.colorSpace = colorSpace
                texture.minFilter = mipmaps ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter
                texture.magFilter = THREE.LinearFilter
                texture.generateMipmaps = mipmaps
                texture.anisotropy = mipmaps ? 4 : 1
                texture.flipY = flipY
                if(repeat)
                {
                    texture.wrapS = THREE.RepeatWrapping
                    texture.wrapT = THREE.RepeatWrapping
                }
                texture.needsUpdate = true
                resolve(texture)
            }, undefined, reject)
        })
    }

    loadGLTF(path)
    {
        return new Promise((resolve, reject) =>
        {
            const loader = new GLTFLoader()
            const draco = new DRACOLoader()
            draco.setDecoderPath('/assets/bruno-runtime/draco/')
            loader.setDRACOLoader(draco)
            loader.setKTX2Loader(this.ktx2Loader)
            loader.load(path, (gltf) =>
            {
                draco.dispose()
                resolve(gltf)
            }, undefined, (error) =>
            {
                draco.dispose()
                reject(error)
            })
        })
    }

    async loadResources()
    {
        const base = '/assets/bruno-runtime/'
        const alpineEnabled = new URLSearchParams(location.search).get('landscape') === 'alpine'
        const [
            paletteTexture,
            floorSlabsTexture,
            foliageTexture,
            terrainTexture,
            terrainModel,
            flowersReferencesModel,
            bushesReferences,
            birchTreesVisualModel,
            birchTreesReferencesModel,
            oakTreesVisualModel,
            oakTreesReferencesModel,
            cherryTreesVisualModel,
            cherryTreesReferencesModel,
            sceneryModel,
            poleLightsModel,
            lanternsModel,
            fencesModel,
            benchesModel,
            bricksModel,
            areasModel,
            alpineModel,
            alpineLodModel,
            alpineSnowTexture,
            alpineSnowNormal,
        ] = await Promise.all([
            this.loadTexture(`${base}palette.png`, { colorSpace: THREE.SRGBColorSpace }),
            this.loadTexture(`${base}floor/slabs.png`, { colorSpace: THREE.SRGBColorSpace, repeat: true }),
            this.loadTexture(`${base}foliage/foliageSDF.png`),
            this.loadTexture(`${base}terrain/terrain.png`, { flipY: false }),
            this.loadGLTF(`${base}terrain/terrain.glb`),
            this.loadGLTF(`${base}flowers/flowersReferences.glb`),
            this.loadGLTF(`${base}bushes/bushesReferences.glb`),
            this.loadGLTF(`${base}birchTrees/birchTreesVisual.glb`),
            this.loadGLTF(`${base}birchTrees/birchTreesReferences.glb`),
            this.loadGLTF(`${base}oakTrees/oakTreesVisual.glb`),
            this.loadGLTF(`${base}oakTrees/oakTreesReferences.glb`),
            this.loadGLTF(`${base}cherryTrees/cherryTreesVisual.glb`),
            this.loadGLTF(`${base}cherryTrees/cherryTreesReferences.glb`),
            this.loadGLTF(`${base}scenery/scenery.glb`),
            this.loadGLTF(`${base}poleLights/poleLights.glb`),
            this.loadGLTF(`${base}lanterns/lanterns.glb`),
            this.loadGLTF(`${base}fences/fences.glb`),
            this.loadGLTF(`${base}benches/benches.glb`),
            this.loadGLTF(`${base}bricks/bricks.glb`),
            this.loadGLTF(`${base}areas/areas-compressed.glb`),
            alpineEnabled ? this.loadGLTF(`${base}alpine/dem/${new URLSearchParams(location.search).get('alpine') === 'matterhorn' ? 'matterhorn' : 'eiger'}-ridge-compressed.glb`) : null,
            alpineEnabled ? this.loadGLTF(`${base}alpine/dem/${new URLSearchParams(location.search).get('alpine') === 'matterhorn' ? 'matterhorn' : 'eiger'}-ridge-lod-compressed.glb`) : null,
            alpineEnabled ? this.loadTexture(`${base}alpine/snow-02-2k/snow_02_diff_2k.jpg`, { colorSpace: THREE.SRGBColorSpace, repeat: true, mipmaps: true }) : null,
            alpineEnabled ? this.loadTexture(`${base}alpine/snow-02-2k/snow_02_nor_gl_2k.jpg`, { repeat: true, mipmaps: true }) : null,
        ])

        return {
            paletteTexture,
            floorSlabsTexture,
            foliageTexture,
            terrainTexture,
            terrainModel,
            flowersReferencesModel,
            bushesReferences,
            birchTreesVisualModel,
            birchTreesReferencesModel,
            oakTreesVisualModel,
            oakTreesReferencesModel,
            cherryTreesVisualModel,
            cherryTreesReferencesModel,
            sceneryModel,
            poleLightsModel,
            lanternsModel,
            fencesModel,
            benchesModel,
            bricksModel,
            areasModel,
            alpineModel,
            alpineLodModel,
            alpineSnowTexture,
            alpineSnowNormal,
        }
    }

    setTableTarget(target, options = {})
    {
        if(this.cameraOrbit?.focusTable)
            return this.cameraOrbit.focusTable(target, options)
        this.view?.setTarget?.(target)
        this.cameraOrbit?.setTarget?.(target)
        return Promise.resolve()
    }

    disposeResources()
    {
        Object.values(this.resources ?? {}).forEach((resource) => resource?.dispose?.())
        this.resources = null
    }

    destroy()
    {
        if(this.destroyed)
            return
        this.destroyed = true
        this.cameraOrbit?.destroy?.()
        this.sceneBridge?.destroy?.()
        this.view?.destroy?.()
        this.viewport?.destroy?.()
        this.rendering?.destroy?.()
        this.world?.distantLandscape?.destroy?.()
        this.scene?.traverse((object) =>
        {
            object.geometry?.dispose?.()
        })
        this.disposeResources()
        Game.instance = null
    }
}
