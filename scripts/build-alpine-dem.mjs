import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'

// @origin ZUOYIZHUO-OFFLINE-ASSET-PIPELINE — real DEM to high-density GLB.
// This script only prepares visual candidates. It does not attach them to the runtime.

const root = process.cwd()
const demRoot = path.join(root, '3D', 'alpine-source', 'dem', 'srtm')
const outputRoot = path.join(root, 'public', 'assets', 'bruno-runtime', 'alpine', 'dem')
const tiles = new Map()

const regions = [
    {
        id: 'matterhorn-ridge',
        bounds: { latMin: 45.78, latMax: 46.05, lonMin: 7.45, lonMax: 7.92 },
        gridX: 256,
        gridZ: 192,
        width: 112,
        depth: 72,
        verticalScale: 0.0085,
    },
    {
        id: 'eiger-ridge',
        bounds: { latMin: 46.34, latMax: 46.78, lonMin: 7.60, lonMax: 8.26 },
        gridX: 256,
        gridZ: 192,
        width: 124,
        depth: 76,
        verticalScale: 0.0085,
    },
]

function tileName(lat, lon)
{
    const latPrefix = lat >= 0 ? `N${String(lat).padStart(2, '0')}` : `S${String(Math.abs(lat)).padStart(2, '0')}`
    const lonPrefix = lon >= 0 ? `E${String(lon).padStart(3, '0')}` : `W${String(Math.abs(lon)).padStart(3, '0')}`
    return `${latPrefix}${lonPrefix}`
}

function loadTile(lat, lon)
{
    const key = `${lat}:${lon}`
    if(tiles.has(key)) return tiles.get(key)

    const name = tileName(lat, lon)
    const filePath = path.join(demRoot, `${name}.hgt.gz`)
    if(!fs.existsSync(filePath)) throw new Error(`Missing DEM tile: ${filePath}`)

    const raw = zlib.gunzipSync(fs.readFileSync(filePath))
    const side = Math.sqrt(raw.length / 2)
    if(!Number.isInteger(side)) throw new Error(`Invalid HGT size for ${name}`)

    const values = new Int16Array(side * side)
    for(let i = 0; i < values.length; i++) values[i] = raw.readInt16BE(i * 2)

    const tile = { lat, lon, side, values }
    tiles.set(key, tile)
    return tile
}

function sampleElevation(lat, lon)
{
    const baseLat = Math.floor(lat)
    const baseLon = Math.floor(lon)
    const tile = loadTile(baseLat, baseLon)
    const max = tile.side - 1
    const x = Math.min(max, Math.max(0, (lon - baseLon) * max))
    const y = Math.min(max, Math.max(0, (baseLat + 1 - lat) * max))
    const x0 = Math.floor(x)
    const y0 = Math.floor(y)
    const x1 = Math.min(max, x0 + 1)
    const y1 = Math.min(max, y0 + 1)
    const tx = x - x0
    const ty = y - y0
    const value = (ix, iy) => {
        const result = tile.values[iy * tile.side + ix]
        if(result === -32768) throw new Error(`Void DEM sample at ${lat}, ${lon}`)
        return result
    }
    const top = value(x0, y0) * (1 - tx) + value(x1, y0) * tx
    const bottom = value(x0, y1) * (1 - tx) + value(x1, y1) * tx
    return top * (1 - ty) + bottom * ty
}

function align4(value)
{
    return (value + 3) & ~3
}

function createGlb({ id, positions, normals, uvs, indices, metadata })
{
    const positionBytes = Buffer.from(positions.buffer)
    const normalBytes = Buffer.from(normals.buffer)
    const uvBytes = Buffer.from(uvs.buffer)
    const indexBytes = Buffer.from(indices.buffer)
    const chunks = []
    const bufferViews = []
    let byteOffset = 0

    const append = (bytes, target) => {
        const alignedOffset = align4(byteOffset)
        if(alignedOffset > byteOffset) chunks.push(Buffer.alloc(alignedOffset - byteOffset))
        byteOffset = alignedOffset
        const viewIndex = bufferViews.length
        bufferViews.push({ buffer: 0, byteOffset, byteLength: bytes.length, target })
        chunks.push(bytes)
        byteOffset += bytes.length
        return viewIndex
    }

    const positionView = append(positionBytes, 34962)
    const normalView = append(normalBytes, 34962)
    const uvView = append(uvBytes, 34962)
    const indexView = append(indexBytes, 34963)
    const bin = Buffer.concat(chunks)
    const json = {
        asset: { version: '2.0', generator: 'ZuYiZhuo Alpine DEM Builder' },
        scene: 0,
        scenes: [{ nodes: [0] }],
        nodes: [{ name: id, mesh: 0, extras: metadata }],
        meshes: [{
            name: id,
            primitives: [{
                attributes: { POSITION: 0, NORMAL: 1, TEXCOORD_0: 2 },
                indices: 3,
                material: 0,
            }],
        }],
        materials: [{
            name: 'alpine-grey-reference',
            doubleSided: true,
            pbrMetallicRoughness: {
                baseColorFactor: [0.39, 0.45, 0.52, 1],
                metallicFactor: 0,
                roughnessFactor: 0.92,
            },
        }],
        accessors: [
            { bufferView: positionView, componentType: 5126, count: positions.length / 3, type: 'VEC3', min: metadata.min, max: metadata.max },
            { bufferView: normalView, componentType: 5126, count: normals.length / 3, type: 'VEC3' },
            { bufferView: uvView, componentType: 5126, count: uvs.length / 2, type: 'VEC2' },
            { bufferView: indexView, componentType: 5125, count: indices.length, type: 'SCALAR', min: [0], max: [positions.length / 3 - 1] },
        ],
        bufferViews,
        buffers: [{ byteLength: bin.length }],
    }

    const jsonBytes = Buffer.from(JSON.stringify(json))
    const paddedJson = Buffer.concat([jsonBytes, Buffer.alloc(align4(jsonBytes.length) - jsonBytes.length, 0x20)])
    const paddedBin = Buffer.concat([bin, Buffer.alloc(align4(bin.length) - bin.length)])
    const totalLength = 12 + 8 + paddedJson.length + 8 + paddedBin.length
    const header = Buffer.alloc(12)
    header.writeUInt32LE(0x46546c67, 0)
    header.writeUInt32LE(2, 4)
    header.writeUInt32LE(totalLength, 8)
    const jsonHeader = Buffer.alloc(8)
    jsonHeader.writeUInt32LE(paddedJson.length, 0)
    jsonHeader.writeUInt32LE(0x4e4f534a, 4)
    const binHeader = Buffer.alloc(8)
    binHeader.writeUInt32LE(paddedBin.length, 0)
    binHeader.writeUInt32LE(0x004e4942, 4)
    return Buffer.concat([header, jsonHeader, paddedJson, binHeader, paddedBin])
}

function buildRegion(region)
{
    const { bounds, gridX, gridZ, width, depth, verticalScale } = region
    const positions = new Float32Array(gridX * gridZ * 3)
    const normals = new Float32Array(gridX * gridZ * 3)
    const uvs = new Float32Array(gridX * gridZ * 2)
    const indices = new Uint32Array((gridX - 1) * (gridZ - 1) * 6)
    const heights = new Float32Array(gridX * gridZ)
    let minElevation = Infinity
    let maxElevation = -Infinity

    for(let z = 0; z < gridZ; z++)
    {
        const v = z / (gridZ - 1)
        const lat = bounds.latMax + (bounds.latMin - bounds.latMax) * v
        for(let x = 0; x < gridX; x++)
        {
            const u = x / (gridX - 1)
            const lon = bounds.lonMin + (bounds.lonMax - bounds.lonMin) * u
            const elevation = sampleElevation(lat, lon)
            const index = z * gridX + x
            heights[index] = elevation
            minElevation = Math.min(minElevation, elevation)
            maxElevation = Math.max(maxElevation, elevation)
            positions[index * 3] = (u - 0.5) * width
            positions[index * 3 + 1] = elevation
            positions[index * 3 + 2] = (v - 0.5) * depth
            uvs[index * 2] = u
            uvs[index * 2 + 1] = v
        }
    }

    // Hide rectangular crop boundaries below the foothills. Keep central DEM
    // relief intact; use one common elevation datum across the entire tile.
    for(let z = 0; z < gridZ; z++)
        for(let x = 0; x < gridX; x++)
        {
            const i = z * gridX + x
            const edge = Math.min(x / (gridX - 1), 1 - x / (gridX - 1),
                z / (gridZ - 1), 1 - z / (gridZ - 1))
            const t = Math.min(1, edge / 0.14)
            const fade = t * t * (3 - 2 * t)
            positions[i * 3 + 1] = (heights[i] - minElevation) * verticalScale * fade - 4
        }

    const xStep = width / (gridX - 1)
    const zStep = depth / (gridZ - 1)
    for(let z = 0; z < gridZ; z++)
    {
        for(let x = 0; x < gridX; x++)
        {
            const index = z * gridX + x
            const left = positions[(z * gridX + Math.max(0, x - 1)) * 3 + 1]
            const right = positions[(z * gridX + Math.min(gridX - 1, x + 1)) * 3 + 1]
            const up = positions[(Math.max(0, z - 1) * gridX + x) * 3 + 1]
            const down = positions[(Math.min(gridZ - 1, z + 1) * gridX + x) * 3 + 1]
            const dx = (right - left) / (xStep * (x > 0 && x < gridX - 1 ? 2 : 1))
            const dz = (down - up) / (zStep * (z > 0 && z < gridZ - 1 ? 2 : 1))
            const nx = -dx
            const ny = 1
            const nz = -dz
            const length = Math.hypot(nx, ny, nz) || 1
            normals[index * 3] = nx / length
            normals[index * 3 + 1] = ny / length
            normals[index * 3 + 2] = nz / length
        }
    }

    let cursor = 0
    for(let z = 0; z < gridZ - 1; z++)
    {
        for(let x = 0; x < gridX - 1; x++)
        {
            const a = z * gridX + x
            const b = a + 1
            const c = a + gridX
            const d = c + 1
            indices[cursor++] = a
            indices[cursor++] = c
            indices[cursor++] = b
            indices[cursor++] = b
            indices[cursor++] = c
            indices[cursor++] = d
        }
    }

    const min = [Infinity, Infinity, Infinity]
    const max = [-Infinity, -Infinity, -Infinity]
    for(let i = 0; i < positions.length; i += 3)
    {
        min[0] = Math.min(min[0], positions[i])
        min[1] = Math.min(min[1], positions[i + 1])
        min[2] = Math.min(min[2], positions[i + 2])
        max[0] = Math.max(max[0], positions[i])
        max[1] = Math.max(max[1], positions[i + 1])
        max[2] = Math.max(max[2], positions[i + 2])
    }

    const glb = createGlb({
        id: region.id,
        positions,
        normals,
        uvs,
        indices,
        metadata: {
            source: 'AWS elevation-tiles-prod/skadi HGT tiles',
            min,
            max,
            bounds,
            minElevation,
            maxElevation,
            grid: [gridX, gridZ],
            verticalScale,
        },
    })
    fs.mkdirSync(outputRoot, { recursive: true })
    const outputPath = path.join(outputRoot, `${region.id}.glb`)
    fs.writeFileSync(outputPath, glb)
    fs.writeFileSync(path.join(outputRoot, `${region.id}.json`), JSON.stringify({
        source: 'AWS elevation-tiles-prod/skadi HGT tiles',
        bounds,
        minElevation,
        maxElevation,
        grid: [gridX, gridZ],
        triangles: indices.length / 3,
        output: `${region.id}.glb`,
    }, null, 2))
    console.log(`${region.id}: ${indices.length / 3} triangles, ${glb.length} bytes`)
}

for(const region of regions)
{
    buildRegion(region)
    buildRegion({ ...region, id: `${region.id}-lod`, gridX: 128, gridZ: 96 })
}
