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
    """
    Extracts centipawn score from [%eval score,depth]. 
    Handles:
    - Integers: [%eval 15] -> 15
    - Floats (pawn units): [%eval 0.15] -> 15
    - Mate tags: [%eval #3] -> 10000, [%eval #-2] -> -10000
    - Signs: [%eval -0.5] -> -50
    """
    # Match group 1: the numeric value (including . and -) or the mate tag (#)
    match = re.search(r'\[%eval\s+([-+]?[#\d\.]+)', comment)
    if not match:
        return None
    
    val_str = match.group(1)
    
    # Handle mate tags
    if '#' in val_str:
        try:
            mate_num_str = val_str.replace('#', '')
            if not mate_num_str or mate_num_str == '+':
                return 10000
            if mate_num_str == '-':
                return -10000
            mate_num = int(mate_num_str)
            return 10000 if mate_num > 0 else -10000
        except ValueError:
            return 10000 if '#' in val_str and '-' not in val_str else -10000

    # Handle numeric evaluations
    try:
        val = float(val_str)
        # If it looks like pawn units (has a decimal point and is small, or just has a decimal point)
        # Standard PGN [%eval] can be either CP or pawns. 
        # Most modern tools use pawn units (floats) or CP (integers).
        if '.' in val_str:
            return int(round(val * 100))
        else:
            return int(val)
    except ValueError:
        return None

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
                
                # Check the starting position comment (if any) for initial eval
                if game.comment:
                    prev_eval = parse_eval(game.comment)

                while node.mainline_moves():
                    move = next(iter(node.mainline_moves()))
                    node = node.variation(move)
                    half_move_idx += 1
                    curr_eval = parse_eval(node.comment)
                    
                    if curr_eval is not None and prev_eval is not None:
                        # Logic: Only analyze if we have a continuous chain of evaluations.
                        # If a move is missing an eval, prev_eval becomes None until the next eval is found.
                        if half_move_idx >= START_HALF_MOVE and abs(prev_eval) <= ADVANTAGE_THRESHOLD:
                            if half_move_idx % 2 != 0: # White move
                                loss = prev_eval - curr_eval
                                player_losses[white].append(max(0, loss))
                            else: # Black move
                                loss = curr_eval - prev_eval
                                player_losses[black].append(max(0, loss))
                    
                    # Update prev_eval for the next move
                    # If current move has no evaluation, we cannot calculate the loss for the NEXT move either.
                    prev_eval = curr_eval
                    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return []

    results = []
    for player, losses in player_losses.items():
        if not losses: continue
        
        mean_acpl = np.mean(losses)
        
        # Bootstrap for Robust SD
        if len(losses) > 1:
            boot_means = [np.mean(np.random.choice(losses, size=len(losses), replace=True)) 
                          for _ in range(BOOTSTRAP_SAMPLES)]
            robust_sd = np.std(boot_means)
        else:
            robust_sd = 0.0
        
        ratings = player_ratings.get(player, [])
        avg_elo = round(np.mean(ratings), 1) if ratings else "N/A"
        
        results.append({
            "Tournament": tournament_name,
            "Player": player,
            "ACPL": round(mean_acpl, 2),
            "Robust_SD": round(robust_sd, 4),
            "AvgElo": avg_elo,
            "AnalyzedMoves": len(losses)
        })
    return results

def fuzzy_resolve_path(path):
    """
    Attempts to resolve a path that might be missing a directory separator.
    Example: 'dataWCC_Lichess1986.pgn' -> 'data/WCC_Lichess/1986.pgn'
    It iteratively checks if a prefix of the path is an existing directory,
    and then if the remaining part exists within that directory.
    """
    if os.path.exists(path):
        return path

    # Normalize separators for processing
    normalized_path = path.replace('\\', '/')
    
    # Try to find a split point where the left part is a directory
    parts = normalized_path.split('/')
    
    # Case 1: The separator is missing between the last directory and the filename
    # e.g., C:/Users/Public/.../data/WCC_Lichess1986.pgn
    if len(parts) > 1:
        base_dir = '/'.join(parts[:-1])
        problematic_part = parts[-1]
        
        if os.path.isdir(base_dir):
            # Try to split the 'problematic_part' into (existing_folder, filename)
            # We iterate through all subdirectories in base_dir
            try:
                for entry in os.scandir(base_dir):
                    if entry.is_dir():
                        folder_name = entry.name
                        if problematic_part.startswith(folder_name):
                            remainder = problematic_part[len(folder_name):]
                            # Handle cases where there might be yet another missing separator
                            # or just the filename with an optional leading separator
                            if remainder.startswith('_') or remainder.startswith('-') or remainder[0].isdigit():
                                # Try joined with a slash
                                candidate = os.path.join(base_dir, folder_name, remainder.lstrip('/\\'))
                                if os.path.exists(candidate):
                                    return candidate
            except Exception:
                pass

    # Case 2: General scan (more expensive but thorough)
    # We walk up the path and try to find where it breaks
    temp_path = normalized_path
    while temp_path and temp_path != '/':
        parent = os.path.dirname(temp_path)
        if os.path.isdir(parent):
            # We found a valid parent. Now see if the 'tail' can be matched inside 'parent'
            tail = normalized_path[len(parent):].lstrip('/')
            try:
                for entry in os.scandir(parent):
                    if tail.startswith(entry.name):
                        sub_remainder = tail[len(entry.name):].lstrip('/')
                        if not sub_remainder: # It was just the folder
                            continue
                        candidate = os.path.join(parent, entry.name, sub_remainder)
                        if os.path.exists(candidate):
                            return candidate
            except Exception:
                pass
        temp_path = parent

    return None

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Statistical analysis of PGN files to evaluate player accuracy.\n\n"
            "Key Logic:\n"
            "- Starts analysis from White's 9th move (half-move 17).\n"
            "- Discards moves where position advantage > 300 CP.\n"
            "- Uses [%eval] tags for calculation (supports floats/CP/mate).\n"
            "- Computes bootstrapped SD for consistency."
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument("pgn_file", nargs="?", help="Path to a single PGN file.")
    parser.add_argument("--pgn_list", metavar="LIST_FILE", help="Text file with PGN filenames (one per line).")

    args = parser.parse_args()
    
    if not args.pgn_file and not args.pgn_list:
        parser.print_help()
        sys.exit(1)
    
    target_files = []
    if args.pgn_list:
        if not os.path.exists(args.pgn_list):
            print(f"Error: List file '{args.pgn_list}' not found.")
            return
        with open(args.pgn_list, 'r', encoding='utf-8') as f:
            # More robust path parsing: strip whitespace, then quotes, then whitespace again
            target_files = [line.strip().strip('"').strip("'").strip() for line in f if line.strip()]
        input_basename = os.path.splitext(os.path.basename(args.pgn_list))[0]
    else:
        # Also clean up the single file path
        target_files = [args.pgn_file.strip().strip('"').strip("'").strip()]
        input_basename = os.path.splitext(os.path.basename(args.pgn_file))[0]

    all_rows = []
    for f_path in target_files:
        if not f_path: continue
        
        resolved_path = f_path
        if not os.path.exists(f_path):
            # Attempt fuzzy resolution
            fuzzy_path = fuzzy_resolve_path(f_path)
            if fuzzy_path:
                print(f"Fuzzy resolved: {f_path} -> {fuzzy_path}")
                resolved_path = fuzzy_path
            else:
                print(f"Warning: File not found: {f_path}")
                continue
            
        print(f"Processing: {resolved_path}...")
        all_rows.extend(process_single_pgn(resolved_path))

    if all_rows:
        df = pd.DataFrame(all_rows)
        output_csv = f"{input_basename}_ACPL-stat.csv"
        df.to_csv(output_csv, index=False)
        print(f"\nAnalysis complete. {len(all_rows)} players analyzed.")
        print(f"Results saved to: {output_csv}")
    else:
        print("No valid evaluation data found for analysis.")

if __name__ == "__main__":
    main()
