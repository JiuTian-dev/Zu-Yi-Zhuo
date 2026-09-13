/** Scenic distant islands, using existing Bruno trees, rocks and lantern meshes. */
import * as THREE from 'three/webgpu'
import { color, mix, vec4, texture, uv } from 'three/tsl'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'
import { alea } from 'seedrandom'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'
import { TABLE_ANCHORS } from '../tableAnchors.js'

export function createRemoteIslands(game)
{
    const group = new THREE.Group()
    group.name = 'product-island-horizon'
    const anchor = TABLE_ANCHORS.valley
    const random = new alea('remote-island-leaves')
    // Both sit beyond the former road, separated in bearing and distance.
    for(const [index, x, z, size, haze] of [[0, -58, -72, 1, 0.48], [1, -116, -85, 0.8, 0.68]])
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
        const shoreGeometry = new THREE.SphereGeometry(1, 48, 20)
        const shorePositions = shoreGeometry.attributes.position
        for(let i = 0; i < shorePositions.count; i++)
        {
            const x = shorePositions.getX(i), z = shorePositions.getZ(i)
            const angle = Math.atan2(z, x)
            const edge = 1 + 0.12 * Math.sin(angle * 3 + index) + 0.06 * Math.cos(angle * 7)
            shorePositions.setXYZ(i, x * edge, shorePositions.getY(i), z * edge)
        }
        shoreGeometry.computeVertexNormals()
        const shore = new THREE.Mesh(shoreGeometry, scenicMaterial('#77766a'))
        shore.scale.set(12, 2, 7)
        shore.position.y = -0.6
        island.add(shore)
        const meadow = new THREE.Mesh(shoreGeometry.clone(), scenicMaterial(index === 0 ? '#818044' : '#626e57'))
        meadow.scale.set(10.4, 1.1, 5.9)
        meadow.position.set(-0.5, 0.4, -0.3)
        island.add(meadow)
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
                if(tree && /leaves/i.test(mesh.name))
                {
                    // The source mesh is a crown volume, not finished foliage.
                    mesh.geometry.computeBoundingBox()
                    const box = mesh.geometry.boundingBox
                    const centre = box.getCenter(new THREE.Vector3())
                    const half = box.getSize(new THREE.Vector3()).multiplyScalar(0.5)
                    const leaves = []
                    for(let leaf = 0; leaf < 96; leaf++)
                    {
                        const direction = new THREE.Vector3().setFromSphericalCoords(
                            Math.cbrt(random()), Math.acos(2 * random() - 1), random() * Math.PI * 2)
                        const plane = new THREE.PlaneGeometry(half.length() * 0.36, half.length() * 0.36)
                        plane.rotateX(random() * Math.PI)
                        plane.rotateY(random() * Math.PI)
                        plane.rotateZ(random() * Math.PI)
                        direction.multiply(half).add(centre)
                        plane.translate(direction.x, direction.y, direction.z)
                        leaves.push(plane)
                    }
                    mesh.geometry = mergeGeometries(leaves)
                    leaves.forEach(leaf => leaf.dispose())
                    mesh.material = scenicMaterial(index === 0 ? '#a88b47' : '#788c65')
                    mesh.material.alphaNode = texture(game.resources.foliageTexture, uv()).r.sub(0.3)
                    mesh.castShadow = false
                    mesh.receiveShadow = false
                    return
                }
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
        const trees = index === 0
            ? [[-4, -0.5, 0.62], [0, -1.2, 0.78], [4, -1, 0.52], [-6, -2, 0.4]]
            : [[-4, -1, 0.46], [2, -1.5, 0.72], [5, 0, 0.42]]
        for(const [x, z, scale] of trees)
            placeAsset(game.resources.oakTreesVisualModel.scene, x, 1, z, scale, true)
        const rock = game.scene.getObjectByName('basaltRocksPhysicalStatic001')
        if(rock)
            for(const [x, y, z, scale] of index === 0
                ? [[-7, 0.1, 2, 0.5], [6, 0, 2, 0.35], [8, -0.2, 0, 0.3]]
                : [[-6, 0.3, 1, 0.7], [-3, 0.1, 2.5, 0.5], [7, 0, 1, 0.45]])
                placeAsset(rock, x, y, z, scale)
        for(const x of index === 0 ? [-3, 3] : [0])
            placeAsset(game.resources.lanternsModel.scene.children[0], x, 1.2, 3, 1.1)
    }
    return group
}
