/** @origin BRUNO-ADAPTED — debug controls disabled in the product runtime. */
export class Debug
{
    constructor()
    {
        this.active = false
    }

    addManualBinding(_panel, object, property, _settings, update, manual = false)
    {
        return {
            manual,
            manualValue: object?.[property],
            update: () => { if(!manual && typeof update === 'function') object[property] = update() },
        }
    }

    addThreeColorBinding()
    {
        return { on: () => this }
    }

    addButtons()
    {
        return this
    }
}
