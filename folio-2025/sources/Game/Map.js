import { clamp } from 'three/src/math/MathUtils.js'
import { Game } from './Game.js'

export class Map
{
    constructor()
    {
        this.game = Game.getInstance()

        this.initiated = false
        this.embed = typeof window !== 'undefined'
            && window.parent
            && window.parent !== window
            && document.documentElement.classList.contains('zuoyizhuo-embed')
        this.modal = this.game.modals.items.get('map')
        this.element = this.modal.element.querySelector('.js-map-container')
        this.panel = this.element.querySelector('.js-zuoyizhuo-map-panel')
        this.tablesElement = this.element.querySelector('.js-open-tables')

        this.setTrigger()
        this.setInputs()

        if(this.embed)
            this.setEmbedPanel()

        this.modal.events.on('open', () =>
        {
            if(this.embed)
            {
                this.requestDiscovery()
                return
            }

            if(!this.initiated)
                this.init()

            this.texture.update()
        })
    }

    setEmbedPanel()
    {
        if(!this.panel)
            return

        this.panel.hidden = false
        this.element.classList.add('is-zuoyizhuo-lobby')

        const texture = this.element.querySelector('.js-texture')
        const player = this.element.querySelector('.js-player')
        if(texture)
            texture.remove()
        if(player)
            player.remove()

        this.panel.querySelector('.js-precise-match')?.addEventListener('click', (event) =>
        {
            event.preventDefault()
            this.game.modals.close()
            this.postParent({ type: 'zuoyizhuo:precise-match' })
        })
        this.panel.querySelector('.js-host-table')?.addEventListener('click', (event) =>
        {
            event.preventDefault()
            this.game.modals.close()
            this.postParent({ type: 'zuoyizhuo:host-table' })
        })
        this.panel.querySelector('.js-refresh-tables')?.addEventListener('click', (event) =>
        {
            event.preventDefault()
            this.requestDiscovery()
        })

        window.addEventListener('message', (event) =>
        {
            const data = event.data
            if(!data || typeof data !== 'object')
                return
            if(data.type === 'zuoyizhuo:discovery')
                this.renderDiscovery(data)
        })

        this.renderDiscovery({ status: 'loading', items: [] })
    }

    postParent(payload)
    {
        try
        {
            window.parent.postMessage(payload, '*')
        }
        catch(_error)
        {
            // Parent may be gone during teardown.
        }
    }

    requestDiscovery()
    {
        this.renderDiscovery({ status: 'loading', items: [] })
        this.postParent({ type: 'zuoyizhuo:request-discovery' })
    }

    renderDiscovery(payload)
    {
        if(!this.tablesElement)
            return

        const status = payload?.status || 'ready'
        const items = Array.isArray(payload?.items) ? payload.items : []

        if(status === 'loading')
        {
            this.tablesElement.innerHTML = `<p class="zuoyizhuo-map-empty" role="status">正在读取已开的桌…</p>`
            return
        }

        if(status === 'error')
        {
            const message = typeof payload?.message === 'string' && payload.message
                ? payload.message
                : '后端暂时不可用'
            this.tablesElement.innerHTML = `
                <p class="zuoyizhuo-map-empty is-error" role="alert">${this.escapeHtml(message)}</p>
                <button type="button" class="js-retry-tables zuoyizhuo-map-retry">重新连接</button>
            `
            this.tablesElement.querySelector('.js-retry-tables')?.addEventListener('click', () => this.requestDiscovery())
            return
        }

        if(!items.length)
        {
            this.tablesElement.innerHTML = `<p class="zuoyizhuo-map-empty" role="status">还没有已开的桌。可以先开桌，或用精准匹配找一桌。</p>`
            return
        }

        this.tablesElement.innerHTML = items.map((item) =>
        {
            const id = this.escapeHtml(String(item.table_id || ''))
            const question = this.escapeHtml(String(item.core_question || item.table_id || '未命名桌'))
            const count = Number(item.participant_count) || 0
            const seats = Number(item.available_seats)
            const seatsLabel = Number.isFinite(seats) && seats > 0 ? `还剩 ${seats} 席` : '进行中'
            const meta = this.escapeHtml(`${count} 人 · ${seatsLabel}`)
            return `
                <button type="button" class="zuoyizhuo-map-table" data-table-id="${id}" role="listitem">
                    <b>${question}</b>
                    <small>${meta}</small>
                </button>
            `
        }).join('')

        for(const button of this.tablesElement.querySelectorAll('.zuoyizhuo-map-table'))
        {
            button.addEventListener('click', () =>
            {
                const tableId = button.getAttribute('data-table-id')
                if(!tableId)
                    return
                this.game.modals.close()
                this.postParent({ type: 'zuoyizhuo:enter-table', tableId })
            })
        }
    }

    escapeHtml(value)
    {
        return value
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;')
    }

    init()
    {
        this.initiated = true
        
        this.setLocations()
        this.setPlayer()
        this.setTexture()

        this.game.ticker.events.on('tick', () =>
        {
            this.update()
        }, 14)
    }

    setLocations()
    {
        this.locations = {}
        this.locations.items = [
            { name: 'Achievements', respawnName: 'achievements', offset: { x: 0, y: -0.01 } },
            { name: 'Altar', respawnName: 'altar', offset: { x: 0, y: -0.05 } },
            { name: 'Behind<br /> the scene', respawnName: 'behindTheScene', offset: { x: 0.01, y: 0 } },
            { name: 'Bowling', respawnName: 'bowling', offset: { x: -0.08, y: 0.03 } },
            { name: 'Career', respawnName: 'career', offset: { x: 0, y: -0.06 } },
            { name: 'Circuit', respawnName: 'circuit', offset: { x: -0.08, y: -0.05 } },
            { name: 'Cookie', respawnName: 'cookie', offset: { x: -0.02, y: -0.01 } },
            { name: 'Lab', respawnName: 'lab', offset: { x: -0.03, y: 0 } },
            { name: 'Landing', respawnName: 'landing', offset: { x: 0.02, y: 0 } },
            { name: 'Projects', respawnName: 'projects', offset: { x: 0, y: -0.02 } },
            { name: 'Social', respawnName: 'social', offset: { x: -0.01, y: -0.04 } },
            { name: 'Time Machine', respawnName: 'timeMachine', offset: { x: 0, y: 0 } },
        ]

        for(const item of this.locations.items)
        {
            const respawn = this.game.respawns.getByName(item.respawnName)
            const mapPosition = this.worldToMap(respawn.position)

            // HTML
            const html = /* html */`
                <div class="pin"></div>
                <div class="name-container">
                    <div class="name">${item.name}</div>
                </div>
            `

            const element = document.createElement('div')
            element.classList.add('location')
            element.innerHTML = html
            element.style.left = `${(mapPosition.x + item.offset.x)* 100}%`
            element.style.top = `${(mapPosition.y + item.offset.y)* 100}%`
            element.style.zIndex = Math.round(mapPosition.y * 1000)
            
            this.element.append(element)

            element.addEventListener('click', () =>
            {
                // Embedded 组一桌: map pin → close map (original anim) → match page.
                if (window.parent && window.parent !== window)
                {
                    this.game.modals.close()
                    window.parent.postMessage({ type: 'zuoyizhuo:enter-match' }, '*')
                    return
                }
                this.game.player.respawn(item.respawnName, () =>
                {
                    this.game.view.focusPoint.isTracking = true
                })
                this.game.modals.close()
            })
        }
    }
    
    setPlayer()
    {
        this.player = {}
        this.player.element = this.element.querySelector('.js-player')
        this.player.roundedPosition = { x: 0, y: 0 }
    }
    
    setTexture()
    {
        this.texture = {}
        this.texture.element = this.element.querySelector('.js-texture')
        this.texture.previousUrl = null

        this.texture.element.addEventListener('load', () =>
        {
            this.texture.element.classList.add('is-visible')
        })
        
        this.texture.update = () =>
        {
            const url = this.game.dayCycles.intervalEvents.get('night').inInterval ? 'ui/map/map-night.webp' : 'ui/map/map-day.webp'

            if(url !== this.texture.previousUrl)
            {
                this.texture.element.classList.remove('is-visible')
                this.texture.previousUrl = url
                this.texture.element.src = url
            }
        }
    }

    setTrigger()
    {
        const element = this.game.domElement.querySelector('.js-map-trigger')
        
        element.addEventListener('click', (event) =>
        {
            // Always open the original map modal (same animation). Match jump is via map pins.
            event.preventDefault()
            this.game.modals.open('map')
        })
        element.addEventListener('keydown', (event) =>
        {
            event.preventDefault()
        })
    }

    setInputs()
    {
        // Inputs keyboard
        this.game.inputs.addActions([
            { name: 'map', categories: [ 'modal', 'menu', 'wandering' ], keys: [ 'Keyboard.m', 'Keyboard.KeyM' ] },
        ])
        this.game.inputs.events.on('map', (action) =>
        {
            if(action.active)
            {
                if(!this.modal.isOpen)
                    this.game.modals.open('map')
                else
                    this.game.modals.close()
            }
        })
    }

    worldToMap(coordinates)
    {
        let x = coordinates.x
        let y = typeof coordinates.z !== 'undefined' ? coordinates.z : coordinates.y

        x /= this.game.terrain.size
        y /= this.game.terrain.size

        x += 0.5
        y += 0.5

        x = clamp(x, 0, 1)
        y = clamp(y, 0, 1)

        return { x, y }
    }

    update()
    {
        if(this.embed || !this.modal.isOpen || !this.player?.element)
            return

        const playerRoundedX = Math.round(this.game.player.position.x)
        const playerRoundedY = Math.round(this.game.player.position.z)

        if(playerRoundedX !== this.player.roundedPosition.x || playerRoundedY !== this.player.roundedPosition.y)
        {
            this.player.roundedPosition.x = playerRoundedX
            this.player.roundedPosition.y = playerRoundedY

            const playerCoordinates = this.worldToMap(this.player.roundedPosition)
            const x = Math.round(playerCoordinates.x * 1000) / 10
            const y = Math.round(playerCoordinates.y * 1000) / 10

            this.player.element.style.left = `${x}%`
            this.player.element.style.top = `${y}%`
            this.player.element.style.transform = `rotate(${-this.game.physicalVehicle.yRotation}rad)`
        }
    }
}
