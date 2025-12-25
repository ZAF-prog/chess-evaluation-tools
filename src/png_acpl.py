#!/usr/bin/env python3
import chess.pgn
import numpy as np
import pandas as pd
import os
import re
import argparse

# --- CONFIGURATION ---
START_HALF_MOVE = 15  # White's 8th move
BOOTSTRAP_SAMPLES = 1000
ADVANTAGE_THRESHOLD = 300  # Discard moves if eval is > +3.00 or < -3.00

def extract_eval_score(comment):
    """
    Parses the [%eval score,depth] tag from a PGN comment.
    Returns the centipawn score from White's perspective.
    """
    match = re.search(r'\[%eval\s+(-?\d+)', comment)
    return int(match.group(1)) if match else None

def process_single_pgn(file_path):
    """
    Processes PGN and calculates CPL for moves where the position is 'competitive'
    (within +/- 300 centipawns).
    """
    player_losses = {}
    
    if not os.path.exists(file_path):
        print(f"Warning: File {file_path} not found.")
        return {}

    with open(file_path, 'r', encoding='utf-8') as pgn_file:
        while True:
            game = chess.pgn.read_game(pgn_file)
            if game is None:
                break
            
            # Filter: Only process games that have [%eval] annotations
            if not any("[%eval" in node.comment for node in game.mainline()):
                continue

            white_player = game.headers.get("White", "White")
            black_player = game.headers.get("Black", "Black")
            player_losses.setdefault(white_player, [])
            player_losses.setdefault(black_player, [])

            node = game
            prev_score = None
            half_move_counter = 0
            
            while node.mainline_moves():
                move = next(iter(node.mainline_moves()))
                node = node.variation(move)
                half_move_counter += 1
                curr_score = extract_eval_score(node.comment)
                
                # We need a baseline (prev_score) to calculate the loss of the current move
                if curr_score is not None and prev_score is not None:
                    # RULE 1: Only start from White's 8th move
                    # RULE 2: Only include moves if the position was not already > 300 CP advantage
                    if half_move_counter >= START_HALF_MOVE and abs(prev_score) <= ADVANTAGE_THRESHOLD:
                        
                        # WHITE'S MOVE (Odd half-moves)
                        if half_move_counter % 2 != 0:
                            loss = prev_score - curr_score
                            player_losses[white_player].append(max(0, loss))
                        
                        # BLACK'S MOVE (Even half-moves)
                        # Correcting sign for Black: positive change in White's eval is a loss for Black
                        else:
                            loss = curr_score - prev_score
                            player_losses[black_player].append(max(0, loss))
                
                # Update the score baseline for the next move
                if curr_score is not None:
                    prev_score = curr_score
                    
    return player_losses

def calculate_stats(all_data):
    """
    Performs ACPL calculation and bootstrapping for robust standard deviation.
    """
    summary = []
    for player, losses in all_data.items():
        if not losses:
            continue
            
        mean_acpl = np.mean(losses)
        
        # Bootstrapping: Resample the distribution of losses 1000 times
        # to calculate the standard deviation of the mean.
        boot_means = [np.mean(np.random.choice(losses, size=len(losses), replace=True)) 
                      for _ in range(BOOTSTRAP_SAMPLES)]
        robust_std = np.std(boot_means)
        
        summary.append({
            "Player": player,
            "ACPL": round(mean_acpl, 2),
            "Robust_StdDev": round(robust_std, 4),
            "Moves_Analyzed": len(losses)
        })
    return summary

def main():
    # Setup Argument Parsing for Positional Params or --pgn_list
    parser = argparse.ArgumentParser(description="Chess Tournament ACPL Analyzer")
    parser.add_argument("pgn_file", nargs="?", help="A single PGN filename")
    parser.add_argument("--pgn_list", help="Text file containing multiple PGN filenames")
    
    args = parser.parse_args()
    
    # Selection logic: prioritize pgn_list, otherwise take positional filename
    target_files = []
    if args.pgn_list:
        if not os.path.exists(args.pgn_list):
            print(f"Error: {args.pgn_list} not found.")
            return
        with open(args.pgn_list, 'r') as f:
            target_files = [line.strip() for line in f if line.strip()]
        output_name = os.path.splitext(os.path.basename(args.pgn_list))[0]
    elif args.pgn_file:
        target_files = [args.pgn_file]
        output_name = os.path.splitext(os.path.basename(args.pgn_file))[0]
    else:
        print("Usage: python script.py <filename.pgn> OR python script.py --pgn_list <list.txt>")
        return

    # Process all files and aggregate move losses per player
    total_stats = {}
    for filepath in target_files:
        print(f"Analyzing {filepath}...")
        file_results = process_single_pgn(filepath)
        for player, losses in file_results.items():
            total_stats.setdefault(player, []).extend(losses)

    # Calculate final statistics and export to CSV
    final_results = calculate_stats(total_stats)
    if final_results:
        df = pd.DataFrame(final_results)
        csv_filename = f"{output_name}_ACPL-stat.csv"
        df.to_csv(csv_filename, index=False)
        print(f"\nAnalysis complete. Results saved to: {csv_filename}")
        print(df)
    else:
        print("No valid moves with evaluations were found.")

if __name__ == "__main__":
    main()