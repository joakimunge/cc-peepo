#!/usr/bin/env python3
"""Sets peepo up on this Mac: builds the Peepo Emoji font from slackmojis' pictures and points the terminal at it.

    python3 scripts/setup.py [iterm2|ghostty|kitty]

`/peepo setup` runs it. Without a terminal named, it finds the one it runs in (through tmux too). Everything it makes
goes in ~/.claude/peepo: a Python environment with fonttools and pillow, the pictures it downloads and the font it
builds. It installs the font to ~/Library/Fonts and then:
  - Ghostty, kitty: adds one line to the terminal's config, mapping the font's characters to the font
  - iTerm2: leaves a helper that, once iTerm2 quits, sets its profile to draw those characters with the font (iTerm2
    writes over its own settings while it runs) and opens iTerm2 again

The font: peepo n (in hooks/peepos.ts) is the three characters from U+E400 + 3n, private-use code points Nerd Fonts
leave empty. Each character draws one slice of the frog as a PNG (an `sbix` table, as Apple Color Emoji has), sized
from the terminal font's own cell: three cells wide, 1.3 lines tall. The pictures are other people's art and are
never part of this repository: each machine downloads its own.
"""
import base64
import io
import json
import math
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
DATA = HOME / '.claude' / 'peepo'
VENV = DATA / 'venv'
ROOT = Path(__file__).resolve().parent.parent
FONTS = HOME / 'Library' / 'Fonts'

FIRST = 0xE400
CELLS = 3
HEIGHT = 1.3
UPEM = 1000
STRIKES = (24, 32, 48, 64, 96, 128)
# each slice reaches this far (of an em) into its neighbours, so a terminal's rounding of its cells to whole points
# or pixels never opens a gap, which shows as a dark line, between the slices of one frog
BLEED = 0.06
PS_NAME = 'PeepoEmoji-Regular'
FULL_NAME = 'Peepo Emoji'
AGENT = {'User-Agent': 'Mozilla/5.0 (peepo for Claude Code)'}
# when a terminal's font cannot be found: a typical monospace cell (advance, ascent, descent, in em)
TYPICAL_CELL = (0.6, 0.95, 0.25)
TERMINALS = ('iterm2', 'ghostty', 'kitty')


def say(text):
    print(text, flush=True)


def bootstrap():
    """Runs this script again in ~/.claude/peepo/venv when fonttools and pillow are not importable here."""
    try:
        import fontTools  # noqa: F401
        import PIL  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get('PEEPO_IN_VENV') == '1':
        sys.exit('fonttools and pillow did not install; see the lines above')
    python = VENV / 'bin' / 'python'
    if not python.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, '-m', 'venv', str(VENV)], check=True)
    if subprocess.run([str(python), '-c', 'import fontTools, PIL'], capture_output=True).returncode != 0:
        subprocess.run([str(python), '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
                        'fonttools', 'pillow'], check=True)
    os.execve(str(python), [str(python), '-I', str(Path(__file__).resolve()), *sys.argv[1:]],
              {**os.environ, 'PEEPO_IN_VENV': '1'})


# -- the terminal ----------------------------------------------------------------------------------------------------

def environment():
    """This process's environment, with what tmux was started with standing in for what tmux replaced."""
    env = dict(os.environ)
    if not env.get('TMUX'):
        return env
    try:
        out = subprocess.run(['tmux', 'show-environment', '-g'], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return env
    for line in out.splitlines():
        key, _, value = line.partition('=')
        if key in ('TERM_PROGRAM', 'LC_TERMINAL', 'ITERM_SESSION_ID', 'GHOSTTY_RESOURCES_DIR', 'KITTY_WINDOW_ID') \
                and (env.get(key) in (None, '', 'tmux')):
            env[key] = value
    return env


def detect(env):
    """The terminal by TERM_PROGRAM first: the other marks can be left over from another terminal (through tmux or
    ssh), and are asked only when it says nothing."""
    program = env.get('TERM_PROGRAM', '').lower()
    known = {'iterm.app': 'iterm2', 'ghostty': 'ghostty', 'kitty': 'kitty'}
    if program in known:
        return known[program]
    if env.get('KITTY_WINDOW_ID') or env.get('TERM') == 'xterm-kitty':
        return 'kitty'
    if env.get('GHOSTTY_RESOURCES_DIR'):
        return 'ghostty'
    if env.get('LC_TERMINAL') == 'iTerm2' or env.get('ITERM_SESSION_ID'):
        return 'iterm2'
    return None


def iterm2_prefs():
    out = subprocess.run(['defaults', 'export', 'com.googlecode.iterm2', '-'], capture_output=True, check=True).stdout
    return plistlib.loads(out)


def iterm2_profile(prefs):
    guid = prefs.get('Default Bookmark Guid')
    profiles = prefs.get('New Bookmarks', [])
    return next((p for p in profiles if p.get('Guid') == guid), profiles[0] if profiles else None)


def config_pairs(path, separator):
    """(key, value) of each setting in a config file: `key = value` (Ghostty, separator '=') or `key value` (kitty,
    separator None), in the file's order."""
    if not path.exists():
        return []
    pairs = []
    for line in path.read_text(errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, value = (line.split('=', 1) if '=' in line else (line, '')) if separator == '=' else \
            (line.split(None, 1) + [''])[:2]
        pairs.append((key.strip(), value.strip().strip('"')))
    return pairs


def ghostty_config():
    for path in (HOME / '.config' / 'ghostty' / 'config',
                 HOME / 'Library' / 'Application Support' / 'com.mitchellh.ghostty' / 'config'):
        if path.exists():
            return path
    return HOME / '.config' / 'ghostty' / 'config'


def kitty_config():
    return HOME / '.config' / 'kitty' / 'kitty.conf'


def terminal_font(terminal):
    """(font name, size in points) the terminal draws text with."""
    if terminal == 'iterm2':
        profile = iterm2_profile(iterm2_prefs()) or {}
        name, _, size = (profile.get('Normal Font') or 'Monaco 12').rpartition(' ')
        return name, float(size)
    if terminal == 'ghostty':
        pairs = config_pairs(ghostty_config(), '=')
        families = [v for k, v in pairs if k == 'font-family' and v]  # the first is the one text uses
        sizes = [v for k, v in pairs if k == 'font-size' and v]  # the last one set wins
        return (families[0] if families else 'JetBrains Mono'), float(sizes[-1] if sizes else 13)
    pairs = dict(config_pairs(kitty_config(), None))
    family = pairs.get('font_family') or 'monospace'
    return ('Menlo' if family in ('monospace', 'auto') else family), float(pairs.get('font_size') or 11)


def font_faces():
    for folder in (FONTS, Path('/Library/Fonts'), Path('/System/Library/Fonts'),
                   Path('/System/Library/Fonts/Supplemental')):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob('*')):
            suffix = path.suffix.lower()
            if suffix in ('.ttf', '.otf'):
                yield path, 0
            elif suffix == '.ttc':
                head = path.read_bytes()[:12]
                count = int.from_bytes(head[8:12], 'big') if head[:4] == b'ttcf' else 1
                for i in range(count):
                    yield path, i


def terminal_cell(name):
    """The cell of the font called `name` (PostScript, full or family name), in em: (advance, ascent, descent)."""
    from fontTools.ttLib import TTFont
    want = name.lower()
    family_match = None
    for path, number in font_faces():
        if path.name.startswith('PeepoEmoji'):
            continue
        try:
            font = TTFont(path, fontNumber=number, lazy=True)
            names = font['name']
            ps, full = (names.getDebugName(6) or '').lower(), (names.getDebugName(4) or '').lower()
            family = (names.getDebugName(16) or names.getDebugName(1) or '').lower()
            style = (names.getDebugName(17) or names.getDebugName(2) or '').lower()
            if want in (ps, full) or (want == family and style == 'regular'):
                return cell_of(font)
            if want == family and family_match is None:
                family_match = cell_of(font)
        except Exception:  # a font file this cannot read, or with no 'M', is not the one
            continue
    return family_match


def cell_of(font):
    upem = font['head'].unitsPerEm
    advance = font['hmtx'][font.getBestCmap()[ord('M')]][0]
    hhea = font['hhea']
    return advance / upem, hhea.ascent / upem, -hhea.descent / upem


# -- the pictures ----------------------------------------------------------------------------------------------------

def peepos():
    """[(name, id, url)] from hooks/peepos.ts: the JSON between its outer brackets."""
    text = (ROOT / 'hooks' / 'peepos.ts').read_text()
    body = text[text.index('= [') + 2:text.rindex(']') + 1]
    return [tuple(entry) for entry in json.loads(body)]


def pictures(entries):
    """name -> the frog, cropped to what it draws; downloads what ~/.claude/peepo/images lacks."""
    from PIL import Image, ImageSequence
    folder = DATA / 'images'
    folder.mkdir(parents=True, exist_ok=True)
    out, failed = {}, []
    for name, number, url in entries:
        file = folder / f'{number}{Path(url).suffix.lower() or ".png"}'
        try:
            if not file.exists():
                data = urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=30).read()
                file.write_bytes(data)
                time.sleep(0.05)
            img = Image.open(io.BytesIO(file.read_bytes()))
            # an animation's still is the frame that draws the most
            frame = max((f.convert('RGBA') for f in ImageSequence.Iterator(img)),
                        key=lambda f: sum(f.getchannel('A').histogram()[128:]))
            bbox = frame.getchannel('A').point(lambda a: 255 if a >= 32 else 0).getbbox()
            if bbox is None:
                raise ValueError('nothing drawn')
            out[name] = frame.crop(bbox)
        except Exception as err:  # this frog is left blank; the rest still build
            file.unlink(missing_ok=True)
            failed.append(f'{name} ({err})')
    return out, failed


# -- the font --------------------------------------------------------------------------------------------------------

def slices(img, ppem, cell, raised):
    """The picture fitted into CELLS cells by HEIGHT lines at `ppem`, cut at the cells' borders, each slice reaching
    BLEED into its neighbours: [(slice, offsetX)], offsetY."""
    from PIL import Image
    width, ascent, descent = cell
    cell_w = round(width * ppem)
    bleed = max(1, round(BLEED * ppem))
    line = (ascent + descent) * ppem
    box_w, box_h = cell_w * CELLS, max(1, round(line * HEIGHT))
    w, h = img.size
    scale = min(box_w / w, box_h / h)
    fit = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    canvas = Image.new('RGBA', (box_w, box_h), (0, 0, 0, 0))
    canvas.paste(fit, ((box_w - fit.width) // 2, (box_h - fit.height) // 2))
    # the box is centred on the line (as far below its bottom as above its top), then raised
    offset_y = round(-descent * ppem + (line - box_h) / 2 + raised * ppem)
    parts = []
    for i in range(CELLS):
        x0, x1 = max(0, i * cell_w - bleed), min(box_w, (i + 1) * cell_w + bleed)
        parts.append((canvas.crop((x0, 0, x1, box_h)), x0 - i * cell_w))
    return parts, offset_y


def png(img):
    out = io.BytesIO()
    img.save(out, format='PNG', optimize=True)
    return out.getvalue()


def build(entries, frogs, cell, family, raised, out):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables._s_b_i_x import table__s_b_i_x
    from fontTools.ttLib.tables.sbixGlyph import Glyph as BitmapGlyph
    from fontTools.ttLib.tables.sbixStrike import Strike

    width, ascent, descent = cell
    advance = round(width * UPEM)
    line = ascent + descent
    order, cmap = ['.notdef', 'space'], {0x20: 'space'}
    for i, (name, _, _) in enumerate(entries):
        for k in range(CELLS):
            glyph = f'{name}.{k}'
            order.append(glyph)
            cmap[FIRST + i * CELLS + k] = glyph

    # each slice's outline is a box over its picture: never drawn (the sbix flags say pictures only), but a terminal
    # that sizes a glyph from its outline sees the picture's size rather than nothing
    bottom = round((-descent + line * (1 - HEIGHT) / 2 + raised) * UPEM)
    top = bottom + round(line * HEIGHT * UPEM)
    pen = TTGlyphPen(None)
    pen.moveTo((0, bottom)); pen.lineTo((0, top)); pen.lineTo((advance, top)); pen.lineTo((advance, bottom))
    pen.closePath()
    box, empty = pen.glyph(), TTGlyphPen(None).glyph()

    fb = FontBuilder(UPEM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf({g: box if g.rpartition('.')[0] in frogs else empty for g in order})
    fb.setupHorizontalMetrics({g: (advance, 0) for g in order})
    fb.setupHorizontalHeader(ascent=round(ascent * UPEM), descent=-round(descent * UPEM))
    fb.setupNameTable({'familyName': family, 'styleName': 'Regular', 'fullName': FULL_NAME, 'psName': PS_NAME,
                       'uniqueFontIdentifier': PS_NAME})
    fb.setupOS2(sTypoAscender=round(ascent * UPEM), sTypoDescender=-round(descent * UPEM), sTypoLineGap=0,
                usWinAscent=round(ascent * UPEM), usWinDescent=round(descent * UPEM))
    fb.setupPost()

    sbix = table__s_b_i_x()
    sbix.version, sbix.flags, sbix.strikes = 1, 1, {}
    for ppem in STRIKES:
        strike = Strike(ppem=ppem, resolution=72)
        for name, _, _ in entries:
            if name not in frogs:
                continue
            parts, offset_y = slices(frogs[name], ppem, cell, raised)
            for k, (part, offset_x) in enumerate(parts):
                glyph = f'{name}.{k}'
                strike.glyphs[glyph] = BitmapGlyph(glyphName=glyph, graphicType='png ', originOffsetX=offset_x,
                                                   originOffsetY=offset_y, imageData=png(part))
        sbix.strikes[ppem] = strike
    fb.font['sbix'] = sbix
    fb.save(out)


def install(font):
    """Copies the font to ~/Library/Fonts under a new file name: a font replaced under the same name is not always
    read again. Earlier builds are removed."""
    FONTS.mkdir(parents=True, exist_ok=True)
    for old in FONTS.glob('PeepoEmoji*.ttf'):
        old.unlink()
    target = FONTS / f'PeepoEmoji-{int(time.time())}.ttf'
    shutil.copyfile(font, target)
    return target


# -- pointing the terminal at the font -------------------------------------------------------------------------------

MARK = '# peepo: Claude Code peepo emoji drawn by the Peepo Emoji font (added by /peepo setup)'


def add_config_line(path, line):
    """Adds `line` under MARK to the config at `path`, in place of an earlier one. True when the file changed."""
    lines = path.read_text().splitlines() if path.exists() else []
    stripped = [l.strip() for l in lines]
    if MARK in stripped and line in stripped:
        return False
    kept, after_mark = [], False
    for l in lines:  # an earlier build's mark and the line under it go
        if l.strip() == MARK:
            after_mark = True
        elif after_mark:
            after_mark = False
        else:
            kept.append(l)
    out = '\n'.join(kept).rstrip('\n')
    out = (out + '\n\n' if out else '') + f'{MARK}\n{line}\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copyfile(path, path.with_name(path.name + '.before-peepo'))
    path.write_text(out)
    return True


def iterm2_entry(count):
    return {'fontName': PS_NAME, 'start': FIRST, 'count': count, 'destination': FIRST}


def iterm2_is_set(profile, count):
    """Whether the profile already draws the range with this font (iTerm2 reads Special Exceptions only while its
    non-ASCII font is on)."""
    if not profile or not profile.get('Use Non-ASCII Font'):
        return False
    try:
        entries = json.loads(profile.get('Special Font Config') or '{}').get('entries', [])
    except json.JSONDecodeError:
        return False
    return any(e.get('start') == FIRST and e.get('count', 0) >= count and e.get('fontName') in (PS_NAME, FULL_NAME)
               for e in entries)


def iterm2_apply(count):
    """Sets iTerm2's default profile to draw the peepos (with_peepo); a copy of the settings before goes to
    ~/.claude/peepo."""
    prefs = iterm2_prefs()
    (DATA / 'iterm2-before-peepo.plist').write_bytes(plistlib.dumps(prefs))
    staged = DATA / 'iterm2-with-peepo.plist'
    staged.write_bytes(plistlib.dumps(with_peepo(prefs, count)))
    subprocess.run(['defaults', 'import', 'com.googlecode.iterm2', str(staged)], check=True)


def with_peepo(prefs, count):
    """The settings with the default profile's non-ASCII font on (the same as its text font if it was off) and a
    Special Exception drawing U+E400.. with the font, in place of any exception over those characters."""
    profile = iterm2_profile(prefs)
    if not profile.get('Use Non-ASCII Font'):
        profile['Non Ascii Font'] = profile.get('Normal Font', 'Monaco 12')
    profile['Use Non-ASCII Font'] = True
    try:
        config = json.loads(profile.get('Special Font Config') or '{}')
    except json.JSONDecodeError:
        config = {}
    last = FIRST + count - 1
    entries = [e for e in config.get('entries', [])
               if e.get('start', 0) + e.get('count', 0) - 1 < FIRST or e.get('start', 0) > last]
    entries.append(iterm2_entry(count))
    config['entries'] = sorted(entries, key=lambda e: e['start'])
    config.setdefault('version', 1)
    profile['Special Font Config'] = json.dumps(config, separators=(',', ':'))
    return prefs


def iterm2_running():
    return subprocess.run(['pgrep', '-x', 'iTerm2'], capture_output=True).returncode == 0


def iterm2_helper(count):
    """`--apply-iterm2 <count>`: waits up to an hour for iTerm2 to quit, sets its profile, opens it again."""
    deadline = time.time() + 3600
    while iterm2_running():
        if time.time() > deadline:
            return
        time.sleep(1)
    iterm2_apply(count)
    subprocess.run(['open', '-a', 'iTerm'])


def configure(terminal, count):
    """Points the terminal at the font; the lines to tell the person."""
    last = f'U+{FIRST + count - 1:04X}'
    if terminal == 'ghostty':
        path = ghostty_config()
        added = add_config_line(path, f'font-codepoint-map = U+{FIRST:04X}-{last}={FULL_NAME}')
        return [f'Ghostty: {"added" if added else "already has"} the font-codepoint-map line in {path}.',
                'Reload Ghostty\'s config (cmd+shift+,) or restart Ghostty.']
    if terminal == 'kitty':
        path = kitty_config()
        added = add_config_line(path, f'symbol_map U+{FIRST:04X}-{last} {FULL_NAME}')
        return [f'kitty: {"added" if added else "already has"} the symbol_map line in {path}.',
                'Reload kitty\'s config (ctrl+cmd+,) or restart kitty.']
    prefs = iterm2_prefs()
    if prefs.get('LoadPrefsFromCustomFolder'):
        return ['iTerm2 loads its settings from a custom folder, so set it by hand: Settings > Profiles > Text, tick',
                '"Use a different font for non-ASCII text" (set it to your normal font and size) and leave it on, then',
                f'Manage Special Exceptions > + > U+{FIRST:04X} to {last}, font {PS_NAME}. Then quit and reopen iTerm2.']
    if iterm2_is_set(iterm2_profile(prefs), count):
        return ['iTerm2 already draws these characters with the font: quit iTerm2 (cmd+Q) and open it again to load',
                'the new build.']
    log = (DATA / 'iterm2-helper.log').open('a')
    subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()), '--apply-iterm2', str(count)],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    return ['iTerm2: quit it now (cmd+Q). A helper then sets your profile to draw peepos with the font and opens',
            'iTerm2 again; tmux sessions carry on. It turns on "Use a different font for non-ASCII text" (with your',
            'normal font), which iTerm2 needs for that, and keeps your old settings in ~/.claude/peepo.']


# -- main ------------------------------------------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if args[:1] == ['--apply-iterm2']:
        iterm2_helper(int(args[1]))
        return
    if any(a not in TERMINALS for a in args):
        sys.exit(f'usage: setup.py [{"|".join(TERMINALS)}]')
    if sys.platform != 'darwin':
        sys.exit('peepo setup supports macOS for now (iTerm2, Ghostty, kitty).')
    bootstrap()

    terminal = args[0] if args else detect(environment())
    if terminal is None:
        sys.exit('Could not tell which terminal this is. Run /peepo setup iterm2, /peepo setup ghostty or '
                 '/peepo setup kitty.')
    name, size = terminal_font(terminal)
    cell = terminal_cell(name)
    found = cell is not None
    cell = cell or TYPICAL_CELL

    entries = peepos()
    frogs, failed = pictures(entries)

    # iTerm2 draws a glyph in colour only when its font's family is Apple's emoji font by name; every other font is
    # drawn as one-colour text, where a picture-only glyph shows as '?'. It also draws emoji from the bottom of the
    # cell rather than the baseline, so there the frogs are raised by the descender, rounded as iTerm2 rounds it
    if terminal == 'iterm2':
        family, raised = 'AppleColorEmoji', math.ceil(cell[2] * size + 0.5) / size
    else:
        family, raised = FULL_NAME, 0.0
    DATA.mkdir(parents=True, exist_ok=True)
    font = DATA / 'PeepoEmoji.ttf'
    build(entries, frogs, cell, family, raised, font)
    installed = install(font)

    lines = [f'Built the Peepo Emoji font for {terminal}: {len(frogs)} peepos, sized for {name} at {size:g} pt'
             + ('' if found else ' (font not found: sized for a typical monospace font)') + '.',
             f'Installed it as {installed}.']
    if failed:
        lines.append(f'{len(failed)} could not be downloaded and stay blank: {", ".join(failed)}.')
    lines += configure(terminal, len(entries) * CELLS)
    (DATA / 'state.json').write_text(json.dumps({'terminal': terminal, 'font': name, 'size': size,
                                                 'installed': str(installed), 'peepos': len(frogs)}, indent=1))
    say('\n'.join(lines))


if __name__ == '__main__':
    main()
