// Product landscape: one centreline shared by the hillside cut and water mask.
export const ALPINE_STREAM = Object.freeze({ startZ: -83, endZ: -9, width: 1.6 })
export function alpineStreamX(z)
{
    const t = Math.max(0, Math.min(1, (-z - 9) / 25))
    return -15 - 20 * t * t * (3 - 2 * t) + Math.sin((z + 9) * 0.13) * 4
}
