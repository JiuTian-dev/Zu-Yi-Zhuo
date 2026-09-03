/** @origin ZUOYIZHUO-SCENE — backend projection into the single Bruno runtime. */

export class SceneBridge
{
    constructor(game)
    {
        this.game = game
    }

    apply({ tableState = null, hostAction = null, speakingId = null, closeState = 'idle' } = {})
    {
        const tableMeeting = this.game.world?.tableMeeting
        if(!tableMeeting) return

        tableMeeting.setTableState?.(tableState, speakingId)
        tableMeeting.setHostAction?.(hostAction, closeState)
    }

    destroy()
    {
        this.game = null
    }
}
