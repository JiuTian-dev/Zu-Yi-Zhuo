/** @origin ZUOYIZHUO-SCENE — project-owned table anchor copied from the
 * Bruno baseline landing coordinate; it replaces the gameplay respawn asset. */

import * as THREE from 'three/webgpu'

export const TABLE_ANCHORS = Object.freeze({
    valley: Object.freeze({ x: 39.5289802551, y: 0.5, z: 37.8252296448 }),
})

export const CAMERA_PRESETS = Object.freeze({
    overview: Object.freeze({ azimuth: 0.62, elevation: 0.42, radius: 16.8 }),
    approach: Object.freeze({ azimuth: 0.62, elevation: 0.36, radius: 10.6 }),
})

export function cloneTableAnchor(worldId = 'valley')
{
    const anchor = TABLE_ANCHORS[worldId] ?? TABLE_ANCHORS.valley
    return new THREE.Vector3(anchor.x, anchor.y, anchor.z)
}
