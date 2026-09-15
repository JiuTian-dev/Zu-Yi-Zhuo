import { Mesh, MeshStandardMaterial, type Object3D } from 'three'

/** The supplied character exports omit NORMAL; preserve textures but avoid flat triangles. */
export function prepareCharacterShading(model: Object3D) {
  model.traverse((node) => {
    if (!(node instanceof Mesh) || node.geometry.getAttribute('normal')) return
    node.geometry.computeVertexNormals()
    // UV seams may duplicate vertices. Average coincident normals without welding
    // the actual geometry, so the original UVs and skinning remain untouched.
    const position = node.geometry.getAttribute('position')
    const normal = node.geometry.getAttribute('normal')
    const sums = new Map<string, [number, number, number]>()
    const keys: string[] = []
    for (let i = 0; i < position.count; i++) {
      const key = [position.getX(i), position.getY(i), position.getZ(i)].map((v) => Math.round(v * 100000)).join(',')
      keys.push(key)
      const sum = sums.get(key) ?? [0, 0, 0]
      sum[0] += normal.getX(i); sum[1] += normal.getY(i); sum[2] += normal.getZ(i)
      sums.set(key, sum)
    }
    for (let i = 0; i < normal.count; i++) {
      const sum = sums.get(keys[i])!
      const length = Math.hypot(...sum) || 1
      normal.setXYZ(i, sum[0] / length, sum[1] / length, sum[2] / length)
    }
    normal.needsUpdate = true
    const materials = Array.isArray(node.material) ? node.material : [node.material]
    materials.forEach((material) => {
      if (!(material instanceof MeshStandardMaterial)) return
      material.flatShading = false
      material.needsUpdate = true
    })
  })
}
