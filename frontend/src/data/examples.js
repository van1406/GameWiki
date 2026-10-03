// Example questions shown as clickable chips under the search box.
export const EXAMPLE_QUESTIONS = {
  gta5: [
    'How do I complete The Jewel Store Job?',
    'Who is Michael?',
    'What weapons are available?',
    'Where is the Vangelico jewelry store?',
  ],
  minecraft: [
    'How do I craft a diamond pickaxe?',
    'How do I defeat the Ender Dragon?',
    'What do creepers drop?',
    'How do I get netherite?',
  ],
  forza_horizon_6: [
    'How do I unlock Legend Island?',
    'What are Wristbands?',
    'What is the best drift car?',
    'What are Touge Battles?',
  ],
}

const DEFAULT_EXAMPLES = [
  'What characters are in this game?',
  'What are the main missions?',
  'What items can I craft?',
  'Tell me about the map locations.',
]

export function examplesFor(gameId) {
  return EXAMPLE_QUESTIONS[gameId] || DEFAULT_EXAMPLES
}
