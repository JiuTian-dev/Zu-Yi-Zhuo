import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'

/**
 * Bruno folio Grass port: wrapped grid of 3-vertex camera-facing blades
 * that follows a focus point, colored by ground palette, sways with wind.
 * Uses three's built-in `cameraPosition` uniform.
 */

const VERT = `
uniform vec2 uCenter;
uniform float uSize;
uniform float uTime;
uniform float uWind;
attribute vec2 aCenter;
attribute float aTip;
attribute float aSide;
attribute float aRand;
varying float vTip;
varying float vShade;
varying vec3 vWorld;
varying vec3 vGroundColor;

vec3 groundColorAt(vec2 xz) {
  float n = sin(xz.x * 0.35) * cos(xz.y * 0.31) * 0.5 + 0.5;
  float m = sin((xz.x + xz.y) * 0.11) * 0.5 + 0.5;
  vec3 a = vec3(0.42, 0.60, 0.36);
  vec3 b = vec3(0.30, 0.50, 0.33);
  vec3 c = vec3(0.50, 0.58, 0.28);
  return mix(mix(a, b, n), c, m * 0.4);
}

void main(){
  vec2 blade = aCenter * uSize;
  vec2 wrapped = mod(blade - uCenter + uSize * 0.5, uSize) - uSize * 0.5;
  vec3 base = vec3(wrapped.x + uCenter.x, 0.0, wrapped.y + uCenter.y);
  float n = sin(base.x * 0.45) * cos(base.z * 0.5) * 0.5 + 0.5;
  float height = 0.62 * mix(0.45, 1.0, aRand) * (0.6 + n * 0.7);
  float width = 0.08;
  vec3 shape = vec3(aSide * width, aTip * height, 0.0);
  vec3 world = base + shape;
  float angleToCam = atan(world.z - cameraPosition.z, world.x - cameraPosition.x) - 1.5707963;
  float ca = cos(angleToCam), sa = sin(angleToCam);
  world.xz = cameraPosition.xz + vec2(
    (world.x - cameraPosition.x) * ca - (world.z - cameraPosition.z) * sa,
    (world.x - cameraPosition.x) * sa + (world.z - cameraPosition.z) * ca
  );
  vec2 windDir = vec2(
    sin(uTime * 1.4 + base.x * 0.6 + base.z * 0.4),
    cos(uTime * 1.1 + base.z * 0.7)
  );
  world.xz += windDir * uWind * aTip * height;
  vTip = aTip;
  vShade = 0.75 + aRand * 0.25;
  vWorld = world;
  vGroundColor = groundColorAt(base.xz) * (0.78 + aTip * 0.4);
  gl_Position = projectionMatrix * viewMatrix * vec4(world, 1.0);
}
`

const FRAG = `
uniform vec3 uFogColor;
uniform float uFogNear;
uniform float uFogFar;
varying float vTip;
varying float vShade;
varying vec3 vWorld;
varying vec3 vGroundColor;
void main(){
  vec3 col = vGroundColor * vShade;
  float d = length(vWorld - cameraPosition);
  float f = smoothstep(uFogNear, uFogFar, d);
  col = mix(col, uFogColor, f);
  gl_FragColor = vec4(col, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`

export function makeSeaGrassGeometry(cells = 26) {
  const blades = cells * cells
  const position = new Float32Array(blades * 3 * 2)
  const aTip = new Float32Array(blades * 3)
  const aSide = new Float32Array(blades * 3)
  const aRand = new Float32Array(blades * 3)
  let v = 0
  for (let iX = 0; iX < cells; iX += 1) {
    for (let iZ = 0; iZ < cells; iZ += 1) {
      const i = iX * cells + iZ
      const cx = (iX + 0.5) / cells - 0.5
      const cz = (iZ + 0.5) / cells - 0.5
      for (let c = 0; c < 3; c += 1) {
        position[v * 2] = cx
        position[v * 2 + 1] = cz
        aTip[v] = c === 0 ? 1 : 0
        aSide[v] = c === 1 ? 1 : c === 2 ? -1 : 0
        aRand[v] = Math.random()
        v += 1
      }
    }
  }
  const zeros = new Float32Array(blades * 3 * 3)
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(zeros, 3))
  geometry.setAttribute('aCenter', new THREE.BufferAttribute(position, 2))
  geometry.setAttribute('aTip', new THREE.BufferAttribute(aTip, 1))
  geometry.setAttribute('aSide', new THREE.BufferAttribute(aSide, 1))
  geometry.setAttribute('aRand', new THREE.BufferAttribute(aRand, 1))
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1)
  return geometry
}

export function SeaGrass({ focus, size = 34, cells = 26, wind = 0.5 }: {
  focus: { current: { x: number; z: number } } | THREE.Vector3
  size?: number
  cells?: number
  wind?: number
}) {
  const geometry = useMemo(() => makeSeaGrassGeometry(cells), [cells])
  const material = useRef<THREE.ShaderMaterial>(null)
  const uniforms = useMemo(() => ({
    uCenter: { value: new THREE.Vector2() },
    uSize: { value: size },
    uTime: { value: 0 },
    uWind: { value: wind },
    uFogColor: { value: new THREE.Color('#aebcc8') },
    uFogNear: { value: 12 },
    uFogFar: { value: 46 },
  }), [size, wind])

  useFrame(({ clock }) => {
    if (!material.current) return
    material.current.uniforms.uTime.value = clock.elapsedTime
    const fp = focus as unknown as { x: number; z: number }
    material.current.uniforms.uCenter.value.set(fp.x, fp.z)
  })

  return (
    <mesh geometry={geometry} frustumCulled={false} renderOrder={2}>
      <shaderMaterial ref={material} vertexShader={VERT} fragmentShader={FRAG} side={THREE.DoubleSide} />
    </mesh>
  )
}
