# peepo for Claude Code

Claude reacts with peepos, the little green frogs of Twitch and Slack, inline in its replies like any emoji, in full
colour and at the size of the text:

> That fixed the flaky test 🐸 and the build is green again.

(The 🐸 stands in for a real peepo, which a README can't show.)

Claude picks a peepo when one fits the moment: a fix that lands, a win, a nasty bug, a puzzle. One or two in a reply at
most, and never in code, commits or files.

## Requirements

- **macOS** with Python 3 (`xcode-select --install` if `python3` is missing)
- **iTerm2, Ghostty or kitty.** Terminal.app and the VS Code terminal can't map characters to a font, so peepos can't
  show there.

## Install

```
/plugin install peepo --marketplace joakimunge/cc-peepo
```

Answer `y` to add the marketplace and pick a scope. Then build the font for your terminal:

```
/peepo setup
```

Setup takes a minute or two. It finds your terminal (through tmux too) and its font and size, downloads the peepos and
builds a font that matches your text, installs it, and points your terminal at it:

- **Ghostty:** adds a `font-codepoint-map` line to your config. Reload the config (`cmd+shift+,`) or restart Ghostty.
- **kitty:** adds a `symbol_map` line to `kitty.conf`. Reload the config (`ctrl+cmd+,`) or restart kitty.
- **iTerm2:** quit iTerm2 when setup says so. A helper then sets your default profile and opens iTerm2 again (iTerm2
  overwrites its settings while it runs, so they can only change while it's closed). It turns on *Use a different font
  for non-ASCII text*, using your normal font, because iTerm2 only reads the font exception while that's on.

Then check and switch on:

```
/peepo        shows two test frogs: if you see them, the font works
/peepo on     Claude starts using peepos
```

If setup picks the wrong terminal, name it: `/peepo setup iterm2`, `/peepo setup ghostty` or `/peepo setup kitty`. If
you change your terminal font or size, run setup again.

### Team and Enterprise accounts

On a Team or Enterprise account, Claude Code's built-in security default keeps installed plugins out of Claude's
system prompt, so Claude never hears about the peepos from the plugin. The plugin keeps the same guide in
`~/.claude/peepo/guide.md` instead; add this line to your `~/.claude/CLAUDE.md` and Claude reads it from the next
session on:

```
@~/.claude/peepo/guide.md
```

`/peepo` reminds you while that line is missing. While peepos are off, the file only says so.

## Commands

| Command | |
|---|---|
| `/peepo setup [terminal]` | Build and install the font, and point the terminal at it |
| `/peepo` | Test frogs, and whether peepos are on |
| `/peepo on` | Claude uses peepos; kept across sessions |
| `/peepo off` | Claude stops using them |

## How it works

- Each peepo is three private-use characters (`U+E400` to `U+E5DF`), a range Nerd Fonts leave empty. Each character
  draws one slice of the frog, so it takes three cells.
- The font stores the slices as PNG pictures in an `sbix` table, the way Apple Color Emoji does. It's sized from your
  terminal font's own cell: three cells wide and 1.3 lines tall, centred on the text.
- While peepos are on, the plugin adds a short section to Claude's system prompt that names every peepo and when to
  use one (or, on Team and Enterprise accounts, your `CLAUDE.md` imports it). In each reply it turns shortcodes like
  `:peepo_clap:` (outside code) into the frog's characters, before the reply is drawn.
- It works with other plugins that draw replies themselves, such as OpenCode look: the text they draw with turns
  shortcodes into frogs too. There a shortcode inside inline code becomes a frog as well.
- iTerm2 needs two workarounds, which setup handles. iTerm2 only draws a glyph in colour if its font's family is
  Apple's emoji font, so the font's family is `AppleColorEmoji`, distinct from Apple's own `Apple Color Emoji`. iTerm2
  also places emoji lower than text, so on iTerm2 the frogs are raised to match.

Everything setup makes goes in `~/.claude/peepo/`: a Python environment with `fonttools` and `pillow`, the downloaded
pictures, the built font, and a copy of your iTerm2 settings from before.

## The pictures

The peepos are other people's art, uploaded to [slackmojis](https://slackmojis.com). Peepo itself is based on Pepe the
Frog by Matt Furie. **This repository contains no pictures:** `hooks/peepos.ts` lists names and links, and each machine
downloads its own copy during setup. The MIT licence covers the code only.

## Uninstall

```
/plugin uninstall peepo
```

Then delete `~/Library/Fonts/PeepoEmoji-*.ttf` and `~/.claude/peepo/`, and remove the peepo lines from your terminal:
the marked lines in your Ghostty or kitty config, or the Special Exception in iTerm2
(*Settings > Profiles > Text*). Setup kept your previous iTerm2 settings in `~/.claude/peepo/iterm2-before-peepo.plist`.

## Status

Developed on **iTerm2**, where the font and its settings are in daily use. **Ghostty and kitty support follows their
documented config but is untested so far.** Issues and screenshots are welcome.
