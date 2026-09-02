import { color, float, uniform, vec2 } from 'three/tsl'

export class Reveal
{
    constructor()
    {
        this.position2Uniform = uniform(vec2(0, 0))
        this.distance = uniform(9999)
        this.thickness = uniform(1)
        this.color = uniform(color('#ffffff'))
        this.intensity = uniform(0)
    }
}
