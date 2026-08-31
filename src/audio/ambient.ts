/** Procedural ambient sound (Web Audio, no assets). Default off; user opt-in. */

type WorldKey = 'valley' | 'campfire' | 'workshop'

let context: AudioContext | null = null
let master: GainNode | null = null
let nodes: AudioNode[] = []
let timers: number[] = []
let current: WorldKey | null = null

function noiseBuffer(audio: AudioContext, seconds = 2): AudioBuffer {
  const buffer = audio.createBuffer(1, audio.sampleRate * seconds, audio.sampleRate)
  const data = buffer.getChannelData(0)
  let last = 0
  for (let i = 0; i < data.length; i += 1) {
    const white = Math.random() * 2 - 1
    last = (last + 0.02 * white) / 1.02
    data[i] = last * 3.2
  }
  return buffer
}

function loopNoise(audio: AudioContext, buffer: AudioBuffer, filter: BiquadFilterNode, gain: GainNode) {
  const source = audio.createBufferSource()
  source.buffer = buffer
  source.loop = true
  source.connect(filter)
  filter.connect(gain)
  gain.connect(master!)
  source.start()
  nodes.push(source, filter, gain)
}

function lfo(audio: AudioContext, target: AudioParam, rate: number, depth: number) {
  const oscillator = audio.createOscillator()
  const amplifier = audio.createGain()
  oscillator.frequency.value = rate
  amplifier.gain.value = depth
  oscillator.connect(amplifier)
  amplifier.connect(target)
  oscillator.start()
  nodes.push(oscillator, amplifier)
}

function birdChirp(audio: AudioContext) {
  const oscillator = audio.createOscillator()
  const gain = audio.createGain()
  const now = audio.currentTime
  oscillator.type = 'sine'
  const base = 2100 + Math.random() * 900
  oscillator.frequency.setValueAtTime(base, now)
  oscillator.frequency.exponentialRampToValueAtTime(base * 1.5, now + 0.09)
  oscillator.frequency.exponentialRampToValueAtTime(base * 0.8, now + 0.22)
  gain.gain.setValueAtTime(0, now)
  gain.gain.linearRampToValueAtTime(0.028, now + 0.03)
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.3)
  oscillator.connect(gain)
  gain.connect(master!)
  oscillator.start(now)
  oscillator.stop(now + 0.35)
}

function scheduleBirds(audio: AudioContext) {
  const tick = () => {
    if (context && current === 'valley') birdChirp(context)
    timers.push(window.setTimeout(tick, 3800 + Math.random() * 5200))
  }
  timers.push(window.setTimeout(tick, 2200))
}

export function setAmbient(on: boolean, world: WorldKey = 'valley') {
  if (on) {
    if (current === world && context) return
    stopAmbient()
    context = context ?? new AudioContext()
    const audio = context
    void audio.resume()
    master = audio.createGain()
    master.gain.value = 0
    master.connect(audio.destination)
    const wind = audio.createGain()
    const water = audio.createGain()
    const buffer = noiseBuffer(audio)
    loopNoise(audio, buffer, Object.assign(audio.createBiquadFilter(), { type: 'lowpass' as BiquadFilterType, frequency: world === 'campfire' ? 240 : 420 }), wind)
    lfo(audio, wind.gain, 0.09, world === 'campfire' ? 0.008 : 0.02)
    loopNoise(audio, buffer, Object.assign(audio.createBiquadFilter(), { type: 'bandpass' as BiquadFilterType, frequency: world === 'campfire' ? 900 : 620, Q: 0.7 }), water)
    lfo(audio, water.gain, 0.23, world === 'campfire' ? 0.012 : 0.014)
    wind.gain.value = world === 'campfire' ? 0.02 : 0.035
    water.gain.value = world === 'campfire' ? 0.03 : 0.022
    if (world === 'campfire') {
      const crackle = audio.createGain()
      loopNoise(audio, buffer, Object.assign(audio.createBiquadFilter(), { type: 'highpass' as BiquadFilterType, frequency: 2600 }), crackle)
      lfo(audio, crackle.gain, 2.7, 0.01)
      crackle.gain.value = 0.012
    }
    current = world
    master.gain.linearRampToValueAtTime(world === 'campfire' ? 0.5 : 0.42, audio.currentTime + 2.2)
    if (world === 'valley') scheduleBirds(audio)
  } else {
    stopAmbient()
  }
}

export function stopAmbient() {
  timers.forEach((timer) => window.clearTimeout(timer))
  timers = []
  if (context && master) {
    const audio = context
    const gain = master
    gain.gain.cancelScheduledValues(audio.currentTime)
    gain.gain.setValueAtTime(gain.gain.value, audio.currentTime)
    gain.gain.linearRampToValueAtTime(0, audio.currentTime + 0.7)
    window.setTimeout(() => {
      for (const node of nodes) {
        const source = node as AudioScheduledSourceNode
        if (typeof source.stop === 'function') {
          try { source.stop() } catch { /* already stopped */ }
        }
        try { node.disconnect() } catch { /* noop */ }
      }
      nodes = []
      gain.disconnect()
    }, 800)
  }
  master = null
  current = null
}

export function ambientSupported(): boolean {
  return typeof AudioContext !== 'undefined'
}
