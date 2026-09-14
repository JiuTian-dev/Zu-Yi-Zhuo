import * as THREE from 'three/webgpu'

/** 19×19 cells, 10m, origin-centered world [-96, 94). Serial 1 = NW (-X,-Z). */
export const PLAN_CELL = 10
export const PLAN_N = 19
export const PLAN_ORIGIN = -96
export const PLAN_SPAN = PLAN_N * PLAN_CELL // 190

/** type codes stored in texture R (0–1 with nearest). */
export const PLAN_TYPE = {
    grass: 1 / 8,
    water: 2 / 8,
    road: 3 / 8,
    dirt: 4 / 8,
    gravel: 5 / 8,
    slab: 6 / 8,
    keep: 7 / 8,
}

const RANGES = [
    [1, 2, 'grass'], [3, 5, 'water'], [6, 6, 'road'], [7, 9, 'grass'], [10, 10, 'road'],
    [11, 16, 'grass'], [17, 17, 'road'], [18, 21, 'grass'], [22, 23, 'water'], [24, 24, 'grass'],
    [25, 25, 'road'], [26, 28, 'grass'], [29, 29, 'road'], [30, 35, 'grass'], [36, 36, 'road'],
    [37, 40, 'grass'], [41, 42, 'water'], [43, 43, 'grass'], [44, 44, 'road'], [45, 47, 'grass'],
    [48, 48, 'road'], [49, 54, 'grass'], [55, 55, 'road'], [56, 58, 'grass'], [59, 61, 'water'],
    [62, 62, 'grass'], [63, 63, 'road'], [64, 66, 'grass'], [67, 67, 'road'], [68, 73, 'grass'],
    [74, 74, 'road'], [75, 76, 'grass'], [77, 79, 'water'], [80, 81, 'grass'], [82, 95, 'road'],
    [96, 98, 'water'], [99, 100, 'grass'], [101, 101, 'road'], [102, 103, 'dirt'], [104, 104, 'water'],
    [105, 105, 'road'], [106, 107, 'water'], [108, 108, 'gravel'], [109, 111, 'slab'], [112, 112, 'road'],
    [113, 114, 'slab'], [115, 116, 'water'], [117, 117, 'grass'], [118, 118, 'slab'], [119, 119, 'grass'],
    [120, 120, 'road'], [121, 121, 'dirt'], [122, 123, 'water'], [124, 124, 'road'], [125, 126, 'water'],
    [127, 128, 'gravel'], [129, 130, 'slab'], [131, 131, 'road'], [132, 133, 'slab'], [134, 135, 'water'],
    [136, 136, 'grass'], [137, 137, 'slab'], [138, 138, 'grass'], [139, 139, 'road'], [140, 142, 'water'],
    [143, 143, 'road'], [144, 144, 'grass'], [145, 146, 'water'], [147, 147, 'gravel'], [148, 149, 'slab'],
    [150, 150, 'road'], [151, 152, 'slab'], [153, 155, 'water'], [156, 157, 'grass'], [158, 158, 'road'],
    [159, 160, 'water'], [161, 161, 'slab'], [162, 162, 'road'], [163, 163, 'slab'], [164, 164, 'grass'],
    [165, 166, 'water'], [167, 168, 'gravel'], [169, 169, 'road'], [170, 172, 'slab'], [173, 174, 'water'],
    [175, 176, 'grass'], [177, 177, 'road'], [178, 179, 'water'], [180, 180, 'slab'], [181, 181, 'road'],
    [182, 183, 'slab'], [184, 184, 'grass'], [185, 187, 'water'], [188, 188, 'road'], [189, 192, 'slab'],
    [193, 195, 'water'], [196, 196, 'road'], [197, 199, 'slab'], [200, 200, 'road'], [201, 202, 'slab'],
    [203, 203, 'grass'], [204, 206, 'water'], [207, 207, 'road'], [208, 211, 'slab'], [212, 214, 'water'],
    [215, 215, 'road'], [216, 218, 'slab'], [219, 219, 'road'], [220, 222, 'slab'], [223, 223, 'grass'],
    [224, 225, 'water'], [226, 226, 'road'], [227, 233, 'slab'], [234, 234, 'road'], [235, 236, 'slab'],
    [237, 239, 'keep'], [240, 242, 'slab'], [243, 243, 'grass'], [244, 244, 'water'], [245, 245, 'road'],
    [246, 247, 'slab'], [248, 255, 'road'], [256, 258, 'keep'], [259, 266, 'road'], [267, 271, 'grass'],
    [272, 272, 'road'], [273, 274, 'grass'], [275, 277, 'keep'], [278, 279, 'grass'], [280, 283, 'water'],
    [284, 284, 'road'], [285, 285, 'dirt'], [286, 286, 'grass'], [287, 289, 'dirt'], [290, 290, 'grass'],
    [291, 291, 'road'], [292, 297, 'dirt'], [298, 301, 'water'], [302, 302, 'dirt'], [303, 303, 'road'],
    [304, 304, 'dirt'], [305, 305, 'grass'], [306, 306, 'dirt'], [307, 307, 'gravel'], [308, 308, 'dirt'],
    [309, 309, 'grass'], [310, 322, 'road'], [323, 323, 'dirt'], [324, 324, 'grass'], [325, 327, 'dirt'],
    [328, 328, 'grass'], [329, 332, 'dirt'], [333, 333, 'road'], [334, 336, 'dirt'], [337, 340, 'water'],
    [341, 342, 'dirt'], [343, 347, 'grass'], [348, 351, 'dirt'], [352, 352, 'road'], [353, 356, 'dirt'],
    [357, 359, 'water'], [360, 361, 'dirt'],
]

export function expandPlanIds()
{
    const ids = new Array(PLAN_N * PLAN_N).fill('dirt')
    for(const [a, b, type] of RANGES)
    {
        for(let n = a; n <= b; n++)
            ids[n - 1] = type
    }
    return ids
}

export function serialToCenter(serial)
{
    const i = serial - 1
    const col = i % PLAN_N
    const row = Math.floor(i / PLAN_N)
    return {
        serial,
        col,
        row,
        x: PLAN_ORIGIN + col * PLAN_CELL + PLAN_CELL * 0.5,
        z: PLAN_ORIGIN + row * PLAN_CELL + PLAN_CELL * 0.5,
    }
}

export function centersForType(type)
{
    const ids = expandPlanIds()
    const out = []
    for(let i = 0; i < ids.length; i++)
    {
        if(ids[i] === type)
            out.push(serialToCenter(i + 1))
    }
    return out
}

export function nearestCenterOfType(type, x, z)
{
    const list = centersForType(type)
    let best = null
    let bestD = Infinity
    for(const cell of list)
    {
        const dx = cell.x - x
        const dz = cell.z - z
        const d = dx * dx + dz * dz
        if(d < bestD)
        {
            bestD = d
            best = cell
        }
    }
    return best
}

export function typeAtColRow(ids, col, row)
{
    if(col < 0 || row < 0 || col >= PLAN_N || row >= PLAN_N)
        return null
    return ids[row * PLAN_N + col]
}

/** 4-way 辅路十字路口 centers. */
export function findRoadCrossings()
{
    const ids = expandPlanIds()
    const out = []
    for(let row = 0; row < PLAN_N; row++)
    {
        for(let col = 0; col < PLAN_N; col++)
        {
            if(typeAtColRow(ids, col, row) !== 'road')
                continue
            const n = typeAtColRow(ids, col, row - 1) === 'road'
            const s = typeAtColRow(ids, col, row + 1) === 'road'
            const e = typeAtColRow(ids, col + 1, row) === 'road'
            const w = typeAtColRow(ids, col - 1, row) === 'road'
            if(n && s && e && w)
                out.push(serialToCenter(row * PLAN_N + col + 1))
        }
    }
    return out
}

/**
 * Curb lamp sockets along 辅路 cell edges that touch non-road.
 * Opposite edges use a half-spacing stagger (对向错位), spacing 12m.
 */
export function auxRoadLampSockets()
{
    const ids = expandPlanIds()
    const half = PLAN_CELL * 0.5
    const spacing = 12
    const stagger = spacing * 0.5
    const sockets = []
    const seen = new Set()

    const push = (x, z, faceX, faceZ, turn) =>
    {
        const key = `${(x * 2).toFixed(0)}_${(z * 2).toFixed(0)}`
        if(seen.has(key))
            return
        seen.add(key)
        sockets.push({
            x,
            z,
            yaw: Math.atan2(faceX, faceZ),
            // Opposite curbs: −1 clockwise 90°, +1 counterclockwise 90°.
            turn,
        })
    }

    for(let row = 0; row < PLAN_N; row++)
    {
        for(let col = 0; col < PLAN_N; col++)
        {
            if(typeAtColRow(ids, col, row) !== 'road')
                continue
            const c = serialToCenter(row * PLAN_N + col + 1)

            // West edge (face +X into road) — clockwise 90°
            if(typeAtColRow(ids, col - 1, row) !== 'road')
            {
                for(let d = 0; d < PLAN_CELL; d += spacing)
                    push(c.x - half + 0.55, c.z - half + d, 1, 0, -1)
            }
            // East edge (face -X) — counterclockwise 90°
            if(typeAtColRow(ids, col + 1, row) !== 'road')
            {
                for(let d = stagger; d < PLAN_CELL; d += spacing)
                    push(c.x + half - 0.55, c.z - half + d, -1, 0, 1)
            }
            // North edge (-Z, face +Z) — clockwise 90°
            if(typeAtColRow(ids, col, row - 1) !== 'road')
            {
                for(let d = 0; d < PLAN_CELL; d += spacing)
                    push(c.x - half + d, c.z - half + 0.55, 0, 1, -1)
            }
            // South edge (+Z, face -Z) — counterclockwise 90°
            if(typeAtColRow(ids, col, row + 1) !== 'road')
            {
                for(let d = stagger; d < PLAN_CELL; d += spacing)
                    push(c.x - half + d, c.z + half - 0.55, 0, -1, 1)
            }
        }
    }

    return sockets
}

/**
 * Discrete coverage map: each cell stores exactly one type code (覆盖, 不叠加).
 * Soft edges are applied in Floor/Grass shaders via neighbor color/weight blend —
 * do not LinearFilter this texture (interpolated codes are invalid).
 */
export function createPlanTexture()
{
    const ids = expandPlanIds()
    const data = new Uint8Array(PLAN_N * PLAN_N * 4)

    for(let i = 0; i < ids.length; i++)
    {
        const code = PLAN_TYPE[ids[i]] ?? 0
        const o = i * 4
        data[o] = Math.round(code * 255)
        data[o + 1] = 0
        data[o + 2] = 0
        data[o + 3] = 255
    }

    const tex = new THREE.DataTexture(data, PLAN_N, PLAN_N, THREE.RGBAFormat)
    tex.magFilter = THREE.NearestFilter
    tex.minFilter = THREE.NearestFilter
    tex.wrapS = THREE.ClampToEdgeWrapping
    tex.wrapT = THREE.ClampToEdgeWrapping
    tex.colorSpace = THREE.NoColorSpace
    tex.flipY = false
    tex.needsUpdate = true
    tex.generateMipmaps = false
    return tex
}
