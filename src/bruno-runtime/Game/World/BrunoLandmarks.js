/** @origin BRUNO-ADAPTED — static landmark fragments from folio-2025 areas.glb.
 * Product boundary: only scenic meshes and waterfall anchors are mounted; labels, physics and
 * interactive points remain out of the runtime. No REST/WS or game semantics. */
import * as THREE from 'three/webgpu'
import { Game } from '../Game.js'
import { TABLE_ANCHORS } from '../tableAnchors.js'
import { LANDSCAPE } from '../landscapeLayout.js'
import { LandmarkWaterfall } from './LandmarkWaterfall.js'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'

export class BrunoLandmarks
{
    constructor()
    {
        const game = Game.getInstance()
        this.game = game
        this.scenicMaterials = new Map()
        const source = game.resources.areasModel.scene
        const anchor = TABLE_ANCHORS.valley
        this.group = new THREE.Group()
        this.group.name = 'product-static-landmarks'

        const ruin = new THREE.Group()
        const achievements = source.getObjectByName('achievements')
        for(const key of ['Cube089', 'Cube110', 'refPillar', 'refWaterfallStill', 'refWaterfallDrop', 'refWaterfallParticles'])
        {
            const part = achievements?.getObjectByName(key)
            if(part) ruin.add(part.clone(true))
        }
        const barSet = new THREE.Group()
        const bowling = source.getObjectByName('bowling')
        for(const key of ['barPhysicalDynamic001', 'stoolPhysicalDynamic001', 'stoolPhysicalDynamic002', 'stoolPhysicalDynamic003', 'stoolPhysicalDynamic007', 'sauceKetchupPhysicalDynamic002', 'sauceMustardPhysicalDynamic002'])
        {
            const part = bowling?.getObjectByName(key)
            if(part) barSet.add(part.clone(true))
        }
        this.waterfall = this.mount(ruin, {
            name: 'product-waterfall-ruin',
            layout: LANDSCAPE.landmarks.waterfall,
            position: new THREE.Vector3(anchor.x, 0, anchor.z),
        })
        this.bar = this.mount(barSet, {
            name: 'product-coastal-bar',
            layout: LANDSCAPE.landmarks.bar,
            position: new THREE.Vector3(anchor.x, 0, anchor.z),
        })
        game.scene.add(this.group)
        this.waterEffects = new LandmarkWaterfall(game, this.waterfall.children[0])
    }

    mount(source, { name, layout, position })
    {
        if(!source) return null
        const object = source.clone(true)
        object.updateMatrixWorld(true)
        const bounds = new THREE.Box3().setFromObject(object)
        if(bounds.isEmpty()) throw new Error(`Missing scenic meshes: ${name}`)
        const centre = bounds.getCenter(new THREE.Vector3())
        object.position.set(-centre.x, -bounds.min.y, -centre.z)
        const placement = new THREE.Group()
        placement.name = name
        placement.add(object)
        placement.position.set(position.x + layout.x, position.y, position.z + layout.z)
        placement.rotation.y = layout.rotation
        placement.scale.setScalar(layout.scale)
        object.traverse((child) =>
        {
            // Keep only water-effect anchors; never mount gameplay controllers.
            child.userData = {}
            child.name = child.name.startsWith('refWaterfall')
                ? 'product-' + child.name.slice(3, 4).toLowerCase() + child.name.slice(4)
                : `${name}-mesh`
            if(!child.isMesh) return
            child.castShadow = true
            child.receiveShadow = true
            this.game.materials.updateObject(child)
            // Free orbit exposes the back of the original single-sided shell.
            // Rebuild node closures against the local material: clone() would
            // retain the original outputNode's single-sided `this` reference.
            const original = child.material
            if(!this.scenicMaterials.has(original))
            {
                let material
                if(original instanceof MeshDefaultMaterial)
                {
                    const parameters = { side: THREE.DoubleSide }
                    for(const key of ['depthWrite', 'depthTest', 'transparent', 'shadowSide', 'alphaTest', 'hasCoreShadows', 'hasDropShadows', 'hasLightBounce', 'hasFog', 'hasWater', 'hasReveal'])
                        parameters[key] = original[key]
                    for(const key of ['colorNode', 'normalNode', 'alphaNode', 'shadowNode'])
                        parameters[key] = original['_' + key]
                    material = new MeshDefaultMaterial(parameters)
                }
                else
                {
                    material = original.clone()
                    material.side = THREE.DoubleSide
                }
                this.scenicMaterials.set(original, material)
            }
            child.material = this.scenicMaterials.get(original)
        })
        this.group.add(placement)
        return placement
    }
}
