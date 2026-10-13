/** whether Claude uses peepos and replies draw them; kept across sessions in the store too */
export type IsOn = boolean

declare module 'claude-code' {
  interface PluginState {
    peepo: { on: IsOn }
  }
}
