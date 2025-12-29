# chess-accuracy-tools
Study relationship between chess playing metrics, Elo strength and engine evaluations.

# ♟️ Chess Accuracy and Strength Analysis

This repository is dedicated to investigating the relationship between calculated **chess engine results** (e.g., Stockfish evaluations) and established **player strength measures** (e.g., Elo rating, Glicko-2 etc.).

It serves as a central hub for the source code, analysis notes, and collated data necessary for this research.

---

## 📁 Repository Structure

The project is organized into four main directories to separate logic from assets:

| Directory | Content | Licensing Note |
| :--- | :--- | :--- |
| **`src/`** | Python scripts for data processing, accuracy score calculation, and statistical analysis. | MIT License |
| **`data/`** | Collated CSV files containing game records and raw data for analysis. | CC BY 4.0 |
| **`binaries/`** | Executable files, including the **Stockfish engine binary** used for generating accuracy scores. | N/A (External License) |
| **`notes/`** | Plain text logs, research findings, and documentation notes. | CC BY 4.0 |

---

## ⚙️ Requirements & Setup

To use the code and contribute to this project, you will need the following tools installed on your system:

### 1. Git and Git LFS

This repository uses **Git Large File Storage (Git LFS)** to manage the large CSV data files and the Stockfish binary efficiently.

```bash
# Install Git LFS (needed on both Windows and Debian)
git lfs install

# Clone the repository
git clone https://github.com/ZAF-prog/chess-evaluation-tools/

### 2. Other repos pulled for local use

This repository uses the following repos for local use:

- [GlickoAssessor](https://github.com/fsmosca/GlickoAssessor) by Ferdinand Mosca, utilized in src/pgn_GlickoAssessor.py
 (not mirrored by this repo, masked by .gitignore)
- utility code from  [World-Chess-Championships](https://github.com/drmehmetismail/World-Chess-Championships) by "drmehmetismail"*"
 (not mirrored by this repo, masked by .gitignore)
