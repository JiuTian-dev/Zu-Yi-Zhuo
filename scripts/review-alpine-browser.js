// Playwright CLI run-code input. Run against the local development page only.
// Camera/day-cycle mutations below are visual QA, never REST/WS actions.
(async (page) => {
    const prefix = page.url().includes('alpine=matterhorn') ? 'alpine-matterhorn' : 'alpine'
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.reload()
    await page.waitForFunction(() => document.querySelector('.bruno-runtime-canvas')?.dataset.runtimeState === 'ready')
    await page.evaluate(async () => {
        const url = performance.getEntriesByType('resource').find(entry => entry.name.includes('/Game/Game.js')).name
        const { Game } = await import(url)
        window.alpineReview = Game.getInstance()
    })
    await page.waitForTimeout(4000)
    for(const name of ['收起问题卡', '收起桌单'])
        if(await page.getByRole('button', { name, exact: true }).count())
            await page.getByRole('button', { name, exact: true }).click()
    const evidence = []
    for(const [name, azimuth, elevation, radius, mode] of [
        ['mountain-day', 0.62, 0.12, 34, 'day'],
        ['mountain-night', 0.62, 0.12, 34, 'night'],
        ['sea-day', 3.76, 0.18, 34, 'day'],
        ['overhead-day', 0.62, 0.8, 24, 'day'],
        ['table-day', 0.62, 0.42, 16.8, 'day'],
    ]) {
        await page.evaluate(({ azimuth, elevation, radius, mode }) => {
            const game = window.alpineReview
            game.cameraOrbit.cancelTransition()
            game.cameraOrbit.goalAzimuth = azimuth
            game.cameraOrbit.goalElevation = elevation
            game.cameraOrbit.goalRadius = radius
            game.dayCycles.setMode(mode)
        }, { azimuth, elevation, radius, mode })
        await page.waitForTimeout(2500)
        await page.screenshot({ path: `output/playwright/${prefix}-${name}.png` })
        evidence.push(await page.evaluate(() => {
            const g = window.alpineReview
            return {
                canvas: document.querySelectorAll('canvas').length,
                state: document.querySelector('.bruno-runtime-canvas').dataset.runtimeState,
                radius: g.cameraOrbit.radius, elevation: g.cameraOrbit.elevation,
                mode: g.dayCycles.mode,
                renderer: g.rendering.renderer.backend.constructor.name,
                lod: g.scene.getObjectByName('product-dem-snow-ridge').getCurrentLevel(),
            }
        }))
    }
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(1000)
    await page.screenshot({ path: `output/playwright/${prefix}-narrow.png` })
    await page.setViewportSize({ width: 1440, height: 900 })
    return evidence
})
