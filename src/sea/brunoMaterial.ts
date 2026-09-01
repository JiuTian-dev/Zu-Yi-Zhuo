import * as THREE from 'three'

/**
 * Bruno-Simon-style stylized material pass (ported from folio-2025
 * MeshDefaultMaterial, MIT). WebGL/R3F adaptation via onBeforeCompile:
 * - two-band core shadow with a colored shadow tint (never pure black)
 * - ground-bounce tint: downward faces pick up the ground color
 * - soft light response on Lambert (no specular harshness)
 */

export interface BrunoStyleOptions {
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

export const brunoShared = {
  lightDir: new THREE.Vector3(0.45, 0.8, 0.35).normalize(),
  shadowTint: new THREE.Color('#7a6a96'),
  groundColor: new THREE.Color('#79a86d'),
  bandLow: -0.15,
  bandHigh: 0.55,
  bounce: 0.35,
}

const patched = new WeakSet<THREE.Material>()

export function applyBrunoStyle(material: THREE.Material, options?: Partial<BrunoStyleOptions>) {
  const mat = material as THREE.Material & { onBeforeCompile: unknown }
  if (patched.has(mat)) return material
  patched.add(mat)

  const dir = options?.lightDir ?? brunoShared.lightDir
  const shadowTint = options?.shadowTint ?? brunoShared.shadowTint
  const groundColor = options?.groundColor ?? brunoShared.groundColor
  const bandLow = options?.bandLow ?? brunoShared.bandLow
  const bandHigh = options?.bandHigh ?? brunoShared.bandHigh
  const bounce = options?.bounce ?? brunoShared.bounce

  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uBrunoLightDir = { value: dir }
    shader.uniforms.uBrunoShadowTint = { value: shadowTint }
    shader.uniforms.uBrunoGround = { value: groundColor }
    shader.uniforms.uBrunoBand = { value: new THREE.Vector2(bandLow, bandHigh) }
    shader.uniforms.uBrunoBounce = { value: bounce }

    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vBrunoNormal;\nvarying vec3 vBrunoWorldPos;')
      .replace('#include <beginnormal_vertex>', '#include <beginnormal_vertex>')
      .replace('#include <defaultnormal_vertex>', '#include <defaultnormal_vertex>\nvBrunoNormal = normalize(transformedNormal);')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvBrunoWorldPos = (modelMatrix * vec4(transformed, 1.0)).xyz;')

    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vBrunoNormal;\nvarying vec3 vBrunoWorldPos;\nuniform vec3 uBrunoLightDir;\nuniform vec3 uBrunoShadowTint;\nuniform vec3 uBrunoGround;\nuniform vec2 uBrunoBand;\nuniform float uBrunoBounce;')
      .replace('#include <lights_fragment_end>', `#include <lights_fragment_end>
  {
    vec3 nB = normalize(vBrunoNormal);
    float ndl = dot(nB, normalize(uBrunoLightDir));
    // two-band stylized core shadow, tinted instead of black
    float band = smoothstep(uBrunoBand.x, uBrunoBand.y, ndl);
    vec3 shadowed = diffuseColor.rgb * uBrunoShadowTint;
    reflectedLight.directDiffuse = mix(shadowed * uBrunoBounce + reflectedLight.indirectDiffuse * 0.4, reflectedLight.directDiffuse, band);
    // ground bounce on downward faces
    float down = smoothstep(-0.1, -0.75, nB.y);
    reflectedLight.directDiffuse += diffuseColor.rgb * uBrunoGround * down * 0.22;
  }`)
  }
  return material
}

/** Tick shared light direction for a slow day drift. Call once per frame. */
export function updateBrunoShared(time: number) {
  const a = time * 0.008
  brunoShared.lightDir.set(Math.cos(a) * 0.6 + 0.25, 0.75 + Math.sin(a * 0.7) * 0.1, Math.sin(a) * 0.45 + 0.3).normalize()
}
