/**
 * The controls, as components rather than as bare elements with a class.
 *
 * Before this file the interface had exactly four primitives -- `Page`,
 * `Loading`, `Failed`, `Sentence` in `Shell.tsx` -- and everything else was a
 * `<div className="...">` with the styling agreed by convention.  That is why
 * the same toolbar was written three times with three different inline padding
 * overrides.
 *
 * The one rule every control here obeys: **an icon never replaces a label.**
 * `MapStage.test.tsx` and all three Playwright specs address controls by their
 * accessible name (`{ name: "TRAILS", exact: true }`) and by their text, and
 * there is not one test id in the repository.  So `label` is rendered as its
 * own text node and `icon` is drawn beside it with `aria-hidden` already set
 * by `Icon`.  A control whose only content is a glyph must be given an
 * `aria-label`, and `IconButton` is the only one that takes one.
 *
 * Sound is wired in here rather than at each call site for the same reason the
 * `aria-hidden` is: a press that sounds in one place and not another is a bug
 * nobody will file, they will just decide the sounds are unreliable.
 */

import type { ComponentType, KeyboardEvent, ReactNode, SVGProps } from "react";
import { useRef } from "react";

import { Icon, ICON_ALONE, Spinner, glyphs } from "./icons";
import { Sentence } from "./Shell";
import { play, playToggle } from "./sound";

type Glyph = ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;

type ButtonProps = {
  label: string;
  icon?: Glyph;
  onClick?: () => void;
  variant?: "default" | "primary" | "ghost" | "danger";
  size?: "sm" | "md";
  disabled?: boolean;
  busy?: boolean;
  title?: string;
  className?: string;
};

/**
 * A button.
 *
 * `label` is a string rather than a node on purpose: it has to end up as one
 * text node, and a caller who could pass `<b>SIGHT</b>` would eventually pass
 * `<>SI<span>GHT</span></>` and break a name lookup two files away.
 */
export function Button({
  label,
  icon,
  onClick,
  variant = "default",
  size = "md",
  disabled = false,
  busy = false,
  title,
  className,
}: ButtonProps) {
  const classes = ["", variant === "default" ? "" : variant, size === "sm" ? "sm" : "", className]
    .filter(Boolean)
    .join(" ")
    .trim();
  return (
    <button
      type="button"
      title={title}
      disabled={disabled || busy}
      className={classes || undefined}
      onClick={() => {
        play("click");
        onClick?.();
      }}
    >
      {busy ? <Spinner /> : icon ? <Icon glyph={icon} /> : null}
      <span>{label}</span>
      {/*
        The trailing cap, on the primary variant only -- a nested circle
        carrying the mark rather than a glyph floating beside the words.  It is
        after the label and `aria-hidden` through `Icon`, so the accessible
        name is still exactly `label` and `findByText(label)` still matches the
        span above: `findByText` reads an element's *direct* text children, and
        this adds a sibling rather than joining that node.
        `views/ui.test.tsx` is the standing check.
      */}
      {variant === "primary" && !busy ? (
        <span className="cap">
          <Icon glyph={glyphs.capArrow} size={13} />
        </span>
      ) : null}
    </button>
  );
}

/**
 * A button whose only content is a glyph.
 *
 * Safe only where nothing addresses it by text.  The `label` becomes the
 * accessible name through `aria-label`, and the icon stays hidden, so a screen
 * reader and a test both still have a name to find.
 */
export function IconButton({
  label,
  icon,
  onClick,
  pressed,
  disabled = false,
  variant = "ghost",
  silent = false,
}: {
  label: string;
  icon: Glyph;
  onClick?: () => void;
  pressed?: boolean;
  disabled?: boolean;
  variant?: "default" | "ghost";
  /** For the sound toggle itself, which has to make its own noise, after. */
  silent?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={pressed}
      title={label}
      disabled={disabled}
      className={`icon-only${variant === "ghost" ? " ghost" : ""}`}
      onClick={() => {
        if (!silent) {
          if (pressed === undefined) {
            play("click");
          } else {
            playToggle(!pressed);
          }
        }
        onClick?.();
      }}
    >
      <Icon glyph={icon} size={ICON_ALONE} />
    </button>
  );
}

/**
 * A layer switch.  `aria-pressed` is the state, which is what the specs read.
 */
export function Toggle({
  label,
  icon,
  pressed,
  onChange,
  title,
}: {
  label: string;
  icon?: Glyph;
  pressed: boolean;
  onChange: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      title={title}
      onClick={() => {
        playToggle(!pressed);
        onChange();
      }}
    >
      {icon ? <Icon glyph={icon} /> : null}
      <span>{label}</span>
    </button>
  );
}

/**
 * One track, N mutually exclusive options.
 *
 * Used for 2D/3D and for the speed row, both of which were previously loose
 * buttons that happened to sit next to each other -- which reads as five
 * independent toggles rather than one choice.
 */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  format,
  label,
}: {
  options: readonly T[];
  value: T;
  onChange: (next: T) => void;
  format?: (option: T) => { label: string; icon?: Glyph };
  label?: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((option) => {
        const shown = format?.(option) ?? { label: String(option) };
        const selected = option === value;
        return (
          <button
            key={String(option)}
            type="button"
            aria-pressed={selected}
            onClick={() => {
              if (!selected) {
                play("click");
                onChange(option);
              }
            }}
          >
            {shown.icon ? <Icon glyph={shown.icon} /> : null}
            <span>{shown.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function Chip({
  children,
  tone = "neutral",
  icon,
  dot,
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "a" | "ok" | "warn" | "bad";
  icon?: Glyph;
  dot?: boolean;
  title?: string;
}) {
  const cls = tone === "neutral" ? "chip" : `chip ${tone}`;
  return (
    <span className={cls} title={title}>
      {dot ? <i className={`dot${tone === "neutral" ? "" : ` ${tone}`}`} /> : null}
      {icon ? <Icon glyph={icon} size={11} /> : null}
      {children}
    </span>
  );
}

export function Panel({
  title,
  icon,
  actions,
  dense,
  className,
  children,
}: {
  title?: string;
  icon?: Glyph;
  actions?: ReactNode;
  dense?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const cls = ["panel", dense ? "dense" : "", className].filter(Boolean).join(" ");
  return (
    <div className={cls}>
      {title !== undefined ? (
        <div className="panel-head">
          {icon ? <Icon glyph={icon} /> : null}
          <h2>{title}</h2>
          <div className="spacer" />
          {actions}
        </div>
      ) : null}
      {children}
    </div>
  );
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="toolbar">{children}</div>;
}

/**
 * A control with a label that is read but not shown.
 *
 * `aria-label` on the `<label>` was the bug: it names the *label element*, and
 * a label names the control it wraps by its **text content** -- of which there
 * was none, because the only other child is an `aria-hidden` glyph.  The map
 * filter on the match list therefore reached a screen reader as an unnamed
 * combo box reading out whichever option happened to be selected.
 *
 * The fix is a real text node that is positioned out of view rather than
 * hidden: `display: none` and `visibility: hidden` both take it back out of
 * the accessibility tree, which is the thing being fixed.
 */
export function Field({
  icon,
  label,
  children,
}: {
  icon?: Glyph;
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field" title={label}>
      {icon ? <Icon glyph={icon} /> : null}
      <span className="sr-only">{label}</span>
      {children}
    </label>
  );
}

export type Tab = { id: string; label: string; icon?: Glyph; count?: number };

/**
 * The two ids a tab strip and its panel have to agree on.
 *
 * Derived from the tab's own id rather than from `useId`, because the strip
 * and the panel it labels are rendered by two different components -- the
 * caller decides what goes in the panel, which is the whole point -- and a
 * generated id cannot be shared across that boundary without threading a
 * context through for one string.  Tab ids are unique within a page by
 * construction: they are the thing `active` is compared against.
 */
const tabId = (id: string) => `tab-${id}`;
const panelId = (id: string) => `panel-${id}`;

/**
 * One choice, N panels -- with the keyboard pattern the roles promise.
 *
 * `role="tablist"`/`role="tab"` is a contract and not a label: a screen reader
 * that reads those roles then tells the user to arrow between the tabs, and
 * announces "1 of 2", and looks for the panel each one controls.  Claiming the
 * roles while leaving all three unimplemented is worse than plain buttons,
 * because the instructions it puts in the user's ear are wrong.
 *
 * So: one tab stop for the whole strip (roving `tabIndex`, the selected one at
 * 0), arrow keys and Home/End to move, and `aria-controls` pointing at a
 * `TabPanel`.  Selection follows focus, which is the pattern for a strip whose
 * panels are already in hand -- there is nothing to fetch, so there is nothing
 * to make an arrow key expensive.
 */
export function Tabs({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: readonly Tab[];
  active: string;
  onChange: (id: string) => void;
  label?: string;
}) {
  const strip = useRef<HTMLDivElement>(null);

  const go = (index: number) => {
    const tab = tabs[index];
    if (!tab) return;
    // Focus the element rather than waiting for the render: the buttons are
    // keyed, so this one survives the state change and is the same node after.
    strip.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[index]?.focus();
    if (tab.id !== active) {
      play("click");
      onChange(tab.id);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const at = tabs.findIndex((tab) => tab.id === active);
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    let next = -1;
    if (step !== 0) next = (at + step + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    if (next < 0) return;
    event.preventDefault();
    go(next);
  };

  return (
    <div className="tabs" role="tablist" aria-label={label} ref={strip} onKeyDown={onKeyDown}>
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={tabId(tab.id)}
            className="tab"
            aria-selected={selected}
            /*
              Only on the selected tab, because only its panel is in the DOM:
              the caller renders one `TabPanel` for whichever tab is active,
              and a reference to an id that does not exist is worse than no
              reference -- a reader that follows it lands on nothing.
            */
            aria-controls={selected ? panelId(tab.id) : undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => {
              if (!selected) {
                play("click");
                onChange(tab.id);
              }
            }}
          >
            {tab.icon ? <Icon glyph={tab.icon} /> : null}
            <span>{tab.label}</span>
            {tab.count === undefined ? null : <span className="tab-count">{tab.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

/**
 * What a tab controls.
 *
 * `tabIndex={0}` is not decoration: the panels here hold a `.scroll-y` table,
 * and a scrollable region with nothing focusable inside it cannot be scrolled
 * from the keyboard at all.  It is also what makes the arrow-key strip above
 * lead somewhere -- Tab out of the tablist and you land in the panel it names.
 */
export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={panelId(id)} aria-labelledby={tabId(id)} tabIndex={0}>
      {children}
    </div>
  );
}

/**
 * A sentence where a picture would go, with a mark above it.
 *
 * The mark is allowed and the drawing is not, and the difference is the whole
 * argument: a schematic in the place a map goes reads as a map however it is
 * captioned, whereas a crossed-out picture frame reads as *there is no
 * picture*, which is exactly the claim being made.  The sentence itself is
 * untouched -- several of them are asserted verbatim.
 */
export function EmptyState({ icon, children }: { icon?: Glyph; children: ReactNode }) {
  return (
    <div className="empty">
      {icon ? (
        <span className="empty-mark">
          <Icon glyph={icon} size={28} />
        </span>
      ) : null}
      {/* `Sentence` rather than a second <p className="sentence">: several of
          these are matched verbatim by tests, and the element they are matched
          in should have one definition. */}
      <Sentence>{children}</Sentence>
    </div>
  );
}
