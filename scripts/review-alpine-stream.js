// Local visual QA only; does not invoke product REST/WS actions.
(async (page) => {
    await page.evaluate(() => {
        const g = window.alpineReview
        g.cameraOrbit.cancelTransition()
        g.cameraOrbit.goalTarget.set(24.5, 0.5, 3)
        g.cameraOrbit.goalRadius = 34
        g.cameraOrbit.goalElevation = 1.2
        g.cameraOrbit.goalAzimuth = 0
        g.dayCycles.setMode('day')
    })
    await page.waitForTimeout(3000)
    await page.screenshot({ path: 'output/playwright/alpine-stream-audit.png' })
    await page.evaluate(() => window.alpineReview.cameraOrbit.goalTarget.set(24.5, 0.5, 24))
    await page.waitForTimeout(2500)
    await page.screenshot({ path: 'output/playwright/alpine-stream-mouth.png' })
})
