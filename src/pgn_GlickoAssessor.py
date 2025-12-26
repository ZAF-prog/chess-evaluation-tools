#!/usr/bin/env python3
#from glicko_assessor import GlickoAssessor, read_games, get_player_names, Rating
#from GlickoAssessor.glicko_assessor import GlickoAssessor, read_games, get_player_names, Rating
import os
import glob
import pandas as pd
from GlickoAssessor.glicko_assessor import GlickoAssessor, read_games, get_player_names

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
    year, _ = os.path.splitext(os.path.basename(pgn_file))[0].split('_', 1)
    if int(year) < 1978 or int(year) > 2023:
        return

    # Read games from PGN file
    games = read_games(pgn_file)

    # Extract players and update ratings
    env = GlickoAssessor(dbfile='example.db', init_rating=None, init_rating_deviation=None, init_volatility=None)
    
    for player in get_player_names(pgn_file):
        if (initial_ratings is not None) and ((initial_ratings['Tournament'] == pgn_file).any() and (initial_ratings['Player'] == player).any()):
            continue  # Skip already processed combination

        try:
            # Assuming initial ratings from 'AvgElo' column
            avg_elo = initial_ratings[(initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player)]['AvgElo'].values[0]
            rating = int(avg_elo)
            rd = 50
            volatility = 0.05
        except Exception:
            # If the combination is not found in the initial ratings, initialize with default values
            # defaults are chosen for GM level players
            rating = 2500
            rd = 50
            volatility = 0.05

        # Create new entry or update existing entry
        if (initial_ratings is None):
            initial_ratings = pd.DataFrame(columns=['Tournament', 'Player', 'Rating', 'RD', 'Volatility'])
        
        if (initial_ratings[(initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player)].empty):
            new_row = {'Tournament': [pgn_file],
                        'Player': [player],
                        'Rating': [rating],
                        'RD': [rd],
                        'Volatility': [volatility]}
            
            initial_ratings = pd.concat([initial_ratings, pd.DataFrame(new_row)], ignore_index=True)
        else:
            initial_ratings.at[(initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player), ['Rating', 'RD', 'Volatility']] = [rating, rd, volatility]
        
        # Simulate Glicko calculation (using the full algorithm)
        result_data = [(player, opponent, score) for opponent, score in games if player != opponent]
        
        updated_rating = env.rate(Rating(mu=rating, phi=rd, sigma=volatility), result_data)
        
        initial_ratings.at[(initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player), ['Rating', 'RD', 'Volatility']] = [updated_rating.mu, updated_rating.phi, updated_rating.sigma]

    return initial_ratings

def main():
    directory = r'C:\Users\Public\Github\chess-evaluation-tools\data\WCC_Lichess'
    output_csv = r'C:\Users\Public\Github\chess-evaluation-tools\data\Glicko-2_ratings.csv'

    # Initialize the ratings DataFrame with placeholder values
    initial_ratings = None
    
    pgn_files = filter_pgn_files(directory)
    
    for pgn_file in pgn_files:
        initial_ratings = process_tournament(pgn_file, initial_ratings)

    # Save updated DataFrame back to CSV
    if initial_ratings is not None:
        initial_ratings.to_csv(output_csv, index=False)
        print(f"Updated ratings saved to {output_csv}")
    else:
        print("No ratings were processed.")

if __name__ == "__main__":
    main()