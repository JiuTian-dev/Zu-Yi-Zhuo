// Shim: debug disabled in the table runtime build.
// The instance itself is a recursive no-op proxy: ANY method call
// (addFolder/addBinding/addManualBinding/...) resolves silently.
const noopTarget = function () {}
const noopProxy = new Proxy(noopTarget, {
    get: (target, key) =>
    {
        if(key === Symbol.toPrimitive)
            return () => ''
        return noopProxy
    },
    apply: () => noopProxy,
    construct: () => noopProxy,
})

export class Debug
{
    constructor()
    {
        this.active = false
        return noopProxy
    }
}
