# Generalized RPG Mechanics and Game Path

## Core Mechanics
A set of reusable mechanics for narrative RPGs, weighted to shape the experience:
- **Dialogue (40%)**: Talk to NPCs to gain info, persuade, or influence. E.g., question Queen Lyra, negotiate with an alien.
- **Decision-Making (30%)**: Make choices that shape the story. E.g., trust an NPC, pick a path.
- **Exploration (20%)**: Investigate locations or objects for clues. E.g., search a castle room, scan a spaceship.
- **Challenge (10%)**: Overcome light obstacles like traps or puzzles. E.g., dodge a guard, hack a door.

Player actions (text commands) map to these mechanics, interpreted by the LLM based on weights.

## Game Path
A linear-with-branches progression with 5 states, side paths, and tricks:
1. **Introduction**:
   - Objective: Meet NPC, learn conflict (e.g., kingdom threat, sabotage plot).
   - Mechanics: Dialogue, Decision-Making.
   - Transition: Choose a path to next state.
2. **Exploration**:
   - Objective: Investigate for clues.
   - Mechanics: Exploration, Dialogue, Challenge.
   - Side Path: False lead (e.g., chase a rumor, find a broken drone). Reward: Item or lore.
   - Transition: Clue leads to next state.
3. **Ally or Obstacle**:
   - Objective: Gain ally or clear challenge.
   - Mechanics: Dialogue, Decision-Making, Challenge.
   - Trick: NPC lies or obstacle misleads (e.g., false meeting spot, tricky riddle).
   - Transition: Success opens new lead.
4. **Revelation**:
   - Objective: Uncover a secret.
   - Mechanics: Exploration, Decision-Making, Dialogue.
   - Side Path: Fake lead (e.g., wrong room, fake data). Reward: Lore or hint.
   - Transition: Secret sets up climax.
5. **Climax**:
   - Objective: Resolve conflict (win condition, e.g., save kingdom, stop saboteur).
   - Mechanics: Dialogue, Decision-Making, Challenge.
   - Transition: Game ends.

## Misleading Paths and Tricks
- **Side Paths**: 1-2 per state (except climax). Seem promising but loop back. Offer rewards (items, lore) to keep interest.
- **Tricks**: Deceptions or obstacles (e.g., lying NPC, trap). Fair hints provided; failure has light setbacks (e.g., retry).
- **Engagement**: Paths deepen story, vary mechanics, and give rewards to avoid frustration.

## Example Applications
- **Medieval RPG**: Save kingdom from traitor. Dialogue-heavy, with exploration and light challenges.
- **Sci-Fi RPG**: Prevent sabotage on a space station. Same mechanics, flavored for sci-fi (e.g., scan labs, negotiate with aliens).

## Notes
- Weights are fixed for testing (40/30/20/10) but can be tweaked.
- Ensure tricks have clear hints to stay fair.
- Vary side path rewards to maintain engagement.