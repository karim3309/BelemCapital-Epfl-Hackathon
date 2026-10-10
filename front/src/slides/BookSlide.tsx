import { useEffect, useState } from 'react'
import { useBook, usePockets } from '../api/hooks'
import { RECORDED_HOLDER } from '../api/recorded'
import { useSource } from '../api/source'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import { verdictColor } from '../lib/colors'
import { kindLabel, pct, pctAuto, shortAddress, usd, usdShort, verdictText } from '../lib/format'
import { useSelection } from '../state/selection'

/** Slide 1: the whole book at a glance, and the way into any pocket. */
export default function BookSlide() {
  const { holder, setHolder, pocketId, setPocketId, goTo } = useSelection()
  const { source } = useSource()
  const pockets = usePockets(holder)
  const book = useBook(holder, pocketId)
  const [draft, setDraft] = useState(holder)
  useEffect(() => setDraft(holder), [holder])

  const holdings = pockets.data?.holdings ?? []
  const rows = new Map((book.data?.pockets ?? []).map((p) => [p.id, p]))
  const exits = book.data?.pockets.filter((p) => p.verdict === 'EXIT') ?? []
  const stays = book.data ? book.data.pockets.length - exits.length : 0
  const maxShare = Math.max(0.0001, ...holdings.map((h) => h.share_of_book))

  const form = (
    <form
      className="flex w-full max-w-[560px] gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (draft.trim()) setHolder(draft)
      }}
    >
      <label htmlFor="holder" className="sr-only">
        Adresse du détenteur
      </label>
      <input
        id="holder"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        spellCheck={false}
        autoComplete="off"
        placeholder="Adresse Ethereum du détenteur (0x…)"
        className="min-w-0 flex-1 rounded-xl bg-surface px-5 py-4 text-body text-chalk outline-none"
      />
      <button type="submit" className="shrink-0 rounded-xl bg-accent px-6 py-4 text-body font-semibold text-chalk hover:opacity-90">
        Analyser
      </button>
    </form>
  )

  return (
    <Slide
      id="portefeuille"
      eyebrow={`Portefeuille · ${shortAddress(holder)} · Ethereum`}
      title={
        pockets.data
          ? `${holdings.length} poches, ${usdShort(pockets.data.total_value_usd)}.`
          : 'Un portefeuille, poche par poche.'
      }
      aside={
        book.data ? (
          <div className="flex items-end gap-10">
            <div>
              <p className="text-figure font-semibold tabular text-safe">{stays}</p>
              <p className="text-body font-normal text-neutral1">STAY</p>
            </div>
            <div>
              <p className="text-figure font-semibold tabular" style={{ color: exits.length ? '#FF3B30' : '#8E8E93' }}>
                {exits.length}
              </p>
              <p className="text-body font-normal text-neutral1">EXIT</p>
            </div>
          </div>
        ) : null
      }
    >
      <div className="mt-8 flex flex-col gap-3">
        {book.data && (
          <p className="text-body font-normal text-neutral1 tabular">
            Perte attendue sur l'horizon : <span className="text-chalk">{usd(book.data.expected_loss_usd)}</span>, soit{' '}
            {pctAuto(book.data.expected_loss_usd / book.data.total_value_usd)} du portefeuille.
            {exits.length > 0 &&
              ` À sortir : ${exits.map((p) => `${p.label} (${verdictText(p.verdict, p.exit_fraction)})`).join(', ')}.`}
          </p>
        )}
        {book.isPending && source.mode === 'live' && pockets.data && (
          <Pending
            title={`Analyse des ${holdings.length} poches en cours.`}
            eta="Le premier calcul d'un bloc prend environ 1 min 30 ; la poche choisie passe en premier."
          />
        )}
        {book.isError && <Failure error={book.error} onRetry={() => book.refetch()} />}
      </div>

      <div className="mt-10 min-h-0 flex-1">
        {pockets.isPending && <Pending title="Recherche des poches du détenteur…" eta="Environ 5 s au premier appel." />}
        {pockets.isError && <Failure error={pockets.error} onRetry={() => pockets.refetch()} />}
        {pockets.data === null && (
          <Unrecorded
            action={
              <button
                type="button"
                onClick={() => setHolder(RECORDED_HOLDER)}
                className="self-start text-body font-semibold text-accent hover:opacity-80"
              >
                Revenir au détenteur enregistré
              </button>
            }
          >
            Aucune réponse enregistrée pour {shortAddress(holder)}.
          </Unrecorded>
        )}

        {holdings.length > 0 && (
          <ul className="thin-scroll max-h-[46vh] overflow-y-auto md:max-h-[44vh]" aria-label="Poches">
            {holdings.map((h) => {
              const row = rows.get(h.id)
              const selected = h.id === pocketId
              return (
                <li key={h.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setPocketId(h.id)
                      goTo('verdict')
                    }}
                    aria-current={selected ? 'true' : undefined}
                    className={`grid w-full grid-cols-[88px_1fr] items-center gap-x-6 gap-y-1 rounded-xl px-4 py-4 text-left md:grid-cols-[112px_minmax(0,1fr)_200px_240px] ${
                      selected ? 'bg-surface' : 'hover:bg-surface'
                    }`}
                  >
                    <span
                      className="text-body font-semibold tabular md:row-span-1"
                      style={{ color: verdictColor(row?.verdict) }}
                    >
                      {row ? verdictText(row.verdict, row.exit_fraction) : '…'}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-body font-normal text-chalk">{h.label}</span>
                      <span className="block text-caption font-normal text-neutral1">
                        {kindLabel(h.kind)} · {h.asset_symbol}
                      </span>
                    </span>
                    <span className="col-start-2 flex items-center gap-3 md:col-start-auto">
                      <span className="w-[72px] shrink-0 text-right text-body font-semibold tabular text-chalk">
                        {usdShort(h.value_usd)}
                      </span>
                      <span className="relative h-[4px] flex-1 bg-surface2">
                        <span
                          className="absolute inset-y-0 left-0 bg-accent"
                          style={{ width: `${(h.share_of_book / maxShare) * 100}%` }}
                        />
                      </span>
                      <span className="w-[48px] shrink-0 text-caption font-normal tabular text-neutral1">
                        {pct(h.share_of_book, 1)}
                      </span>
                    </span>
                    <span className="col-start-2 text-caption font-normal tabular text-neutral1 md:col-start-auto md:text-right">
                      {row ? `perte ${usd(row.expected_loss_usd)} · sortie ${usd(row.exit_cost_usd)}` : ''}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div className="mt-8 flex flex-col gap-3">
        {form}
        <p className="text-caption font-normal text-neutral1">
          Poches localisées par l'API Morpho, montants prouvés on-chain. ← → pour passer d'une poche à l'autre, ↑ ↓ pour
          les questions.
        </p>
      </div>
    </Slide>
  )
}
