import * as THREE from 'three/webgpu'
import { color, Fn, mix, positionLocal, texture, uv, vec3, vec2, uniform } from 'three/tsl'
import { Game } from '../Game.js'
import { Grass } from './Grass.js'
import { Floor } from './Floor.js'
import { Flowers } from './Flowers.js'
import { MeshDefaultMaterial } from '../Materials/MeshDefaultMaterial.js'

/**
 * One table: meadow floor + grass + flowers + round table, stools,
 * seated figures, candle and lanterns. The scene uses the project's own
 * table palette and restrained dusk lighting.
 */
export class TableWorld
{
    constructor()
    {
        this.game = Game.getInstance()

        this.floor = new Floor()
        this.grass = new Grass()
        this.flowers = new Flowers()

        this.tableGroup = new THREE.Group()
        this.buildTable()
        this.buildFigures()
        this.buildLanterns()

        this.game.scene.add(this.tableGroup)
    }

    paletteMaterial(hex, opts = {})
    {
        return new MeshDefaultMaterial({ colorNode: color(hex), ...opts })
    }

    buildTable()
    {
        const wood = this.paletteMaterial('#8a5a35')
        const woodDark = this.paletteMaterial('#5d3f28')

        // Table top + leg
        const top = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.55, 0.09, 20), wood)
        top.position.set(0, 0.74, 0)
        top.castShadow = true
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.13, 0.7, 10), woodDark)
        leg.position.set(0, 0.36, 0)
        leg.castShadow = true
        const heart = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.14, 0.06, 10), this.paletteMaterial('#b0563f'))
        heart.position.set(0, 0.8, 0)
        this.tableGroup.add(top, leg, heart)

        // Candle + flame: the table's warm emissive light source.
        const candleMat = this.game.materials.getFromName?.('emissiveOrangeRadialGradient', new THREE.MeshBasicNodeMaterial({ transparent: true }))
            ?? this.paletteMaterial('#ffcf6e')
        const candle = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.05, 0.12, 10), this.paletteMaterial('#f3e2bb'))
        candle.position.set(0, 0.86, 0)
        const flame = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 10), candleMat)
        flame.position.set(0, 0.98, 0)
        const candleLight = new THREE.PointLight('#ffb85c', 2.2, 3.4, 2)
        candleLight.position.set(0, 1.02, 0)
        this.tableGroup.add(candle, flame, candleLight)

        // Mugs
        for(const [mx, mz] of [[0.42, 0.28], [-0.36, -0.3], [0.1, -0.42]])
        {
            const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.045, 0.09, 10), this.paletteMaterial('#e8dcc2'))
            mug.position.set(mx, 0.83, mz)
            mug.castShadow = true
            this.tableGroup.add(mug)
        }
    }

    buildFigures()
    {
        // Five seated figures (palette accents), gentle idle bob
        const accents = ['#e8dfca', '#d87843', '#59698c', '#739d94', '#ffd58c']
        const seats = 5
        for(let i = 0; i < seats; i++)
        {
            const a = (i / seats) * Math.PI * 2 + Math.PI / 5
            const x = Math.cos(a) * 1.02
            const z = Math.sin(a) * 1.02
            const g = new THREE.Group()
            g.position.set(x, 0, z)
            g.rotation.y = -a + Math.PI

            const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.16, 0.22, 4, 10), this.paletteMaterial(accents[i]))
            body.position.set(0, 0.5, 0)
            body.castShadow = true
                        const head = new THREE.Mesh(new THREE.SphereGeometry(0.13, 12, 10), this.paletteMaterial('#e6bd93'))
            head.position.set(0, 0.85, 0)
            head.castShadow = true
            g.add(body, head)
            this.tableGroup.add(g)
        }
    }

    buildLanterns()
    {
        const lampMat = this.paletteMaterial('#ffcf6e', { transparent: true })
        const lampCore = this.paletteMaterial('#c9a0ff')
        for(const [lx, lz, s] of [[2.6, 1.9, 1], [-2.3, 2.3, 0.85]])
        {
            const post = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.04, 0.85 * s, 6), this.paletteMaterial('#4c3a28'))
            post.position.set(lx, 0.42 * s, lz)
            const box = new THREE.Mesh(new THREE.BoxGeometry(0.2 * s, 0.24 * s, 0.2 * s), lampMat)
            box.position.set(lx, 0.92 * s, lz)
            const light = new THREE.PointLight('#c9a0ff', 1.6, 4.5, 2)
            light.position.set(lx, 0.98 * s, lz)
            this.tableGroup.add(post, box, light)
        }
    }
}
