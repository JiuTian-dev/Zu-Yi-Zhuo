import { Game } from '../../Game.js'
import { AltarArea } from './AltarArea.js'
import { CookieArea } from './CookieArea.js'
import { LandingArea } from './LandingArea.js'
import { ProjectsArea } from './ProjectsArea.js'
import { LabArea } from './LabArea.js'
import { CareerArea } from './CareerArea.js'
import { SocialArea } from './SocialArea.js'
import { ToiletArea } from './ToiletArea.js'
import { BowlingArea } from './BowlingArea.js'
import { CircuitArea } from './CircuitArea.js'
import { BehindTheSceneArea } from './BehindTheSceneArea.js'
import { AchievementsArea } from './AchievementsArea.js'
import { TimeMachineArea } from './TimeMachineArea.js'
import { EasterArea } from './EasterArea.js'

export class Areas
{
    constructor()
    {
        this.game = Game.getInstance()

        const list = [
            [ 'achievements', AchievementsArea ],
            [ 'altar', AltarArea ],
            [ 'behindTheScene', BehindTheSceneArea ],
            [ 'bowling', BowlingArea ],
            [ 'career', CareerArea ],
            [ 'circuit', CircuitArea ],
            [ 'cookie', CookieArea ],
            [ 'easter', EasterArea ],
            [ 'lab', LabArea ],
            [ 'landing', LandingArea ],
            [ 'projects', ProjectsArea ],
            [ 'social', SocialArea ],
            [ 'toilet', ToiletArea ],
            [ 'timeMachine', TimeMachineArea ],
        ]

        const model = [...this.game.resources.areasModel.scene.children]
        
        for(const child of model)
        {
            for(const [ name, AreaClass ] of list)
            {
                if(child.name.startsWith(name))
                    this[name] = new AreaClass(child)
            }
        }

        // 组一桌: remove Bruno portfolio set pieces (screenshots: bowling/cookie/projects/career/social/achievements/easter/altar/…).
        // Keep vehicle, road, respawns, map; suburban dressing is separate.
        this.stripOriginalPortfolio()
    }

    stripOriginalPortfolio()
    {
        for(const key of Object.keys(this))
        {
            const area = this[key]
            if(area && typeof area.strip === 'function')
                area.strip()
        }

        // Any interactive points created by areas stay permanently hidden.
        const points = this.game.interactivePoints?.items
        if(points)
        {
            for(const item of points)
            {
                item.permanentlyHidden = true
                if(typeof item.hide === 'function')
                    item.hide()
                if(item.intersect)
                    item.intersect.active = false
                item.recoveryState = 3 // STATE_HIDDEN
                item.showAfterReveal = false
            }
        }
    }
}