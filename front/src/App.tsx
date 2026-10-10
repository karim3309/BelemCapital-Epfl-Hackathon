import { useMemo, useRef, useState } from 'react'
import PositionInput from './components/PositionInput'
import DependencyGraph from './components/DependencyGraph'
import NodePanel from './components/NodePanel'
import RiskSignal from './components/RiskSignal'
import VerdictPanel, { type ScenarioMode } from './components/VerdictPanel'
import ScenarioDrawer from './components/ScenarioDrawer'
import { positions } from './data/mock'
import { assess, baseScenario, scenariosEqual, stressScenario, type Scenario } from './lib/risk'

export default function App() {
  const [positionKey, setPositionKey] = useState('pendle_pt_susde')
  const [scenario, setScenario] = useState<Scenario>(() => baseScenario(positions.pendle_pt_susde))
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const graphRef = useRef<HTMLDivElement>(null)

  const position = positions[positionKey]
  const assessment = useMemo(() => assess(position, scenario), [position, scenario])

  const mode: ScenarioMode = scenariosEqual(scenario, baseScenario(position))
    ? 'base'
    : scenariosEqual(scenario, stressScenario(position))
      ? 'stress'
      : 'custom'

  const selectPosition = (key: string) => {
    setPositionKey(key)
    setScenario(baseScenario(positions[key]))
    setSelectedNodeId(null)
    setDrawerOpen(false)
  }

  const selectedNode = assessment.nodes.find((n) => n.id === selectedNodeId) ?? null

  return (
    <main className="min-h-screen w-full bg-ink">
      <PositionInput
        positionKey={positionKey}
        onSelect={selectPosition}
        onScan={() => graphRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
      />

      <div ref={graphRef}>
        <DependencyGraph
          position={position}
          nodes={assessment.nodes}
          selectedId={selectedNodeId}
          onSelect={(id) => setSelectedNodeId((current) => (current === id ? null : id))}
        />
      </div>

      <section className="w-full px-8 py-32 md:px-16">
        <div className="mx-auto grid max-w-stage grid-cols-1 gap-30 lg:grid-cols-[3fr_2fr] lg:gap-18">
          <RiskSignal position={position} assessment={assessment} />
          <VerdictPanel
            assessment={assessment}
            mode={mode}
            onBase={() => {
              setScenario(baseScenario(position))
              setDrawerOpen(false)
            }}
            onStress={() => {
              if (mode === 'base') setScenario(stressScenario(position))
              setDrawerOpen(true)
            }}
          />
        </div>
      </section>

      <footer className="w-full px-8 pb-32 md:px-16">
        <p className="mx-auto max-w-stage text-caption font-normal text-neutral1">
          Dependency set and incident rates from the 09 Oct 2026 snapshot. Expected loss is the
          sum of incident probability × loss-given-incident across every dependency, over a
          30-day horizon.
        </p>
      </footer>

      <NodePanel
        node={selectedNode}
        exposureUsd={position.tvl_exposure}
        onClose={() => setSelectedNodeId(null)}
      />

      <ScenarioDrawer
        open={drawerOpen}
        scenario={scenario}
        assessment={assessment}
        onChange={setScenario}
        onReset={() => setScenario(baseScenario(position))}
        onClose={() => setDrawerOpen(false)}
      />
    </main>
  )
}
