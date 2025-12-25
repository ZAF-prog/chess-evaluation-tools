#!/usr/bin/env python3
"""
PGN ACPL STATISTICAL ANALYZER
=============================

This program performs a statistical accuracy analysis of chess games stored in PGN format.
It specifically targets "Average Centipawn Loss" (ACPL) based on engine evaluations 
embedded within the PGN comments (e.g., [%eval 0.15]).

CORE LOGIC:
1. Data Source: Only games containing [%eval] tags are processed. Others are discarded.
2. Opening Filter: Analysis starts from White's 9th move (half-move 17) to exclude 
   extended opening book theory.
3. Advantage Filter: Moves are discarded if the evaluation before the move is outside 
   the range of +/- 300 centipawns (3.00 pawns).
4. ACPL Calculation:
   - White Loss: (Previous Eval) - (Current Eval)
   - Black Loss: (Current Eval) - (Previous Eval)
   - All losses are capped at a minimum of 0.
5. Robust Statistics: Calculates a bootstrapped Standard Deviation (1,000 samples) 
   to provide a stable measure of consistency.
6. Rating Analysis: Calculates the average Elo for each player per tournament/file.

OUTPUT:
Generates a CSV file named '{input_basename}_ACPL-stat.csv' with columns:
Tournament, Player, ACPL, Robust_SD, AvgElo, AnalyzedMoves.
"""

import chess.pgn
import numpy as np
import pandas as pd
import os
import re
import argparse
import sys

# --- CONSTANTS ---
START_HALF_MOVE = 17  # White's move 9
BOOTSTRAP_SAMPLES = 1000
ADVANTAGE_THRESHOLD = 300  # +/- 3.00 pawns

def parse_eval(comment):
    """Extracts centipawn score from [%eval score,depth]. Handles mate tags (#)."""
    match = re.search(r'\[%eval\s+([-#]?\d+)', comment)
    if not match:
        return None
    val_str = match.group(1)
    if '#' in val_str:
        mate_num = int(val_str.replace('#', ''))
        return 10000 if mate_num > 0 else -10000
    return int(val_str)

def process_single_pgn(file_path):
    """Analyzes one PGN file as a distinct tournament/match entity."""
    player_losses = {}
    player_ratings = {}
    tournament_name = os.path.basename(file_path)

    try:
        with open(file_path, 'r', encoding='utf-8') as pgn:
            while True:
                game = chess.pgn.read_game(pgn)
                if game is None: break
                
                if not any("[%eval" in node.comment for node in game.mainline()):
                    continue

                white = game.headers.get("White", "Unknown")
                black = game.headers.get("Black", "Unknown")
                
                for side, name in [("WhiteElo", white), ("BlackElo", black)]:
                    rating = game.headers.get(side)
                    if rating and rating.isdigit():
                        player_ratings.setdefault(name, []).append(int(rating))
                
                player_losses.setdefault(white, [])
                player_losses.setdefault(black, [])

                node = game
                prev_eval = None
                half_move_idx = 0
                
                while node.mainline_moves():
                    move = next(iter(node.mainline_moves()))
                    node = node.variation(move)
                    half_move_idx += 1
                    curr_eval = parse_eval(node.comment)
                    
                    if curr_eval is not None and prev_eval is not None:
                        if half_move_idx >= START_HALF_MOVE and abs(prev_eval) <= ADVANTAGE_THRESHOLD:
                            if half_move_idx % 2 != 0: # White
                                loss = prev_eval - curr_eval
                                player_losses[white].append(max(0, loss))
                            else: # Black
                                loss = curr_eval - prev_eval
                                player_losses[black].append(max(0, loss))
                    
                    if curr_eval is not None:
                        prev_eval = curr_eval
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []

    results = []
    for player, losses in player_losses.items():
        if not losses: continue
        
        mean_acpl = np.mean(losses)
        boot_means = [np.mean(np.random.choice(losses, size=len(losses), replace=True)) 
                      for _ in range(BOOTSTRAP_SAMPLES)]
        
        ratings = player_ratings.get(player, [])
        avg_elo = round(np.mean(ratings), 1) if ratings else "N/A"
        
        results.append({
            "Tournament": tournament_name,
            "Player": player,
            "ACPL": round(mean_acpl, 2),
            "Robust_SD": round(np.std(boot_means), 4),
            "AvgElo": avg_elo,
            "AnalyzedMoves": len(losses)
        })
    return results

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Statistical analysis of PGN files to evaluate player accuracy.\n\n"
            "Key Logic:\n"
            "- Starts analysis from White's 9th move (half-move 17).\n"
            "- Discards moves where position advantage > 300 CP.\n"
            "- Uses [%eval] tags for calculation.\n"
            "- Computes bootstrapped SD for consistency."
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument("pgn_file", nargs="?", help="Path to a single PGN file.")
    parser.add_argument("--pgn_list", metavar="LIST_FILE", help="Text file with PGN filenames (one per line).")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()
    
    target_files = []
    if args.pgn_list:
        if not os.path.exists(args.pgn_list):
            print(f"Error: List file '{args.pgn_list}' not found.")
            return
        with open(args.pgn_list, 'r') as f:
            # FIX: .strip(" \n\r\t\"'") removes whitespace AND quotes
            target_files = [line.strip().strip('"').strip("'") for line in f if line.strip()]
        input_basename = os.path.splitext(os.path.basename(args.pgn_list))[0]
    else:
        target_files = [args.pgn_file.strip('"').strip("'")]
        input_basename = os.path.splitext(os.path.basename(args.pgn_file))[0]

    all_rows = []
    for f_path in target_files:
        if not f_path: continue
        print(f"Processing: {f_path}...")
        all_rows.extend(process_single_pgn(f_path))

    if all_rows:
        df = pd.DataFrame(all_rows)
        output_csv = f"{input_basename}_ACPL-stat.csv"
        df.to_csv(output_csv, index=False)
        print(f"\nAnalysis complete. Results saved to: {output_csv}")
    else:
        print("No valid evaluation data found for analysis.")

if __name__ == "__main__":
    main()