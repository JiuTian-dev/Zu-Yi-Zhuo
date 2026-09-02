import * as THREE from 'three'

/**
 * Project table material pass. WebGL/R3F adaptation via onBeforeCompile:
 * - two-band core shadow with a colored shadow tint (never pure black)
 * - ground-bounce tint: downward faces pick up the ground color
 * - soft light response on Lambert (no specular harshness)
 */

export interface TableStyleOptions {
  /** light direction (world, normalized) */
  lightDir: THREE.Vector3
  /** shadow tint, multiplied into base color in shadowed bands */
  shadowTint: THREE.Color
  /** ground/bounce color reflected on downward faces */
  groundColor: THREE.Color
  bandLow?: number
  bandHigh?: number
  bounce?: number
}

export const tableShared = {
  lightDir: new THREE.Vector3(0.45, 0.8, 0.35).normalize(),
  shadowTint: new THREE.Color('#7a6a96'),
  groundColor: new THREE.Color('#79a86d'),
  bandLow: -0.15,
  bandHigh: 0.55,
  bounce: 0.35,
}

const patched = new WeakSet<THREE.Material>()

export function applyTableStyle(material: THREE.Material, options?: Partial<TableStyleOptions>) {
  const mat = material as THREE.Material & { onBeforeCompile: unknown }
  if (patched.has(mat)) return material
  patched.add(mat)

  const dir = options?.lightDir ?? tableShared.lightDir
  const shadowTint = options?.shadowTint ?? tableShared.shadowTint
  const groundColor = options?.groundColor ?? tableShared.groundColor
  const bandLow = options?.bandLow ?? tableShared.bandLow
  const bandHigh = options?.bandHigh ?? tableShared.bandHigh
  const bounce = options?.bounce ?? tableShared.bounce

  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uTableLightDir = { value: dir }
    shader.uniforms.uTableShadowTint = { value: shadowTint }
    shader.uniforms.uTableGround = { value: groundColor }
    shader.uniforms.uTableBand = { value: new THREE.Vector2(bandLow, bandHigh) }
    shader.uniforms.uTableBounce = { value: bounce }

    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vTableNormal;\nvarying vec3 vTableWorldPos;')
      .replace('#include <beginnormal_vertex>', '#include <beginnormal_vertex>')
      .replace('#include <defaultnormal_vertex>', '#include <defaultnormal_vertex>\nvTableNormal = normalize(transformedNormal);')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvTableWorldPos = (modelMatrix * vec4(transformed, 1.0)).xyz;')

    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vTableNormal;\nvarying vec3 vTableWorldPos;\nuniform vec3 uTableLightDir;\nuniform vec3 uTableShadowTint;\nuniform vec3 uTableGround;\nuniform vec2 uTableBand;\nuniform float uTableBounce;')
      .replace('#include <lights_fragment_end>', `#include <lights_fragment_end>
  {
    vec3 nB = normalize(vTableNormal);
    float ndl = dot(nB, normalize(uTableLightDir));
    // two-band stylized core shadow, tinted instead of black
    float band = smoothstep(uTableBand.x, uTableBand.y, ndl);
    vec3 shadowed = diffuseColor.rgb * uTableShadowTint;
    reflectedLight.directDiffuse = mix(shadowed * uTableBounce + reflectedLight.indirectDiffuse * 0.4, reflectedLight.directDiffuse, band);
    // ground bounce on downward faces
    float down = smoothstep(-0.1, -0.75, nB.y);
    reflectedLight.directDiffuse += diffuseColor.rgb * uTableGround * down * 0.22;
  }`)
  }
  return material
}

/** Tick shared light direction for a slow day drift. Call once per frame. */
export function updateTableShared(time: number) {
  const a = time * 0.008
  tableShared.lightDir.set(Math.cos(a) * 0.6 + 0.25, 0.75 + Math.sin(a * 0.7) * 0.1, Math.sin(a) * 0.45 + 0.3).normalize()
}
