import { Game } from '../Game.js'
import { InstancedGroup } from '../InstancedGroup.js'

export class Lanterns
{
    constructor()
    {
        this.game = Game.getInstance()

        // Base and references
        const [ base, references ] = InstancedGroup.getBaseAndReferencesFromInstances(this.game.resources.lanternsModel.scene.children)

        // Setup base
        for(const child of base.children)
        {
            child.name = child.name.replace(/[0-9]+$/i, '') // Set clear name to retrieve it later as instances
            child.castShadow = true
            child.receiveShadow = true
            child.frustumCulled = false
        }

        // Update materials 
        this.game.materials.updateObject(base)
        
        // Instanced group
        this.instancedGroup = new InstancedGroup(references, base)
    }
}
