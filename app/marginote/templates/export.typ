// The PDF of an export (export_pdf.py). Everything it prints comes in as data (sys.inputs.data, JSON), never
// as code, so whatever a quote contains (# * [ ] $ \ …) prints as it is.
#let data = json(bytes(sys.inputs.data))
#let L = data.labels
#let grey = luma(40%)
#let rich(runs) = runs.map(r => if r.at(1) { emph(r.at(0)) } else { r.at(0) }).join()
#let lines(text) = text.split("\n").join(linebreak())

#set document(title: data.title + " — " + data.subtitle, author: data.account)
#set text(lang: data.lang, font: "New Computer Modern", size: 11pt)
#set par(justify: true, leading: 0.6em, spacing: 0.85em)
#set page(paper: "a4", margin: (top: 2.6cm, bottom: 2.4cm, x: 2.6cm),
  header: context {
    if counter(page).get().first() > 1 {
      let before = query(heading.where(level: 1).before(here()))
      if before.len() > 0 { align(right, text(8.5pt, fill: grey, smallcaps(before.last().body))) }
    }
  },
  footer: context align(center, text(9pt, fill: grey, counter(page).display())))

// chapters (an author, a topic or a source), then works and parts inside them
#show heading: set block(sticky: true)
#show heading.where(level: 1): it => {
  v(2.2em, weak: true)
  block(below: 0.35em, text(18pt, weight: "regular", it.body))
}
#show heading.where(level: 2): it => {
  let label = it.body.func() == smallcaps
  block(above: if label { 1.8em } else { 1.5em }, below: 0.3em,
    if label { text(10.5pt, weight: "regular", tracking: 0.06em, fill: grey, it.body) }
    else { text(13pt, weight: "regular", it.body) })
}
#show heading.where(level: 3): it => block(above: 1.2em, below: 0.25em, text(11.5pt, weight: "regular", it.body))

#let section-label(t) = block(sticky: true, above: 1.8em, below: 0.4em, text(10.5pt, tracking: 0.06em, fill: grey, smallcaps(t)))

#let quote-block(q) = block(breakable: true, above: 1.05em, below: 0.5em, inset: (left: 1em, y: 0.15em),
  stroke: (left: 0.6pt + luma(72%)))[
  #L.open#q.text#L.close
  #block(width: 100%, above: 0.45em, below: 0pt, align(right, text(9.5pt, rich(q.ref))))
  #if q.topics.len() > 0 { block(above: 0.35em, below: 0pt, text(8.5pt, fill: grey, q.topics.join("  ·  "))) }
  #if q.comment != "" { block(above: 0.45em, below: 0pt, text(9.5pt, [#smallcaps(L.comment) — #emph(q.comment)])) }
]

#let note-block(n) = block(breakable: true, width: 100%, above: 1.05em, below: 0.5em, fill: luma(95.5%),
  inset: (x: 0.9em, y: 0.75em), radius: 2pt)[
  #grid(columns: (1fr, auto), column-gutter: 1em,
    text(10pt)[#smallcaps(L.note)#if n.title != "" [ — #strong(n.title)]],
    text(9pt, fill: grey, n.place))
  #v(0.15em)
  #set par(spacing: 0.6em)
  #for p in n.paras [#p #parbreak()]
  #if n.topics.len() > 0 { block(above: 0.5em, below: 0pt, text(8.5pt, fill: grey, n.topics.join("  ·  "))) }
]

#let source-group(g) = {
  if g.head != none {
    heading(level: g.level, outlined: g.level == 2, emph(g.head.title))
    block(sticky: true, above: 0.2em, below: 0.7em, text(9.5pt, fill: grey,
      [#if g.head.subtitle != "" [#g.head.subtitle#linebreak()]#g.head.meta]))
  }
  for i in g.items {
    if i.type == "quote" { quote-block(i) } else { note-block(i) }
  }
}

// ----- the top of page 1: what this is, then the contents (each line a link) -----
#block(below: 0.3em, text(9pt, tracking: 0.14em, fill: grey, smallcaps[Marginote]))
#block(below: 0.25em, text(25pt, data.title))
#block(below: 0.35em, text(13pt, style: "italic", data.subtitle))
#text(9.5pt, fill: grey, data.byline)
#v(0.9em)
#line(length: 100%, stroke: 0.4pt + luma(70%))
#v(0.4em)
#block(below: 0.9em, text(10.5pt, tracking: 0.06em, fill: grey, smallcaps(L.contents)))
#show outline.entry.where(level: 1): it => { v(0.7em, weak: true); it }
#show outline.entry.where(level: 2): set text(10pt)
#outline(title: none, depth: 2, indent: 1.6em)
#pagebreak()

// ----- the chapters -----
#for c in data.chapters {
  heading(level: 1, rich(c.title))
  if c.meta != "" { block(sticky: true, above: 0.2em, below: 0.8em, text(9.5pt, fill: grey, lines(c.meta))) }
  line(length: 100%, stroke: 0.4pt + luma(80%))
  for s in c.sections {
    if s.label != "" {
      if s.outlined { heading(level: 2, smallcaps(s.label)) } else { section-label(s.label) }
    }
    for g in s.groups { source-group(g) }
  }
}

// ----- every source cited -----
#if data.bibliography.len() > 0 {
  heading(level: 1, L.bibliography)
  line(length: 100%, stroke: 0.4pt + luma(80%))
  v(0.6em)
  set par(hanging-indent: 1.6em, justify: false, spacing: 0.7em)
  for b in data.bibliography [#rich(b) #parbreak()]
}
