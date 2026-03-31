import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# Configuración de la página
st.set_page_config(page_title="HelpyHand Data Descriptives", layout="wide")

# Función para cargar datos
@st.cache_data
def load_data():
    data_dir = Path("data/generated")
    datasets = {}
    if not data_dir.exists():
        st.error("Directorio data/generated no encontrado. Ejecuta primero: python run_data_generation.py")
        return None

    files = {
        "clients": "clients.csv",
        "demographics": "demographics.csv",
        "digital_sessions": "digital_sessions.csv",
        "transactions": "transactions.csv",
        "loan_applications": "loan_applications.csv",
        "payments": "payments.csv",
        "risk_features": "risk_features.csv",
        "target": "target.csv",
    }

    for name, filename in files.items():
        path = data_dir / filename
        if path.exists():
            datasets[name] = pd.read_csv(path)
        else:
            st.warning(f"Archivo {filename} no encontrado.")
            datasets[name] = pd.DataFrame()

    return datasets

# Cargar datos
datasets = load_data()
if datasets is None:
    st.stop()

# Sidebar para navegación
st.sidebar.title("HelpyHand Data Descriptives")
page = st.sidebar.radio("Sección", [
    "Overview",
    "Clients",
    "Demographics",
    "Digital Sessions",
    "Transactions",
    "Payments",
    "Loan Applications",
    "Risk Features",
    "Target",
    "Correlations"
])

# Función helper para mostrar stats básicas
def show_basic_stats(df, title):
    st.subheader(title)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Filas", len(df))
    with col2:
        st.metric("Columnas", len(df.columns))
    with col3:
        st.metric("Nulos totales", df.isnull().sum().sum())

    st.dataframe(df.describe())

# Overview
if page == "Overview":
    st.title("📊 Overview - HelpyHand Synthetic Data")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Clientes", len(datasets["clients"]))
    with col2:
        st.metric("Sesiones Digitales", len(datasets["digital_sessions"]))
    with col3:
        st.metric("Transacciones", len(datasets["transactions"]))
    with col4:
        st.metric("Aplicaciones de Crédito", len(datasets["loan_applications"]))

    # Distribución de riesgo
    if not datasets["target"].empty:
        fig = px.histogram(datasets["target"], x="p_default", nbins=50, title="Distribución de Probabilidad de Default")
        st.plotly_chart(fig)

        default_rate = datasets["target"]["default"].mean()
        st.metric("Tasa de Default", f"{default_rate:.3f}")

# Clients
elif page == "Clients":
    st.title("👥 Clients Analysis")
    df = datasets["clients"]
    show_basic_stats(df, "Estadísticas Básicas")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(df, x="declared_income", nbins=50, title="Distribución de Ingreso Declarado")
        st.plotly_chart(fig)

    with col2:
        fig = px.pie(df, names="employment_type", title="Tipo de Empleo")
        st.plotly_chart(fig)

    st.subheader("Bancarización por Tipo de Empleo")
    banked_by_emp = df.groupby("employment_type")["is_banked"].mean().reset_index()
    fig = px.bar(banked_by_emp, x="employment_type", y="is_banked", title="Tasa de Bancarización")
    st.plotly_chart(fig)

# Demographics
elif page == "Demographics":
    st.title("👨‍👩‍👧‍👦 Demographics Analysis")
    df = datasets["demographics"]
    show_basic_stats(df, "Estadísticas Básicas")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(df, x="age", nbins=20, title="Distribución de Edad")
        st.plotly_chart(fig)

    with col2:
        fig = px.pie(df, names="sex", title="Distribución por Género")
        st.plotly_chart(fig)

    st.subheader("Urbano vs Rural")
    fig = px.pie(df, names="city_type", title="Tipo de Ciudad")
    st.plotly_chart(fig)

# Digital Sessions
elif page == "Digital Sessions":
    st.title("🌐 Digital Sessions Analysis")
    df = datasets["digital_sessions"]
    show_basic_stats(df, "Estadísticas Básicas")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(df, x="session_duration_sec", nbins=50, title="Duración de Sesiones")
        st.plotly_chart(fig)

    with col2:
        fig = px.pie(df, names="device_type", title="Tipo de Dispositivo")
        st.plotly_chart(fig)

    st.subheader("Sesiones por Canal de Marketing")
    fig = px.bar(df["marketing_channel"].value_counts(), title="Sesiones por Canal")
    st.plotly_chart(fig)

# Transactions
elif page == "Transactions":
    st.title("💳 Transactions Analysis")
    df = datasets["transactions"]
    show_basic_stats(df, "Estadísticas Básicas")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(df, x="amount", nbins=50, title="Monto de Transacciones")
        st.plotly_chart(fig)

    with col2:
        fig = px.pie(df, names="tx_type", title="Tipo de Transacción")
        st.plotly_chart(fig)

    st.subheader("Transacciones por Categoría")
    fig = px.bar(df["merchant_category"].value_counts(), title="Categorías de Comercio")
    st.plotly_chart(fig)

# Payments
elif page == "Payments":
    st.title("💰 Payments Analysis")
    df = datasets["payments"]
    show_basic_stats(df, "Estadísticas Básicas")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(df, x="dpd", nbins=30, title="Días de Mora (DPD)")
        st.plotly_chart(fig)

    with col2:
        fig = px.histogram(df, x="amount_paid", nbins=50, title="Monto Pagado")
        st.plotly_chart(fig)

    st.subheader("Tasa de Pagos Puntuales")
    on_time = (df["dpd"] <= 0).mean()
    st.metric("Pagos Puntuales", f"{on_time:.3f}")

# Loan Applications
elif page == "Loan Applications":
    st.title("📄 Loan Applications Analysis")
    df = datasets["loan_applications"]
    show_basic_stats(df, "Estadísticas Básicas")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(df, x="amount_requested", nbins=50, title="Monto Solicitado")
        st.plotly_chart(fig)

    with col2:
        fig = px.pie(df, names="decision", title="Decisiones de Crédito")
        st.plotly_chart(fig)

    st.subheader("Solicitudes por Producto")
    fig = px.bar(df["product_type"].value_counts(), title="Tipo de Producto")
    st.plotly_chart(fig)

# Risk Features
elif page == "Risk Features":
    st.title("🎯 Risk Features Analysis")
    df = datasets["risk_features"]
    show_basic_stats(df, "Estadísticas Básicas")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(df, x="risk_index", nbins=50, title="Índice de Riesgo")
        st.plotly_chart(fig)

    with col2:
        fig = px.histogram(df, x="on_time_rate", nbins=20, title="Tasa de Pagos Puntuales")
        st.plotly_chart(fig)

    st.subheader("Riesgo por Tipo de Empleo")
    if not df.empty:
        risk_by_emp = df.groupby("employment_type")["risk_index"].mean().reset_index()
        fig = px.bar(risk_by_emp, x="employment_type", y="risk_index", title="Riesgo Promedio por Empleo")
        st.plotly_chart(fig)

# Target
elif page == "Target":
    st.title("🎯 Target Analysis")
    df = datasets["target"]
    show_basic_stats(df, "Estadísticas Básicas")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(df, x="p_default", nbins=50, title="Probabilidad de Default")
        st.plotly_chart(fig)

    with col2:
        default_count = df["default"].value_counts()
        fig = px.pie(values=default_count.values, names=default_count.index, title="Default vs No Default")
        st.plotly_chart(fig)

    st.metric("Tasa de Default", f"{df['default'].mean():.3f}")

# Correlations
elif page == "Correlations":
    st.title("🔗 Correlations Analysis")
    df = datasets["risk_features"].select_dtypes(include=[np.number])
    if not df.empty:
        corr = df.corr()
        fig = px.imshow(corr, text_auto=True, title="Matriz de Correlación")
        st.plotly_chart(fig)

        st.subheader("Correlaciones con Riesgo")
        risk_corr = corr["risk_index"].sort_values(ascending=False)
        st.dataframe(risk_corr)

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("Desarrollado para HelpyHand PoC")
st.sidebar.markdown("Ejecuta `python run_data_generation.py` para regenerar datos")