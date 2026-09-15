// Rebuild from the supplied originals. Never simplify an already-decimated mesh.
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
const requireTools = createRequire(resolve(process.argv[2], 'package.json'))
const { NodeIO } = requireTools('@gltf-transform/core')
const { ALL_EXTENSIONS } = requireTools('@gltf-transform/extensions')
const { weld, simplify, meshopt } = requireTools('@gltf-transform/functions')
const { MeshoptDecoder, MeshoptEncoder, MeshoptSimplifier } = requireTools('meshoptimizer')
await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready, MeshoptSimplifier.ready])
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder,
})
const sources = {
  blue: 'e09e73e8524fd993165b7c4263704496(1).glb',
  orange: '44d7944750115a2333dd04d9aacfb786(1).glb',
  white: '40fa0bf976830ed35fa4de475447d855(1).glb',
  green: '63d9b2ad245a203ddb365ffa3765273e(1).glb',
}
for (const [color, source] of Object.entries(sources)) {
  const doc = await io.read(resolve('图', source))
  const previous = await io.read(resolve('public/scene', `avatar-${color}.glb`))
  const oldMat = previous.getRoot().listMaterials()[0]
  const mat = doc.getRoot().listMaterials()[0]
  // Reuse the working 2K textures losslessly, retaining all PBR texture slots.
  for (const slot of ['BaseColor', 'Normal', 'MetallicRoughness', 'Occlusion', 'Emissive']) {
    const oldTexture = oldMat[`get${slot}Texture`]()
    const texture = mat[`get${slot}Texture`]()
    if (oldTexture && texture) texture.setImage(oldTexture.getImage()).setMimeType(oldTexture.getMimeType())
  }
  await doc.transform(weld(), simplify({ simplifier: MeshoptSimplifier, ratio: .2, error: .0001 }), meshopt({ encoder: MeshoptEncoder, level: 'high' }))
  const target = resolve('public/scene', `avatar-${color}-hd.glb`)
  await io.write(target, doc)
  console.log(color, 'triangles:', doc.getRoot().listMeshes()[0].listPrimitives()[0].getIndices().getCount() / 3)
}
