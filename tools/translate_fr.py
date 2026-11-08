"""Make the French screens (static/app.fr.js) from the English ones (static/app.js).

Every change is an exact replacement, checked: a sentence that is no longer found is reported, so the
French file never silently drifts from the English one. After changing app.js, run:

    python tools/translate_fr.py

and add the French for any new text to the tables below (tests fail while app.fr.js is out of date).
"""
import re
import sys
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "marginote" / "static"
NB, NN = "\u00a0", "\u202f"     # before ':' / before '?', '!', ';' and inside « »


def fr(text):
    """French spacing, outside ${…} only."""
    parts = re.split(r"(\$\{[^}]*\})", text)
    out = []
    for p in parts:
        if p.startswith("${"):
            out.append(p)
            continue
        p = p.replace(" :", NB + ":").replace(" ?", NN + "?").replace(" !", NN + "!").replace(" ;", NN + ";")
        p = p.replace("« ", "«" + NN).replace(" »", NN + "»")
        out.append(p)
    return "".join(out)



def translate(source: str) -> tuple[str, list[str], list[str]]:
    """The French version of the English script, with what could not be placed."""
    s = source
    missing = []


    def ctx(old, new, n=1):
        nonlocal s
        c = s.count(old)
        if c != n:
            missing.append(f"ctx x{c} (want {n}): {old[:90]}")
            return
        s = s.replace(old, new)


    # ---------- code that carries words ----------
    ctx("const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];",
        "const MONTHS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];")
    ctx("  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;",
        "  return `${d.getDate() === 1 ? '1er' : d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;")
    ctx("function plainDate(value) {   // '2026-10-02' -> '2 Oct 2026', '2026-10' -> 'Oct 2026'",
        "function plainDate(value) {   // '2026-10-02' -> '2 oct. 2026', '2026-10' -> 'oct. 2026'")
    ctx("  return [m[3] ? Number(m[3]) : null, m[2] ? MONTHS[Number(m[2]) - 1] : null, m[1]].filter(Boolean).join(' ');",
        "  return [m[3] ? (Number(m[3]) === 1 ? '1er' : Number(m[3])) : null, m[2] ? MONTHS[Number(m[2]) - 1] : null, m[1]].filter(Boolean).join(' ');")
    ctx("""  if (!bytes) return '0 KB';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;""", """  if (!bytes) return '0 Ko';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} Mo`;
  return `${(bytes / 1024 ** 3).toFixed(2).replace('.', ',')} Go`;""")
    ctx("""const WORDS = { entry: 'entries', copy: 'copies', person: 'people', other: 'other', class: 'classes' };
const plural = (n, word) => `${n} ${n === 1 ? word : WORDS[word] || word + 's'}`;""",
        """// how many of something, in French: 0 and 1 take the singular
const WORDS = { quote: ['citation', 'citations'], note: ['note', 'notes'], source: ['source', 'sources'], page: ['page', 'pages'],
  person: ['personne', 'personnes'], work: ['œuvre', 'œuvres'], word: ['mot', 'mots'], entry: ['entrée', 'entrées'],
  copy: ['copie', 'copies'], translation: ['traduction', 'traductions'], author: ['auteur', 'auteurs'],
  topic: ['thème', 'thèmes'] };
const plural = (n, word) => { const w = WORDS[word] || [word, word + 's']; return `${n} ${n <= 1 ? w[0] : w[1]}`; };""")

    a = s.index("// What each kind of source is called")
    b = s.index("const kindOf = ")
    s = s[:a] + """// What each kind of source is called, what it is made by, and how to say where in it a passage is.
// notesFirst: mostly your own notes on it (a video, a class), so capture starts on Note and its page shows them first.
const KINDS = {
  book: { name: 'Livre', label: 'livre', several: 'livres', the: 'le livre', this: 'ce livre', maker: 'author', makerLabel: 'auteur(s)', publisher: 'éditeur', where: 'page', photos: true },
  ebook: { name: 'Livre numérique', label: 'livre numérique', several: 'livres numériques', the: 'le livre', this: 'ce livre numérique', maker: 'author', makerLabel: 'auteur(s)', publisher: 'éditeur', where: 'page ou chapitre', photos: true },
  article: { name: 'Article', label: 'article', several: 'articles', the: 'l’article', this: 'cet article', maker: 'author', makerLabel: 'auteur(s)', publisher: 'site', where: null, link: true, dated: true },
  video: { name: 'Vidéo', label: 'vidéo', several: 'vidéos', the: 'la vidéo', this: 'cette vidéo', maker: 'speaker', makerLabel: 'qui parle', publisher: 'chaîne', where: null, link: true, dated: true, notesFirst: true },
  podcast: { name: 'Podcast', label: 'podcast', several: 'podcasts', the: 'le podcast', this: 'ce podcast', maker: 'speaker', makerLabel: 'qui parle', publisher: 'émission', where: null, link: true, dated: true, notesFirst: true },
  class: { name: 'Cours', label: 'cours', several: 'cours', the: 'le cours', this: 'ce cours', maker: 'speaker', makerLabel: 'enseignant(s)', publisher: 'école ou université', where: 'séance', photos: true, notesFirst: true },
  talk: { name: 'Conférence', label: 'conférence', several: 'conférences', the: 'la conférence', this: 'cette conférence', maker: 'speaker', makerLabel: 'qui parle', publisher: 'événement ou lieu', where: 'diapo ou partie', photos: true, dated: true },
  other: { name: 'Autre', label: 'autre', several: 'autres', the: 'la source', this: 'cette source', maker: 'author', makerLabel: 'par', publisher: 'éditeur ou lieu', where: 'où', photos: true },
};
""" + s[b:]

    # the kind of a source, as shown
    ctx("  return joinDots([h('span', { class: 'sc', text: s.kind }), who || s.publisher || null,",
        "  return joinDots([h('span', { class: 'sc', text: kindOf(s).label }), who || s.publisher || null,")
    ctx("  const details = joinDots([h('span', { class: 'sc', text: source.kind }), source.publisher,",
        "  const details = joinDots([h('span', { class: 'sc', text: k.label }), source.publisher,")
    ctx("        k.link && source.kind !== 'article' ? `Open the ${source.kind}` : 'Open the link', icon('external', 14)) : null,",
        "        k.link && source.kind !== 'article' ? `Ouvrir ${k.the}` : 'Ouvrir le lien', icon('external', 14)) : null,")
    ctx("      `Delete this ${k.name.toLowerCase()}…`)));", "      `Supprimer ${k.this}…`)));")
    ctx("  const linkLabel = source?.kind === 'article' ? 'Open at this passage' : `Open the ${source?.kind}`;",
        "  const linkLabel = source?.kind === 'article' ? 'Ouvrir à ce passage' : `Ouvrir ${kindOf(source).the}`;")
    ctx("`open the ${source.kind === 'article' ? 'article' : source.kind} ›`", "`ouvrir ${kindOf(source).the} ›`")

    # words that are also keys: changed where they are shown only
    ctx("    bits.push(h('span', { class: 'sc ink', text: e.by && e.by.id !== person ? `${surname(e.by)}, said` : 'said' }));",
        "    bits.push(h('span', { class: 'sc ink', text: e.by && e.by.id !== person ? `paroles de ${surname(e.by)}` : 'paroles' }));")
    ctx("  if (e.note) bits.push('comment');", "  if (e.note) bits.push('commentaire');")
    ctx("h('th', { style: { width: '64px' }, text: 'where' }), h('th', { text: 'quote' }),",
        "h('th', { style: { width: '64px' }, text: 'où' }), h('th', { text: 'citation' }),")
    ctx("showSource ? h('th', { style: { width: '200px' }, text: 'source' }) : null,", "showSource ? h('th', { style: { width: '200px' }, text: 'source' }) : null,")
    ctx("h('th', { style: { width: '150px' }, text: 'topics' }), h('th', { style: { width: '110px' }, text: 'added' }))),",
        "h('th', { style: { width: '150px' }, text: 'thèmes' }), h('th', { style: { width: '110px' }, text: 'ajoutée' }))),")
    ctx("text: opts.head || 'quote' })),", "text: opts.head || 'citation' })),")
    ctx("head: both ? false : 'quote' })", "head: both ? false : 'citation' })")
    ctx("showSource ? h('td', { class: 'it' }, e.source ? e.source.title : [h('span', { class: 'sc', text: 'said ' }), e.by?.name || '',",
        "showSource ? h('td', { class: 'it' }, e.source ? e.source.title : [h('span', { class: 'sc', text: 'paroles de ' }), e.by?.name || '',")
    ctx("""      h('option', { value: 'recent' }, 'recent first'), h('option', { value: 'title' }, 'by title'), h('option', { value: 'added' }, 'by date added'));""",
        """      h('option', { value: 'recent' }, 'récents d’abord'), h('option', { value: 'title' }, 'par titre'), h('option', { value: 'added' }, 'par date d’ajout'));""")
    ctx("present.length > 1 ? [['', 'all'], ...present.map((k) => [k, KINDS[k].several])]",
        "present.length > 1 ? [['', 'tout'], ...present.map((k) => [k, KINDS[k].several])]")
    ctx("h('span', { style: { flex: 1 }, text: 'source' }), h('span', { class: 'w40 r', text: 'items' }))",
        "h('span', { style: { flex: 1 }, text: 'source' }), h('span', { class: 'w40 r', text: 'total' }))")
    ctx("h('span', { style: { flex: 1 }, text: 'person' }), h('span', { class: 'w40 r', text: 'quotes' }))",
        "h('span', { style: { flex: 1 }, text: 'personne' }), h('span', { class: 'w40 r', text: 'citations' }))")
    ctx("h('span', { style: { flex: 1 }, text: 'topic' }), h('span', { class: 'w40 r', text: 'quotes' })),",
        "h('span', { style: { flex: 1 }, text: 'thème' }), h('span', { class: 'w40 r', text: 'citations' })),")
    ctx("filterRow([['everyone', 'everyone'], ['authors', 'authors'], ['about', 'written about']], which,",
        "filterRow([['everyone', 'tout le monde'], ['authors', 'auteurs'], ['about', 'sujets']], which,")
    ctx("filterRow([['name', 'a–z'], ['use', 'most used'], ['notes', 'with notes']], order,",
        "filterRow([['name', 'a–z'], ['use', 'les plus utilisés'], ['notes', 'avec des notes']], order,")
    ctx("translated ${p.translated}", "${plural(p.translated, 'translation')}", 2)
    ctx("""  } }, order === 'page' ? `by ${k.where === 'page' ? 'page' : 'place'}` : 'by date') : null;""",
        """  } }, order === 'page' ? `par ${k.where === 'page' ? 'page' : 'emplacement'}` : 'par date') : null;""")
    ctx("""      text: (n ? `It has ${plural(n, 'quote')}. This cannot be undone.` : 'This cannot be undone.') + kept,""",
        """      text: (n ? `Elle contient ${plural(n, 'quote')}. C’est définitif.` : 'C’est définitif.') + kept,""")
    ctx("""    const kept = notes.length ? ` Your ${plural(notes.length, 'note')} on it ${notes.length === 1 ? 'is' : 'are'} kept.` : '';""",
        """    const kept = notes.length ? (notes.length === 1 ? ' Votre note sur elle est gardée.' : ` Vos ${plural(notes.length, 'note')} sur elle sont gardées.`) : '';""")
    ctx("""        { label: n ? `Delete it and its ${plural(n, 'quote')}` : 'Delete it', value: 'all', danger: true },""",
        """        { label: n ? `La supprimer avec ses ${plural(n, 'quote')}` : 'La supprimer', value: 'all', danger: true },""")
    ctx("""      h('span', { class: 'grow', text: chosen.size ? `${chosen.size} selected` : 'Tap the quotes to delete' }),""",
        """      h('span', { class: 'grow', text: chosen.size ? `${chosen.size} sélectionnée${chosen.size > 1 ? 's' : ''}` : 'Touchez les citations à supprimer' }),""")
    ctx("""        try { await deleteEntries([...chosen]); toast(`${plural(n, 'quote')} deleted`); render(); } catch (err) { toast(err.message); }""",
        """        try { await deleteEntries([...chosen]); toast(`${plural(n, 'quote')} supprimée${n > 1 ? 's' : ''}`); render(); } catch (err) { toast(err.message); }""")
    ctx("""        toast(`${plural(n, 'quote')} deleted`);""", """        toast(`${plural(n, 'quote')} supprimée${n > 1 ? 's' : ''}`);""")
    ctx("""const SECTION_TITLES = { works: 'Works', translated: 'Translations', said: 'Said', quoted: 'Quoted elsewhere' };""",
        """const SECTION_TITLES = { works: 'Œuvres', translated: 'Traductions', said: 'Paroles', quoted: 'Cité ailleurs' };""")
    ctx("""    p.said ? `said ${p.said}` : null, p.quoted_in""", """    p.said ? `${p.said} parole${p.said > 1 ? 's' : ''}` : null, p.quoted_in""")
    ctx("""kinds.length > 1 ? filterRow([['', 'all'], ...kinds.map((m) => [m, `${m === 'said' ? 'said' : KINDS[m].several} ${media[m]}`])], '',""",
        """kinds.length > 1 ? filterRow([['', 'tout'], ...kinds.map((m) => [m, `${m === 'said' ? 'paroles' : KINDS[m].several} ${media[m]}`])], '',""")
    ctx("""segmented('Group quotes by', [['person', 'person'], ['source', 'source'], ['date', 'date']], by,""",
        """segmented('Grouper les citations par', [['person', 'personne'], ['source', 'source'], ['date', 'date']], by,""")
    ctx("""const pair = (label, which) => h('span', { class: 'nudge' }, label,
    h('button', { type: 'button', 'aria-label': `Move the ${which} one word back`, onclick: () => sel.nudge(which, -1) }, icon('left')),
    h('button', { type: 'button', 'aria-label': `Move the ${which} one word on`, onclick: () => sel.nudge(which, 1) }, icon('right')));
  return h('div', { class: 'nudges' }, pair('start', 'start'), pair('end', 'end'));""",
        """const pair = (label, which) => h('span', { class: 'nudge' }, label,
    h('button', { type: 'button', 'aria-label': `Reculer ${which === 'start' ? 'le début' : 'la fin'} d’un mot`, onclick: () => sel.nudge(which, -1) }, icon('left')),
    h('button', { type: 'button', 'aria-label': `Avancer ${which === 'start' ? 'le début' : 'la fin'} d’un mot`, onclick: () => sel.nudge(which, 1) }, icon('right')));
  return h('div', { class: 'nudges' }, pair('début', 'start'), pair('fin', 'end'));""")
    ctx("text: 'continue' })),", "text: 'reprendre' })),")
    ctx("text: 'something new' })),", "text: 'nouveau' })),", 2)
    ctx("          state.textContent = 'sent';", "          state.textContent = 'envoyée';")
    ctx("""          counter.textContent = `${plural(count, 'page')} sent. They are read on the server; sort them from the inbox.`;""",
        fr("""          counter.textContent = `${plural(count, 'page')} envoyée${count > 1 ? 's' : ''}. Elles sont lues sur le serveur ; triez-les depuis « À trier ».`;"""))
    ctx("            p.entry_count ? plural(p.entry_count, 'quote') + ' saved' : null,",
        "            p.entry_count ? `${plural(p.entry_count, 'quote')} enregistrée${p.entry_count > 1 ? 's' : ''}` : null,")
    ctx("  const isbn = field('s-isbn', 'isbn',", "  const isbn = field('s-isbn', 'isbn',")
    ctx("  const url = field('s-url', 'link',", "  const url = field('s-url', 'lien',")
    ctx("  const title = field('s-title', 'title',", "  const title = field('s-title', 'titre',")
    ctx("  const subtitle = field('s-subtitle', 'subtitle',", "  const subtitle = field('s-subtitle', 'sous-titre',")
    ctx("  const fieldIn = field('s-field', 'kind of work',", "  const fieldIn = field('s-field', 'genre',")
    ctx("  const publisher = field('s-publisher', 'publisher',", "  const publisher = field('s-publisher', 'éditeur',")
    ctx("  const edition = field('s-edition', 'edition',", "  const edition = field('s-edition', 'édition',")
    ctx("  const year = field('s-year', 'year',", "  const year = field('s-year', 'année',")
    ctx("    const title = field('l-title', 'title',", "    const title = field('l-title', 'titre',")
    ctx("  const name = field('t-name', 'name',", "  const name = field('t-name', 'nom',")
    ctx("topicsInput('topics',", "topicsInput('thèmes',", 3)
    ctx("h('span', { class: 'label', text: kind === 'video' || kind === 'podcast' ? 'picture' : 'cover' }),",
        "h('span', { class: 'label', text: kind === 'video' || kind === 'podcast' ? 'image' : 'couverture' }),")
    ctx("h('option', { value: 'fr' }, 'French'), h('option', { value: 'en' }, 'English'), h('option', { value: 'other' }, 'Other'));",
        "h('option', { value: 'fr' }, 'Français'), h('option', { value: 'en' }, 'Anglais'), h('option', { value: 'other' }, 'Autre'));")
    ctx("        ['Before upgrades', upgrades.length ? upgrades.map((c) => c.file).join(', ') : 'none'],",
        "        ['Avant les mises à jour', upgrades.length ? upgrades.map((c) => c.file).join(', ') : 'aucune'],")
    for label, fr_label, key in (("Page straightening", "Redressement des pages", "straighten_pages"),
                                 ("Barcode reader", "Lecteur de code-barres", "barcode_reader"),
                                 ("Online lookups", "Recherches en ligne", "lookups_enabled")):
        ctx(f"        ['{label}', health.{key} ? 'on' : 'off'],", f"        ['{fr_label}', health.{key} ? 'activé' : 'désactivé'],")
    ctx("  const aboutIn = peopleInput('about', about || entry?.about", "  const aboutIn = peopleInput('sur', about || entry?.about")
    ctx("h('span', { text: 'password' }), pw),", "h('span', { text: 'mot de passe' }), pw),")
    ctx("? `Sur ${surname(p)}`", "? `Sur ${surname(p)}`", 0)   # (made by the literal pass below)

    ctx("h('div', { class: 'chips' }, h('span', { class: 'label', text: 'people' }),",
        "h('div', { class: 'chips' }, h('span', { class: 'label', text: 'personnes' }),")
    ctx("h('span', { style: { flex: 1 }, text: 'recent' })),", "h('span', { style: { flex: 1 }, text: 'récents' })),")
    ctx("[['article', 'Article'], ['video', 'Video'], ['podcast', 'Podcast']]", "[['article', 'Article'], ['video', 'Vidéo'], ['podcast', 'Podcast']]")
    ctx("h('span', { class: 'label', text: 'on ' }), personLinks(n.people))", "h('span', { class: 'label', text: 'sur ' }), personLinks(n.people))")

    # Settings: sending from other apps, in French
    a = s.index("      h('h2', { class: 'section-title', text: 'Sending from other apps' }),")
    b = s.index("      h('h2', { class: 'section-title', text: 'App' }),")
    s = s[:a] + fr("""      h('h2', { class: 'section-title', text: 'Envoyer depuis d’autres apps' }),
      way('computer', 'Sur un ordinateur : un favori', [
        h('p', {}, 'Faites glisser ce bouton dans votre barre de favoris, une fois. Ensuite, sélectionnez du texte sur n’importe quelle page et cliquez sur le favori : la page s’ouvre ici, avec le passage, son lien et son titre déjà remplis.'),
        h('a', { class: 'btn small bookmarklet', href: bookmarklet(), onclick: (ev) => { ev.preventDefault(); toast('Faites-le glisser dans la barre des favoris'); } }, '→ Marginote')]),
      way('iphone', 'Sur l’iPhone : « Marginote » dans le menu Partager de toutes les apps', [
        h('p', {}, 'Un raccourci, créé une fois dans l’app Raccourcis. Ensuite, sélectionnez du texte dans n’importe quelle app (Safari, Notes, Mail, Livres, un PDF…), touchez Partager, puis Marginote : l’app s’ouvre avec le passage et vous demande d’où il vient. Un lien partagé seul (YouTube, Podcasts, un article) ouvre ici son formulaire.'),
        steps([
          'Dans Raccourcis, touchez + (en haut à droite). Touchez le nom en haut, « Renommer », et tapez Marginote.',
          'Touchez ⓘ (en bas, ou dans le menu sous le nom) et activez « Dans la feuille de partage » (« Afficher dans la feuille de partage » sur les iPhone plus anciens), puis OK. Une première ligne apparaît : « Recevoir … ». Touchez le mot bleu après « Recevoir », touchez « Effacer », cochez seulement « Texte » et « URL », puis OK.',
          'Ajoutez l’action « Texte » (champ de recherche en bas). Touchez l’intérieur de son cadre, puis « Entrée du raccourci » dans la barre au-dessus du clavier.',
          'Ajoutez l’action qui encode le texte pour une adresse : cherchez « encod » et choisissez « Encoder l’URL » (le nom peut varier un peu). Elle prend toute seule le Texte du dessus ; laissez-la sur « Encoder ».',
          'Ajoutez l’action « URL ». Collez l’adresse ci-dessous dans son cadre puis, juste après, sans espace, touchez le résultat de l’étape d’encodage dans la barre au-dessus du clavier.',
          'Ajoutez l’action « Ouvrir les URL », puis OK (en haut à droite).',
        ]),
        h('pre', { class: 'code', text: shareAddress() }),
        copyBtn(shareAddress(), 'Copier l’adresse'),
        h('p', { class: 'note-line', text: 'C’est bon quand : dans Notes, vous sélectionnez une phrase, touchez Partager (derrière › dans le petit menu si besoin), faites défiler jusqu’à Marginote, et l’app s’ouvre sur « D’où vient ce passage ? » avec votre phrase. La première fois, iOS demande si le raccourci peut ouvrir l’adresse : Autoriser.' }),
        h('p', { class: 'note-line', text: 'Il s’ouvre dans Safari : connectez-vous-y une fois (l’app de l’écran d’accueil garde sa propre connexion), avec Tailscale activé. Pour avoir Marginote en haut du menu Partager : « Modifier les actions… » tout en bas, puis ajoutez-le aux Favoris.' }),
        h('p', { class: 'note-line', text: 'Une app sans Partager dans son menu (Kindle) : copiez le passage, puis ici, Ajouter › Coller ce que vous avez copié.' })]),
      way('android', 'Sur Android (Samsung et autres) : « Marginote » dans le menu Partager', [
        h('p', {}, 'Rien à créer : une fois l’app installée depuis Chrome, Android l’ajoute au menu Partager. Ensuite, sélectionnez du texte dans n’importe quelle app (Chrome, Samsung Notes, Gmail, un PDF…), touchez Partager, puis Marginote : l’app s’ouvre avec le passage et vous demande d’où il vient. Un lien partagé seul (YouTube, un article) ouvre ici son formulaire.'),
        steps([
          'Activez Tailscale, puis ouvrez cette adresse dans Chrome (le navigateur de Google, pas Samsung Internet) et connectez-vous.',
          'Dans Chrome, touchez ⋮ (en haut à droite), puis « Installer l’application ». Si vous ne voyez que « Ajouter à l’écran d’accueil », touchez-le, puis « Installer ».',
          'Confirmez. Marginote apparaît parmi vos applications, avec sa propre icône.',
        ]),
        h('pre', { class: 'code', text: location.origin }),
        copyBtn(location.origin, 'Copier l’adresse'),
        h('p', { class: 'note-line', text: 'C’est bon quand : dans Samsung Notes, vous sélectionnez une phrase, touchez Partager, et Marginote est dans la liste (parfois sous « Plus », ou au bout d’une minute) ; le toucher ouvre l’app sur « D’où vient ce passage ? » avec votre phrase.' }),
        h('p', { class: 'note-line', text: 'L’app installée et Chrome partagent la même connexion : connectez-vous une fois. Si l’icône sur l’écran d’accueil porte un petit logo Chrome dans un coin, Chrome a créé un simple raccourci au lieu d’installer l’app, et un raccourci n’est pas dans le menu Partager : supprimez-le, puis installez à nouveau depuis ⋮.' }),
        h('p', { class: 'note-line', text: 'Une app qui ne partage qu’un lien vers le livre (Kindle) : copiez plutôt le passage, puis ici, Ajouter › Coller ce que vous avez copié.' })]),
""") + s[b:]

    ctx("    put(kindsBox, kinds.length > 1 ? filterRow([['', 'all'], ...kinds.map((k) => [k, `${KINDS[k].several} ${present[k]}`])], st.kind,",
        "    put(kindsBox, kinds.length > 1 ? filterRow([['', 'tout'], ...kinds.map((k) => [k, `${KINDS[k].several} ${present[k]}`])], st.kind,")

    # ---------- plain texts: replaced wherever they appear as a whole string ----------
    L = {
        "Cannot reach your server. Is Tailscale on?": "Impossible de joindre votre serveur. Tailscale est-il activé ?",
        "Please log in": "Veuillez vous connecter",
        "Something went wrong (${res.status})": "Un problème est survenu (${res.status})",
        "Cancel": "Annuler",
        " and ": " et ",
        "${surname(e.words_by)}, quoted": "${surname(e.words_by)}, cité",
        "about ": "sur ",
        "Try again": "Réessayer",
        "${rest.length} more ›": "${rest.length} de plus ›",
        "add": "ajouter",
        "+ ${newLabel} “${input.value.trim()}”": "+ ${newLabel} « ${input.value.trim()} »",
        "Remove ${i.label}": "Retirer ${i.label}",
        "type a name": "tapez un nom",
        "new person": "nouvelle personne",
        "find a source": "chercher une source",
        "new topic": "nouveau thème",
        "add a topic": "ajouter un thème",
        "Quote or note": "Citation ou note",
        "Quote": "Citation",
        "Log in": "Se connecter",
        "People": "Personnes",
        "Topics": "Thèmes",
        "Search the library": "Chercher dans la bibliothèque",
        "Order": "Ordre",
        "Nothing here yet.": "Rien ici pour l’instant.",
        "Capture something": "Ajouter quelque chose",
        "Nothing matches.": "Aucun résultat.",
        "quoted in ${p.quoted_in}": "cité dans ${p.quoted_in}",
        "written about in ${p.about_in}": "sujet de ${p.about_in}",
        "People appear here as you add sources and say who they are about.": "Les personnes apparaissent ici quand vous ajoutez des sources et dites de qui elles parlent.",
        "Nobody matches.": "Personne ne correspond.",
        "Topics appear here as you add them to quotes, sources and notes.": "Les thèmes apparaissent ici quand vous les ajoutez aux citations, aux sources et aux notes.",
        "No topic matches.": "Aucun thème ne correspond.",
        "Show the library by": "Afficher la bibliothèque par",
        "Library": "Bibliothèque",
        "Quotes containing “${q.value.trim()}” ›": "Citations contenant « ${q.value.trim()} » ›",
        "Notes containing “${q.value.trim()}” ›": "Notes contenant « ${q.value.trim()} » ›",
        "Settings": "Réglages",
        "Add a source": "Ajouter une source",
        "inbox · ${plural(inbox.length, 'page')} to sort": "à trier · ${plural(inbox.length, 'page')}",
        "Show this part": "Afficher cette partie",
        "Hide this part": "Masquer cette partie",
        "Search here": "Chercher ici",
        "Search in this source": "Chercher dans cette source",
        "None": "Aucune",
        "All": "Toutes",
        "Delete ${plural(n, 'quote')}?": "Supprimer ${plural(n, 'quote')} ?",
        "This cannot be undone.": "C’est définitif.",
        "Delete ${plural(n, 'quote')}": "Supprimer ${plural(n, 'quote')}",
        "Delete": "Supprimer",
        "Done": "Terminé",
        "Select": "Sélectionner",
        "Your notes": "Vos notes",
        "Quotes": "Citations",
        "Nothing captured from it yet.": "Rien d’ajouté pour l’instant.",
        "+ Capture": "+ Ajouter",
        "Delete “${source.title}”?": "Supprimer « ${source.title} » ?",
        "Delete only its ${plural(n, 'quote')}": "Supprimer seulement ses ${plural(n, 'quote')}",
        "Deleted": "Supprimée",
        "translated by ": "traduit par ",
        "Export": "Exporter",
        "Edit": "Modifier",
        "also on ${also.join(', ')}": "aussi sur ${also.join(', ')}",
        "About ${surname(p)}": "Sur ${surname(p)}",
        "Nothing about this person yet.": "Rien sur cette personne pour l’instant.",
        "No notes on them yet.": "Pas encore de note sur cette personne.",
        "quoted in ${plural(p.quoted_in, 'source')}": "cité dans ${plural(p.quoted_in, 'source')}",
        "Also written: ${p.aliases.join(', ')}": "Aussi écrit : ${p.aliases.join(', ')}",
        "+ Words ${surname(p)} said": "+ Paroles de ${surname(p)}",
        "+ Capture about ${surname(p)}": "+ Ajouter sur ${surname(p)}",
        "No author": "Sans auteur",
        "Said, no source": "Paroles, sans source",
        "often with": "souvent avec",
        "group by": "grouper par",
        "No quote on this topic yet.": "Pas encore de citation sur ce thème.",
        "Search words, people, topics": "Chercher des mots, des personnes, des thèmes",
        "Search quotes": "Chercher dans les citations",
        "From": "Provenance",
        "from everything": "de partout",
        "from ${v.several}": "des ${v.several}",
        "said, no source": "paroles, sans source",
        "No quotes yet.": "Pas encore de citation.",
        "Show more": "Afficher plus",
        "${e.words_by.name}, quoted in ": "${e.words_by.name}, cité dans ",
        "Delete this quote?": "Supprimer cette citation ?",
        "Delete the quote": "Supprimer la citation",
        "Quote deleted": "Citation supprimée",
        "Copied with its reference": "Copiée avec sa référence",
        "Copying is not allowed here": "Copier n’est pas permis ici",
        "said by ": "paroles de ",
        "words of ": "paroles de ",
        ", quoted by ${makers(source).map((p) => p.name).join(', ') || 'the source'}": ", cité par ${makers(source).map((p) => p.name).join(', ') || 'la source'}",
        "Comment.": "Commentaire.",
        "in your notes ": "dans vos notes ",
        "Copy": "Copier",
        "Delete…": "Supprimer…",
        "none: words someone said": "aucune : paroles de quelqu’un",
        "who it is about": "de qui il s’agit",
        "your comment": "votre commentaire",
        "said by": "dit par",
        "words of (when not the author’s)": "paroles de (si ce n’est pas l’auteur)",
        "who said it": "qui l’a dit",
        "a quote within the quote": "une citation dans la citation",
        "where, when": "où, quand",
        "where": "où",
        "Say who said it: with no source, a quote needs a person.": "Dites qui l’a dit : sans source, une citation a besoin d’une personne.",
        "Saved": "Enregistré",
        "Save": "Enregistrer",
        "Change the selection on the photo": "Changer la sélection sur la photo",
        "Use this selection": "Utiliser cette sélection",
        "Tap the first word, then the last.": "Touchez le premier mot, puis le dernier.",
        "Use this selection?": "Utiliser cette sélection ?",
        "The saved text is replaced by the words selected on the photo.": "Le texte enregistré est remplacé par les mots sélectionnés sur la photo.",
        "Replace the text": "Remplacer le texte",
        "Selection saved": "Sélection enregistrée",
        "Large text": "Grand texte",
        "Zoom in": "Agrandir",
        "Zoom out": "Réduire",
        "Select on": "Sélectionner sur",
        "Photo of the page": "Photo de la page",
        "Drag to move the start": "Glisser pour déplacer le début",
        "Drag to move the end": "Glisser pour déplacer la fin",
        "Change": "Changer",
        "Capture": "Ajouter",
        "Back": "Retour",
        "Nothing to keep in what was shared.": "Rien à garder dans ce qui a été partagé.",
        "What are you reading or watching?": "Que lisez-vous ou regardez-vous ?",
        "About ${aboutPreset[0].name}.": "Sur ${aboutPreset[0].name}.",
        "On ${topicPreset[0]}.": "Thème : ${topicPreset[0]}.",
        "Paste what you copied": "Coller ce que vous avez copié",
        "Something else from the library ›": "Autre chose de la bibliothèque ›",
        "Book or ebook": "Livre ou livre numérique",
        "Photo of a page or a screenshot; the book from its ISBN or back cover": "Photo d’une page ou capture d’écran ; le livre par son ISBN ou son dos",
        "Link": "Lien",
        "Article, video or podcast: paste the link, or share it from the app": "Article, vidéo ou podcast : collez le lien, ou partagez-le depuis l’app",
        "Class": "Cours",
        "A course you take: notes for each session, and quotes": "Un cours que vous suivez : des notes par séance, et des citations",
        "Something else": "Autre chose",
        "A talk, a film: type its title and who gave it": "Une conférence, un film : son titre et qui l’a donné",
        "Words someone said": "Paroles de quelqu’un",
        "Heard or read, with no source to point to": "Entendues ou lues, sans source précise",
        "Your own thoughts on a person, a topic or a source": "Vos propres réflexions sur une personne, un thème ou une source",
        "Photos to sort later": "Photos à trier plus tard",
        "Find a source": "Chercher une source",
        "+ New source": "+ Nouvelle source",
        "Take a photo": "Prendre une photo",
        "Choose a photo": "Choisir une photo",
        "or drop a photo or a screenshot here": "ou déposez ici une photo ou une capture d’écran",
        "Write a note": "Écrire une note",
        "Choose a screenshot": "Choisir une capture d’écran",
        "Choose a photo or a screenshot": "Choisir une photo ou une capture d’écran",
        "Several pages, sort later": "Plusieurs pages, à trier plus tard",
        "Type a quote": "Taper une citation",
        "sending…": "envoi…",
        "Choose photos": "Choisir des photos",
        "Sort later": "À trier plus tard",
        "You choose the source of each page when you sort it.": "Vous choisirez la source de chaque page en la triant.",
        "Paste a passage or a link.": "Collez un passage ou un lien.",
        "Paste": "Coller",
        "a passage, a link, or both": "un passage, un lien, ou les deux",
        "Touch the box, then Paste.": "Touchez la case, puis Coller.",
        "Click the box and paste (Ctrl+V).": "Cliquez dans la case et collez (Ctrl+V).",
        "Next": "Suivant",
        "Shared": "Partagé",
        "Where is it from?": "D’où vient ce passage ?",
        "named with the passage": "nommé avec le passage",
        "New ebook: ${b.title}": "Nouveau livre numérique : ${b.title}",
        "From Apple Books": "Depuis Apple Books",
        "A web page, a video or a podcast": "Une page web, une vidéo ou un podcast",
        "Paste its link; the passage is kept with it": "Collez son lien ; le passage y est rattaché",
        "A book, a talk, anything else": "Un livre, une conférence, autre chose",
        "Type its title and who wrote it": "Son titre et qui l’a écrit",
        "Someone said it": "Quelqu’un l’a dit",
        "Who said it, with no source to point to": "Qui l’a dit, sans source précise",
        "Your own note": "Votre propre note",
        "Keep it as a note on a person, a topic or a source": "La garder comme note sur une personne, un thème ou une source",
        "The words are empty": "Les paroles sont vides",
        "Say who said it": "Dites qui l’a dit",
        "what was said": "ce qui a été dit",
        "Reading the page…": "Lecture de la page…",
        "No text found on this photo. Take it again, closer.": "Aucun texte trouvé sur cette photo. Reprenez-la, de plus près.",
        "Next · ${plural(r.end - r.start + 1, 'word')}": "Suivant · ${plural(r.end - r.start + 1, 'word')}",
        "Inbox": "À trier",
        "Retake": "Reprendre",
        "Type": "Taper",
        "Note saved": "Note enregistrée",
        "The text is empty": "Le texte est vide",
        "Another from this page": "Une autre de cette page",
        "Paste or type a link": "Collez ou tapez un lien",
        "link to the article, video or podcast": "lien vers l’article, la vidéo ou le podcast",
        "Pasting is not allowed here: long-press the field and choose Paste.": "Coller n’est pas permis ici : appuyez longuement dans le champ et choisissez Coller.",
        "this new source": "cette nouvelle source",
        "Give it a title": "Donnez-lui un titre",
        "In your library": "Dans votre bibliothèque",
        "New source": "Nouvelle source",
        "${note}. Type the details in.": "${note}. Saisissez les détails.",
        "${f.note}. Type the details in.": "${f.note}. Saisissez les détails.",
        "Kind of source": "Type de source",
        "This page is still being read": "Cette page est encore en cours de lecture",
        "Remove this page?": "Retirer cette page ?",
        "No quote was saved from it. The photo is deleted.": "Aucune citation n’en a été tirée. La photo est supprimée.",
        "Remove the photo": "Supprimer la photo",
        "pages to sort": "pages à trier",
        "No source yet": "Pas encore de source",
        "being read…": "en cours de lecture…",
        "could not be read": "illisible",
        "Sort": "Trier",
        "Remove…": "Retirer…",
        "Nothing to sort.": "Rien à trier.",
        "author(s)": "auteur(s)",
        "translator(s)": "traducteur(s)",
        "editor(s)": "sous la direction de",
        "about (people)": "sur (personnes)",
        "language": "langue",
        " Already in your library: ": " Déjà dans votre bibliothèque : ",
        "${prefix}Looking up…": "${prefix}Recherche…",
        "${prefix}Found on ${f.source}.": "${prefix}Trouvé sur ${f.source}.",
        "Details read from the page.": "Détails lus sur la page.",
        "Photo of the back cover": "Photo du dos du livre",
        "Reading the barcode…": "Lecture du code-barres…",
        "Barcode read. ": "Code-barres lu. ",
        "ISBN read. ": "ISBN lu. ",
        "Look up": "Chercher",
        "Back cover": "Dos du livre",
        "Read the page": "Lire la page",
        "The year must be a number": "L’année doit être un nombre",
        "Use my own picture": "Utiliser ma propre image",
        "Sending…": "Envoi…",
        "Picture saved.": "Image enregistrée.",
        "Looking online…": "Recherche en ligne…",
        "Found.": "Trouvée.",
        "Find online": "Chercher en ligne",
        "Use my picture": "Utiliser mon image",
        "Add it": "Ajouter",
        "name, as usually written": "nom, tel qu’on l’écrit",
        "in an index": "dans un index",
        "Choose who this is": "Choisissez de qui il s’agit",
        "The same person?": "La même personne ?",
        "${p.name} and ${other.name} become one. Which name stays? The other is kept as another spelling.":
            "${p.name} et ${other.name} ne font plus qu’un. Quel nom garder ? L’autre reste comme autre graphie.",
        "Merged": "Fusionnées",
        "Remove ${p.name}?": "Retirer ${p.name} ?",
        "They are taken off every source, quote and note. Those stay.": "Cette personne est retirée de chaque source, citation et note, qui restent.",
        "Remove this person": "Retirer cette personne",
        "Edit person": "Modifier la personne",
        "other spellings, one per line": "autres graphies, une par ligne",
        "the same person as": "la même personne que",
        "Merge…": "Fusionner…",
        "Remove this person…": "Retirer cette personne…",
        "Merged into ${t.name}": "Fusionné avec ${t.name}",
        "Remove the topic ${data.topic.name}?": "Retirer le thème ${data.topic.name} ?",
        "It is taken off every quote, source and note. Those stay.": "Il est retiré de chaque citation, source et note, qui restent.",
        "Remove the topic": "Retirer le thème",
        "Edit topic": "Modifier le thème",
        "Giving it the name of another topic merges the two.": "Lui donner le nom d’un autre thème fusionne les deux.",
        "Remove this topic…": "Retirer ce thème…",
        "Search your notes": "Chercher dans vos notes",
        "No note contains these words.": "Aucune note ne contient ces mots.",
        "Your own writing goes here: on a book, a video, a class, a person or a topic.":
            "Vos propres écrits viennent ici : sur un livre, une vidéo, un cours, une personne ou un thème.",
        "note · most recent first": "note · les plus récentes d’abord",
        "Delete this note?": "Supprimer cette note ?",
        "Delete the note": "Supprimer la note",
        "Note deleted": "Note supprimée",
        "changed ${fullDate(n.updated_at)}": "modifiée le ${fullDate(n.updated_at)}",
        "refers to": "renvoie à",
        "New note": "Nouvelle note",
        "title, if you want one": "titre, si vous voulez",
        "on (a book, a video, a class…)": "sur (un livre, une vidéo, un cours…)",
        "where in it (page, chapter, session)": "où dedans (page, chapitre, séance)",
        "Words of the quote, its source, a person": "Mots de la citation, sa source, une personne",
        "Find a quote": "Chercher une citation",
        "Remove this reference": "Retirer ce renvoi",
        "The note is empty": "La note est vide",
        "Edit note": "Modifier la note",
        "refers to (optional)": "renvoie à (facultatif)",
        "+ Link a quote": "+ Lier une citation",
        "Shown on the page of each source, person and topic it is on.": "Affichée sur la page de chaque source, personne et thème concernés.",
        "Copied": "Copié",
        "Copying is not allowed here: select the text and copy it": "Copier n’est pas permis ici : sélectionnez le texte et copiez-le",
        "Backups": "Sauvegardes",
        "Last copy": "Dernière copie",
        "none yet": "aucune pour l’instant",
        "Copies kept": "Copies gardées",
        "${daily.length}: the last ${backups.kept} days, and the first of each of the last ${backups.monthly} months":
            "${daily.length} : les ${backups.kept} derniers jours, et la première de chacun des ${backups.monthly} derniers mois",
        "Next copy": "Prochaine copie",
        "Copies of the database are zips in ${folder}/backups on the NAS. Photos and covers are plain files: your NAS snapshots keep them.":
            "Les copies de la base sont des zips dans ${folder}/backups sur le NAS. Photos et couvertures sont des fichiers ordinaires : les instantanés de votre NAS les gardent.",
        # accounts and language
        "your name": "votre nom",
        "Account": "Compte",
        "Rename": "Renommer",
        "Language": "Langue",
        "Your library is yours alone: nobody else can see it, not even the owner.":
            "Votre bibliothèque n’est qu’à vous : personne d’autre ne peut la voir, pas même le propriétaire.",
        "Your password is MARGINOTE_PASSWORD, in the compose file: change it there, then redeploy.":
            "Votre mot de passe est MARGINOTE_PASSWORD, dans le fichier compose : changez-le là, puis redéployez.",
        "Change your password": "Changer votre mot de passe",
        "current password": "mot de passe actuel",
        "new password (8 characters at least)": "nouveau mot de passe (8 caractères au moins)",
        "Change the password": "Changer le mot de passe",
        "Password changed": "Mot de passe changé",
        "${a.name} can log in now": "${a.name} peut maintenant se connecter",
        "since ${fullDate(a.created_at)}": "depuis le ${fullDate(a.created_at)}",
        "New password set: they are logged out everywhere": "Nouveau mot de passe enregistré : la personne est déconnectée partout",
        "New password…": "Nouveau mot de passe…",
        "Remove ${a.name}?": "Retirer ${a.name} ?",
        "They can no longer log in. Their library is kept on the NAS, in data/users/removed.":
            "Cette personne ne peut plus se connecter. Sa bibliothèque est gardée sur le NAS, dans data/users/removed.",
        "Remove the account": "Retirer le compte",
        "Account removed": "Compte retiré",
        "People with access": "Personnes ayant accès",
        "Each person has their own library. Nobody, not even you, can read or change another person’s quotes, notes or photos in the app.":
            "Chaque personne a sa propre bibliothèque. Personne, pas même vous, ne peut lire ni modifier dans l’app les citations, notes ou photos d’une autre.",
        "Add someone": "Ajouter quelqu’un",
        "their name": "son nom",
        "password (8 characters at least)": "mot de passe (8 caractères au moins)",
        "Add": "Ajouter",
        "Copy made": "Copie faite",
        "Back up now": "Sauvegarder maintenant",
        "Download everything (.zip)": "Tout télécharger (.zip)",
        "Space used": "Espace utilisé",
        "Database": "Base de données",
        "Page photos": "Photos de pages",
        "Covers and pictures": "Couvertures et images",
        "App": "Application",
        "Text recognition": "Reconnaissance du texte",
        "missing": "absente",
        "Log out": "Se déconnecter",
        "Main": "Principal",
        # export
        "Your quotes and notes in a PDF or Word file, by author, by topic or by source, with a table of contents you can tap.":
            "Vos citations et notes dans un fichier PDF ou Word, classées par auteur, par thème ou par source, avec un sommaire cliquable.",
        "Export…": "Exporter…",
        "All authors": "Tous les auteurs",
        "All topics": "Tous les thèmes",
        "All sources": "Toutes les sources",
        "Search an author": "Chercher un auteur",
        "Search a topic": "Chercher un thème",
        "Search a source": "Chercher une source",
        "No author has quotes or notes yet.": "Aucun auteur n’a encore de citations ni de notes.",
        "No topic has quotes or notes yet.": "Aucun thème n’a encore de citations ni de notes.",
        "No source has quotes or notes yet.": "Aucune source n’a encore de citations ni de notes.",
        "${n} of ${total}": "${n} sur ${total}",
        "Said, with no source": "Paroles sans source",
        "what people said · ${plural(choices.said, 'quote')}": "ce que des personnes ont dit · ${plural(choices.said, 'quote')}",
        "Choose at least one.": "Choisissez-en au moins un.",
        "Choose quotes, notes, or both.": "Choisissez les citations, les notes, ou les deux.",
        "Download the PDF": "Télécharger le PDF",
        "Download the Word file": "Télécharger le fichier Word",
        "Preparing…": "Préparation…",
        "Open the PDF": "Ouvrir le PDF",
        "Open the Word file": "Ouvrir le fichier Word",
        "Ready (${size(made.size)}) · ": "Prêt (${size(made.size)}) · ",
        "Download again": "Télécharger à nouveau",
        "Opens in Safari, where you can share it or save it to Files.":
            "S’ouvre dans Safari, où vous pouvez le partager ou l’enregistrer dans Fichiers.",
        "Your quotes and notes, gathered in one file.": "Vos citations et notes, rassemblées en un fichier.",
        "Organise by": "Classer par",
        "Choose": "Choisir",
        "Content": "Contenu",
        "Authors": "Auteurs",
        "with your comments": "avec vos commentaires",
        "Bibliography at the end": "Bibliographie à la fin",
    }
    pat = re.compile(r"'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`")
    used = {k: 0 for k in L}


    def swap(m):
        t = m.group(1) if m.group(1) is not None else m.group(2)
        if t in L:
            used[t] += 1
            new = fr(L[t])
            q = "'" if m.group(1) is not None else "`"
            if q == "'" and "'" in new:
                new = new.replace("'", "\\'")
            return q + new + q
        return m.group(0)


    s = pat.sub(swap, s)

    unused = [k for k, v in used.items() if v == 0]
    return s, missing, unused


def main() -> int:
    english = (STATIC / "app.js").read_text(encoding="utf-8")
    french, missing, unused = translate(english)
    (STATIC / "app.fr.js").write_text(french, encoding="utf-8")
    for line in missing:
        print("NOT FOUND", line)
    for key in unused:
        print("unused", key)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
