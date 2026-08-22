/**
 * The rule that lets a redesign add icons without breaking the test suite.
 *
 * There is not one `data-testid` in this repository.  `MapStage.test.tsx`
 * finds controls with `findByText("SIGHT")`; `e2e/gallery.spec.ts` and
 * `e2e/minimap.spec.ts` press them with
 * `getByRole("button", { name: "TRAILS", exact: true })`; `e2e/harness.ts`
 * clicks `getByTitle("Next event")`.  Those seven labels and two titles are
 * an interface, and an icon inside a button is exactly the change that would
 * rename them without any file that mentions them being edited.
 *
 * So every glyph is `aria-hidden`, applied centrally in `icons.tsx`, and the
 * label is its own text node beside it.  This file is the standing check on
 * that -- it is deliberately about accessible names and nothing about looks.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { glyphs } from "./icons";
import { Button, Chip, Field, IconButton, Segmented, TabPanel, Tabs, Toggle } from "./ui";

afterEach(cleanup);

describe("an icon never renames the control it sits in", () => {
  it("leaves a button's accessible name equal to its label", () => {
    render(<Button label="DECODE POSITIONS" icon={glyphs.decode} />);
    expect(
      screen.getByRole("button", { name: "DECODE POSITIONS" }),
    ).toBeTruthy();
  });

  it("keeps the label findable as its own text node", () => {
    // `findByText` matches on an element's *direct* text children, so a label
    // that got concatenated with anything else would stop being found.
    render(<Toggle label="SIGHT" icon={glyphs.sight} pressed={false} onChange={() => undefined} />);
    expect(screen.getByText("SIGHT")).toBeTruthy();
  });

  it("keeps every option in a segmented control addressable by name", () => {
    render(
      <Segmented
        options={["2D", "3D"] as const}
        value="2D"
        onChange={() => undefined}
        format={(option) => ({
          label: option,
          icon: option === "2D" ? glyphs.view2d : glyphs.view3d,
        })}
      />,
    );
    // Exactly as `gallery.spec.ts` presses them.
    expect(screen.getByRole("button", { name: "2D" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "3D" })).toBeTruthy();
    expect(screen.getByText("3D")).toBeTruthy();
  });

  it("leaves a primary button's name alone when it grows a trailing cap", () => {
    // The cap is a second, nested glyph after the label -- the one shape of
    // change that renames a control without any file that mentions it being
    // edited.  `MapStage.test.tsx` finds this exact button by its text.
    const { container } = render(
      <Button label="DECODE POSITIONS" icon={glyphs.decode} variant="primary" />,
    );
    expect(screen.getByRole("button", { name: "DECODE POSITIONS" })).toBeTruthy();
    expect(screen.getByText("DECODE POSITIONS")).toBeTruthy();
    expect(container.querySelector(".cap")).not.toBeNull();
    // Both glyphs -- the leading icon and the cap's mark -- stay out of the
    // accessibility tree, or the name above would have picked them up.
    const marks = container.querySelectorAll("svg");
    expect(marks.length).toBe(2);
    marks.forEach((mark) => expect(mark.getAttribute("aria-hidden")).toBe("true"));
  });

  it("drops the cap while the button is busy, so it never sits beside a spinner", () => {
    const { container } = render(
      <Button label="DECODING…" icon={glyphs.decode} variant="primary" busy />,
    );
    expect(container.querySelector(".cap")).toBeNull();
  });

  it("gives the cap to the primary variant only", () => {
    const { container } = render(<Button label="BACK" icon={glyphs.back} />);
    expect(container.querySelector(".cap")).toBeNull();
  });

  it("hides the glyph from the accessibility tree", () => {
    const { container } = render(<Button label="RESCAN" icon={glyphs.rescan} />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });

  it("draws svg rather than img, which one page asserts over its whole tree", () => {
    // `MatchList.test.tsx` checks `container.querySelector("img")` is null in
    // the no-thumbnail state, over everything rendered -- so a decorative mark
    // that happened to be an <img> would fail a test about map art.
    const { container } = render(
      <Chip tone="ok" icon={glyphs.ok}>
        positions
      </Chip>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });
});

describe("a control with no words gets a name anyway", () => {
  it("names an icon-only button through aria-label and title", () => {
    // The transport's step buttons are located by `getByTitle("Next event")`
    // in `e2e/harness.ts`, and a screen reader needs the same words.
    render(<IconButton label="Next event" icon={glyphs.nextEvent} />);
    expect(screen.getByRole("button", { name: "Next event" })).toBeTruthy();
    expect(screen.getByTitle("Next event")).toBeTruthy();
  });

  it("reports its pressed state where it has one", () => {
    render(<IconButton label="Loop this round" icon={glyphs.loop} pressed />);
    expect(screen.getByRole("button", { pressed: true })).toBeTruthy();
  });
});

describe("a control whose label is not drawn still has one", () => {
  it("names a wrapped select through the label's own text", () => {
    // The map filter on the match list.  `aria-label` on the <label> named the
    // label element and left the select anonymous, so this asserts the name
    // the *control* reports rather than the attribute that was set.
    render(
      <Field icon={glyphs.mapPin} label="Filter by map">
        <select defaultValue="">
          <option value="">every map</option>
        </select>
      </Field>,
    );
    expect(screen.getByRole("combobox", { name: "Filter by map" })).toBeTruthy();
  });
});

function Strip() {
  const [active, setActive] = useState("rounds");
  return (
    <>
      <Tabs
        label="Timeline"
        active={active}
        onChange={setActive}
        tabs={[
          { id: "rounds", label: "Rounds", count: 24 },
          { id: "casts", label: "Ability casts", count: 3 },
        ]}
      />
      <TabPanel id={active}>{active === "rounds" ? "the rounds" : "the casts"}</TabPanel>
    </>
  );
}

describe("a tablist keeps the promise its roles make", () => {
  it("puts one tab stop on the strip, not one per tab", () => {
    render(<Strip />);
    const [rounds, casts] = screen.getAllByRole("tab");
    expect(rounds?.getAttribute("tabindex")).toBe("0");
    expect(casts?.getAttribute("tabindex")).toBe("-1");
  });

  it("points each tab at the panel it actually controls", () => {
    render(<Strip />);
    const selected = screen.getByRole("tab", { selected: true });
    const panel = screen.getByRole("tabpanel");
    expect(selected.getAttribute("aria-controls")).toBe(panel.getAttribute("id"));
    expect(panel.getAttribute("aria-labelledby")).toBe(selected.getAttribute("id"));
  });

  it("moves the selection with the arrow keys and Home", () => {
    render(<Strip />);
    const strip = screen.getByRole("tablist");
    fireEvent.keyDown(strip, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { selected: true }).textContent).toContain("Ability casts");
    expect(screen.getByRole("tabpanel").textContent).toBe("the casts");
    fireEvent.keyDown(strip, { key: "Home" });
    expect(screen.getByRole("tab", { selected: true }).textContent).toContain("Rounds");
  });

  it("wraps at the ends rather than stopping", () => {
    render(<Strip />);
    const strip = screen.getByRole("tablist");
    fireEvent.keyDown(strip, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { selected: true }).textContent).toContain("Ability casts");
  });
});
