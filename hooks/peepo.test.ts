import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'
import { GLYPHS, GUIDE, GUIDE_OFF, IMPORT, withPeepos } from './register'
import { PEEPOS } from './peepos'

const clap = GLYPHS.get('peepo_clap')!
const gg = GLYPHS.get('peepo_gg')!

test('each peepo is three characters from U+E400 on, in the list order', () => {
  expect(GLYPHS.size).toBe(PEEPOS.length)
  PEEPOS.forEach(([name], i) => {
    const s = GLYPHS.get(name)!
    expect([...s].map((c) => c.charCodeAt(0))).toEqual([0, 1, 2].map((k) => 0xe400 + i * 3 + k))
  })
  expect(0xe400 + PEEPOS.length * 3 - 1).toBeLessThanOrEqual(0xe5f9) // the gap Nerd Fonts leave empty
})

test('a known shortcode becomes its peepo anywhere in the text, outside code', () => {
  expect(withPeepos('That did it :peepo_clap: and :peepo_gg:')).toBe(`That did it ${clap} and ${gg}`)
  expect(withPeepos('run `echo :peepo_clap:` then :peepo_clap:')).toBe(`run \`echo :peepo_clap:\` then ${clap}`)
  expect(withPeepos('```\n:peepo_clap:\n```\n:peepo_clap:')).toBe(`\`\`\`\n:peepo_clap:\n\`\`\`\n${clap}`)
  expect(withPeepos('no :not_a_peepo: or :constructor: here')).toBe('no :not_a_peepo: or :constructor: here')
})

const beneath = (on: On, seen: string[]) => {
  on('ui.render', { component: 'AssistantMessage' }, ((_$: unknown, e: { props: { text: string } }) => {
    seen.push(e.props.text)
    return { type: 'Text', props: {}, children: [e.props.text] }
  }) as never)
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'You are Claude.', scope: 'shared' }] }) as never)
}
/** a session starting, with something beneath to register its command */
const start = async ($: { session: { start: (e: never) => Promise<unknown> } }, on: On) => {
  on('command.register', ((_$: unknown, e: { name: string }) => ({ value: { command: e.name } })) as never)
  on('session.start', (() => ({ cwd: '/tmp' })) as never)
  await $.session.start({ source: 'startup', cwd: '/tmp' } as never)
}
/** `/peepo <args>`, typed at the prompt */
const peepo = ($: { command: { run: (e: never) => Promise<{ text?: string }> } }, args: string) =>
  $.command.run({ command: 'peepo', args, origin: { kind: 'composer' }, presentation: 'transcript' } as never)
const request = { model: 'claude-opus-5-5', promptModel: 'claude-opus-5-5', tools: [], outputStyle: null, traits: [] }
const reply = { plugin: 'peepo', surface: 'terminal', component: 'AssistantMessage', props: { text: 'Fixed :peepo_clap:', isFirstOfReply: true } } as const

test('off until /peepo on: replies and the system prompt are left alone', async ($, on) => {
  mock.store(on)
  const seen: string[] = []
  beneath(on, seen)
  await start($, on)
  await $.ui.mount(reply)
  expect(seen).toEqual(['Fixed :peepo_clap:'])
  const { sections } = await $.prompt.compose({ ...request, surfaces: ['terminal'] })
  expect(sections.map((s) => s.id)).toEqual(['intro'])
})

test('/peepo on draws peepos and names them in the system prompt, /peepo off stops', async ($, on) => {
  mock.store(on)
  const seen: string[] = []
  beneath(on, seen)
  await start($, on)
  const { text } = await peepo($, 'on')
  expect(text).toContain('Peepos on')
  await $.ui.mount(reply)
  expect(seen).toEqual([`Fixed ${clap}`])
  const { sections } = await $.prompt.compose({ ...request, surfaces: ['terminal'] })
  expect(sections.map((s) => s.id)).toEqual(['intro', 'peepo:guide'])
  expect(sections[1]).toMatchObject({ scope: 'session', text: GUIDE })
  await peepo($, 'off')
  await $.ui.mount(reply)
  expect(seen.at(-1)).toBe('Fixed :peepo_clap:')
})

test('a session starts with peepos on when an earlier one turned them on', async ($, on) => {
  mock.store(on, { on: true })
  const seen: string[] = []
  beneath(on, seen)
  await start($, on)
  await $.ui.mount(reply)
  expect(seen).toEqual([`Fixed ${clap}`])
})

test('a plugin that draws replies itself gets peepos in its Text, while on', async ($, on) => {
  mock.store(on)
  // as opencode-look does, from the table, never handing the text on (its own text, as if it stood above)
  on('ui.render', { component: 'AssistantMessage' }, (($: { ui: { resolve: (e: unknown) => { Text: (p: object) => unknown } } }, e: unknown) =>
    $.ui.resolve(e).Text({ children: ['Drawn ', ':peepo_gg:', ' and :peepo_clap:'] })) as never)
  await start($, on)
  const drawn = async () => (await $.ui.mount(reply)).find({ type: 'Text' })
  expect(await drawn()).toMatchObject({ children: ['Drawn ', ':peepo_gg:', ' and :peepo_clap:'] })
  await peepo($, 'on')
  expect(await drawn()).toMatchObject({ children: ['Drawn ', gg, ` and ${clap}`] })
})

/** a home at /home/u: what is written there, and a CLAUDE.md when one is given */
const home = (on: On, claudeMd?: string) => {
  const written: Record<string, string> = {}
  mock.env(on, { HOME: '/home/u' })
  on('fs.write', ((_$: unknown, e: { path: string; text: string }) => {
    written[e.path] = e.text
    return { value: undefined }
  }) as never)
  on('fs.read', ((_$: unknown, e: { path: string }) => {
    if (e.path === '/home/u/.claude/CLAUDE.md' && claudeMd !== undefined) return { value: claudeMd }
    throw new Error(`ENOENT: ${e.path}`)
  }) as never)
  return written
}

test('the guide is kept in ~/.claude/peepo/guide.md for CLAUDE.md to import, and /peepo asks for the import', async ($, on) => {
  mock.store(on)
  const written = home(on)
  await start($, on)
  expect(written['/home/u/.claude/peepo/guide.md']).toBe(`${GUIDE_OFF}\n`)
  await peepo($, 'on')
  expect(written['/home/u/.claude/peepo/guide.md']).toBe(`${GUIDE}\n`)
  expect((await peepo($, '')).text).toContain(IMPORT)
})

test('/peepo stops asking for the import once CLAUDE.md has it', async ($, on) => {
  mock.store(on)
  home(on, `# Mine\n\n${IMPORT}\n`)
  await start($, on)
  expect((await peepo($, '')).text).not.toContain(IMPORT)
})

test('/peepo alone shows the test frogs', async ($, on) => {
  mock.store(on)
  await start($, on)
  const { text } = await peepo($, '')
  expect(text).toContain(clap)
  expect(text).toContain('Peepos are off')
})
