# HelpyHand
Alternative Credit Scoring for Financial Inclusion - A Synthetic Data ML System (PoC)

## Overview

HelpyHand is a Proof of Concept (PoC) system designed to enable **nano-credits** to unbanked or underbanked populations in Colombia using **alternative risk signals**. Instead of traditional credit histories, it builds a Probability of Default (PD) prediction model using synthetic behavioral data from digital interactions, transaction patterns, and payment history.

The system follows a **data-to-model-to-API** pipeline: Data Generation → Risk Features → Model Training → API Serving.

## Purpose

This project demonstrates how machine learning can assess creditworthiness for underserved populations by leveraging non-traditional data sources like:
- Digital engagement patterns (website visits, session duration, conversion rates)
- Transaction behavior (frequency, amounts, merchant categories)
- Payment history (on-time rates, delinquency patterns)
- Demographic and employment information

## Architecture and Workflow

### Core Components
1. **Data Generation Pipeline**: Modular synthetic data creation with risk-correlated signals
2. **Feature Engineering**: Aggregation of behavioral and demographic features into a risk index
3. **Model Training**: Logistic regression for PD prediction with feature selection
4. **API Service**: RESTful API for real-time risk scoring
5. **Analysis Dashboard**: Streamlit app for data exploration and validation

### End-to-End Workflow
```
Data Generation → Data Validation → Model Training → API Deployment → Risk Predictions
```

## Project Structure

### Root Level
- `README.md`: This file - comprehensive project documentation
- `requirements.txt`: Python dependencies
- `run_data_generation.py`: Main script to execute data generation pipeline

### `data/`
- `generated/`: Output directory for synthetic CSV files
  - `clients.csv`: Core client demographics (income, employment, bancarización, age, etc.)
  - `demographics.csv`: Extended demographic details
  - `digital_sessions.csv`: Digital behavior data (visits, conversions, device info)
  - `transactions.csv`: Financial transaction records
  - `loan_applications.csv`: Credit application history
  - `payments.csv`: Payment and delinquency data
  - `risk_features.csv`: Aggregated feature matrix for modeling
  - `target.csv`: Default probability and binary labels
  - `model_mt.csv`: Master table combining features and target
- `raw/`: Directory for any raw input data (currently empty)

### `src/`
- `mt_generator.py`: Utility for master table generation
- `api/`: API service components
  - `app.py`: FastAPI application with endpoints
  - `predictor.py`: Prediction service class
  - `schemas.py`: Pydantic models for request/response validation
  - `README_API.md`: API-specific documentation
- `config/`: Configuration files
  - `config.ini`: Training and data configuration
- `data_generation/`: Modular data generation pipeline
  - `__init__.py`: Package initialization
  - `clients_generator.py`: Base client table generation
  - `demographics_generator.py`: Demographic features
  - `digital_sessions_generator.py`: Digital behavior simulation
  - `loan_applications_generator.py`: Credit application simulation
  - `payments_generator.py`: Payment history generation
  - `pipeline.py`: Orchestrates the complete data generation workflow
  - `risk_feature_builder.py`: Feature aggregation and risk index calculation
  - `target_builder.py`: Default target construction using logistic function
  - `transactions_generator.py`: Transaction record generation
  - `validation.py`: Data integrity and correlation validation
- `training/`: Model training components
  - `feature_selection.py`: Feature selection utilities
  - `preprocess.py`: Data preprocessing pipeline
  - `train_logistic_regression.py`: Main training script

### `models/`
- `logistic_regression/`: Trained model artifacts
  - `full/`: Models trained with all available features
    - `runs/{timestamp}/`: Individual training runs
      - `feature_importance.json`: Feature importance scores
      - `metrics.json`: Model performance metrics
      - `model_logs.json`: Training metadata
      - `selected_features.json`: Selected features list
      - `train_columns.json`: Training column information
  - `selected/`: Models trained with pre-selected features

### `notebooks/`
- `01_data_model_and_synthetic_design.ipynb`: Jupyter notebook for exploratory analysis and synthetic data design

### `descriptives/`
- `app.py`: Streamlit dashboard for interactive data analysis
- `README.md`: Dashboard-specific documentation

### `docs/`
- `data_model.md`: Detailed data model documentation with ER diagram
- `HelpyHand - Flowchart.drawio`: Process flowchart (Draw.io format)

## Installation and Setup

### Prerequisites
- Python 3.8+
- pip package manager

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Key Dependencies
- **Data/ML**: numpy, pandas, scikit-learn, joblib
- **API**: fastapi, uvicorn
- **Visualization**: matplotlib, seaborn, plotly, streamlit

## Usage Guide

### 1. Data Generation
Generate synthetic data for credit risk modeling:

```bash
python run_data_generation.py --n-clients 10000 --base-rate 0.15 --seed 42
```

**Parameters:**
- `--n-clients`: Number of clients to generate (default: 10000)
- `--base-rate`: Baseline default rate (default: 0.15)
- `--seed`: Random seed for reproducibility (default: 42)

**Output:** 8 CSV files in `data/generated/` plus master table `model_mt.csv`

### 2. Data Exploration and Validation
Launch the Streamlit dashboard to analyze generated data:

```bash
streamlit run descriptives/app.py
```

**Features:**
- Overview of risk distributions and default rates
- Client demographics analysis
- Digital session patterns
- Transaction and payment behavior
- Correlation analysis with default probability

### 3. Model Training
Train the logistic regression model for PD prediction:

```bash
python -m src.training.train_logistic_regression
```

**Configuration:** Edit `src/config/config.ini` to set:
- Training mode: "full" (all features) or "selected" (pre-defined features)
- Test size, random state, solver parameters
- Feature selection settings

**Output:** Trained model and metrics saved to `models/logistic_regression/{mode}/runs/{timestamp}/`

### 4. API Deployment
Serve the trained model via REST API:

```bash
uvicorn src.api.app:app --reload
```

**API Endpoints:**
- `GET /`: Welcome message with documentation links
- `GET /health`: Service health check
- `GET /model-info`: Model configuration and selected features
- `POST /risk-score`: Generate risk prediction

**Swagger Documentation:** http://localhost:8000/docs

### 5. Making Predictions
Example API request for risk scoring:

```bash
curl -X POST http://localhost:8000/risk-score \
  -H "Content-Type: application/json" \
  -d '{
    "declared_income": 1200000,
    "is_banked": 0,
    "employment_type": "informal",
    "age": 32,
    "city_type": "rural",
    "total_sessions": 15,
    "pct_conversion": 0.30,
    "tx_income_pct": 0.60,
    "payments_count": 8,
    "on_time_rate": 0.70,
    "overdue_rate": 0.20,
    "avg_decision_score": 0.55
  }'
```

**Response:**
```json
{
  "probability_of_default": 0.28,
  "risk_category": "MEDIUM",
  "decision": "REVIEW",
  "top_features": ["on_time_rate", "overdue_rate", "declared_income"]
}
```

## Configuration

### Model Configuration (`src/config/config.ini`)
- **DATA**: Input paths and column specifications
- **TRAINING**: Model hyperparameters and training settings
- **FEATURES**: Feature selection mode and selected features list

### API Configuration
Set environment variables for model paths:
```bash
export MODEL_PATH=models/logistic_regression/selected/runs/2026-04-10_163938/model.pkl
export MODEL_LOGS_PATH=models/logistic_regression/selected/runs/2026-04-10_163938/model_logs.json
export SELECTED_FEATURES_PATH=models/logistic_regression/selected/runs/2026-04-10_163938/selected_features.json
```

## Data Model

The system uses a star schema with `clients` as the central entity:
- **Clients**: Core demographic and financial information
- **Demographics**: Extended personal details
- **Digital Sessions**: Online behavior and engagement
- **Transactions**: Financial activity records
- **Loan Applications**: Credit application history
- **Payments**: Repayment and delinquency data

These aggregate into **Risk Features** table with engineered risk index, then combined with **Target** for modeling.

See [docs/data_model.md](docs/data_model.md) for detailed schemas and relationships.

## Key Design Principles

1. **Risk Generating Process (RGP)**: Systematic injection of latent risk scores ensures realistic correlations between behavioral signals and default probability
2. **Modularity**: Independent data generators allow easy modification and Bayesian refinement
3. **Reproducibility**: Seed management throughout the pipeline
4. **API-First Design**: Stateless RESTful predictions for production deployment
5. **Monitoring**: Built-in validation and descriptive analytics for data quality assurance

## Contributing

This is a PoC system. For extensions:
- Add new data generators in `src/data_generation/`
- Implement additional models in `src/training/`
- Extend API endpoints in `src/api/`
- Update feature engineering in `risk_feature_builder.py`

## License

[Add license information if applicable]
