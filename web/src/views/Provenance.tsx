/**
 * Every claim the interface makes, and where each one came from.
 *
 * The sections arrive already divided -- read from the file, decoded from the
 * replication stream, looked up in Riot's catalogue, inferred here, absent
 * altogether -- and this only lays them out.  The division is the content: a
 * reader who cannot tell a read fact from a derived one cannot tell what the
 * viewer knows from what it worked out.
 *
 * The desktop viewer rendered this as a monospaced block whose alignment was
 * the only thing separating a label from a claim.  A definition list does that
 * job in a way that survives a proportional font, which is why the server sends
 * entries rather than pre-formatted lines.
 */

import { Fragment } from "react";

import type { ProvenanceSection } from "../api/types";

export function Provenance({ sections }: { sections: ProvenanceSection[] }) {
  return (
    <div className="provenance">
      {sections.map((section) => (
        <section key={section.title}>
          <h3>{section.title}</h3>
          <dl>
            {section.entries.map((entry, index) =>
              entry.bare ? (
                // A note: derived prose, or a line about the art cache. It has
                // no label because it is a sentence, not a field.
                <div className="bare" key={`${section.title}-${index}`}>
                  {entry.value}
                </div>
              ) : (
                <Fragment key={`${section.title}-${index}`}>
                  <dt>{entry.label}</dt>
                  <dd>{entry.value}</dd>
                </Fragment>
              ),
            )}
          </dl>
        </section>
      ))}
    </div>
  );
}
