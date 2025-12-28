#!/usr/bin/env python3
#from GlickoAssessor.glicko_assessor import Glicko2, read_games, get_player_names, GlickoAssessor
#from GlickoAssessor.glicko2 import Rating
import os
import glob
import pandas as pd
from GlickoAssessor.glicko_assessor import GlickoAssessor, read_games, get_player_names
from GlickoAssessor.glicko2 import Rating

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
        if initial_ratings is None:
            rating = 2500  # Defaults for GM level players
            rd = 50
            volatility = 0.05

            new_row = {'Tournament': [pgn_file],
                        'Player': [player],
                        'Rating': [rating],
                        'RD': [rd],
                        'Volatility': [volatility]}
            
            initial_ratings = pd.DataFrame(new_row, index=[0])
        else:
            if (initial_ratings['Tournament'] == pgn_file).any() and (initial_ratings['Player'] == player).any():
                continue  # Skip already processed combination

            rating_info = initial_ratings[(initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player)]
            if not rating_info.empty:
                rating, rd, volatility = rating_info[['Rating', 'RD', 'Volatility']].values[0]
            else:
                rating = 2500  
                rd = 50
                volatility = 0.05

        # Simulate Glicko calculation (using the full algorithm)
        for game in games[:10]:  # Print only the first 10 games for debugging purposes
            print(f"Game: {game}")  # Debugging print statement

            try:
                opponent, score = game
            except ValueError as e:
                print(f"Error unpacking game: {game} with error: {e}")
                continue

            updated_rating = env.rate(Rating(mu=rating, phi=rd, sigma=volatility), Rating(mu=2500, phi=350, sigma=0.06))

            rating, rd, volatility = updated_rating.mu, updated_rating.phi, updated_rating.sigma
            initial_ratings.loc[(initial_ratings['Tournament'] == pgn_file) & (initial_ratings['Player'] == player), ['Rating', 'RD', 'Volatility']] = [rating, rd, volatility]

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