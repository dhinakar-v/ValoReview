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
 */

import type { ComponentType, KeyboardEvent, ReactNode, SVGProps } from "react";
import { useEffect, useId, useRef, useState } from "react";

import { Icon, ICON_ALONE, Spinner, glyphs } from "./icons";
import { Sentence } from "./Shell";

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
          } else {
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

/**
 * A dropdown that belongs to this interface rather than to the operating
 * system.
 *
 * The map filter was a bare `<select>`, and the one thing CSS cannot reach on
 * a `<select>` is the part people actually look at: the popup is drawn by the
 * platform, so it opened as a white-on-black OS list with a system highlight
 * and a scrollbar belonging to nothing else on the page.  `color-scheme: dark`
 * is as far as styling gets.
 *
 * So it is a `role="combobox"` button over a `role="listbox"`, which means the
 * behaviour a native select gave for free has to be implemented rather than
 * assumed -- that is the whole cost of this control and the reason it is here
 * and not inlined at the call site:
 *
 *   * the name comes from `aria-labelledby` pointing at the clipped label,
 *     **not** from the button's own text.  A combobox named by its contents
 *     announces the current value where its name should be, and
 *     `ui.test.tsx` asserts the name is the label and nothing else;
 *   * `aria-activedescendant` moves without the focus, which is what keeps the
 *     button focused while the arrows walk the list;
 *   * Enter and Space commit, Escape closes without committing and returns the
 *     focus, Home and End jump, and typing a letter jumps to the next option
 *     starting with it -- all of which a `<select>` does and nobody would
 *     forgive this for not doing.
 *
 * `shortcuts.ts` yields the arrows, Home and End to `[role="listbox"]` and
 * `[role="combobox"]`, because its `editing()` check recognises a native
 * `SELECT` by tag name and a div with a role is not one.
 */
export function Select({
  icon,
  label,
  value,
  options,
  onChange,
}: {
  icon?: Glyph;
  /** Read but not drawn, and the accessible name of the control. */
  label: string;
  value: string;
  /** `value` is what the caller stores; `label` is what a person reads. */
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrap = useRef<HTMLDivElement | null>(null);
  const base = useId();
  const labelId = `${base}-label`;
  const listId = `${base}-list`;
  const optionId = (index: number) => `${base}-option-${index}`;

  const chosen = options.findIndex((option) => option.value === value);
  const shown = options[chosen === -1 ? 0 : chosen]?.label ?? "";

  useEffect(() => {
    if (!open) {
      return;
    }
    const onDown = (event: MouseEvent) => {
      if (!wrap.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const commit = (index: number) => {
    const option = options[index];
    if (option !== undefined) {
      onChange(option.value);
    }
    setOpen(false);
    wrap.current?.querySelector("button")?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const last = options.length - 1;
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter")) {
      setActive(chosen === -1 ? 0 : chosen);
      setOpen(true);
      event.preventDefault();
      return;
    }
    if (!open) {
      return;
    }
    if (event.key === "ArrowDown") {
      setActive((at) => Math.min(last, at + 1));
    } else if (event.key === "ArrowUp") {
      setActive((at) => Math.max(0, at - 1));
    } else if (event.key === "Home") {
      setActive(0);
    } else if (event.key === "End") {
      setActive(last);
    } else if (event.key === "Enter" || event.key === " ") {
      commit(active);
    } else if (event.key === "Escape") {
      // Closes without committing, which is what a native select does and
      // what makes arrowing through a long list safe to abandon.
      setOpen(false);
      wrap.current?.querySelector("button")?.focus();
    } else if (event.key.length === 1) {
      const from = event.key.toLowerCase();
      const found = options.findIndex((option) =>
        option.label.toLowerCase().startsWith(from),
      );
      if (found === -1) {
        return;
      }
      setActive(found);
    } else {
      return;
    }
    event.preventDefault();
  };

  return (
    <div className="field select-field" ref={wrap}>
      {icon ? <Icon glyph={icon} /> : null}
      <span className="sr-only" id={labelId}>
        {label}
      </span>
      <button
        type="button"
        role="combobox"
        className="select-button"
        aria-labelledby={labelId}
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        aria-activedescendant={open ? optionId(active) : undefined}
        title={label}
        onKeyDown={onKeyDown}
        onClick={() => {
          setActive(chosen === -1 ? 0 : chosen);
          setOpen((was) => !was);
        }}
      >
        <span>{shown}</span>
        <Icon glyph={glyphs.pageNext} />
      </button>
      <ul
        className={open ? "select-list" : "select-list is-shut"}
        id={listId}
        role="listbox"
        aria-labelledby={labelId}
      >
        {options.map((option, index) => (
          <li
            key={option.value}
            id={optionId(index)}
            role="option"
            aria-selected={option.value === value}
            className={index === active ? "select-option is-active" : "select-option"}
            onMouseEnter={() => setActive(index)}
            onMouseDown={(event) => {
              // Before blur, or the outside-click handler closes the list out
              // from under the click that was choosing something.
              event.preventDefault();
              commit(index);
            }}
          >
            {option.label}
          </li>
        ))}
      </ul>
    </div>
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

/* -------------------------------------------------------------------------
 * Floating things.
 *
 * Three of them, and each is here rather than in the component that opens it
 * because each has one behaviour that is easy to get subtly wrong and easy to
 * regress: a popover must close on Escape and on a click outside it, a modal
 * must trap focus and give it back, and a checkbox must be a real checkbox.
 * ---------------------------------------------------------------------- */

/**
 * A checkbox with a label and an optional glyph.
 *
 * A real `<input type="checkbox">` rather than a `button[aria-pressed]`, which
 * is what the layer toggles were.  Inside a menu of nine that difference is
 * audible: a screen reader announces "checked / not checked" and the count of
 * the group, where nine pressed buttons announce nine unrelated states.  The
 * visible box is drawn from the input's own `:checked`, so nothing has to keep
 * a second copy of the state in sync.
 *
 * `label` stays a string, for the reason at the top of this file.
 */
export function CheckRow({
  label,
  icon,
  checked,
  onChange,
  tone,
  title,
  disabled,
  reason,
}: {
  label: string;
  icon?: Glyph;
  checked: boolean;
  onChange: () => void;
  /**
   * Outlines the row in a colour that means something.
   *
   * `a`/`b` are the team colours, as the reference does.  The four event tones
   * are the rail's own tick colours, which is what makes the layers menu the
   * legend for a 24px canvas that cannot carry one.
   */
  tone?: "a" | "b" | "kill" | "cast" | "ult" | "spike";
  title?: string;
  disabled?: boolean;
  /**
   * Why this switch cannot be used, shown under the label.
   *
   * **Outside the `<label>`, and that is load-bearing.**  A `<label>` names the
   * control it wraps by its *text content*, so a reason rendered inside it
   * renames the checkbox from `SIGHT` to `SIGHT 3D only` -- which breaks every
   * `getByRole("checkbox", { name })` in the suite and is the exact failure
   * class `ui.test.tsx` exists to catch.  It is attached with
   * `aria-describedby` instead, so a reader announces it as a description.
   */
  reason?: string;
}) {
  const id = useId();
  const classes = [
    "check-row",
    tone ? `is-${tone}` : "",
    disabled ? "is-disabled" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <>
      <label className={classes} title={title}>
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-describedby={reason ? id : undefined}
          onChange={onChange}
        />
        <span className="check-box" aria-hidden="true" />
        {icon ? <Icon glyph={icon} /> : null}
        <span className="check-label">{label}</span>
      </label>
      {reason ? (
        <p className="check-why" id={id}>
          {reason}
        </p>
      ) : null}
    </>
  );
}

/**
 * A button that opens a panel beneath it.
 *
 * Closes on Escape, on a click anywhere outside, and on losing focus to
 * something outside -- three separate exits because each covers a different
 * way of leaving: the keyboard, the mouse and the tab key.  The panel is a
 * sibling of the button inside one positioned wrapper rather than a portal,
 * because it is anchored to the button and nothing here needs to escape an
 * overflow.
 */
export function Menu({
  label,
  icon,
  children,
  align = "end",
  drop = "down",
  title,
}: {
  label: string;
  icon?: Glyph;
  children: ReactNode;
  align?: "start" | "end";
  /**
   * Which way the panel opens.
   *
   * `up` exists because the layers menu moved off the stage head and down into
   * the playback bar, where everything else that changes what is being watched
   * already lives.  A panel that still dropped downward from there would open
   * off the bottom of a viewer that does not scroll.
   */
  drop?: "down" | "up";
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onDown = (event: MouseEvent) => {
      if (!wrap.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        // Back to the button, not to the body: a menu that dumps the focus at
        // the top of the document makes Escape more expensive than the mouse.
        wrap.current?.querySelector("button")?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="menu" ref={wrap}>
      <button
        type="button"
        className={open ? "menu-button is-open" : "menu-button"}
        aria-expanded={open}
        aria-haspopup="true"
        title={title}
        onClick={() => setOpen((was) => !was)}
      >
        {icon ? <Icon glyph={icon} /> : null}
        <span>{label}</span>
      </button>
      {open ? (
        <div
          className={[
            "menu-panel",
            align === "start" ? "at-start" : "",
            drop === "up" ? "drops-up" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

/**
 * A modal dialog over a dimmed, blurred page.
 *
 * Focus is moved in on open and given back on close, and Tab is cycled inside:
 * a dialog you can Tab out of is a dialog that puts the focus behind its own
 * backdrop, where the user cannot see what has it.  The backdrop closes on a
 * click, which is what every other dialog on the web does and what a user will
 * try first.
 */
export function Modal({
  title,
  onClose,
  children,
  actions,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Anything that belongs beside the title -- a stepper, a legend. */
  actions?: ReactNode;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  const returnTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    returnTo.current = document.activeElement as HTMLElement | null;
    box.current?.focus();
    return () => returnTo.current?.focus();
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      onClose();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    const focusable = box.current?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable === undefined || focusable.length === 0) {
      return;
    }
    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      last.focus();
      event.preventDefault();
    } else if (!event.shiftKey && document.activeElement === last) {
      first.focus();
      event.preventDefault();
    }
  };

  return (
    <div className="scrim" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={box}
        onKeyDown={onKeyDown}
        // The backdrop closes; the dialog itself must not, or every click
        // inside it would travel to the handler above and shut it.
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          {actions}
          <div className="spacer" />
          <IconButton label="Close" icon={glyphs.close} onClick={onClose} />
        </div>
        {children}
      </div>
    </div>
  );
}
