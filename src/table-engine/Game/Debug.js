// Shim: debug disabled in the table runtime build.
// The instance is a no-op proxy, but primitives stay primitives:
// `.active` MUST be false (truthy proxy here once poisoned WGSL
// uniforms with NaN and invalidated every render pipeline).
const shim = new Proxy(function () {}, {
    get: (target, key) =>
    {
        if(key === 'active')
            return false
        if(key === 'value')
            return 0
        if(key === Symbol.toPrimitive)
            return () => 0
        if(key === Symbol.iterator)
            return [][Symbol.iterator]()
        return shim
    },
    apply: () => shim,
    construct: () => shim,
})

export class Debug
{
    constructor()
    {
        this.active = false
        return shim
    }
}
