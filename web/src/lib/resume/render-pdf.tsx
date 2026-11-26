import "server-only";

import { Document, Font, Link, Page, StyleSheet, Text, View, renderToBuffer } from "@react-pdf/renderer";

// No automatic hyphenation: it splits words ("conges-tion", "Text--to-Speech"), and a split keyword
// is a keyword an ATS can't find.
Font.registerHyphenationCallback((word) => [word]);

import type { TailoredResume } from "./types";

// Plain single-column layout (what ATS parsers read best), in the style of the original LaTeX resume.
// Built-in Times fonts: no font files to ship, and every character is real, extractable text.
const s = StyleSheet.create({
  page: { paddingTop: 30, paddingBottom: 28, paddingHorizontal: 40, fontFamily: "Times-Roman", fontSize: 10, lineHeight: 1.25, color: "#111" },
  name: { fontFamily: "Times-Bold", fontSize: 18, lineHeight: 1.1, textAlign: "center", letterSpacing: 0.6, marginBottom: 2 },
  headline: { fontSize: 10.5, textAlign: "center", marginTop: 3 },
  contact: { fontSize: 9.5, textAlign: "center", marginTop: 2 },
  link: { color: "#1a3db8", textDecoration: "none" },
  section: { marginTop: 8 },
  heading: { fontFamily: "Times-Bold", fontSize: 10.5, borderBottomWidth: 0.6, borderBottomColor: "#111", paddingBottom: 1, marginBottom: 3 },
  row: { flexDirection: "row", justifyContent: "space-between" },
  bold: { fontFamily: "Times-Bold" },
  italic: { fontFamily: "Times-Italic" },
  bulletRow: { flexDirection: "row", marginTop: 1.5, paddingLeft: 6 },
  bulletDot: { width: 9 },
  bulletText: { flex: 1 },
  entry: { marginTop: 4 },
});

/** "Built **LLM** agents" -> text with bold runs */
function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**") ? (
          <Text key={i} style={s.bold}>
            {p.slice(2, -2)}
          </Text>
        ) : (
          <Text key={i}>{p}</Text>
        ),
      )}
    </>
  );
}

function Bullets({ items }: { items: { text: string }[] }) {
  return (
    <>
      {items.map((b, i) => (
        <View key={i} style={s.bulletRow} wrap={false}>
          <Text style={s.bulletDot}>•</Text>
          <Text style={s.bulletText}>
            <Rich text={b.text} />
          </Text>
        </View>
      ))}
    </>
  );
}

export function ResumePdf({ r }: { r: TailoredResume }) {
  const [role, ...rest] = (r.basics.headline ?? "").split(/\s+–\s+/);
  const contact = [r.basics.phone, r.basics.location].filter(Boolean).join("  |  ");
  return (
    <Document title={`${r.basics.name} - Resume`} author={r.basics.name} subject="Resume" creator="Job Radar">
      <Page size="A4" style={s.page}>
        <Text style={s.name}>{r.basics.name.toUpperCase()}</Text>
        {r.basics.headline && (
          <Text style={s.headline}>
            <Text style={s.bold}>{role}</Text>
            {rest.length ? ` – ${rest.join(" – ")}` : ""}
          </Text>
        )}
        <Text style={s.contact}>
          {contact}
          {contact ? "  |  " : ""}
          <Link src={`mailto:${r.basics.email}`} style={s.link}>
            {r.basics.email}
          </Link>
        </Text>
        {!!r.basics.links?.length && (
          <Text style={s.contact}>
            {r.basics.links.map((l, i) => (
              <Text key={l.url}>
                {i > 0 ? "  |  " : ""}
                <Link src={l.url} style={s.link}>
                  {l.label}
                </Link>
              </Text>
            ))}
          </Text>
        )}

        {r.summary && (
          <View style={s.section}>
            <Text style={s.heading}>SUMMARY</Text>
            <Text>
              <Rich text={r.summary} />
            </Text>
          </View>
        )}

        <View style={s.section}>
          <Text style={s.heading}>TECHNICAL SKILLS</Text>
          {r.skills
            .filter((g) => g.items.length)
            .map(({ group, items }) => (
              <Text key={group} style={{ marginTop: 1 }}>
                <Text style={s.bold}>{group}: </Text>
                {items.join(", ")}
              </Text>
            ))}
        </View>

        <View style={s.section}>
          <Text style={s.heading}>EXPERIENCE</Text>
          {r.experience.map((e) => (
            <View key={e.id} style={s.entry}>
              <View style={s.row}>
                <Text style={{ flex: 1 }}>
                  <Text style={s.bold}>{e.title}</Text> – {e.company}
                </Text>
                <Text>{e.dates}</Text>
              </View>
              {e.subtitle && <Text style={s.italic}>{e.subtitle}</Text>}
              <Bullets items={e.bullets} />
            </View>
          ))}
        </View>

        {!!r.projects.length && (
          <View style={s.section}>
            <Text style={s.heading}>PROJECTS</Text>
            {r.projects.map((p) => (
              <View key={p.id} style={s.entry}>
                <View style={s.row}>
                  <Text style={{ flex: 1 }}>
                    <Text style={s.bold}>{p.name}</Text>
                    {p.tech?.length ? <Text style={s.italic}> — {p.tech.join(", ")}</Text> : null}
                  </Text>
                  {p.link && (
                    <Link src={p.link.url} style={s.link}>
                      {p.link.label}
                    </Link>
                  )}
                </View>
                <Bullets items={p.bullets} />
              </View>
            ))}
          </View>
        )}

        {(!!r.education?.length || !!r.certifications?.items.length) && (
          <View style={s.section}>
            <Text style={s.heading}>EDUCATION & CERTIFICATIONS</Text>
            {r.education?.map((ed) => (
              <View key={ed.degree} style={s.row}>
                <Text style={{ flex: 1 }}>
                  <Text style={s.bold}>{ed.degree}</Text> – {ed.school}
                </Text>
                <Text>{ed.dates}</Text>
              </View>
            ))}
            {!!r.certifications?.items.length && (
              <Text>
                <Text style={s.bold}>{r.certifications.items.join("  ·  ")}</Text>
                {r.certifications.link && (
                  <Text>
                    {"  "}
                    <Link src={r.certifications.link.url} style={s.link}>
                      ({r.certifications.link.label})
                    </Link>
                  </Text>
                )}
              </Text>
            )}
          </View>
        )}
      </Page>
    </Document>
  );
}

export async function renderPdf(r: TailoredResume): Promise<Buffer> {
  return renderToBuffer(<ResumePdf r={r} />);
}
