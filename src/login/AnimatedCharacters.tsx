/** @origin LOGIN — flat cartoon cast adapted from careercompass AnimatedCharacters (MIT), extended for 组一桌 prompt. */

import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'

export type CharacterMood = 'idle' | 'curious' | 'peek' | 'cover' | 'sad' | 'happy' | 'sing'

interface PupilProps {
  size?: number
  maxDistance?: number
  pupilColor?: string
  forceLookX?: number
  forceLookY?: number
  closed?: boolean
}

function Pupil({
  size = 12,
  maxDistance = 5,
  pupilColor = '#2D2D2D',
  forceLookX,
  forceLookY,
  closed = false,
}: PupilProps) {
  const [mouseX, setMouseX] = useState(0)
  const [mouseY, setMouseY] = useState(0)
  const pupilRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      setMouseX(event.clientX)
      setMouseY(event.clientY)
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  if (closed) {
    return <span className="login-eye-lid" style={{ width: size * 1.6, height: 3 }} aria-hidden="true" />
  }

  let x = 0
  let y = 0
  if (forceLookX !== undefined && forceLookY !== undefined) {
    x = forceLookX
    y = forceLookY
  } else if (pupilRef.current) {
    const box = pupilRef.current.getBoundingClientRect()
    const cx = box.left + box.width / 2
    const cy = box.top + box.height / 2
    const dx = mouseX - cx
    const dy = mouseY - cy
    const distance = Math.min(Math.hypot(dx, dy), maxDistance)
    const angle = Math.atan2(dy, dx)
    x = Math.cos(angle) * distance
    y = Math.sin(angle) * distance
  }

  return (
    <div
      ref={pupilRef}
      className="login-pupil"
      style={{
        width: size,
        height: size,
        background: pupilColor,
        transform: `translate(${x}px, ${y}px)`,
      }}
      aria-hidden="true"
    />
  )
}

interface EyeBallProps {
  size?: number
  pupilSize?: number
  maxDistance?: number
  isBlinking?: boolean
  forceLookX?: number
  forceLookY?: number
  closed?: boolean
}

function EyeBall({
  size = 18,
  pupilSize = 7,
  maxDistance = 5,
  isBlinking = false,
  forceLookX,
  forceLookY,
  closed = false,
}: EyeBallProps) {
  const [mouseX, setMouseX] = useState(0)
  const [mouseY, setMouseY] = useState(0)
  const eyeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      setMouseX(event.clientX)
      setMouseY(event.clientY)
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  if (closed || isBlinking) {
    return <span className="login-eye-lid" style={{ width: size, height: 3 }} aria-hidden="true" />
  }

  let x = 0
  let y = 0
  if (forceLookX !== undefined && forceLookY !== undefined) {
    x = forceLookX
    y = forceLookY
  } else if (eyeRef.current) {
    const box = eyeRef.current.getBoundingClientRect()
    const cx = box.left + box.width / 2
    const cy = box.top + box.height / 2
    const dx = mouseX - cx
    const dy = mouseY - cy
    const distance = Math.min(Math.hypot(dx, dy), maxDistance)
    const angle = Math.atan2(dy, dx)
    x = Math.cos(angle) * distance
    y = Math.sin(angle) * distance
  }

  return (
    <div ref={eyeRef} className="login-eyeball" style={{ width: size, height: size }} aria-hidden="true">
      <div
        className="login-pupil"
        style={{
          width: pupilSize,
          height: pupilSize,
          background: '#2D2D2D',
          transform: `translate(${x}px, ${y}px)`,
        }}
      />
    </div>
  )
}

function useLook(ref: RefObject<HTMLDivElement | null>, mouseX: number, mouseY: number) {
  if (!ref.current) return { faceX: 0, faceY: 0, bodySkew: 0 }
  const rect = ref.current.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 3
  const deltaX = mouseX - centerX
  const deltaY = mouseY - centerY
  return {
    faceX: Math.max(-15, Math.min(15, deltaX / 20)),
    faceY: Math.max(-10, Math.min(10, deltaY / 30)),
    bodySkew: Math.max(-6, Math.min(6, -deltaX / 120)),
  }
}

interface AnimatedCharactersProps {
  mood: CharacterMood
  accountFocused: boolean
  showPassword: boolean
  passwordLength: number
  singingId: string | null
}

export default function AnimatedCharacters({
  mood,
  accountFocused,
  showPassword,
  passwordLength,
  singingId,
}: AnimatedCharactersProps) {
  const [mouseX, setMouseX] = useState(0)
  const [mouseY, setMouseY] = useState(0)
  const [purpleBlink, setPurpleBlink] = useState(false)
  const [blackBlink, setBlackBlink] = useState(false)
  const [orangePeek, setOrangePeek] = useState(false)

  const purpleRef = useRef<HTMLDivElement>(null)
  const blackRef = useRef<HTMLDivElement>(null)
  const yellowRef = useRef<HTMLDivElement>(null)
  const orangeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      setMouseX(event.clientX)
      setMouseY(event.clientY)
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  useEffect(() => {
    let alive = true
    const schedule = (setter: (v: boolean) => void) => {
      const wait = Math.random() * 4000 + 3000
      const t = window.setTimeout(() => {
        if (!alive) return
        setter(true)
        window.setTimeout(() => {
          if (!alive) return
          setter(false)
          schedule(setter)
        }, 150)
      }, wait)
      return t
    }
    const a = schedule(setPurpleBlink)
    const b = schedule(setBlackBlink)
    return () => {
      alive = false
      window.clearTimeout(a)
      window.clearTimeout(b)
    }
  }, [])

  useEffect(() => {
    if (!(passwordLength > 0 && showPassword && mood !== 'sad' && mood !== 'happy')) {
      setOrangePeek(false)
      return
    }
    let alive = true
    const tick = () => {
      const t = window.setTimeout(() => {
        if (!alive) return
        setOrangePeek(true)
        window.setTimeout(() => {
          if (!alive) return
          setOrangePeek(false)
          tick()
        }, 900)
      }, Math.random() * 2800 + 1600)
      return t
    }
    const first = tick()
    return () => {
      alive = false
      window.clearTimeout(first)
    }
  }, [mood, passwordLength, showPassword])

  const purplePos = useLook(purpleRef, mouseX, mouseY)
  const blackPos = useLook(blackRef, mouseX, mouseY)
  const yellowPos = useLook(yellowRef, mouseX, mouseY)
  const orangePos = useLook(orangeRef, mouseX, mouseY)

  const curious = accountFocused || mood === 'curious'
  const covering = passwordLength > 0 && !showPassword
  const peekMode = passwordLength > 0 && showPassword
  const sad = mood === 'sad'
  const happy = mood === 'happy'

  const lean = curious || covering
  const othersCoverEyes = peekMode

  const mouthFor = (who: 'orange' | 'purple' | 'black' | 'yellow'): CSSProperties => {
    if (happy || singingId === who || singingId === 'all') {
      return { height: 10, borderRadius: '0 0 12px 12px', transform: 'scaleY(1.2)' }
    }
    if (sad) {
      return { height: 10, borderRadius: '12px 12px 0 0', transform: 'translateY(2px) scaleY(1.1)' }
    }
    if (who === 'yellow') {
      return { height: 4, borderRadius: 999, width: 48 }
    }
    if (who === 'orange') {
      return { height: 8, borderRadius: '0 0 14px 14px', width: 56 }
    }
    if (who === 'purple') {
      return { height: 6, borderRadius: 999, width: 40, transform: curious ? 'translateY(2px)' : undefined }
    }
    return { height: 4, borderRadius: 999, width: 36 }
  }

  const bodyClass = [
    'login-cast',
    lean ? 'is-lean' : '',
    sad ? 'is-sad' : '',
    happy ? 'is-happy' : '',
    singingId ? 'is-singing' : '',
  ].filter(Boolean).join(' ')

  return (
    <div className={bodyClass} aria-hidden="true">
      {/* Purple tsundere rectangle — back */}
      <div
        ref={purpleRef}
        className={`login-char login-char-purple ${singingId === 'purple' || singingId === 'all' ? 'is-solo-sing' : ''}`}
        style={{
          transform: peekMode
            ? 'skewX(0deg) scaleY(1)'
            : lean
              ? `skewX(${purplePos.bodySkew - 10}deg) translateX(36px) scaleY(1.08)`
              : `skewX(${purplePos.bodySkew}deg) scaleY(1)`,
        }}
      >
        <div
          className="login-char-face"
          style={{
            left: peekMode ? 18 : 45 + purplePos.faceX,
            top: peekMode ? 32 : 40 + purplePos.faceY,
          }}
        >
          <div className="login-eyes">
            <EyeBall
              size={18}
              pupilSize={7}
              isBlinking={purpleBlink}
              closed={othersCoverEyes}
              forceLookX={othersCoverEyes ? undefined : curious ? 2 : undefined}
              forceLookY={othersCoverEyes ? undefined : curious ? 3 : undefined}
            />
            <EyeBall
              size={18}
              pupilSize={7}
              isBlinking={purpleBlink}
              closed={othersCoverEyes}
              forceLookX={othersCoverEyes ? undefined : curious ? 2 : undefined}
              forceLookY={othersCoverEyes ? undefined : curious ? 3 : undefined}
            />
          </div>
          <span className="login-mouth" style={mouthFor('purple')} />
        </div>
      </div>

      {/* Black calm rectangle */}
      <div
        ref={blackRef}
        className={`login-char login-char-black ${singingId === 'black' || singingId === 'all' ? 'is-solo-sing' : ''}`}
        style={{
          transform: peekMode
            ? 'skewX(0deg)'
            : lean
              ? `skewX(${blackPos.bodySkew * 1.4}deg)`
              : `skewX(${blackPos.bodySkew}deg)`,
        }}
      >
        <div
          className="login-char-face"
          style={{
            left: peekMode ? 12 : 26 + blackPos.faceX,
            top: peekMode ? 24 : 32 + blackPos.faceY,
          }}
        >
          <div className="login-eyes">
            <EyeBall size={16} pupilSize={6} maxDistance={4} isBlinking={blackBlink} closed={othersCoverEyes} />
            <EyeBall size={16} pupilSize={6} maxDistance={4} isBlinking={blackBlink} closed={othersCoverEyes} />
          </div>
          <span className="login-mouth" style={mouthFor('black')} />
        </div>
      </div>

      {/* Orange cheerful semi-circle — peeks when password visible */}
      <div
        ref={orangeRef}
        className={`login-char login-char-orange ${singingId === 'orange' || singingId === 'all' ? 'is-solo-sing' : ''}`}
        style={{
          transform: peekMode ? 'skewX(0deg)' : `skewX(${orangePos.bodySkew}deg)`,
        }}
      >
        <div
          className="login-char-face"
          style={{
            left: peekMode ? 48 : 82 + orangePos.faceX,
            top: peekMode ? 78 : 90 + orangePos.faceY,
          }}
        >
          <div className="login-eyes">
            {peekMode ? (
              <>
                <Pupil size={12} closed={!orangePeek} forceLookX={4} forceLookY={3} />
                <Pupil size={12} closed forceLookX={0} forceLookY={0} />
              </>
            ) : (
              <>
                <Pupil size={12} maxDistance={5} />
                <Pupil size={12} maxDistance={5} />
              </>
            )}
          </div>
          <span className="login-mouth" style={mouthFor('orange')} />
        </div>
      </div>

      {/* Yellow gentle rounded rectangle */}
      <div
        ref={yellowRef}
        className={`login-char login-char-yellow ${singingId === 'yellow' || singingId === 'all' ? 'is-solo-sing' : ''}`}
        style={{
          transform: peekMode ? 'skewX(0deg)' : `skewX(${yellowPos.bodySkew}deg)`,
        }}
      >
        <div
          className="login-char-face"
          style={{
            left: peekMode ? 18 : 52 + yellowPos.faceX,
            top: peekMode ? 28 : 40 + yellowPos.faceY,
          }}
        >
          <div className="login-eyes">
            <Pupil size={12} closed={othersCoverEyes} />
            <Pupil size={12} closed={othersCoverEyes} />
          </div>
          <span className="login-mouth" style={mouthFor('yellow')} />
        </div>
      </div>
    </div>
  )
}

export const CHARACTER_HIT_TARGETS = [
  { id: 'orange', label: '橙色半圆' },
  { id: 'purple', label: '紫色方块' },
  { id: 'black', label: '黑色方块' },
  { id: 'yellow', label: '黄色圆角' },
] as const
