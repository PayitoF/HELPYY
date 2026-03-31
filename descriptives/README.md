# Descriptives Dashboard

Esta carpeta contiene la aplicación de Streamlit para análisis descriptivo de los datos sintéticos de HelpyHand.

## Uso

1. Asegúrate de que los datos estén generados en `data/generated/`:
   ```bash
   python run_data_generation.py --n-clients 10000
   ```

2. Ejecuta la aplicación:
   ```bash
   streamlit run descriptives/app.py
   ```

3. Abre el navegador en la URL mostrada (generalmente http://localhost:8501)

## Secciones

- **Overview**: Métricas generales y distribución de riesgo
- **Clients**: Análisis de clientes (ingreso, empleo, bancarización)
- **Demographics**: Distribución demográfica
- **Digital Sessions**: Comportamiento digital
- **Transactions**: Actividad transaccional
- **Payments**: Comportamiento de pagos
- **Loan Applications**: Solicitudes de crédito
- **Risk Features**: Features agregados para modelado
- **Target**: Análisis del target de default
- **Correlations**: Matriz de correlaciones y relaciones con riesgo

## Propósito

Esta dashboard permite monitorear en tiempo real los cambios en la distribución de datos sintéticos cuando se modifican los módulos de generación (ej. cambiando a elicitación bayesiana). Facilita iteraciones rápidas y validación visual de la calidad de los datos.