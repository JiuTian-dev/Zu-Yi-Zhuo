/** Scenic distant islands, using existing Bruno trees, rocks and lantern meshes. */
import * as THREE from 'three/webgpu'
import { color, mix, vec4 } from 'three/tsl'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'
import { TABLE_ANCHORS } from '../tableAnchors.js'

export function createRemoteIslands(game)
{
    const group = new THREE.Group()
    group.name = 'product-island-horizon'
    const anchor = TABLE_ANCHORS.valley
    // Both sit beyond the former road, separated in bearing and distance.
    for(const [index, x, z, size, haze] of [[0, -58, -72, 1, 0.58], [1, -116, -85, 0.8, 0.78]])
    {
        const island = new THREE.Group()
        island.name = `product-distant-island-${index}`
        island.position.set(anchor.x + x, 0, anchor.z + z)
        island.scale.setScalar(size)
        group.add(island)
        const scenicMaterial = tint => {
            const material = new MeshDefaultMaterial({ colorNode: color(tint),
                hasFog: false, hasReveal: false, hasWater: false,
                hasDropShadows: false, hasLightBounce: false, side: THREE.DoubleSide })
            const lit = material.outputNode
            material.outputNode = vec4(mix(lit.rgb, game.fog.color, haze), 1)
            return material
        }
        const shore = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 16), scenicMaterial('#656657'))
        shore.scale.set(12, 2, 7)
        shore.position.y = -0.6
        island.add(shore)
        // Clone geometry as well so disposing a remote island never invalidates main-island assets.
        const placeAsset = (source, x, y, z, scale, tree = false) => {
            const model = source.clone(true)
            model.position.set(0, 0, 0)
            model.rotation.set(0, 0, 0)
            model.scale.setScalar(1)
            model.updateMatrixWorld(true)
            const bounds = new THREE.Box3().setFromObject(model)
            const centre = bounds.getCenter(new THREE.Vector3())
            model.position.set(-centre.x, -bounds.min.y, -centre.z)
            const placement = new THREE.Group()
            placement.add(model)
            placement.position.set(x, y, z)
            placement.scale.setScalar(scale)
            model.traverse(mesh => {
                if(!mesh.isMesh) return
                mesh.geometry = mesh.geometry.clone()
                const glow = /glass|light/i.test(mesh.name)
                if(glow)
                {
                    const material = new THREE.MeshBasicNodeMaterial({ side: THREE.DoubleSide })
                    material.colorNode = mix(color('#ffb65e').mul(index === 0 ? 2.8 : 2.1), game.fog.color, haze)
                    mesh.material = material
                }
                else mesh.material = scenicMaterial(tree && /leaves/i.test(mesh.name) ? '#737b51' : '#77736b')
                mesh.castShadow = false
                mesh.receiveShadow = false
            })
            island.add(placement)
        }
        for(const [x, z, scale] of [[-4, 0, 0.65], [1, 1, 0.8], [4, -1, 0.55]])
            placeAsset(game.resources.oakTreesVisualModel.scene, x, 1, z, scale, true)
        const rock = game.scene.getObjectByName('basaltRocksPhysicalStatic001')
        if(rock) placeAsset(rock, -6, 0.7, 1, 0.55)
        for(const x of index === 0 ? [-3, 3] : [0])
            placeAsset(game.resources.lanternsModel.scene.children[0], x, 1.2, 3, 1.1)
    }
    return group
}
