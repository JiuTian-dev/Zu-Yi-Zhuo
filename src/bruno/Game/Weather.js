import { uniform } from 'three/tsl'

export class Weather
{
    constructor()
    {
        this.wind = { value: uniform(0.55) }
    }
}
