import { useEffect, useState } from 'react'
import type { TableSummary, WorldSummary } from './domain'
import { findTable, findWorld, worlds } from './domain'

type Route =
  | { name: 'lobby' }
  | { name: 'world'; world: WorldSummary }
  | { name: 'table'; table: TableSummary }

const resolveRoute = (pathname: string): Route => {
  if (pathname === '/world/campfire') {
    return { name: 'world', world: findWorld('campfire')! }
  }
  if (pathname === '/table/leaving-the-city') {
    return { name: 'table', table: findTable('leaving-the-city')! }
  }
  return { name: 'lobby' }
}
interface LobbyProps {
  worlds: WorldSummary[]
  onEnterWorld: (world: WorldSummary) => void
}

function Lobby({ worlds, onEnterWorld }: LobbyProps) {
  return (
    <main>
      <p>组一桌</p>
      <h1>有些答案，不在任何一个人那里。</h1>
      <p>看看现在有哪些桌正在形成。</p>
      <nav aria-label="正在形成的世界">
        {worlds.map((world) => (
          <button key={world.id} onClick={() => onEnterWorld(world)}>
            {world.name}
          </button>
        ))}
      </nav>
    </main>
  )
}

interface WorldProps {
  world: WorldSummary
  onBack: () => void
  onEnterTable: (table: TableSummary) => void
}

function World({ world, onBack, onEnterTable }: WorldProps) {
  return (
    <main>
      <button onClick={onBack}>返回大厅</button>
      <p>{world.atmosphere}</p>
      <h1>{world.name}</h1>
      {world.tables.map((table) => (
        <article key={table.id}>
          <h2>{table.hook}</h2>
          <p>{table.seatedCount} 人已入席 · {table.missingPerspective}</p>
          {table.id === 'leaving-the-city' && (
            <button onClick={() => onEnterTable(table)}>坐下来看看</button>
          )}
        </article>
      ))}
    </main>
  )
}

interface TableProps {
  table: TableSummary
  onBack: () => void
}

function Table({ table, onBack }: TableProps) {
  return (
    <main>
      <button onClick={onBack}>回到篝火世界</button>
      <p>{table.seatedCount} 人已入席</p>
      <h1>{table.hook}</h1>
      <p>这一桌，{table.missingPerspective}。</p>
    </main>
  )
}

export default function App() {
  const [route, setRoute] = useState(() => resolveRoute(window.location.pathname))

  useEffect(() => {
    const updateRoute = () => setRoute(resolveRoute(window.location.pathname))
    window.addEventListener('popstate', updateRoute)
    return () => window.removeEventListener('popstate', updateRoute)
  }, [])

  const navigate = (pathname: string) => {
    window.history.pushState(null, '', pathname)
    setRoute(resolveRoute(pathname))
  }

  if (route.name === 'world') {
    return <World world={route.world} onBack={() => navigate('/')} onEnterTable={() => navigate('/table/leaving-the-city')} />
  }
  if (route.name === 'table') {
    return <Table table={route.table} onBack={() => navigate('/world/campfire')} />
  }
  return <Lobby worlds={worlds} onEnterWorld={(world) => navigate(world.id === 'campfire' ? '/world/campfire' : '/')} />
}
