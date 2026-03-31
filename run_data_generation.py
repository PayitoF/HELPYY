#!/usr/bin/env python3
"""
HelpyHand Data Generation Runner

Ejecuta la generación completa de datos sintéticos para el PoC.

Uso:
    python run_data_generation.py --n-clients 10000 --seed 42 --base-rate 0.15

Opciones:
    --n-clients: Número de clientes (default: 20000)
    --seed: Semilla para reproducibilidad (default: 42)
    --base-rate: Tasa base de default (default: 0.15)
    --output-dir: Directorio de salida (default: data/generated)
    --no-save: No guardar CSV
"""

import argparse
import sys
from pathlib import Path

# Añadir src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from data_generation import run_data_generation_pipeline


def main():
    parser = argparse.ArgumentParser(description="Generar datos sintéticos para HelpyHand PoC")
    parser.add_argument("--n-clients", type=int, default=20000, help="Número de clientes")
    parser.add_argument("--seed", type=int, default=42, help="Semilla para RNG")
    parser.add_argument("--base-rate", type=float, default=0.15, help="Tasa base de default")
    parser.add_argument("--output-dir", type=str, default="data/generated", help="Directorio de salida")
    parser.add_argument("--no-save", action="store_true", help="No guardar CSV")

    args = parser.parse_args()

    print("🚀 Iniciando generación de datos HelpyHand...")
    print(f"📊 Clientes: {args.n_clients}")
    print(f"🎲 Semilla: {args.seed}")
    print(f"📈 Base rate: {args.base_rate}")
    print(f"💾 Output: {args.output_dir}")

    datasets = run_data_generation_pipeline(
        n_clients=args.n_clients,
        seed=args.seed,
        base_rate=args.base_rate,
        output_dir=args.output_dir,
        save_csv=not args.no_save,
    )

    print("✅ Generación completada!")
    print(f"📋 Tasa de default final: {datasets['target']['default'].mean():.3f}")
    print(f"📁 Archivos guardados en: {args.output_dir}")


if __name__ == "__main__":
    main()