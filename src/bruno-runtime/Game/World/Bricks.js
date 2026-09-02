import { Game } from '../Game.js'
import { InstancedGroup } from '../InstancedGroup.js'

export class Bricks
{
    constructor()
    {
        this.game = Game.getInstance()

        // Base and references
        const [ base, references ] = InstancedGroup.getBaseAndReferencesFromInstances(this.game.resources.bricksModel.scene.children)

        base.castShadow = true
        base.receiveShadow = true
        base.frustumCulled = false

        // Update materials 
        this.game.materials.updateObject(base)
        
        // Instanced group
        this.instancedGroup = new InstancedGroup(references, base)
    }
}
