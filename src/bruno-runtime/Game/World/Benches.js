import { Game } from '../Game.js'
import { InstancedGroup } from '../InstancedGroup.js'

export class Benches
{
    constructor()
    {
        this.game = Game.getInstance()

        // Base and references
        const [ base, references ] = InstancedGroup.getBaseAndReferencesFromInstances(this.game.resources.benchesModel.scene.children)
        base.castShadow = true
        base.receiveShadow = true
        base.frustumCulled = true

        // Update materials 
        this.game.materials.updateObject(base)

        // Instanced group
        this.instancedGroup = new InstancedGroup(references, base)
    }
}
