import { Events } from './Events.js'

export class Viewport
{
    constructor(domElement)
    {
        this.domElement = domElement

        this.events = new Events()
        this.throttleTimeout = null
        this.onResize = this.onResize.bind(this)
        
        this.measure()
        this.setResize()
    }

    measure()
    {
        const bounding = this.domElement.getBoundingClientRect()

        this.width = bounding.width
        this.height = bounding.height
        this.ratio = this.width / this.height

        this.pixelRatioPure = window.devicePixelRatio
        this.pixelRatioMax = 2
        this.pixelRatio = Math.min(this.pixelRatioPure, this.pixelRatioMax)
    }

    setResize()
    {
        addEventListener('resize', this.onResize)
    }

    onResize()
    {
        this.measure()
        this.events.trigger('change')

        if(this.throttleTimeout)
        {
            clearTimeout(this.throttleTimeout)
        }

        this.throttleTimeout = setTimeout(() =>
        {
            this.throttleTimeout = null
            this.events.trigger('throttleChange')
        }, 400)
    }

    destroy()
    {
        removeEventListener('resize', this.onResize)
        if(this.throttleTimeout)
            clearTimeout(this.throttleTimeout)
    }
}
