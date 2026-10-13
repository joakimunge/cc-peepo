// peepo: Claude reacts with peepos, the little green frogs of Twitch and Slack, inline in its replies like any emoji.
//  - /peepo setup builds the Peepo Emoji font on this machine and points the terminal at it (scripts/setup.py);
//    /peepo shows a test frog and whether peepos are on, /peepo on and /peepo off switch them
//  - while on, the system prompt names every peepo and how to show one, by its shortcode (`:peepo_clap:`), and in a
//    reply each known shortcode outside code becomes the three characters the font draws that frog with; the reply
//    is then drawn as it would be without this mod, by the hooks beneath or the engine
//  - a plugin that draws replies itself (opencode-look does) can stand above this one, so the reply never reaches
//    the hook that swaps its text; the Text such a plugin draws with swaps the shortcodes in its strings instead
//  - on Team and Enterprise accounts the built-in security default keeps installed plugins out of the system
//    prompt, so the guide is also kept in ~/.claude/peepo/guide.md (a line saying peepos are off, while off) for
//    your ~/.claude/CLAUDE.md to import; /peepo says when it does not
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'
import { PEEPOS } from './peepos'

/** the first character of the font's range; peepo n is drawn by CELLS characters from FIRST + CELLS * n */
const FIRST = 0xe400
const CELLS = 3
const SETUP_TIMEOUT = 600_000

const isOn = atom({ plugin: 'peepo', key: 'on' } as const, false)
/** isOn, for the Text other plugins draw with: an element is built at once, with no read to wait on */
let drawing = false

export const GLYPHS = new Map(
  PEEPOS.map(([name], i) => [
    name,
    String.fromCharCode(...Array.from({ length: CELLS }, (_, k) => FIRST + i * CELLS + k)),
  ]),
)

const CODE = /:([a-z0-9_]+):/g
const FENCE = /^[ \t]*(```|~~~)/
/** inline code, which is left alone */
const SPAN = /(`+)[^`]*?\1/g

/** a stretch of text that is not code, with each known shortcode as its peepo */
function swap(text: string) {
  return text.replace(CODE, (code, name: string) => GLYPHS.get(name) ?? code)
}

/** a Text's children with each known shortcode in their strings as its peepo */
function swapChildren(children: RenderChildren): RenderChildren {
  if (typeof children === 'string') return swap(children)
  if (Array.isArray(children)) return (children as readonly RenderChildren[]).map(swapChildren)
  return children
}

/** the reply with its shortcodes as peepos: outside code fences and inline code only */
export function withPeepos(text: string) {
  let fence: string | undefined
  return text
    .split('\n')
    .map((line) => {
      const mark = FENCE.exec(line)?.[1]
      if (fence !== undefined || mark !== undefined) {
        if (fence === undefined) fence = mark
        else if (mark === fence) fence = undefined
        return line
      }
      let out = ''
      let at = 0
      for (const m of line.matchAll(SPAN)) {
        out += swap(line.slice(at, m.index)) + m[0]
        at = m.index + m[0].length
      }
      return out + swap(line.slice(at))
    })
    .join('\n')
}

export const GUIDE = [
  '# Peepo emojis',
  'The terminal can show peepos, the little green frog emojis from Twitch and Slack, inline like any emoji: write ' +
    'the shortcode in your sentence, such as "That did it :peepo_clap:". Each is drawn three cells wide and a ' +
    'little taller than the text.',
  'Use them as you would any emoji, whenever one adds warmth or humour and fits the moment: a fix that finally works (peepo_clap, peepo_happy), ' +
    'a win (peepo_gg), a nasty bug or a loss (peepo_cry, peepo_sad), a puzzle (peepo_think, peepo_huh), something out ' +
    'of your hands (peepo_shrug). One or two in a reply at most, and not in every reply. Leave them out of terse or ' +
    'serious replies, and never put them in code, commit messages, files or anything other than your reply text.',
  `Only these exist; any other shortcode shows as plain text: ${[...GLYPHS.keys()].join(', ')}.`,
].join('\n\n')
export const GUIDE_OFF = '# Peepo emojis\n\nPeepos are off (/peepo off): write no peepo shortcodes.'

/** the guide's file under your home, and the line in ~/.claude/CLAUDE.md that imports it */
const GUIDE_FILE = '.claude/peepo/guide.md'
export const IMPORT = '@~/.claude/peepo/guide.md'

const TEST = `${GLYPHS.get('peepo_clap')} ${GLYPHS.get('peepo_happy')}`

/** ~/.claude/CLAUDE.md, or '' where there is none or no home */
async function claudeMd($: EngineInterface) {
  try {
    const home = await $.env.get('HOME')
    return home ? await $.fs.read(`${home}/.claude/CLAUDE.md`) : ''
  } catch {
    return ''
  }
}

/** the guide in its file, or the line saying peepos are off; one that can't be written leaves the last in place */
async function writeGuide($: EngineInterface, on: boolean) {
  try {
    const home = await $.env.get('HOME')
    if (home) await $.fs.write(`${home}/${GUIDE_FILE}`, `${on ? GUIDE : GUIDE_OFF}\n`)
  } catch {}
}

async function status($: EngineInterface) {
  const on = await read($, isOn)
  const imported = (await claudeMd($)).includes(GUIDE_FILE)
  return [
    `Test: ${TEST}  <- two frogs here mean the font works in this terminal; boxes or nothing mean it does not yet.`,
    on
      ? 'Peepos are on: Claude uses them in its replies. /peepo off turns them off.'
      : 'Peepos are off. Run /peepo setup first if you have not, then /peepo on once the frogs above show.',
    imported
      ? ''
      : `On a Team or Enterprise account Claude only learns the peepos from your ~/.claude/CLAUDE.md: add the line ${IMPORT} to it.`,
  ].filter(Boolean).join('\n')
}

async function switchTo($: EngineInterface, on: boolean) {
  drawing = on
  await update($, isOn, () => on)
  await $.store.set('on', on)
  await writeGuide($, on)
  // replies drawn by a plugin above never read isOn, so they redraw on this
  $.ui.invalidate('ui.render')
}

/** runs scripts/setup.py with the terminal named after `/peepo setup`, if one is */
async function setup($: EngineInterface, args: string[]) {
  $.ui.toast('peepo: building the font, which takes a minute or two')
  const script = `${$.plugin.root}/scripts/setup.py`
  let result
  try {
    result = await $.process.run(['python3', script, ...args], { timeoutMs: SETUP_TIMEOUT })
  } catch (err) {
    return { text: `peepo setup could not run python3 (${String(err)}). It needs Python 3: run xcode-select --install.`, exitCode: 1 }
  }
  const out = result.stdout.trim()
  if (result.exitCode !== 0) {
    return { text: ['peepo setup failed.', out, result.stderr.trim()].filter(Boolean).join('\n'), exitCode: result.exitCode }
  }
  return { text: `${out}\n\nThen run /peepo: if the test frogs show, /peepo on.` }
}

export const register: Register = (on) => {
  on('session.start', async ($, e, next) => {
    const stored = (await $.store.get('on')) === true
    drawing = stored
    await update($, isOn, () => stored)
    // rewritten each session, so an update's new peepos reach the guide
    await writeGuide($, stored)
    await $.command.register({
      name: 'peepo',
      description: 'Peepo emoji: setup builds the font, on and off switch them, alone it shows a test frog',
      argumentHint: '[setup [iterm2|ghostty|kitty] | on | off]',
    })
    return next(e)
  })

  on('command.run', { command: 'peepo' }, async ($, e) => {
    const [verb = '', ...rest] = e.args.trim().split(/\s+/).filter(Boolean)
    switch (verb) {
      case 'setup':
        return setup($, rest)
      case 'on':
        await switchTo($, true)
        return { text: 'Peepos on: Claude uses them in its replies from the next one.' }
      case 'off':
        await switchTo($, false)
        return { text: 'Peepos off.' }
      case '':
        return { text: await status($) }
      default:
        return { text: 'Usage: /peepo [setup [iterm2|ghostty|kitty] | on | off]', exitCode: 1 }
    }
  })

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    if (!(await read($, isOn)) || !e.surfaces.includes('terminal') || e.traits.includes('bare')) return composed
    return { sections: [...composed.sections, { id: 'peepo:guide', text: GUIDE, scope: 'session' as const }] }
  })

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    if (e.surface !== 'terminal' || !(await read($, isOn))) return next(e)
    const text = withPeepos(e.props.text)
    return next(text === e.props.text ? e : { ...e, props: { ...e.props, text } })
  })

  // the Text a plugin draws a reply with; its strings are already out of their markdown, so inline code is not told
  // apart here and a shortcode in it shows as its peepo too
  on('ui.resolve', { component: 'AssistantMessage' }, async ($, e, next) => {
    if (e.surface !== 'terminal') return next(e)
    const table = await next(e)
    const { Text } = table
    return { ...table, Text: (props) => Text(drawing ? { ...props, children: swapChildren(props.children) } : props) }
  })
}
