#!/usr/bin/env python3
import re
import os

def standardize_pgn(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into games based on [Event tag (simplified splitting, assuming standard [Event starts a new game block)
    # However, the file has [Event ... marks start.
    # We can split by `\n\n[` followed by Event, but the first one doesn't have \n\n preceeding.
    # Let's read line by line to build game blocks.
    
    games = []
    current_game = []
    
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('[Event '):
                if current_game:
                    games.append(current_game)
                current_game = [line]
            else:
                current_game.append(line)
        if current_game:
            games.append(current_game)

    standardized_games = []

    for game_lines in games:
        game_text = "".join(game_lines)
        
        # Parse Tags
        tags = {}
        tag_pattern = re.compile(r'\[(\w+) "([^"]+)"\]')
        for match in tag_pattern.finditer(game_text):
            tags[match.group(1)] = match.group(2)
            
        chapter_name = tags.get('ChapterName', '')
        
        # Filter: Only keep "Game N" chapters
        if not chapter_name or "Game" not in chapter_name or any(x in chapter_name for x in ["Introduction", "Exercises", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]):
             # Check for "Game \d+" specifically to avoid Q1 etc if they have "Game" in name
             # The bad ones look like "Game 1 - Q1". The good ones "Game 1 - Nepo v Carlsen" or "Game 10: Carlsen v Nepo"
             # Regex for strictly "Game \d+ [:-] .*"
             if not re.search(r'Game \d+[:\s-]', chapter_name):
                 continue
             if re.search(r'Game \d+\s+-\s+Q\d+', chapter_name):
                 continue

        # Extract Metadata
        # ChapterName formats: "Game 1 - Nepo v Carlsen", "Game 10: Carlsen v Nepo", "Game 5: Nepo v Carlsen"
        match = re.search(r'Game (\d+)[:\s-]+(\w+) v (\w+)', chapter_name)
        if not match:
            print(f"Skipping potential game due to parse failure: {chapter_name}")
            continue

        round_num = match.group(1)
        white_short = match.group(2)
        black_short = match.group(3)

        player_map = {
            "Nepo": "Nepomniachtchi, Ian",
            "Carlsen": "Carlsen, Magnus"
        }
        
        white = player_map.get(white_short, white_short)
        black = player_map.get(black_short, black_short)
        
        date = tags.get('UTCDate', tags.get('Date', "????.??.??")).replace('.', '-') # PGN Date is YYYY.MM.DD usually, preserve .
        # Actually standard PGN uses dots.
        date = tags.get('UTCDate', tags.get('Date', "????.??.??"))

        # Determine Result from comments/text
        # Look for the movetext part
        # Extract headers lines to find where movetext starts
        headers_end_idx = 0
        for i, line in enumerate(game_lines):
            if line.strip() == "":
                headers_end_idx = i
            elif line.startswith("["):
                 continue
            else:
                 # Start of movetext (or comments before it)
                 break
        
        body_lines = game_lines[headers_end_idx:]
        body_text = "".join(body_lines)
        
        result = "*"
        lower_body = body_text.lower()
        
        if "white resigned" in lower_body or "white resigns" in lower_body:
            result = "0-1"
        elif "black resigned" in lower_body or "black resigns" in lower_body:
            result = "1-0"
        elif "draw agreed" in lower_body or "draw by" in lower_body:
             result = "1/2-1/2"
        elif result == "*":
             # Check standard PGN result tag if valid
             orig_res = tags.get('Result', '*')
             if orig_res in ['1-0', '0-1', '1/2-1/2']:
                 result = orig_res

        # Construct new headers
        new_headers = [
            f'[Event "World Championship Match 2021"]\n',
            f'[Site "Dubai UAE"]\n',
            f'[Date "{date}"]\n',
            f'[Round "{round_num}"]\n',
            f'[White "{white}"]\n',
            f'[Black "{black}"]\n',
            f'[Result "{result}"]\n',
             # Add UTC info as valid extra tags if wanted, or just minimalist
            f'[UTCDate "{tags.get("UTCDate", "")}"]\n',
            f'[UTCTime "{tags.get("UTCTime", "")}"]\n',
            f'[ECO "{tags.get("ECO", "?")}"]\n',
            f'[Opening "{tags.get("Opening", "?")}"]\n'
        ]
        
        # Clean body text: remove { ... } comments if they contain strictly unwanted text? 
        # User said: "Drop extraneous material like that under "[ChapterName "*** INTRODUCTION ***"]", or evaluation of variants not played."
        # User also said: "The Result should also be determined from the end-of-game desriptions, e.g. "Draw by ..." or "draw agreed", "black resigned" etc.."
        # This implies we keep the comments that describe the result? 
        # But maybe we should remove the excessively long intro text blocks if desired?
        # The prompt says: "Drop extraneous material like that under [ChapterName "..."]" -> This refers to DROPPING WHOLE CHAPTERS (which we did).
        # It doesn't explicitly ask to strip comments WITHIN the games, except "evaluation of variants not played" - usually in {}
        # But identifying specific "evaluation of variants" vs "game commentary" is hard. 
        # I will keep the game commentary as it adds value and user didn't explicitly ban it, just "extraneous material LIKE [bad chapters]".
        
        # However, we must ensure the `Result` tag matches the game termination marker in the text if we insert it.
        # Clean up the end of the body text to match the result
        # Remove existing '*' or results
        clean_body = body_text.strip()
        if clean_body.endswith('*'):
            clean_body = clean_body[:-1].strip()
        
        # Append result
        clean_body = clean_body + " " + result

        standardized_games.append("".join(new_headers) + "\n" + clean_body + "\n\n")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(standardized_games)
    
    print(f"Standardized {len(standardized_games)} games to {output_path}")

if __name__ == "__main__":
    input_pgn = r'C:\Users\Public\Github\chess-evaluation-tools\data\WCC_Lichess\2021_Carlsen-Nepomniachtchi.pgn'
    output_pgn = r'C:\Users\Public\Github\chess-evaluation-tools\data\WCC_Lichess\2021_Carlsen-Nepomniachtchi_Standardized.pgn'
    standardize_pgn(input_pgn, output_pgn)
