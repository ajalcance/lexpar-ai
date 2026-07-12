/**
 * File: src/components/DemoScript.tsx
 * Purpose: A reviewer/judge aid shown beside the live sparring session — a read-aloud script that
 *   lets a non-lawyer experience the full loop (objection → ruling → scorecard) in ~90 seconds.
 *   The four "baits" alternate overrule → sustain so a judge sees the bench rule both ways.
 *   Presentational only; gated at the call site by VITE_SHOW_DEMO_SCRIPT (see SparringRoom) so it
 *   flips off after the hackathon without a code change.
 * Depends on: components/ui/badge, lib/utils (cn)
 * Related: pages/SparringRoom.tsx (renders this in the left column)
 * Security notes: The case (G.R. No. 218738) is a real, publicly-available Philippine Supreme Court
 *   decision used as a neutral public fixture — no work product here.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type Outcome = 'none' | 'overrule' | 'sustain' | 'close';

const OUTCOME: Record<Outcome, { label: string; className: string }> = {
  none: { label: 'No objection', className: 'text-muted-foreground' },
  overrule: { label: 'Should be overruled', className: 'text-green-600 dark:text-green-500' },
  sustain: { label: 'Should be sustained', className: 'text-amber-600 dark:text-amber-500' },
  close: { label: 'Then: End session', className: 'text-blue-600 dark:text-blue-500' },
};

const SEGMENTS: { n: number; heading: string; outcome: Outcome; read: string; cue: string }[] = [
  {
    n: 1,
    heading: 'Clean opening',
    outcome: 'none',
    read: 'Your Honor, this is Civil Case No. 2001-11-164, filed by Salazar Realty Corporation against Metropolitan Bank and Trust Company before Branch 9 of the Tacloban City Regional Trial Court. SARC seeks to quiet title over five parcels of land registered in its name, after those lots were mortgaged to secure an eighteen-and-a-half-million-peso loan extended not to SARC, but to a separate corporation, Tacloban RAS Construction Corporation.',
    cue: 'Grounded facts — nothing should fire.',
  },
  {
    n: 2,
    heading: 'Proper legal argument',
    outcome: 'overrule',
    read: 'Your Honor, for a corporation to pledge its own real property to secure the debt of a separate, unrelated corporation is an ultra vires act as a matter of law — SARC exceeded its corporate powers, and the mortgage was void from its inception.',
    cue: 'OC objects (legal conclusion / assumes facts) → the Judge overrules: arguing the legal effect of the record is proper advocacy in oral argument.',
  },
  {
    n: 3,
    heading: 'Assumes a fact not in the record',
    outcome: 'sustain',
    read: "And Metrobank knew full well, at the moment it accepted this mortgage, that SARC's board had no authority to grant it — the bank proceeded in bad faith.",
    cue: "OC objects (assumes facts) → the Judge sustains: the record establishes nothing about Metrobank's knowledge or bad faith.",
  },
  {
    n: 4,
    heading: 'Legal inference from the record',
    outcome: 'overrule',
    read: 'With two board seats left vacant by the deaths of Ramon and Consuelo Salazar, and the remaining directors having themselves approved this very encumbrance, a demand upon that board would plainly have been futile as a matter of law.',
    cue: 'OC objects (assumes facts) → the Judge overrules: demand futility is a legitimate legal inference from established record facts.',
  },
  {
    n: 5,
    heading: 'Strays from the issues',
    outcome: 'sustain',
    read: "I'd add, Your Honor, that Metrobank's separate dispute with a borrower in Cebu over an unrelated equipment lease reveals the very same pattern of overreach and cannot simply be ignored here.",
    cue: 'OC objects (relevance) → the Judge sustains: that matter appears nowhere in this record and strays from the questions at issue.',
  },
  {
    n: 6,
    heading: 'Close',
    outcome: 'close',
    read: 'On that basis, Your Honor, SARC respectfully submits that the mortgage and the foreclosure arising from it are void for want of corporate authority, and that title should be quieted in SARC’s favor.',
    cue: 'Then click “End session” — the Judge delivers a spoken closing ruling and a scorecard.',
  },
];

export function DemoScript({ className }: { className?: string }) {
  return (
    <aside
      className={cn(
        'flex flex-col gap-4 rounded-lg border border-amber-500/30 bg-muted/30 p-5 text-sm',
        className,
      )}
    >
      <div>
        <p className="text-xs font-medium tracking-wide text-amber-600 uppercase dark:text-amber-500">
          For reviewers · read aloud
        </p>
        <h2 className="mt-1 text-base font-semibold">Live test script</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          You are counsel for SARC (respondent), presenting oral argument. Allow the microphone,
          then read each segment aloud at a normal pace — <strong>pause after each</strong> to give
          opposing counsel room to object and the judge to rule. The four baits alternate so you see
          the bench rule both ways.
        </p>
      </div>

      <ol className="flex flex-col gap-3">
        {SEGMENTS.map((segment) => (
          <li key={segment.n} className="flex flex-col gap-1 border-t pt-3 first:border-t-0 first:pt-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground">
                {segment.n}. {segment.heading}
              </span>
              <Badge variant="outline" className={cn('text-[11px]', OUTCOME[segment.outcome].className)}>
                {OUTCOME[segment.outcome].label}
              </Badge>
            </div>
            <p className="leading-relaxed">“{segment.read}”</p>
            <p className="text-xs text-muted-foreground">{segment.cue}</p>
          </li>
        ))}
      </ol>

      <p className="border-t pt-3 text-[11px] leading-relaxed text-muted-foreground">
        <strong>Disclaimer:</strong> Metropolitan Bank &amp; Trust Co. v. Salazar Realty Corp.,
        G.R. No. 218738 (Mar. 9, 2022) is a real, published decision of the Supreme Court of the
        Philippines and is publicly available. It is used here only as a neutral public fixture to
        exercise the pipeline — not as legal advice.
      </p>
    </aside>
  );
}
