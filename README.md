# HelpyHand
Alternative Credit Scoring for Financial Inclusion A Synthetic Data ML System (HelpyHand PoC)

## Overview

HelpyHand is a Proof of Concept (PoC) for enabling nano-credits to unbanked or underbanked populations in Colombia using alternative risk signals. The system generates synthetic data simulating client behavior and builds a risk scoring model.

## Architecture

- **Data Layer**: Synthetic data generation with risk-correlated signals
- **Feature Engineering**: Aggregated features from multiple sources
- **Modeling**: Probability of Default (PD) prediction
- **API**: Risk score exposure (future)

## Data Model

See [docs/data_model.md](docs/data_model.md) for detailed entity-relationship diagram and table schemas.

## Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Run data generation: `python run_data_generation.py --n-clients 10000`
3. Launch descriptives dashboard: `streamlit run descriptives/app.py`
4. Explore in notebook: `notebooks/01_data_model_and_synthetic_design.ipynb`

## Project Structure

- `src/data_generation/`: Modular synthetic data generators
- `notebooks/`: Exploratory analysis and design
- `descriptives/`: Streamlit dashboard for data analysis
- `data/`: Generated datasets
- `docs/`: Detailed documentation

## Key Components

- Risk Generating Process (RGP): Latent score + heuristics for realistic correlations
- Tables: clients, demographics, digital_sessions, transactions, payments, loan_applications, risk_features, target
- Validation: Integrity checks and monotonicity analysis
