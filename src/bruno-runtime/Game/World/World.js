/** @origin BRUNO-ADAPTED — original environment assembly. */
import { Game } from '../Game.js'
import { Floor } from './Floor.js'
import { WaterSurface } from './WaterSurface.js'
import { Grass } from './Grass.js'
import { Leaves } from './Leaves.js'
import { Bushes } from './Bushes.js'
import { Trees } from './Trees.js'
import { Flowers } from './Flowers.js'
import { Fences } from './Fences.js'
import { Benches } from './Benches.js'
import { Bricks } from './Bricks.js'
import { PoleLights } from './PoleLights.js'
import { Lanterns } from './Lanterns.js'
import { Scenery } from './Scenery.js'
import { TableMeeting } from './TableMeeting.js'
import { DistantLandscape } from './DistantLandscape.js'
import { BrunoLandmarks } from './BrunoLandmarks.js'

export class World
{
    constructor()
    {
        this.game = Game.getInstance()

        // These systems are the original environment baseline. Product state
        // stays outside the scene and no gameplay systems are mounted.
        this.floor = new Floor()
        this.waterSurface = new WaterSurface()
        this.grass = new Grass()
        // The upstream wind streaks are long, high-contrast curves that read
        // as stray guide lines over the table. Keep the world calm and let
        // weather affect foliage/water without adding a screen-spanning line.
        this.windLines = null
        this.leaves = new Leaves()
        this.bushes = new Bushes()
        this.birchTrees = new Trees('Birch Tree', this.game.resources.birchTreesVisualModel.scene, this.game.resources.birchTreesReferencesModel.scene.children, '#ff4f2b', '#ff903f')
        this.oakTrees = new Trees('Oak Tree', this.game.resources.oakTreesVisualModel.scene, this.game.resources.oakTreesReferencesModel.scene.children, '#b4b536', '#d8cf3b')
        this.cherryTrees = new Trees('Cherry Tree', this.game.resources.cherryTreesVisualModel.scene, this.game.resources.cherryTreesReferencesModel.scene.children, '#ff6d6d', '#ff9990')
        this.flowers = new Flowers()
        this.bricks = new Bricks()
        this.fences = new Fences()
        this.benches = new Benches()
        this.poleLights = new PoleLights()
        this.lanterns = new Lanterns()
        this.scenery = new Scenery()
        this.distantLandscape = new DistantLandscape(this.flowers)
        this.landmarks = new BrunoLandmarks()
        // Product table asset: static scene geometry only; participant state
        // and seat availability are rendered by the DOM/backend bridge.
        this.tableMeeting = new TableMeeting()
    }
}
