/**
 * The shape of what is arriving, held open until it lands.
 *
 * **A skeleton is for content that is *arriving*; a sentence is for content
 * that is *absent*.**  That distinction is this file's whole licence, because
 * every other module here states the opposite rule: `Shell.Sentence`,
 * `ui.EmptyState`, `MatchList.Thumbnail` and `MapStage`'s three empty branches
 * all refuse to draw a stand-in, on the grounds that a schematic in the place a
 * map goes reads as the map however it is captioned, and a grey box where a
 * thumbnail goes reads as the picture.  Nothing here contradicts that.  A
 * skeleton draws no map, no portrait and no picture -- it is the *geometry* of
 * the row on its way, in the surface ramp's own greys, and it is gone the
 * moment the content lands.  Where something is permanently missing the page
 * still says so in words, and not one of those branches changed.
 *
 * Two rules keep it out of the test suite's way, and both cost more to break
 * than an assertion:
 *
 *   * **a skeleton may reuse a pure-layout container class, and never a class a
 *     spec selects.**  Reusing `.stage-head`, `.arena`, `.stage-canvas`,
 *     `.transport`, `.round-strip`, `.captions` and `.card-facts` is what makes
 *     the placeholder the same geometry as the real thing with no second copy
 *     of the grid to fall out of step.  Reusing `.card`, `.player-card`,
 *     `.round-chip` or `canvas.minimap` would be read as the real thing by
 *     `e2e/harness.ts`, which clicks `a.card.playable` and treats
 *     `canvas.minimap` being visible as the signal that the replay page is
 *     ready -- and the failure there is not a red test but a sixty-second hang;
 *   * **no `<img>` and no `data-enter`.**  `MatchList.test.tsx` asserts there is
 *     no `<img>` anywhere on the page in the no-thumbnail state, and
 *     `e2e/docshots.spec.ts` waits for every `[data-enter]` node to reach full
 *     opacity, which a node that unmounts mid-wait never does.
 *
 * The sentence the page said before this is unchanged and still said.  It is
 * `.sr-only` inside a `role="status"`, so a reader hears exactly `Reading the
 * decoded tracks…` and the rest, while the eye gets the blocks instead of one
 * line of grey text on an empty page.  `role="status"` sits on the sentence and
 * not on the wrapper, or a reader announces the whole subtree; the drawn parts
 * are `aria-hidden`, because being walked through nine empty divs is worse than
 * being told nothing.  `.sr-only` is `position: absolute`, so it is **not a
 * grid item** -- which is what lets `StageSkeleton` carry it inside the same
 * four-row grid the real stage defines.
 */

import type { CSSProperties, ReactNode } from "react";

/**
 * One block where something is arriving.
 *
 * The dimensions are attributes rather than a class per bar, for the reason
 * `MatchList.Thumbnail` already gives about its own `width`/`height`: they are
 * the *content's* measurements, and what they are for is holding the row's
 * height before the content arrives.  A class per measurement would be twenty
 * single-property rules, which is the state the stylesheet was rebuilt out of.
 * `className` is for the ones that are layout instead -- a portrait that has to
 * be round, a rail that has to fill the row.
 *
 * Neither has a default here, and that is a fix rather than a preference: an
 * inline `height` beats a stylesheet, so a `h = 12` default silently overrode
 * every `className` that sets its own, and the portraits, the transport
 * buttons, the rail and the round strip all drew twelve pixels tall.  The
 * fallback is `.skel`'s own `height` in `app.css`, which a class can win.
 */
export function Block({
  w,
  h,
  className,
  style,
}: {
  w?: number | string;
  h?: number | string;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      className={className ? `skel ${className}` : "skel"}
      style={{ width: w, height: h, ...style }}
    />
  );
}

/**
 * The words, for a reader who cannot see the blocks.
 *
 * One definition of the sentence, which is why it is a component and not four
 * string literals: `Shell.Loading` used to hold it and both of its callers are
 * now here.
 */
function Says({ what }: { what: string }) {
  return (
    <p className="sr-only" role="status">
      Reading {what}…
    </p>
  );
}

/** The wrapper: the sentence, then the drawing, which announces nothing. */
function Skeleton({
  what,
  className,
  children,
}: {
  what: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={className} aria-busy="true">
      <Says what={what} />
      {children}
    </div>
  );
}

/* -- the match list ------------------------------------------------------ */

/**
 * One row of the library, as its three columns and nothing else.
 *
 * `.skel-card` and not `.card`, per the rule at the top of this file.  The grid
 * is restated in `app.css` rather than shared, and four duplicated lines is the
 * price of the class name not being duplicated.  `.card-facts` and `.card-line`
 * *are* reused: they are pure layout, nothing selects them, and reusing them is
 * what puts the four facts where the four facts will land.
 */
function CardRowSkeleton() {
  return (
    <div className="skel-card">
      {/* The box `.card-thumb` reserves, and never an `<img>`. */}
      <Block w={200} h={52} />
      {/* The heights are the line boxes a real row measures at -- 25 for the
          map name at `--text-xl`, 15 for a fact at `--text-sm` -- so the three
          rows of this column stack to the same 42px `.card-facts` does. */}
      <div className="card-facts">
        <Block w={172} h={25} />
        <span className="card-line">
          <Block w={124} h={15} />
          <Block w={82} h={15} />
          <Block w={72} h={15} />
          <Block w={74} h={15} />
        </span>
      </div>
      {/*
        The team strip, through its own layout classes.

        `.match-teams`, `.match-team` and `.match-agents` are reused for the
        same reason `.card-facts` is: they are pure geometry, nothing selects
        them, and reusing them means the strip's height -- which is what drives
        the row's, the portraits being the tallest thing on it -- cannot fall
        out of step with the real one.  The tone class is deliberately not
        passed, so the row draws in `--team-unknown`: nothing is known yet, and
        that is the colour this interface already has for that.
      */}
      <div className="match-teams">
        {Array.from({ length: 2 }, (_, row) => (
          <div className="match-team" key={row}>
            <Block w={18} h={16} />
            <span className="match-agents">
              {Array.from({ length: 5 }, (_, seat) => (
                <Block key={seat} w={28} h={28} />
              ))}
            </span>
          </div>
        ))}
        {/*
          The `+N undecided` line.

          `TeamStrip` draws it only where a scoreline could be *attributed* and
          some round went unattributed -- `rounds_won` is null until a capture
          has been decoded, so a cold library shows none of these and a warm one
          shows most.  Measured on the reference library once `prewarm` had
          caught up: eight rows in ten.  The strip is the tallest thing in the
          row, so it is what sets the row's height, and holding the majority
          shape is worth seventeen pixels of error on the other two.
        */}
        <Block w={92} h={15} />
      </div>
      <div className="card-badges">
        {/* A `READY` chip, which is the one most rows carry. */}
        <Block w={65} h={20} />
      </div>
    </div>
  );
}

/**
 * The library, arriving.
 *
 * Four rows.  Enough to read as a list rather than as one stray box, and short
 * of the server's `per_page: 7` -- seven grey rows over a library of one would
 * be stating a count this cannot know.  The filter block above them holds the
 * toolbar's height, so the real rows land where the placeholders were instead
 * of stepping down the page when a `Select` appears above them.
 */
export function MatchListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <Skeleton what="the replay library" className="skel-page">
      <div className="toolbar" aria-hidden="true">
        <Block w={220} h={29} />
      </div>
      <div className="cards" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <CardRowSkeleton key={index} />
        ))}
      </div>
    </Skeleton>
  );
}

/* -- the viewer ---------------------------------------------------------- */

/**
 * What stands in the canvas cell while there is nothing to draw in it.
 *
 * Deliberately a small centred plate rather than a sweep filling the cell.
 * `.stage-canvas::before` already paints the vignette that stands in for the
 * radar's negative space, and a block covering that edge to edge would read as
 * a *picture* arriving where a map goes -- which is the one thing this
 * interface does not do.  A caption-sized plate in an otherwise untouched cell
 * reads as an absence, which is the claim.
 */
function CanvasPlate() {
  return (
    <div className="stage-loading" aria-hidden="true">
      <span className="skel-plate">
        <Block w={150} h={14} />
        <Block w={92} h={10} />
      </span>
    </div>
  );
}

/**
 * The same plate as a `Suspense` fallback, which needs its own sentence.
 *
 * `Scene3D` is about a megabyte of `three` fetched the first time somebody asks
 * for the 3D view, and the cell it lands in already exists at the right size --
 * so there is no shape to hold here, only the words that used to sit beside a
 * spinner.
 */
export function RendererSkeleton() {
  return (
    <>
      <Says what="the renderer" />
      <CanvasPlate />
    </>
  );
}

/** One gutter: a head and five slots that stretch, as `.roster` lays out. */
function GutterSkeleton({ mirrored = false }: { mirrored?: boolean }) {
  return (
    <div className={mirrored ? "skel-gutter is-mirrored" : "skel-gutter"}>
      <div className="skel-gutter-head">
        <Block w={49} h={20} />
        <Block w={22} h={22} />
        <div className="spacer" />
        <Block w={14} h={24} />
      </div>
      <div className="skel-gutter-cards">
        {Array.from({ length: 5 }, (_, index) => (
          <div className="skel-player" key={index}>
            <Block className="skel-portrait" />
            <div className="skel-player-lines">
              <Block w="65%" h={12} />
              <Block w="40%" h={10} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * The arena, arriving.
 *
 * `.panel.stage` is kept on the root so it inherits `.viewer > .panel.stage`'s
 * four-row grid rather than restating it, and the four children are the real
 * stage's own four rows: the head, the arena, the transport (which holds the
 * round strip above its bar) and the captions.  `is-skeleton` is the hook a
 * spec would need if one ever has to tell the two apart.
 *
 * That reuse is safe because this only ever renders inside `main.viewer`.
 * `MapStage` returns its own sentence for a capture with no positions before it
 * can reach the loading branch, and `Viewer` sends that same capture to the
 * document shape -- so wherever this appears, the real stage is what replaces
 * it.  Which is the point: the head, both gutters, the canvas cell and the
 * transport are present from the first frame, so the stage *fills in* rather
 * than appearing, and the page does not jump.
 *
 * `what` differs between the two callers and the difference is real: `Viewer`
 * is still reading the replay itself, `MapStage` already has it and is reading
 * the tracks and the radar.
 */
export function StageSkeleton({ what }: { what: string }) {
  return (
    <Skeleton what={what} className="panel stage is-skeleton">
      {/* Three, with a spacer either side of the middle one: the disclaimer
          chip, the clock pill the head centres, and the 2D/3D switch. */}
      <div className="stage-head" aria-hidden="true">
        <Block w={93} h={20} />
        <div className="spacer" />
        <Block w={79} h={22} />
        <div className="spacer" />
        <Block w={112} h={28} />
      </div>

      <div className="arena" aria-hidden="true">
        <GutterSkeleton />
        {/*
          Reused, and empty.  It is the box the map arrives into, it carries the
          glow and the overflow rule, and a second class with the same rules is
          the thing that drifts.  No canvas inside it: `e2e/harness.ts` treats
          `canvas.minimap` being visible as the replay page being ready.
        */}
        <div className="stage-canvas">
          <CanvasPlate />
        </div>
        <GutterSkeleton mirrored />
      </div>

      <div className="transport" aria-hidden="true">
        {/*
          One block and not N chips.  A row of grey chips where the round
          numbers go states how many rounds there were, which is a number this
          has not read yet.
        */}
        <div className="round-strip">
          <Block className="skel-strip" />
        </div>
        {/*
          Every control the bar carries, at the widths they measure: the five
          transport buttons, the rail, the readout, the speed track, LOOP, the
          two dialogs and LAYERS.  Modelling only the left half would have made
          the row look like a different bar -- and the rail's 40px is what sets
          the bar's own height, so getting it wrong moves the arena above it.
        */}
        <div className="transport-bar">
          <Block w={26} h={26} />
          <Block w={26} h={26} />
          <Block w={86} h={29} />
          <Block w={26} h={26} />
          <Block w={26} h={26} />
          <Block className="skel-rail" />
          <Block w={79} h={16} />
          <Block w={243} h={28} />
          <Block w={85} h={29} />
          <Block w={26} h={26} />
          <Block w={26} h={26} />
          <Block w={84} h={24} />
        </div>
      </div>

      <div className="captions" aria-hidden="true">
        <p>
          <Block className="skel-caption" />
        </p>
      </div>
    </Skeleton>
  );
}
