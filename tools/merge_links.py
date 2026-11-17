#!/usr/bin/env python3
"""Scala linki do filmów w literał VLINKS w arabeska.html.

Użycie:
    python tools/merge_links.py [--html arabeska.html] [--dry-run] PLIK.json [PLIK.json ...]

Przyjmowane pliki JSON:
  * gotowy kształt VLINKS: {"ex":{id:[V]}, "plan":{id:[V]}, "step":{id:[V]}}
  * wyniki wyszukiwania YouTube: {"areas":{...}, "exercises":{...}, "dead_existing":[id, ...]}
  * wyniki z dance-masterclass.com: {"areas":{...}, "full_classes":[...], "stretching_conditioning":[...]}

V = {src:'yt'|'dmc', url, title, author, min, lang, note?, kind:'tut'|'follow'|'class', ph?:[0,1,2]}

Kolejność scalania: obecny literał VLINKS (baza), potem pliki w podanej kolejności, na końcu
jednorazowo dawne STEP_VIDS i VIDEOS, jeśli jeszcze są w pliku HTML. Duplikaty (ten sam url
w tej samej liście) są pomijane, wygrywa pierwszy. Nieznane id (spoza EX / PROG / STEPS) i linki,
które nie przechodzą walidacji, są wypisywane i pomijane; skrypt nigdy nie przerywa budowania.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START, END = '/*VLINKS-START*/', '/*VLINKS-END*/'
YT_RE = re.compile(r'^https://(www\.)?(youtube\.com/watch\?v=|youtu\.be/)')
DMC_RE = re.compile(r'^https://(www\.)?dance-masterclass\.com/')
YT_ID_RE = re.compile(r'(?:v=|youtu\.be/)([\w-]{11})')

# obszary z plików wyszukiwania -> id planów w PROG
AREA_PLAN = {'split_front': 'split', 'split_middle': 'middle', 'backbend': 'back',
             'feet_strength': 'feet', 'pointe_work': 'pointe', 'pirouettes': 'turns'}
# ćwiczenia z wyszukiwania YouTube -> id w EX
EX_MAP = {
    'couch_stretch': ['f_couch'], 'oversplit_block': ['f_over_front', 'f_over_back'],
    'active_flex_leg_lifts': ['f_active'], 'cobra_sphinx': ['f_cobra'], 'bridge': ['b_bridge', 'b_bridge_walk'],
    'walkover_bridge_from_standing': ['b_dropback'], 'cambre_barre': ['b_cambre'], 'doming': ['ft_dome', 'ft_dome_stand'],
    'theraband_pointe': ['ft_band'], 'single_leg_releve': ['ft_rel1', 'ft_rel1_slow'], 'rises_on_pointe': ['ft_pointe'],
    'echappe_pointe': ['ft_echappe'], 'bourree_pointe': ['pt_bourree'], 'pique_pointe': ['pt_pique'],
    'spotting_drill': ['t_spot'], 'passe_balance': ['t_bal', 'pt_balance'], 'double_pirouette_tips': ['t_pir2'],
    'pirouette_en_dedans': ['tr_pir1_dd'],
}
# pełne lekcje DMC: tylko te, które pasują do planów (fragment url -> plany)
DMC_CLASS_MAP = {
    '/posts/2189227609': ['feet'],     # Sharp & Clean Footwork
    '/posts/2185978084': ['feet'],     # Ballet Barre – Advanced Footwork Focus
    '/posts/2183507906': ['split'],    # Ballet Barre for Increased Flexibility
    '/posts/2190657161': ['turns'],    # Balance and Full-Body Stability
    '/posts/2183507455': ['turns'],    # Center Exercises for More Balance
    '/posts/2183700952': ['middle'],   # Turnout (40 min)
    '/posts/2195892463': ['split'],    # Floor Barre: Mobility & Extensions
}
# programy rozciągania i kondycji DMC (fragment url -> plany)
DMC_STRETCH_MAP = {
    'flexibility-training-for-adults-over-30': ['split', 'middle'],
    'flexibility-for-higher-leg-extensions-anna-ol': ['split'],
    'workout-program-splits-stretch': ['split', 'middle'],
    'workout-program-hips-hamstrings-release': ['split'],
    'flexibility-training-inspired-by-yoga': ['split'],
    'healthy-hips-mobility-and-control': ['middle'],
    'healthy-spine-strong-core-safe-back': ['back'],
    'turnout-training-pilates-lab': ['middle'],
    'barre-method-for-a-pain-free-back': ['back'],
    'the-science-of-flexibility-dr-darcy-lei': ['split'],
}
# lekcje z niepewnym id kategorii: zamiast nich potwierdzony adres kursu
DMC_COURSE_FOR = {'2148040698': 'https://www.dance-masterclass.com/products/beginner-pointe-class-leonore-baulac'}


def yt_url(vid):
    return 'https://www.youtube.com/watch?v=' + vid


def yt_kind(k):
    return {'follow-along': 'follow', 'follow': 'follow', 'tutorial': 'tut', 'tut': 'tut', 'class': 'class'}.get(k, 'tut')


def dmc_kind(url, title):
    u = url.lower()
    if '/ballet-training' in u or 'ballet-classes' in u or 'fun-ballet-classes' in u or '/floor-barre' in u:
        return 'class'
    if 'workout-program' in u:
        return 'follow'
    if re.search(r'exercises|routine|workout', title, re.I):
        return 'follow'
    return 'tut'


def phases_for(plan, title, note=''):
    """Fazy planu, do których film pasuje (None = wszystkie)."""
    t = (title + ' ' + (note or '')).lower()
    if plan == 'split' and ('oversplit' in t or 'over split' in t):
        return [2]
    if plan == 'back' and 'from standing' in t:
        return [2]
    if plan == 'pointe' and ('advanced' in t or 'turns on pointe' in t or 'pirouettes on pointe' in t or 'solos' in t):
        return [2]
    if plan == 'turns' and 'fouett' in t:
        return [2]
    return None


def mk(src, url, title, author, minutes, lang, kind, note=None, ph=None):
    v = {'src': src, 'url': url, 'title': (title or '').strip(), 'author': (author or '').strip(),
         'min': minutes, 'lang': lang, 'kind': kind}
    if note:
        v['note'] = note.strip()
    if ph:
        v['ph'] = ph
    return v


# ---------- czytanie HTML ----------

def read_html(path):
    return open(path, encoding='utf-8', newline='').read()


def block(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i)]


def known_ids(src):
    ex = set(re.findall(r'^ (\w+):\{n:', block(src, 'const EX={', '\n};'), re.M))
    prog = set(re.findall(r'^ (\w+):\{n:', block(src, 'const PROG={', '\n};'), re.M))
    steps = set(re.findall(r"\{id:'(\w+)'", block(src, 'const STEPS=[', '\n];')))
    return {'ex': ex, 'plan': prog, 'step': steps}


def current_vlinks(src):
    i, j = src.index(START) + len(START), src.index(END)
    return json.loads(src[i:j])


def js_literal(text, consts):
    """Mały parser literałów JS (stringi '…' i "…", liczby, [], {}, klucze bez cudzysłowów, stałe)."""
    pos = 0

    def ws():
        nonlocal pos
        while pos < len(text) and text[pos] in ' \t\r\n':
            pos += 1

    def val():
        nonlocal pos
        ws()
        c = text[pos]
        if c in '\'"':
            q, pos, out = c, pos + 1, []
            while text[pos] != q:
                if text[pos] == '\\':
                    pos += 1
                out.append(text[pos])
                pos += 1
            pos += 1
            return ''.join(out)
        if c == '[':
            pos += 1
            arr = []
            while True:
                ws()
                if text[pos] == ']':
                    pos += 1
                    return arr
                arr.append(val())
                ws()
                if text[pos] == ',':
                    pos += 1
        if c == '{':
            pos += 1
            obj = {}
            while True:
                ws()
                if text[pos] == '}':
                    pos += 1
                    return obj
                m = re.compile(r'[\w$]+').match(text, pos)
                if m:
                    k, pos = m.group(0), m.end()
                else:
                    k = val()
                ws()
                pos += 1  # ':'
                obj[k] = val()
                ws()
                if text[pos] == ',':
                    pos += 1
        m = re.compile(r'-?\d+(\.\d+)?').match(text, pos)
        if m:
            pos = m.end()
            return float(m.group(0)) if m.group(1) else int(m.group(0))
        m = re.compile(r'[\w$]+').match(text, pos)
        pos = m.end()
        return consts.get(m.group(0))

    return val()


def legacy_links(src):
    """Dawne STEP_VIDS i VIDEOS (jeśli są jeszcze w pliku) w nowym kształcie."""
    out = {'ex': {}, 'plan': {}, 'step': {}}
    consts = {}
    m = re.search(r"const SBAN='([^']*)';", src)
    if m:
        consts['SBAN'] = m.group(1)
    if 'const STEP_VIDS={' in src:
        lit = js_literal(src[src.index('const STEP_VIDS=') + len('const STEP_VIDS='):], consts)
        for sid, rows in lit.items():
            for r in rows:
                vid, title, ch, mins = r[0], r[1], r[2], r[3]
                lang = r[4] if len(r) > 4 and r[4] else 'en'
                out['step'].setdefault(sid, []).append(mk('yt', yt_url(vid), title, ch, mins, lang, 'tut'))
    if 'const VIDEOS={' in src:
        lit = js_literal(src[src.index('const VIDEOS=') + len('const VIDEOS='):], consts)
        for area, plan in (('split', 'split'), ('feet', 'feet'), ('turns', 'turns'), ('hips', 'middle')):
            for v in lit.get(area, []):
                out['plan'].setdefault(plan, []).append(
                    mk('yt', yt_url(v['id']), v['t'], v['ch'], v['m'], 'pl' if v.get('pl') else 'en', 'follow',
                       ph=phases_for(plan, v['t'])))
    return out


# ---------- konwersja plików wejściowych ----------

def convert(data, dead):
    if all(k in ('ex', 'plan', 'step') for k in data):  # gotowy kształt VLINKS
        return data
    out = {'ex': {}, 'plan': {}, 'step': {}}
    if 'dead_existing' in data:
        dead.update(data['dead_existing'])
    if 'exercises' in data:  # YouTube
        for area, rows in data.get('areas', {}).items():
            plan = AREA_PLAN.get(area)
            if not plan:
                print('  pomijam obszar', area)
                continue
            for r in rows:
                out['plan'].setdefault(plan, []).append(
                    mk('yt', yt_url(r['id']), r['title'], r['author'], r.get('min'), r.get('lang') or 'en',
                       yt_kind(r.get('kind')), r.get('note'), phases_for(plan, r['title'], r.get('note'))))
        for key, rows in data['exercises'].items():
            ids = EX_MAP.get(key)
            if not ids:
                print('  nieznane ćwiczenie z wyszukiwania:', key)
                continue
            for exid in ids:
                for r in rows:
                    out['ex'].setdefault(exid, []).append(
                        mk('yt', yt_url(r['id']), r['title'], r['author'], r.get('min'), r.get('lang') or 'en',
                           yt_kind(r.get('kind')), r.get('note')))
        return out
    # dance-masterclass.com
    def dmc(r, plan):
        url = r['url']
        m = re.search(r'/products/(\d+)/posts/', url)
        if m and r.get('url_note') and m.group(1) in DMC_COURSE_FOR:
            url = DMC_COURSE_FOR[m.group(1)]
        author = r.get('teacher') or 'Dance Masterclass'
        if author == 'None':
            author = 'Dance Masterclass'
        title = r['title']
        p = phases_for(plan, title, r.get('note'))
        if plan == 'turns' and 'on pointe' in title.lower():
            plan, p = 'pointe', [2]
        return plan, mk('dmc', url, title, author, r.get('min'), r.get('lang') or 'en', dmc_kind(url, title), r.get('note'), p)
    for area, rows in data.get('areas', {}).items():
        plan0 = AREA_PLAN.get(area)
        if not plan0:
            print('  pomijam obszar', area)
            continue
        for r in rows:
            plan, v = dmc(r, plan0)
            out['plan'].setdefault(plan, []).append(v)
    for r in data.get('full_classes', []):
        plans = next((v for k, v in DMC_CLASS_MAP.items() if k in r['url']), None)
        for plan in plans or []:
            out['plan'].setdefault(plan, []).append(dmc(r, plan)[1])
        if not plans:
            print('  lekcja bez planu (pominięta):', r['title'][:70])
    for r in data.get('stretching_conditioning', []):
        plans = next((v for k, v in DMC_STRETCH_MAP.items() if k in r['url']), None)
        for plan in plans or []:
            out['plan'].setdefault(plan, []).append(dmc(r, plan)[1])
        if not plans:
            print('  program bez planu (pominięty):', r['title'][:70])
    return out


def fill_minutes(lst):
    """Strona kursu/programu bez długości: mediana długości lekcji z tej samej listy
    (ten sam adres albo adresy lekcji pod adresem kursu), czyli typowa długość jednego treningu."""
    for v in lst:
        if isinstance(v.get('min'), (int, float)) or not v.get('url'):
            continue
        base = v['url'].rstrip('/')
        m = sorted(x['min'] for x in lst if x is not v and isinstance(x.get('min'), (int, float))
                   and (x.get('url') == v['url'] or x.get('url', '').startswith(base + '/')))
        if m:
            v['min'] = m[len(m) // 2]


def valid(v):
    if v.get('src') == 'yt':
        ok = bool(YT_RE.match(v.get('url', '')))
    elif v.get('src') == 'dmc':
        ok = bool(DMC_RE.match(v.get('url', '')))
    else:
        ok = False
    return (ok and isinstance(v.get('min'), (int, float)) and not isinstance(v.get('min'), bool)
            and isinstance(v.get('lang'), str) and re.fullmatch(r'[a-z]{2}', v['lang'])
            and v.get('kind') in ('tut', 'follow', 'class') and bool(v.get('title')))


def merge(sources, known, dead):
    res = {'ex': {}, 'plan': {}, 'step': {}}
    stats = {'added': 0, 'dup': 0, 'invalid': 0, 'unknown': 0, 'dead': 0}
    for src in sources:
        for scope in ('ex', 'plan', 'step'):
            for key, lst in (src.get(scope) or {}).items():
                if key not in known[scope]:
                    print('  nieznane id %s.%s (pominięte, %d linków)' % (scope, key, len(lst)))
                    stats['unknown'] += len(lst)
                    continue
                fill_minutes(lst)
                cur = res[scope].setdefault(key, [])
                seen = {v['url'] for v in cur}
                for v in lst:
                    m = YT_ID_RE.search(v.get('url', '')) if v.get('src') == 'yt' else None
                    if m and m.group(1) in dead:
                        stats['dead'] += 1
                        continue
                    if not valid(v):
                        print('  niepoprawny link (pominięty): %s.%s %s' % (scope, key, v.get('url') or v.get('title')))
                        stats['invalid'] += 1
                        continue
                    if v['url'] in seen:
                        stats['dup'] += 1
                        continue
                    seen.add(v['url'])
                    cur.append({k: v[k] for k in ('src', 'url', 'title', 'author', 'min', 'lang', 'note', 'kind', 'ph') if v.get(k) is not None})
                    stats['added'] += 1
    for scope in res:
        res[scope] = {k: v for k, v in sorted(res[scope].items()) if v}
    return res, stats


def dump(vl, nl='\n'):
    """JSON z jednym linkiem w wierszu (czytelny diff)."""
    parts = []
    for scope in ('ex', 'plan', 'step'):
        rows = []
        for key, lst in vl[scope].items():
            items = ',\n'.join('  ' + json.dumps(v, ensure_ascii=False, separators=(',', ':')) for v in lst)
            rows.append(' %s:[\n%s]' % (json.dumps(key), items))
        parts.append('%s:{\n%s}' % (json.dumps(scope), ',\n'.join(rows)))
    return ('{\n' + ',\n'.join(parts) + '}').replace('\n', nl)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*')
    ap.add_argument('--html', default=os.path.join(ROOT, 'arabeska.html'))
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--legacy-from', help='plik HTML, z którego wziąć dawne STEP_VIDS/VIDEOS (np. wersja sprzed zmian)')
    a = ap.parse_args()
    src = read_html(a.html)
    known = known_ids(src)
    dead = set()
    sources = [current_vlinks(src)]
    for f in a.files:
        print('plik:', f)
        try:
            sources.append(convert(json.load(open(f, encoding='utf-8')), dead))
        except Exception as e:  # nigdy nie przerywamy budowania
            print('  nie udało się wczytać:', e)
    leg = legacy_links(read_html(a.legacy_from) if a.legacy_from else src)
    if any(leg[s] for s in leg):
        print('dawne STEP_VIDS/VIDEOS: kroki %d, plany %d' % (len(leg['step']), len(leg['plan'])))
        sources.append(leg)
    vl, st = merge(sources, known, dead)
    n = {s: sum(len(x) for x in vl[s].values()) for s in vl}
    src_n = {k: sum(1 for s in vl for L in vl[s].values() for v in L if v['src'] == k) for k in ('yt', 'dmc')}
    print('wynik: ex %d linków (%d ćwiczeń), plan %d (%d planów), step %d (%d kroków); YT %d, DMC %d' % (
        n['ex'], len(vl['ex']), n['plan'], len(vl['plan']), n['step'], len(vl['step']), src_n['yt'], src_n['dmc']))
    print('pominięte: duplikaty %(dup)d, martwe %(dead)d, niepoprawne %(invalid)d, nieznane id %(unknown)d' % st)
    if a.dry_run:
        return
    i, j = src.index(START) + len(START), src.index(END)
    src = src[:i] + dump(vl, '\r\n' if '\r\n' in src else '\n') + src[j:]
    open(a.html, 'w', encoding='utf-8', newline='').write(src)
    print('zapisano', a.html)


if __name__ == '__main__':
    main()
