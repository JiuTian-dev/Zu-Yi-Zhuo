import { uniform } from 'three/tsl'

export class Water
{
    constructor()
    {
        this.surfaceElevationUniform = uniform(-0.55)
        this.surfaceThicknessUniform = uniform(0.3)
    }
}
