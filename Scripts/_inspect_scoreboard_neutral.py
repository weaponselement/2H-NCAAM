import json
import glob

files = sorted(glob.glob('data/cache/scoreboard_daily/scoreboard_*.json'))
march_files = [f for f in files if '2026-03' in f]
print('March files:', len(march_files), 'Total:', len(files))

if march_files:
    with open(march_files[0]) as f:
        sb = json.load(f)
    games = sb.get('games', [])
    print('File:', march_files[0], '->', len(games), 'games')
    for item in games[:5]:
        g = item.get('game', {})
        keys = list(g.keys())
        title = g.get('title', '')
        bracket_round = g.get('bracketRound', '')
        bracket_id = g.get('bracketId', '')
        network = g.get('network', '')
        home_desc = (g.get('home') or {}).get('description', '')
        away_desc = (g.get('away') or {}).get('description', '')
        print(f'  title={title!r} bracketRound={bracket_round!r} bracketId={bracket_id!r} network={network!r}')
        print(f'    home_desc={home_desc!r} away_desc={away_desc!r}')

# Count games with bracketRound set across all files
bracket_games = 0
total_games = 0
neutral_titles = set()
for fpath in files:
    with open(fpath) as f:
        sb = json.load(f)
    for item in sb.get('games', []):
        g = item.get('game', {})
        total_games += 1
        br = g.get('bracketRound', '')
        bi = g.get('bracketId', '')
        if br or bi:
            bracket_games += 1
            title = g.get('title', '')
            neutral_titles.add(br)

print(f'\nTotal games across all files: {total_games}')
print(f'Games with bracketRound/bracketId: {bracket_games}')
print('bracketRound values seen:', sorted(neutral_titles)[:20])
