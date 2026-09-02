import { Game } from '../Game.js'
import { InstancedGroup } from '../InstancedGroup.js'

export class Fences
{
    constructor()
    {
        this.game = Game.getInstance()

        // Base and references
        const [ base, references ] = InstancedGroup.getBaseAndReferencesFromInstances(this.game.resources.fencesModel.scene.children)
        base.castShadow = true
        base.receiveShadow = true
        base.frustumCulled = true

        // Update materials 
        this.game.materials.updateObject(base)

        // Setup base
        for(const child of base.children)
            child.name = child.name.replace(/[0-9]+$/i, '') // Set clear name to retrieve it later as instances

        // Instanced group
        this.instancedGroup = new InstancedGroup(references, base)
    }
}
