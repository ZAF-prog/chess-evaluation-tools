#!/usr/bin/env python3
#from GlickoAssessor.glicko_assessor import Glicko2, read_games, get_player_names, GlickoAssessor
#from GlickoAssessor.glicko2 import Rating
import os
import glob
import argparse
import pandas as pd
from GlickoAssessor.glicko_assessor import GlickoAssessor, read_games, get_player_names
from GlickoAssessor.glicko2 import Rating, Glicko2
from collections import defaultdict

def filter_pgn_files(directory):
    """Filter PGN files based on year."""
    all_pgn_files = []
    for filename in sorted(os.listdir(directory)):
        if (filename.startswith('19') or filename.startswith('20')) and filename.endswith('.pgn'):
            full_path = os.path.join(directory, filename)
            all_pgn_files.append(full_path)
    return all_pgn_files

def process_tournament(pgn_file, history_ratings):
    # Extract year from the filename (assuming format YYYY_*)
    try:
        year_str = os.path.basename(pgn_file).split('_', 1)[0]
        year = int(year_str)
    except (ValueError, IndexError):
         print(f"Skipping {pgn_file}: Cannot extract year.")
         return []

    if year < 1978 or year > 2023:
        return []

    # Read games from PGN file
    games = read_games(pgn_file)
    if not games:
        print(f"No games found in {pgn_file}")
        return []

    # Initialize Glicko environment
    env = Glicko2(mu=1500, phi=350, sigma=0.06)

    # Local cache for player ratings: {player_name: RatingObject}
    player_ratings = {}
    
    # Metadata collections
    tournament_dates = []
    player_elos = {} # {player_name: [list_of_elos]}

    # 1. Initialize ratings and collect metadata
    participants = set()
    for game in games:
        p1 = game['White']
        p2 = game['Black']
        participants.add(p1)
        participants.add(p2)
        
        # Collect dates
        if game['Date'] and '?' not in game['Date']:
            tournament_dates.append(game['Date'])
            
        # Collect Elos
        if p1 not in player_elos: player_elos[p1] = []
        if p2 not in player_elos: player_elos[p2] = []
        
        if game['WhiteElo']: player_elos[p1].append(float(game['WhiteElo']))
        if game['BlackElo']: player_elos[p2].append(float(game['BlackElo']))

    # Determine StartDate and EndDate
    start_date = min(tournament_dates) if tournament_dates else None
    end_date = max(tournament_dates) if tournament_dates else None

    # Calculate AvgElo for each player
    player_avg_elos = {}
    for p in participants:
         elos = player_elos.get(p, [])
         if elos:
             player_avg_elos[p] = int(sum(elos) / len(elos))
         else:
             player_avg_elos[p] = None

    for player in participants:
        # Check if player exists in history_ratings (carry over from previous tournaments)
        if player in history_ratings:
            player_ratings[player] = history_ratings[player]
        else:
            # Default GM ratings for new players
            player_ratings[player] = Rating(mu=2500, phi=50, sigma=0.05)

    # 2. Process games and collect results (Batch Processing)
    player_results = defaultdict(list)

    for game in games:
        p1_name = game['White']
        p2_name = game['Black']
        result = game['Result']

        r1 = player_ratings[p1_name]
        r2 = player_ratings[p2_name]
        
        # Store match results for batch update.
        # r1 and r2 are the ratings at the START of the tournament/rating period.
        player_results[p1_name].append((result, r2))
        player_results[p2_name].append((1.0 - result, r1))

    # 3. Update ratings based on collected results
    for player in participants:
        if player in player_results:
            try:
                # env.rate calculates the new rating based on the list of (score, opponent_rating)
                new_rating = env.rate(player_ratings[player], player_results[player])
                player_ratings[player] = new_rating
            except TypeError as e:
                print(f"Error rating player {player}: {e}")

    # Update history_ratings with the new ratings at the end of the tournament
    for player, r_obj in player_ratings.items():
        history_ratings[player] = r_obj

    # 4. Return new rows
    rows_to_add = []
    
    for player, r_obj in player_ratings.items():
        avg_elo = player_avg_elos.get(player)
        
        rows_to_add.append({
            'Tournament': pgn_file,
            'Player': player,
            'Rating': r_obj.mu,
            'RD': r_obj.phi,
            'Volatility': r_obj.sigma,
            'StartDate': start_date,
            'EndDate': end_date,
            'AvgElo': avg_elo
        })

    return rows_to_add

def read_games(fn):
    """
    Returns a list of dictionaries with game info.
    """
    ret = []
    game_info = {'White': None, 'Black': None, 'Result': 0.5, 'Date': None, 'WhiteElo': None, 'BlackElo': None}
    
    with open(fn) as h:
        for lines in h:
            line = lines.strip()
            
            if line.startswith("[White "):
                game_info['White'] = line.split('"')[1].strip()
            elif line.startswith("[Black "):
                game_info['Black'] = line.split('"')[1].strip()
            elif line.startswith("[Date "):
                game_info['Date'] = line.split('"')[1].strip()
            elif line.startswith("[WhiteElo "):
                try:
                    game_info['WhiteElo'] = int(line.split('"')[1].strip())
                except ValueError:
                    pass
            elif line.startswith("[BlackElo "):
                try:
                    game_info['BlackElo'] = int(line.split('"')[1].strip())
                except ValueError:
                    pass
            elif line.startswith("[Result"):
                result_str = '0.5' 
                if '1-0' in line: 
                    result_str = '1'
                elif '0-1' in line:
                    result_str = '0'
                game_info['Result'] = float(result_str)
            
            if line.startswith("[Event "):
                 # New game starting. If we have a previous game recorded, save it.
                 if game_info['White'] and game_info['Black']:
                     ret.append(game_info)
                 
                 # Reset
                 game_info = {'White': None, 'Black': None, 'Result': 0.5, 'Date': None, 'WhiteElo': None, 'BlackElo': None}

    # Push last game
    if game_info['White'] and game_info['Black']:
         ret.append(game_info)
         
    return ret

def main():
    parser = argparse.ArgumentParser(description="Calculate Glicko-2 ratings from PGN files.")
    parser.add_argument('--directory', type=str, default=r'C:\Users\Public\Github\chess-evaluation-tools\data\WCC_Lichess', help='Directory containing PGN files')
    parser.add_argument('--input_csv', type=str, default=None, help='Path to additional data file (CSV) to merge with output')
    parser.add_argument('--output_csv', type=str, default=r'C:\Users\Public\Github\chess-evaluation-tools\data\Glicko-2_ratings.csv', help='Output CSV file path')
    
    args = parser.parse_args()
    
    directory = args.directory
    output_csv = args.output_csv

    # Initialize the ratings DataFrame with placeholder values
    # initial_ratings was confusingly named, it is now just an accumulator.
    # We will build the list of dicts first.
    all_rating_rows = []
    
    # State dictionary to carry ratings across tournaments
    history_ratings = {} # {player_name: RatingObject}

    pgn_files = filter_pgn_files(directory)
    
    for pgn_file in pgn_files:
        new_rows = process_tournament(pgn_file, history_ratings)
        all_rating_rows.extend(new_rows)

    # Save updated DataFrame back to CSV
    if all_rating_rows:
        final_df = pd.DataFrame(all_rating_rows)
        # Reorder columns to match expectation
        cols = ['Tournament', 'Player', 'Rating', 'RD', 'Volatility', 'StartDate', 'EndDate', 'AvgElo']
        # Ensure all cols exist
        for c in cols:
            if c not in final_df.columns: final_df[c] = None
        # Don't restrict columns yet if we are merging
        # final_df = final_df[cols] 

        # Merge with external data if provided
        if args.input_csv and os.path.exists(args.input_csv):
            try:
                print(f"Reading additional data from {args.input_csv}...")
                additional_data = pd.read_csv(args.input_csv)
                
                # Normalize Tournament column to basename for better matching
                final_df['Tournament'] = final_df['Tournament'].apply(os.path.basename)
                if 'Tournament' in additional_data.columns:
                     additional_data['Tournament'] = additional_data['Tournament'].apply(os.path.basename)

                # Outer merge to keep all records
                final_df = final_df.merge(additional_data, on=['Tournament', 'Player'], how='outer')
                print(f"Merged with additional data. Total rows: {len(final_df)}")
            except Exception as e:
                print(f"Error reading/merging {args.input_csv}: {e}")

        final_df.to_csv(output_csv, index=False)
        print(f"Updated ratings saved to {output_csv}")
    else:
        print("No ratings were processed.")

if __name__ == "__main__":
    main()