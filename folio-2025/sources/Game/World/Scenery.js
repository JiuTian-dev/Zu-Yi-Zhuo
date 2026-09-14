import { color, float, Fn, max, PI, positionWorld, texture, uniform, uv, vec3 } from 'three/tsl'
import { Game } from '../Game.js'
import { References } from '../References.js'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'

export class Scenery
{
    constructor()
    {
        this.game = Game.getInstance()

        this.references = new References()
        const model = [...this.game.resources.sceneryModel.scene.children]
        for(const child of model)
        {
            // Add
            if(typeof child.userData.prevent === 'undefined' || child.userData.prevent === false)
            {
                // Objects
                this.game.objects.addFromModel(
                    child,
                    {

                    },
                    {
                        position: child.position,
                        rotation: child.quaternion,
                        sleeping: true,
                        mass: child.userData.mass
                    }
                )
            }

            this.references.parse(child)
        }

        this.setRoad()

        this.game.ticker.events.on('tick', () =>
        {
            this.update()
        })
    }
    
    setRoad()
    {
        this.road = {}

        // All road meshes share the starry highway material (not only the first).
        const meshes = this.references.items.get('road') || []
        if(!meshes.length)
            return

        this.road.color = uniform(color('#383039'))
        this.road.glitterVariation = uniform(0)
        this.road.glitterScarcity = uniform(100)
        this.road.glitterIntensity = uniform(0.45)
        this.road.glitterPerlinFrequency = uniform(0.05)
        this.road.glitterHashFrequency = uniform(0.2)

        const colorNode = Fn(() =>
        {
            const glitter = float(0)

            // Hash
            const hashUv = positionWorld.xz.mul(this.road.glitterHashFrequency)
            const hash = texture(this.game.noises.hash, hashUv).r.mul(2).add(this.road.glitterVariation).mod(2).sub(1).abs()
            glitter.addAssign(hash)

            // Scarcity
            glitter.assign(glitter.pow(this.road.glitterScarcity))

            // Intensity
            glitter.mulAssign(this.road.glitterIntensity)
            
            const perlinUv = positionWorld.xz.mul(this.road.glitterPerlinFrequency)
            const perlin = texture(this.game.noises.perlin, perlinUv).r
            glitter.mulAssign(perlin)

            const middle = uv().y.mul(PI).sin()
            glitter.mulAssign(middle)
            
            // Output
            const baseColor = this.road.color.toVar()
            baseColor.addAssign(glitter)

            return vec3(baseColor)
        })()

        const material = new MeshDefaultMaterial({
            colorNode: colorNode,

            hasLightBounce: false,
            hasWater: false,
        })

        for(const mesh of meshes)
            mesh.material = material

        // Also apply to any other scenery refs named like road*
        this.references.items.forEach((list, name) =>
        {
            if(name === 'road')
                return
            if(!/^road/i.test(name))
                return
            for(const mesh of list)
                mesh.material = material
        })

        // Debug
        if(this.game.debug.active)
        {
            const debugPanel = this.game.debug.panel.addFolder({
                title: '🛣️ Road',
                expanded: false
            })
            this.game.debug.addThreeColorBinding(debugPanel, this.road.color.value, 'color')
            debugPanel.addBinding(this.road.glitterScarcity, 'value', { label: 'glitterScarcity', min: 100, max: 10000, step: 1 })
            debugPanel.addBinding(this.road.glitterIntensity, 'value', { label: 'glitterIntensity', min: 0, max: 10, step: 0.01 })
            debugPanel.addBinding(this.road.glitterPerlinFrequency, 'value', { label: 'glitterPerlinFrequency', min: 0, max: 0.1, step: 0.0001 })
            debugPanel.addBinding(this.road.glitterHashFrequency, 'value', { label: 'glitterHashFrequency', min: 0, max: 1, step: 0.0001 })
        }
    }

    update()
    {
        this.road.glitterVariation.value += this.game.ticker.deltaScaled * 0.004 + this.game.view.delta.length() * 0.004
    }
}