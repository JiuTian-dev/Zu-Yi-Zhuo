import * as THREE from 'three/webgpu'
import { Game } from '../Game.js'
import { Foliage } from './Foliage.js'
import { color, uniform } from 'three/tsl'
import { TABLE_ANCHORS } from '../tableAnchors.js'
import { LANDSCAPE } from '../landscapeLayout.js'

export class Trees
{
    constructor(name, visual, references, colorA, colorB)
    {
        this.game = Game.getInstance()

        // Debug
        if(this.game.debug.active)
        {
            this.debugPanel = this.game.debug.panel.addFolder({
                title: `🌳 ${name}`,
                expanded: false,
            })
        }

        this.visual = visual
        // Product furniture occupies the old landing. Relocate only trees whose
        // roots intersect the seating disk, as complete trunk + crown units.
        this.references = references.filter(source =>
            Math.hypot(source.position.x - TABLE_ANCHORS.valley.x, source.position.z - TABLE_ANCHORS.valley.z) < 36).map((source) => {
            const anchor = TABLE_ANCHORS.valley
            const dx = source.position.x - anchor.x
            const dz = source.position.z - anchor.z
            const ruin = LANDSCAPE.landmarks.waterfall
            if(Math.abs(dx - ruin.x) < 5 && Math.abs(dz - ruin.z) < 7)
            {
                const reference = source.clone(false)
                reference.position.x = anchor.x + ruin.x + (dx < ruin.x ? -7 : 7)
                reference.updateMatrix()
                reference.updateMatrixWorld(true)
                return reference
            }
            if(Math.hypot(dx, dz) >= 4.8) return source
            const reference = source.clone(false)
            // Restore the original near-table cherry, keeping its full asset.
            // Apply before instancing so trunks, leaves and camera bounds agree.
            if(name === 'Cherry Tree')
            {
                reference.position.x = anchor.x + LANDSCAPE.cherry.x
                reference.position.z = anchor.z + LANDSCAPE.cherry.z
                reference.updateMatrix()
                reference.updateMatrixWorld(true)
                return reference
            }
            let angle = Math.atan2(dz, dx)
            if(Math.cos(angle - 2.36) > 0.5) angle += 1.1
            reference.position.x = anchor.x + Math.cos(angle) * 12
            reference.position.z = anchor.z + Math.sin(angle) * 12
            reference.updateMatrix()
            reference.updateMatrixWorld(true)
            return reference
        })
        this.colorA = colorA
        this.colorB = colorB

        this.setModelParts()
        this.setBodies()
        this.setLeaves()
    }

    setModelParts()
    {
        this.modelParts = {}
        this.modelParts.leaves = []
        this.modelParts.body = null
        
        this.visual.traverse((_child) =>
        {
            if(_child.isMesh)
            {
                if(_child.name.startsWith('treeLeaves'))
                    this.modelParts.leaves.push(_child)
                else if(_child.name.startsWith('treeBody'))
                    this.modelParts.body = _child
            }
        })
    }

    setBodies()
    {
        this.game.materials.updateObject(this.modelParts.body)
        this.bodies = new THREE.InstancedMesh(this.modelParts.body.geometry, this.modelParts.body.material, this.references.length)
        this.bodies.instanceMatrix.setUsage(THREE.StaticDrawUsage)
        this.bodies.castShadow = true
        this.bodies.receiveShadow = true
        
        let i = 0
        for(const treeReference of this.references)
        {
            this.bodies.setMatrixAt(i, treeReference.matrix)
            i++
        }

        this.game.scene.add(this.bodies)
    }

    setLeaves()
    {
        const references = []
        
        for(const treeReference of this.references)
        {
            for(const leaves of this.modelParts.leaves)
            {
                const finalMatrix = leaves.matrix.clone().premultiply(treeReference.matrixWorld)
                const reference = new THREE.Object3D()
                reference.applyMatrix4(finalMatrix)

                references.push(reference)
            }
        }

        const leavesColorANode = uniform(color(this.colorA))
        const leavesColorBNode = uniform(color(this.colorB))
        // BRUNO-ADAPTED: free orbit replaces the driving camera. Do not erase
        // any tree crossing the screen centre; retain its full crown instead.
        this.leaves = new Foliage(references, leavesColorANode, leavesColorBNode, false, true)

        // Debug
        if(this.game.debug.active)
        {
            this.game.debug.addThreeColorBinding(this.debugPanel, leavesColorANode.value, 'leavesColorA')
            this.game.debug.addThreeColorBinding(this.debugPanel, leavesColorBNode.value, 'leavesColorB')
            this.debugPanel.addBinding(this.leaves.material.shadowOffset, 'value', { label: 'shadowOffset', min: 0, max: 2, step: 0.001 })
            this.debugPanel.addBinding(this.leaves.material.threshold, 'value', { label: 'threshold', min: 0, max: 1, step: 0.001 })
            this.debugPanel.addBinding(this.leaves.material.seeThroughEdgeMin, 'value', { label: 'seeThroughEdgeMin', min: 0, max: 1, step: 0.001 })
            this.debugPanel.addBinding(this.leaves.material.seeThroughEdgeMax, 'value', { label: 'seeThroughEdgeMax', min: 0, max: 1, step: 0.001 })
        }
    }

}
