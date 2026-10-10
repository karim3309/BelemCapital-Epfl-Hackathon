import { motion } from 'framer-motion'
import { recordedCoverage } from '../api/recorded'
import { useSource } from '../api/source'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import VerdictWord from '../components/VerdictWord'
import { C, verdictColor } from '../lib/colors'
import { kindLabel, pct, pctAuto, usd, usdShort } from '../lib/format'
import { usePocketView, useSelection } from '../state/selection'

function Big({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-caption font-normal text-neutral1">{label}</p>
      <p className="text-sub font-semibold tabular" style={{ color: tone ?? C.chalk }}>
        {value}
      </p>
      {note && <p className="text-caption font-normal text-neutral1">{note}</p>}
    </div>
  )
}

/** Slide 2: the answer. Largest type in the deck, nothing competing with it. */
export default function VerdictSlide() {
  const { stepPocket, goTo, setIncidentId } = useSelection()
  const { source } = useSource()
  const v = usePocketView()
  const d = v.decision
  const partial = d && d.verdict === 'EXIT' && d.exit_fraction > 0 && d.exit_fraction < 0.999
  const avoided = v.expectedLoss !== null && v.exitableNow !== null ? v.expectedLoss * v.exitableNow : null
  const scale = Math.max(avoided ?? 0, v.exitCost ?? 0, 1)
  const top = v.topRisk
  const fullAnalysis = v.risk !== null || (source.mode === 'recorded' && v.holding && recordedCoverage(v.holding.id).risk)

  return (
    <Slide
      id="verdict"
      eyebrow={
        v.holding
          ? `Poche ${v.position} sur ${v.count} · ${kindLabel(v.holding.kind)} · ${usdShort(v.holding.value_usd)} · ${pct(v.holding.share_of_book, 1)} du portefeuille`
          : 'Verdict'
      }
      title={v.holding?.label ?? 'Rester ou sortir ?'}
    >
      <div className="mt-6 grid flex-1 grid-cols-1 items-center gap-12 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] lg:gap-16">
        <div className="flex flex-col">
          <div className="flex items-center gap-2 md:gap-6">
            <button
              type="button"
              onClick={() => stepPocket(-1)}
              aria-label="Poche précédente"
              className="hidden h-14 w-14 shrink-0 items-center justify-center rounded-xl text-sub text-neutral1 hover:bg-surface hover:text-chalk md:flex"
            >
              ‹
            </button>
            {d ? (
              <VerdictWord verdict={d.verdict} />
            ) : v.holderUnrecorded ? (
              <Unrecorded>Aucune réponse enregistrée pour ce détenteur.</Unrecorded>
            ) : v.riskQuery.isError && (v.bookQuery.isError || v.bookQuery.isSuccess) ? (
              <Failure error={v.riskQuery.error} onRetry={() => v.riskQuery.refetch()} />
            ) : (
              <Pending title="Calcul du verdict…" eta="10 à 30 s au premier appel pour cette poche." />
            )}
            <button
              type="button"
              onClick={() => stepPocket(1)}
              aria-label="Poche suivante"
              className="hidden h-14 w-14 shrink-0 items-center justify-center rounded-xl text-sub text-neutral1 hover:bg-surface hover:text-chalk md:flex"
            >
              ›
            </button>
          </div>
          {partial && (
            <p className="mt-2 text-sub font-semibold tabular" style={{ color: verdictColor('EXIT') }}>
              Sortir {pct(d!.exit_fraction, 0)} de la poche
            </p>
          )}
          {d && (
            <motion.p
              key={d.sentence}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4 }}
              className="mt-8 max-w-[720px] text-lead font-normal text-chalk tabular"
            >
              {d.sentence}
            </motion.p>
          )}
          {d && !fullAnalysis && (
            <p className="mt-4 text-caption font-normal text-neutral1">
              Verdict issu de l'analyse du portefeuille. Le détail de cette poche se calcule en direct.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-10">
          <div className="flex flex-col gap-6">
            <div>
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-body font-normal text-neutral1">Sortir éviterait</span>
                <span className="text-sub font-semibold tabular text-chalk">{usd(avoided)}</span>
              </div>
              <div className="mt-2 h-[8px] bg-surface2">
                <motion.div
                  className="h-full bg-warn"
                  initial={false}
                  animate={{ width: `${((avoided ?? 0) / scale) * 100}%` }}
                  transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
              <p className="mt-2 text-caption font-normal text-neutral1 tabular">
                perte attendue {usd(v.expectedLoss)} × {pctAuto(v.exitableNow)} sortable maintenant
              </p>
            </div>
            <div>
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-body font-normal text-neutral1">Sortir coûterait</span>
                <span className="text-sub font-semibold tabular text-chalk">{usd(v.exitCost)}</span>
              </div>
              <div className="mt-2 h-[8px] bg-surface2">
                <motion.div
                  className="h-full bg-accent"
                  initial={false}
                  animate={{ width: `${((v.exitCost ?? 0) / scale) * 100}%` }}
                  transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
              <p className="mt-2 text-caption font-normal text-neutral1">coût certain pour sortir la part sortable, mesuré au bloc</p>
            </div>
          </div>

          {top && top.p_star !== null && top.p_star < 1 && (
            <button
              type="button"
              onClick={() => {
                setIncidentId(top.id)
                goTo('incident')
              }}
              className="flex flex-col items-start gap-2 rounded-xl bg-surface p-6 text-left hover:bg-surface2"
            >
              <span className="text-caption font-normal text-neutral1">La question de 3 h du matin</span>
              <span className="text-body font-normal text-chalk">
                Croyez-vous à plus de <span className="font-semibold">{pctAuto(top.p_star)}</span> de risque «{' '}
                {top.title} » ?
              </span>
              <span className="text-caption font-normal text-neutral1 tabular">
                Notre estimation : {pctAuto(top.p_horizon)}. Au-delà du seuil, sortir coûte moins que rester.
              </span>
              <span className="text-caption font-semibold text-accent">Tester votre estimation</span>
            </button>
          )}
          {top && (top.p_star === null || top.p_star >= 1) && (
            <Big
              label="Risque principal"
              value={usd(top.loss_if_incident_usd)}
              note={`si « ${top.title} » arrive. Même certain, il coûterait moins que la sortie.`}
            />
          )}
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between gap-4 md:hidden">
        <button type="button" onClick={() => stepPocket(-1)} className="text-body font-semibold text-accent">
          ‹ Précédente
        </button>
        <button type="button" onClick={() => stepPocket(1)} className="text-body font-semibold text-accent">
          Suivante ›
        </button>
      </div>
    </Slide>
  )
}
