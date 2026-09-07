import * as THREE from 'three/webgpu'
import { Game } from '../Game.js'
import { color, float, Fn, materialNormal, min, mix, mul, normalWorld, positionLocal, positionWorld, texture, uniform, uv, vec3, vec4 } from 'three/tsl'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'

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

        this.setVisual()
        this.game.ticker.events.on('tick', () =>
        {
            this.update()
        }, 10)
    }

    setVisual()
    {
        this.size = Math.round(this.game.view.optimalArea.surfaceRadius * 2) + 1
        this.halfSize = this.size * 0.5
        // Narrow stream banks need enough vertices to avoid triangular shore steps.
        this.cellSize = this.game.quality.level === 0 ? 0.75 : 1
        this.subdivisions = this.size / this.cellSize

        // Geometry
        let geometry = new THREE.PlaneGeometry(this.size, this.size, this.subdivisions, this.subdivisions)
        geometry.rotateX(-Math.PI * 0.5)
        geometry.deleteAttribute('normal')

        // Terrain data
        const terrainData = this.game.terrain.terrainNode(positionWorld.xz)
        const slabHighColor = uniform(color('#ffcf8b'))
        const slabLowColor = uniform(color('#a87762'))
        const slabTextureFrequency = uniform(0.175)
        const slabNoiseFrequency = uniform(0.03)
        const colorNode = Fn(() =>
        {
            const baseColor = this.game.terrain.colorNode(terrainData)
            
            const slabTerrain = terrainData.r
            const slabNoiseUv = positionWorld.xz.mul(slabNoiseFrequency)
            const slabNoise = texture(this.game.noises.perlin, slabNoiseUv).r
            const slabsTexture = texture(this.game.resources.floorSlabsTexture, positionWorld.xz.mul(slabTextureFrequency)).r
            const slabColor = mix(slabLowColor, slabHighColor, slabsTexture)
            // return vec3(slabsTexture.mul(slabStrength))

            const slab = slabTerrain.mul(slabNoise)
            // return vec3(slab)
            
            const finalColor = mix(baseColor, slabColor, slab)
            return finalColor
        })()

        // Material
        const material = new MeshDefaultMaterial({
            colorNode: colorNode,
            normalNode: vec3(0, 1, 0),
            shadowNode: terrainData.g,
            hasWater: false,
            hasFog: false,
            hasLightBounce: false,
            wireframe: false
        })
        // Offshore fog continues gradually to the horizon. Near-ground fog
        // stays exactly on the original day-cycle curve.
        const litFloor = material.outputNode
        const sea = this.game.terrain.seaDepthNode(positionWorld.xz).smoothstep(0.1, 0.8)
        const distance = positionWorld.xz.sub(this.game.terrain.productWaterAnchor).length()
        const fog = mix(this.game.fog.strength, distance.smoothstep(40, 170), sea)
        material.outputNode = vec4(mix(litFloor.rgb, this.game.fog.color, fog), litFloor.a)
        // Displacement
        material.positionNode = Fn(() =>
        {
            const uvDim = min(min(uv().x, uv().y).mul(20), 1)

            const newPosition = positionLocal
            newPosition.y.addAssign(terrainData.b.mul(-1.5).mul(uvDim))

            return newPosition
        })()

        // Mesh
        this.mesh = new THREE.Mesh(geometry, material)
        this.mesh.receiveShadow = true
        // this.mesh.castShadow = true
        this.game.scene.add(this.mesh)

        // Resize
        this.game.viewport.events.on('throttleChange', () =>
        {
            this.size = Math.round(this.game.view.optimalArea.surfaceRadius * 2) + 1
            this.halfSize = this.size * 0.5
            this.subdivisions = this.size / this.cellSize
            
            geometry.dispose()
            
            geometry = new THREE.PlaneGeometry(this.size, this.size, this.subdivisions, this.subdivisions)
            geometry.rotateX(-Math.PI * 0.5)
            geometry.deleteAttribute('normal')

            this.mesh.geometry = geometry
        }, 2)

        if(this.game.debug.active)
        {
            this.debugPanel.addBinding(slabTextureFrequency, 'value', { label: 'slabTextureFrequency', min: 0, max: 1, step: 0.001 })
            this.debugPanel.addBinding(slabNoiseFrequency, 'value', { label: 'slabNoiseFrequency', min: 0, max: 0.1, step: 0.001 })
            this.game.debug.addThreeColorBinding(this.debugPanel, slabHighColor.value, 'slabHighColor')
            this.game.debug.addThreeColorBinding(this.debugPanel, slabLowColor.value, 'slabLowColor')
        }
    }

    update()
    {
        this.mesh.position.x = Math.round(this.game.view.optimalArea.position.x / this.cellSize) * this.cellSize
        this.mesh.position.z = Math.round(this.game.view.optimalArea.position.z / this.cellSize) * this.cellSize
    }
}
