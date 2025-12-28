#!/usr/bin/env python3
#from GlickoAssessor.glicko_assessor import Glicko2, read_games, get_player_names, GlickoAssessor
#from GlickoAssessor.glicko2 import Rating
import os
import glob
import argparse
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
        # Check if player exists in initial_ratings for this tournament
        rating_info = initial_ratings[(initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player)]
        
        if not rating_info.empty:
            r, rd, vol = rating_info[['Rating', 'RD', 'Volatility']].values[0]
            player_ratings[player] = Rating(mu=r, phi=rd, sigma=vol)
        else:
            # Default GM ratings
            player_ratings[player] = Rating(mu=2500, phi=50, sigma=0.05)

    # 2. Process games and update ratings
    for game in games:
        p1_name = game['White']
        p2_name = game['Black']
        result = game['Result']

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
    rows_to_add = []
    
    # Ensure DataFrame has new columns if they don't exist
    for col in ['StartDate', 'EndDate', 'AvgElo']:
        if col not in initial_ratings.columns:
            initial_ratings[col] = None

    for player, r_obj in player_ratings.items():
        avg_elo = player_avg_elos.get(player)
        
        # Check if we should update existing row or add new
        mask = (initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player)
        
        if mask.any():
            initial_ratings.loc[mask, ['Rating', 'RD', 'Volatility', 'StartDate', 'EndDate', 'AvgElo']] = \
                [r_obj.mu, r_obj.phi, r_obj.sigma, start_date, end_date, avg_elo]
        else:
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
            
    if rows_to_add:
        initial_ratings = pd.concat([initial_ratings, pd.DataFrame(rows_to_add)], ignore_index=True)

    return initial_ratings

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
    parser.add_argument('--output_csv', type=str, default=r'C:\Users\Public\Github\chess-evaluation-tools\data\Glicko-2_ratings.csv', help='Output CSV file path')
    
    args = parser.parse_args()
    
    directory = args.directory
    output_csv = args.output_csv

    # Initialize the ratings DataFrame with placeholder values
    initial_ratings = pd.DataFrame(columns=['Tournament', 'Player', 'Rating', 'RD', 'Volatility', 'StartDate', 'EndDate', 'AvgElo'])
    
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