import { Events } from './Events.js'

export class Viewport
{
    constructor(domElement)
    {
        this.domElement = domElement
        this.events = new Events()
        this.pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
        this.width = domElement.clientWidth || window.innerWidth
        this.height = domElement.clientHeight || window.innerHeight

        this.resize = this.resize.bind(this)
        window.addEventListener('resize', this.resize)
    }

    resize()
    {
        this.width = this.domElement?.clientWidth || window.innerWidth
        this.height = this.domElement?.clientHeight || window.innerHeight
        this.pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
        this.events.trigger('change')
    }

    destroy()
    {
        window.removeEventListener('resize', this.resize)
    }
}
