#!/usr/bin/env python3
import os
import argparse
import pandas as pd
import numpy as np
import chess
import chess.pgn
import chess.engine
from collections import defaultdict

# Constants from reference implementation
WDL_VALUES = [1, 0.5, 0]
WEIGHTED_GI = False

def calculate_expected_value(win_prob, draw_prob, loss_prob, turn):
    win_value, draw_value, loss_value = WDL_VALUES
    if turn == chess.WHITE:
        expected_value_white = win_prob * win_value + draw_prob * draw_value
        expected_value_black = loss_prob * win_value + draw_prob * draw_value
    else:
        expected_value_white = loss_prob * win_value + draw_prob * draw_value
        expected_value_black = win_prob * win_value + draw_prob * draw_value
    return expected_value_white, expected_value_black

def calculate_normalized_gi(gi):
    a, b = 157.57, 18.55
    return a + b * gi

def extract_eval(node):
    if node.comment:
        # Simple extraction for [%eval x.xx]
        # This is a fallback if python-chess doesn't automatically parse it into comment
        # behavior depends on version, but let's try to use common logic or the text
        pass
    
    # python-chess might not parse %eval by default into a purely numeric structure unless using specific visitors
    # But usually extract_eval_from_node in the reference implementation uses node.eval()
    # node.eval() works if the PGN was read with a visitor or if we parse the comment manually.
    # The reference implementation uses node.eval() which implies the evaluations are propagated or parsed.
    # However, standard chess.pgn.read_game doesn't automatically parse [%eval] into .eval() unless configured.
    # We will manually parse the comment for safety.
    
    import re
    match = re.search(r'\[%eval\s+([-+]?[\d\.]+|#-?\d+)\]', node.comment)
    if match:
        val_str = match.group(1)
        if '#' in val_str:
            # Mate
            mate_in = int(val_str.replace('#', ''))
            score = chess.engine.Mate(mate_in)
            return chess.engine.PovScore(score, node.turn()) # Eval is usually white-relative in PGN? No, usually check PGN spec.
            # Lichess PGNs: [%eval 0.23] is usually White's perspective?
            # Actually Lichess standard says "Evaluation in centipawns ... from the point of view of the side to move" OR white?
            # Reference implementation: cp_value = node_evaluation.pov(chess.WHITE).score()
            # If we parse text manually, we need to be careful.
            # Let's trust the comment parsing if possible, but for now let's reuse the simple float extraction
            # and wrap it in a pseudo-score object if needed, or just return float (pawns).
            pass
            
    return None

# Simplified eval parsing from comment
def get_eval_cp(node):
    # Returns score in centipawns from White's perspective
    import re
    if not node.comment:
        return None
    match = re.search(r'\[%eval\s+([-+]?[\d\.]+|#-?\d+)\]', node.comment)
    if not match:
        return None
    val_str = match.group(1)
    
    if '#' in val_str:
        mate_in = int(val_str.replace('#', ''))
        # Mate score: strictly large number
        if mate_in > 0: return 10000 
        else: return -10000
    else:
        # Float strings like 0.35 are usually pawns. Convert to cp.
        return int(float(val_str) * 100)

def process_game(game):
    white = game.headers.get("White", "?")
    black = game.headers.get("Black", "?")
    date = game.headers.get("Date", "????.??.??")
    result_str = game.headers.get("Result", "*")
    
    white_elo = int(game.headers.get("WhiteElo", 0)) if game.headers.get("WhiteElo", "0").isdigit() else 0
    black_elo = int(game.headers.get("BlackElo", 0)) if game.headers.get("BlackElo", "0").isdigit() else 0

    if result_str == '1-0': result = 1.0
    elif result_str == '0-1': result = 0.0
    elif result_str == '1/2-1/2': result = 0.5
    else: result = 0.5 # Default/Unknown

    # Evaluation processing
    node = game
    pawns_list = []
    
    # Initial position
    # If root has eval? usually not, but check
    cp = get_eval_cp(node)
    if cp is not None:
        pawns_list.append(cp / 100.0)
    else:
        pawns_list.append(0.0) # Start from 0.0 if not specified
        
    for move in game.mainline_moves():
        node = node.variation(move)
        cp = get_eval_cp(node)
        if cp is not None:
            pawns_list.append(cp / 100.0)
        else:
            # If missing eval, repeat previous (simple interpolation or gap filling)
            if len(pawns_list) > 0:
                pawns_list.append(pawns_list[-1])
            else:
                pawns_list.append(0.0)
                
    if len(pawns_list) < 2:
        return None # Not analyzed

    # ACPL Calcs
    white_losses = []
    black_losses = []
    
    # pawns_list[0] is start (White to move)
    # pawns_list[1] is after 1. Move (Black to move)
    # diff = current - previous
    
    for i in range(1, len(pawns_list)):
        diff = pawns_list[i] - pawns_list[i-1]
        # Move i was made by:
        # i=1 (post 1. WhiteMove), White made it.
        # Eval is always White perspective in our get_eval_cp (standard Lichess PGN behavior)
        
        # If White moved, and eval dropped, it's a loss.
        # drop = prev - curr
        
        if i % 2 == 1: # White's move just happened
            loss = (pawns_list[i-1] - pawns_list[i]) * 100
            white_losses.append(max(0, loss))
        else: # Black's move just happened
            # Black wants eval to go DOWN.
            # Loss if eval went UP.
            # gain = curr - prev
            loss = (pawns_list[i] - pawns_list[i-1]) * 100
            black_losses.append(max(0, loss))

    white_acpl = np.mean(white_losses) if white_losses else 0
    black_acpl = np.mean(black_losses) if black_losses else 0
    
    # GI/Missed Points Logic
    white_gpl = 0
    black_gpl = 0
    white_move_count = 0
    black_move_count = 0
    
    # Need WDL
    # Using chess.engine.Cp to calculate wdl prob
    # Reference: premove_eval = Cp(int(100 * val))
    
    for i in range(1, len(pawns_list)):
        prev_cp = int(pawns_list[i-1] * 100)
        curr_cp = int(pawns_list[i] * 100)
        
        pre_score = chess.engine.Cp(prev_cp)
        post_score = chess.engine.Cp(curr_cp)
        
        # WDL
        # Note: chess.engine.Cp.wdl() might assume standard Stockfish model
        # We need check if wdl() handles perspective. PovScore does.
        # But here we have absolute cents (White perspective).
        # We can construct PovScore(Cp(x), WHITE)
        
        # Use simple Score.wdl() which returns Wdl object (with wins/draws/losses)
        # instead of PovScore.wdl() which returns PovWdl (which might not have wins directly exposed in older versions or behaving differently)
        pre_wdl = pre_score.wdl()
        post_wdl = post_score.wdl()
        
        pre_w, pre_d, pre_l = pre_wdl.wins/1000, pre_wdl.draws/1000, pre_wdl.losses/1000
        post_w, post_d, post_l = post_wdl.wins/1000, post_wdl.draws/1000, post_wdl.losses/1000
        
        turn = chess.WHITE if i % 2 == 1 else chess.BLACK # Who made the move leading to i
        
        pre_exp_w, pre_exp_b = calculate_expected_value(pre_w, pre_d, pre_l, turn)
        post_exp_w, post_exp_b = calculate_expected_value(post_w, post_d, post_l, turn)
        
        if turn == chess.WHITE:
            # White moved. Expected value for White dropped?
            loss = pre_exp_w - post_exp_w
            white_gpl += max(0, loss)
            white_move_count += 1
        else:
            loss = pre_exp_b - post_exp_b
            black_gpl += max(0, loss)
            black_move_count += 1
            
    # Calculate GI
    # Needs game result
    # Logic from reference:
    # white_gi = (RelevantResultValue - white_gpl) / WinVal
    
    win_val = WDL_VALUES[0]
    draw_val = WDL_VALUES[1]
    loss_val = WDL_VALUES[2]

    # result var is float (1.0, 0.5, 0.0) -> match to WDL_VALUES?
    # WDL_VALUES = [1, 0.5, 0] so they match nicely
    
    if result == 1.0:
        w_res_val = win_val
        b_res_val = loss_val
    elif result == 0.5:
        w_res_val = draw_val
        b_res_val = draw_val
    else:
        w_res_val = loss_val
        b_res_val = win_val
        
    white_gi_raw = (w_res_val - white_gpl) / win_val
    black_gi_raw = (b_res_val - black_gpl) / win_val
    
    white_gi = calculate_normalized_gi(white_gi_raw)
    black_gi = calculate_normalized_gi(black_gi_raw)
    
    return {
        'Tournament': '',
        'White': white,
        'Black': black,
        'WhiteResult': result,
        'BlackResult': 1.0 - result,
        'WhiteElo': white_elo,
        'BlackElo': black_elo,
        'white_gi': white_gi,
        'black_gi': black_gi,
        'white_missed_points': white_gpl,
        'black_missed_points': black_gpl,
        'white_acpl': white_acpl,
        'black_acpl': black_acpl,
        'white_moves': white_move_count,
        'black_moves': black_move_count
    }

def calculate_player_stats(pgn_file):
    tournament = os.path.basename(pgn_file)
    games_data = []
    
    # Use utf-8 encoding for PGNs (common for Lichess)
    try:
        f = open(pgn_file, encoding='utf-8')
    except Exception as e:
        print(f"Error opening file {pgn_file}: {e}")
        return pd.DataFrame()

    with f:
        while True:
            try:
                game = chess.pgn.read_game(f)
            except ValueError as e:
                print(f"Error reading game in {pgn_file}: {e}")
                break
            if game is None:
                break
            
            g_data = process_game(game)
            if g_data:
                g_data['Tournament'] = tournament
                games_data.append(g_data)

    if not games_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(games_data)
    
    # Aggregation per player
    # We have one row per game with White and Black stats.
    # Split into two rows per game (one for white player, one for black player)
    
    white_df = df[['Tournament', 'White', 'WhiteResult', 'WhiteElo', 'white_gi', 'white_missed_points', 'white_acpl', 'white_moves']].copy()
    white_df.columns = ['Tournament', 'Player', 'Result', 'Elo', 'gi', 'missed_points', 'acpl', 'moves']
    white_df['IsWhite'] = True
    
    black_df = df[['Tournament', 'Black', 'BlackResult', 'BlackElo', 'black_gi', 'black_missed_points', 'black_acpl', 'black_moves']].copy()
    black_df.columns = ['Tournament', 'Player', 'Result', 'Elo', 'gi', 'missed_points', 'acpl', 'moves']
    black_df['IsWhite'] = False
    
    combined = pd.concat([white_df, black_df], ignore_index=True)
    
    # Now aggregations
    stats = []
    for (tourn, player), group in combined.groupby(['Tournament', 'Player']):
        total_games = len(group)
        wins = len(group[group['Result'] == 1.0])
        draws = len(group[group['Result'] == 0.5])
        score = wins + 0.5 * draws
        
        avg_elo = group['Elo'].mean()
        # TPR
        tpr = avg_elo + 400 * (score - total_games/2) / total_games if total_games > 0 else avg_elo
        
        total_moves = group['moves'].sum()
        
        avg_acpl = group['acpl'].mean()
        avg_gi = group['gi'].mean()
        avg_missed_points = group['missed_points'].mean()
        
        gi_median = group['gi'].median()
        missed_points_median = group['missed_points'].median()
        
        # Split white/black stats
        white_games = group[group['IsWhite']]
        black_games = group[~group['IsWhite']]
        
        avg_gi_white = white_games['gi'].mean() if not white_games.empty else 0
        avg_gi_black = black_games['gi'].mean() if not black_games.empty else 0
        
        avg_missed_points_white = white_games['missed_points'].mean() if not white_games.empty else 0
        avg_missed_points_black = black_games['missed_points'].mean() if not black_games.empty else 0
        
        stats.append({
            'Tournament': tourn,
            'Player': player,
            'Elo': avg_elo,
            'TPR': tpr,
            'total_game_count': total_games,
            'total_moves': total_moves,
            'avg_acpl': avg_acpl,
            'avg_gi': avg_gi,
            'avg_missed_points': avg_missed_points,
            'avg_missed_points_white': avg_missed_points_white,
            'avg_missed_points_black': avg_missed_points_black,
            'avg_gi_white': avg_gi_white,
            'avg_gi_black': avg_gi_black,
            'gi_median': gi_median,
            'missed_points_median': missed_points_median
        })
        
    return pd.DataFrame(stats)

def generate_summary_stats(player_stats, summary_stats_path):
    # Calculate summary statistics
    # Only describe numeric columns
    numeric_cols = ['Elo', 'TPR', 'total_game_count', 'total_moves', 'avg_acpl', 'avg_gi', 'avg_missed_points', 
                    'avg_missed_points_white', 'avg_missed_points_black', 'avg_gi_white', 'avg_gi_black', 
                    'gi_median', 'missed_points_median']
    
    summary_stats = player_stats[numeric_cols].describe().transpose()
    summary_stats = summary_stats[['mean', '50%', 'std', 'min', 'max']]
    summary_stats.columns = ['Mean', 'Median', 'Std Dev', 'Min', 'Max']
    summary_stats = summary_stats.round(2)

    # Calculate total moves and games
    total_moves = player_stats['total_moves'].sum()
    total_games = player_stats['total_game_count'].sum() / 2 # Since we summed player games, actual games is half

    # Add total moves and games to summary stats
    summary_stats.loc['Total Moves'] = [total_moves, total_moves, 0, total_moves, total_moves]
    summary_stats.loc['Total Games'] = [total_games, total_games, 0, total_games, total_games]

    # Reorder rows for better readability
    desired_order = ['Total Moves', 'Total Games', 'avg_gi', 'avg_missed_points', 'avg_missed_points_white', 'avg_missed_points_black', 'avg_gi_white', 'avg_gi_black', 'avg_acpl', 'Elo', 'TPR', 'gi_median', 'missed_points_median']
    # Filter only those that exist
    desired_order = [c for c in desired_order if c in summary_stats.index]
    summary_stats = summary_stats.reindex(desired_order)

    # Save summary statistics to CSV if path provided
    if summary_stats_path:
        summary_stats.to_csv(summary_stats_path)

    return summary_stats

def main():
    parser = argparse.ArgumentParser(description="Generate player statistics from PGN files and optionally merge with additional CSV.")
    parser.add_argument('pgn_file', nargs='?', help='PGN file containing chess games')
    parser.add_argument('--directory', type=str, default=r'C:\Users\Public\Github\chess-evaluation-tools\data\WCC_Lichess', help='Directory containing PGN files')
    parser.add_argument('--input_csv', help='Path to additional CSV to merge with player stats')
    parser.add_argument('--output_csv', default=None, help='Output CSV file path for player stats')
    
    args = parser.parse_args()

    # Determine output CSV path
    if args.output_csv:
        output_csv_path = args.output_csv
    elif args.input_csv:
        base, _ = os.path.splitext(args.input_csv)
        output_csv_path = f"{base}_TPR-stats.csv"
    else:
        output_csv_path = 'player_stats.csv'

    pgn_files = []
    if args.pgn_file:
        pgn_files.append(args.pgn_file)
    elif args.directory and os.path.exists(args.directory):
        for f in os.listdir(args.directory):
            if f.endswith(".pgn"):
                pgn_files.append(os.path.join(args.directory, f))
    
    if not pgn_files:
        print("No PGN files found or provided.")
        return
    
    all_player_stats = []
    for pgn_file in pgn_files:
        print(f"Processing {pgn_file}...")
        try:
            stats = calculate_player_stats(pgn_file)
            if not stats.empty:
                all_player_stats.append(stats)
        except Exception as e:
            print(f"Error processing {pgn_file}: {e}")
            import traceback
            traceback.print_exc()

    if all_player_stats:
        player_stats = pd.concat(all_player_stats, ignore_index=True)
    else:
        player_stats = pd.DataFrame()

    # Merge with additional CSV if provided
    if args.input_csv and os.path.exists(args.input_csv) and not player_stats.empty:
        additional_data = pd.read_csv(args.input_csv)
        # Outer merge on ['Tournament', 'Player']
        player_stats = player_stats.merge(additional_data, on=['Tournament', 'Player'], how='outer')
        # Coalesce columns if they exist in both
        for col in ['Elo', 'TPR', 'total_game_count', 'total_moves', 'avg_acpl', 'avg_gi']:
            if f'{col}_x' in player_stats.columns and f'{col}_y' in player_stats.columns:
                player_stats[col] = player_stats[f'{col}_y'].combine_first(player_stats[f'{col}_x'])
                player_stats.drop(columns=[f'{col}_x', f'{col}_y'], inplace=True)
    
    if not player_stats.empty:
        # Rename columns to match required output format
        output_df = player_stats[['Tournament', 'Player', 'Elo', 'total_game_count', 'total_moves', 'TPR', 'avg_gi', 'avg_acpl']].copy()
        output_df.columns = ['Tournament', 'Player', 'Elo_Rating', 'Total_Games', 'Total_Moves', 'Elo_TPR', 'avg_gi', 'avg_acpl']
        
        # Round numeric columns for cleaner output
        output_df['Elo_Rating'] = output_df['Elo_Rating'].round(0)
        output_df['Elo_TPR'] = output_df['Elo_TPR'].round(0)
        output_df['avg_gi'] = output_df['avg_gi'].round(2)
        output_df['avg_acpl'] = output_df['avg_acpl'].round(2)
        
        # Save to CSV
        output_df.to_csv(output_csv_path, index=False)
        print(f"Player statistics saved to {output_csv_path}")
        print(f"Total players: {len(output_df)}")
    else:
        print("No valid player statistics generated.")

if __name__ == "__main__":
    main()