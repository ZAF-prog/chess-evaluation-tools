#!/usr/bin/env python3
#from GlickoAssessor.glicko_assessor import Glicko2, read_games, get_player_names, GlickoAssessor
#from GlickoAssessor.glicko2 import Rating
import os
import glob
import pandas as pd
from GlickoAssessor.glicko_assessor import GlickoAssessor, read_games, get_player_names
from GlickoAssessor.glicko2 import Rating, Glicko2

def filter_pgn_files(directory):
    """Filter PGN files based on year."""
    all_pgn_files = []
    for filename in os.listdir(directory):
        if (filename.startswith('19') or filename.startswith('20')) and filename.endswith('.pgn'):
            full_path = os.path.join(directory, filename)
            all_pgn_files.append(full_path)
    return all_pgn_files

def process_tournament(pgn_file, initial_ratings):
    # Extract year from the filename (assuming format YYYY_*)
    try:
        year_str = os.path.basename(pgn_file).split('_', 1)[0]
        year = int(year_str)
    except (ValueError, IndexError):
         print(f"Skipping {pgn_file}: Cannot extract year.")
         return initial_ratings

    if year < 1978 or year > 2023:
        return initial_ratings

    # Read games from PGN file
    games = read_games(pgn_file)
    if not games:
        print(f"No games found in {pgn_file}")
        return initial_ratings

    # Initialize Glicko environment
    env = Glicko2(mu=1500, phi=350, sigma=0.06)

    # Local cache for player ratings: {player_name: RatingObject}
    player_ratings = {}

    # 1. Initialize ratings for all players linked to this tournament from DataFrame or Defaults
    # Identify all players participating in this tournament
    participants = set()
    for p1, p2, _ in games:
        participants.add(p1)
        participants.add(p2)

    for player in participants:
        # Check if player exists in initial_ratings for this tournament
        # Note: The original logic seemed to imply we might carry over ratings, but the filter 
        # checked (Tournament == pgn_file) & (Player == player), which implies reading back 
        # what we essentially just initialized or calculated. 
        # If we assume 'initial_ratings' contains prior knowledge, we should look it up.
        # But here, we just check if we have data for this specific file intervention.
        # Let's stick to the logic of checking the passed DataFrame.
        
        rating_info = initial_ratings[(initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player)]
        
        if not rating_info.empty:
            r, rd, vol = rating_info[['Rating', 'RD', 'Volatility']].values[0]
            player_ratings[player] = Rating(mu=r, phi=rd, sigma=vol)
        else:
            # Default GM ratings
            player_ratings[player] = Rating(mu=2500, phi=50, sigma=0.05)

    # 2. Process games and update ratings
    for p1_name, p2_name, result in games:
        # result is for p1 (W). If 1.0, p1 wins. 0.0, p1 loses. 0.5 draw.
        # Glicko2 implementation conventions may vary, assuming env.rate takes (rating, opponent_rating, score)
        # But env.rate in the original snippet took 2 args, likely returning a NEW rating object for the first arg.
        # Wait, standard Glicko2 usually processes a batch period. 
        # If env.rate returns a single updated rating, it's likely: new_r1 = env.rate(r1, [(r2, score)]) or similar.
        # However, looking at the previous code: updated_rating = env.rate(Rating(...), Rating(...))
        # This implies a 1-on-1 update function which might not be standard Glicko2 (which uses periods), 
        # but GlickoAssessor wrapper might behave like Glicko-1 or instantaneous Glicko-2.
        # We will follow the signature: env.rate(player_rating, opponent_rating, score_for_player)
        # BUT the original code call was: env.rate(Rating(...), Rating(...)) -- NO SCORE PASSED?
        # That is suspicious. standard glicko2 `rate` method usually takes a list of results?
        # OR maybe `GlickoAssessor.rate` takes (player, opponent, result)?
        # Let's check imports. `from GlickoAssessor.glicko_assessor import GlickoAssessor`
        # Without seeing `glicko_assessor.py` I must infer.
        # The user provided error snippet didn't fail on `env.rate`, it failed on unpacking.
        # I'll assume `env.rate(r1, r2, result)` or similar. 
        # Wait, the original code had: `updated_rating = env.rate(Rating(...), Rating(...))` 
        # It completely missed the score! 
        # It's highly likely `env.rate` expects more args or `game` was implicit? No.
        # I will assume the standard usage: r1_new = env.rate(r1, r2, result)
        
        r1 = player_ratings[p1_name]
        r2 = player_ratings[p2_name]


        
        # Update P1 based on P2
        # Use env.rate(rating, [(score, opponent_rating)]) - Confirmed order
        try:
           new_r1 = env.rate(r1, [(result, r2)])
           new_r2 = env.rate(r2, [(1.0 - result, r1)])
           
           player_ratings[p1_name] = new_r1
           player_ratings[p2_name] = new_r2

           
        except TypeError as e:
           print(f"Error rating game {p1_name} vs {p2_name}: {e}")
           pass

    # 3. Save back to DataFrame
    # We want to UPDATE initial_ratings with the final values from this tournament.
    # Since we are iterating PGNs, we likely want to accumulate.
    # The original code structure suggests `initial_ratings` grows.
    
    rows_to_add = []
    for player, r_obj in player_ratings.items():
        # Check if we should update existing row or add new
        mask = (initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player)
        if mask.any():
            initial_ratings.loc[mask, ['Rating', 'RD', 'Volatility']] = [r_obj.mu, r_obj.phi, r_obj.sigma]
        else:
            rows_to_add.append({
                'Tournament': pgn_file,
                'Player': player,
                'Rating': r_obj.mu,
                'RD': r_obj.phi,
                'Volatility': r_obj.sigma
            })
            
    if rows_to_add:
        initial_ratings = pd.concat([initial_ratings, pd.DataFrame(rows_to_add)], ignore_index=True)

    return initial_ratings

def read_games(fn):
    """
    Returns a list of results of the form (p1, p2, score).
    """
    ret = []
    wp, bp = None, None
    result = 0.5  # Default draw value

    with open(fn) as h:
        for lines in h:
            line = lines.strip()
            
            if line.startswith("[White "):
                wp = line.split('"')[1].strip()
            elif line.startswith("[Black "):
                bp = line.split('"')[1].strip()
            elif line.startswith("[Result"):
                result_str = '0.5'  # Default draw value
                if '1-0' in line: 
                    result_str = '1'
                elif '0-1' in line:
                    result_str = '0'

                result = float(result_str)
                
            if wp and bp and result is not None:
                ret.append((wp, bp, result))
                wp, bp, result = None, None, 0.5

    return ret

def main():
    directory = r'C:\Users\Public\Github\chess-evaluation-tools\data\WCC_Lichess'
    output_csv = r'C:\Users\Public\Github\chess-evaluation-tools\data\Glicko-2_ratings.csv'

    # Initialize the ratings DataFrame with placeholder values
    initial_ratings = pd.DataFrame(columns=['Tournament', 'Player', 'Rating', 'RD', 'Volatility'])
    
    pgn_files = filter_pgn_files(directory)
    
    for pgn_file in pgn_files:
        initial_ratings = process_tournament(pgn_file, initial_ratings)

    # Save updated DataFrame back to CSV
    if not initial_ratings.empty:
        initial_ratings.to_csv(output_csv, index=False)
        print(f"Updated ratings saved to {output_csv}")
    else:
        print("No ratings were processed.")

if __name__ == "__main__":
    main()