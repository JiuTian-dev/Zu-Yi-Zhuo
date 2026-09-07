// Local visual QA: inspect full orbit and asset loading without business writes.
(async (page) => {
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.reload()
    await page.waitForFunction(() => document.querySelector('.bruno-runtime-canvas')?.dataset.runtimeState === 'ready')
    await page.evaluate(async () => {
        const url = performance.getEntriesByType('resource').find(e => e.name.includes('/Game/Game.js')).name
        window.islandReview = (await import(url)).Game.getInstance()
    })
    for(const name of ['收起问题卡', '收起桌单'])
        if(await page.getByRole('button', { name, exact: true }).count())
            await page.getByRole('button', { name, exact: true }).click()
    const evidence = []
    for(let i = 0; i < 8; i++) {
        await page.evaluate(i => {
            const g = window.islandReview
            g.dayCycles.setMode('day')
            g.cameraOrbit.goalAzimuth = 0.62 + i * Math.PI / 4
            g.cameraOrbit.goalElevation = 0.22
            g.cameraOrbit.goalRadius = 25
        }, i)
        await page.waitForTimeout(1800)
        await page.screenshot({ path: `output/playwright/island-orbit-${i}.png` })
        evidence.push(await page.evaluate(() => ({
            state: document.querySelector('.bruno-runtime-canvas').dataset.runtimeState,
            elevation: window.islandReview.cameraOrbit.renderElevation,
            mountains: Boolean(window.islandReview.scene.getObjectByName('product-dem-snow-ridge')),
            canvas: document.querySelectorAll('canvas').length,
        })))
    }
    await page.evaluate(() => { window.islandReview.dayCycles.setMode('night'); window.islandReview.cameraOrbit.reset() })
    await page.waitForTimeout(2000)
    await page.screenshot({ path: 'output/playwright/island-night.png' })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'output/playwright/island-mobile.png' })
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.evaluate(() => window.islandReview.dayCycles.setMode('day'))
    await page.waitForTimeout(2000)
    await page.screenshot({ path: 'output/playwright/island-default.png' })
    return { errors, evidence, alpineRequests: await page.evaluate(() => performance.getEntriesByType('resource').filter(e => e.name.includes('/alpine/')).map(e => e.name)) }
})
