#!/usr/bin/env python3
"""
PGN ACPL-Elo REGRESSION ANALYZER
================================

This program performs a multivariable linear regression analysis on chess player data.
It models Average Elo (AvgElo) as a function of Average Centipawn Loss (ACPL) 
and its variability (Robust_SD).

Model: AvgElo ~ beta0 + beta1 * ACPL + beta2 * Robust_SD

Input: CSV file with columns [Tournament, Player, ACPL, Robust_SD, AvgElo, AnalyzedMoves]
Output: CSV file with fitted values, residuals, and regression parameters.
"""

import pandas as pd
import numpy as np
import statsmodels.api as sm
import argparse
import os
import sys

def perform_regression(df):
    """
    Performs OLS regression: AvgElo ~ ACPL + Robust_SD.
    Iteratively removes variables with p-value > 0.1.
    Returns (model, variables_used).
    """
    initial_vars = ['ACPL', 'Robust_SD']
    current_vars = initial_vars.copy()
    
    while True:
        # Define X and y
        X = df[current_vars]
        X = sm.add_constant(X)
        y = df['AvgElo']
        
        # Fit OLS model
        model = sm.OLS(y, X).fit()
        
        # Check p-values for independent variables (exclude 'const')
        p_values = model.pvalues.drop('const')
        
        # Find variables with p > 0.1
        bad_vars = p_values[p_values > 0.1]
        
        if bad_vars.empty or not current_vars:
            break
            
        # Remove the variable with the highest p-value
        var_to_remove = bad_vars.idxmax()
        print(f"Variable '{var_to_remove}' has p-value {bad_vars[var_to_remove]:.4f} > 0.1. Removing and re-fitting...")
        current_vars.remove(var_to_remove)
        
    return model, current_vars

def main():
    parser = argparse.ArgumentParser(description="Multivariable regression of AvgElo vs ACPL and Robust_SD.")
    parser.add_argument("input_csv", help="Path to the input ACPL-stat CSV file.")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_csv):
        print(f"Error: File '{args.input_csv}' not found.")
        sys.exit(1)
        
    # Load data
    try:
        df_raw = pd.read_csv(args.input_csv)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)
        
    # Prepare data: Convert to numeric and handles 'N/A'
    # We create a copy to avoid SettingWithCopyWarning
    df = df_raw.copy()
    
    cols_to_fix = ['ACPL', 'Robust_SD', 'AvgElo']
    for col in cols_to_fix:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # Drop rows with missing values in our target columns
    df_clean = df.dropna(subset=cols_to_fix).copy()
    
    if df_clean.empty:
        print("Error: No valid data rows with numeric AvgElo, ACPL, and Robust_SD found.")
        sys.exit(1)
        
    print(f"Analyzing {len(df_clean)} data points...")
    
    # Perform Regression with iterative filtering
    model, final_vars = perform_regression(df_clean)
    
    # Print Summary to Console
    print("\n--- REGRESSION SUMMARY ---")
    print(model.summary())
    
    # Extract Parameters (handle cases where variables were removed)
    intercept = model.params['const']
    slope_acpl = model.params.get('ACPL', 0.0)
    slope_sd = model.params.get('Robust_SD', 0.0)
    
    # Extra statistics requested
    r2 = model.rsquared
    intercept_se = model.bse['const']
    
    # Calculate Fitted Values and Residuals
    df_clean['Fitted_Elo'] = model.fittedvalues.round(1)
    df_clean['Residual'] = (df_clean['AvgElo'] - df_clean['Fitted_Elo']).round(1)
    
    # Add parameters to the dataframe for the output
    df_clean['Intercept'] = round(intercept, 4)
    df_clean['Intercept_SD'] = round(intercept_se, 4)
    df_clean['Slope_ACPL'] = round(slope_acpl, 4) if 'ACPL' in final_vars else "N/A"
    df_clean['Slope_SD'] = round(slope_sd, 4) if 'Robust_SD' in final_vars else "N/A"
    df_clean['R2'] = round(r2, 4)
    
    # Prepare Final Output
    # We want to keep Tournament and Player for identification
    output_cols = [
        'Tournament', 'Player', 'AvgElo', 'ACPL', 'Robust_SD', 'Fitted_Elo', 
        'Residual', 'Intercept', 'Intercept_SD', 'Slope_ACPL', 'Slope_SD', 'R2'
    ]
    df_output = df_clean[output_cols]
    
    # Generate Output Filename in the same directory as input
    input_dir = os.path.dirname(args.input_csv)
    basename = os.path.splitext(os.path.basename(args.input_csv))[0]
    output_filename = f"{basename}-fit.csv"
    output_csv = os.path.join(input_dir, output_filename) if input_dir else output_filename
    
    # Write to File
    try:
        df_output.to_csv(output_csv, index=False)
        print(f"\nResults successfully saved to: {output_csv}")
    except Exception as e:
        print(f"Error saving output CSV: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
