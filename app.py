import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import os # Importado para manejar rutas de archivos

# --- Configuración de la Página ---
st.set_page_config(
    page_title="Dashboard Avanzado de Productividad",
    page_icon="🚀",
    layout="wide"
)

# --- Estilos CSS para mejorar la apariencia ---
st.markdown("""
<style>
    /* Estilo para las tarjetas de métricas (KPIs) */
    .stMetric {
        border: 1px solid rgba(0,0,0,0.1);
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        background-color: #f9f9f9; /* Un fondo muy sutil */
    }
    /* El tema oscuro de Streamlit sobreescribirá esto si está activo */
    [data-theme="dark"] .stMetric {
        background-color: #262730;
        border-color: rgba(255,255,255,0.2);
    }
    .stMetric .st-emotion-cache-1g8m2i9 { /* Selector para el valor de la métrica */
        font-size: 2.2rem;
        font-weight: bold;
    }
    .stMetric .st-emotion-cache-1xarl3l { /* Selector para la etiqueta de la métrica */
        font-size: 1rem;
        color: #6c757d; /* Un gris suave para la etiqueta */
    }
    [data-theme="dark"] .stMetric .st-emotion-cache-1xarl3l {
        color: #a0a4a8;
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1, h2, h3 {
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# --- Funciones de Carga y Procesamiento de Datos ---

@st.cache_data
def load_sessions_data(uploaded_file):
    """Carga el archivo de sesiones de operadores, omitiendo la segunda fila de sub-encabezados."""
    if uploaded_file:
        try:
            # Se usa sep='\t' y skiprows=[1] para omitir la fila de descripción que causa problemas
            return pd.read_csv(uploaded_file, sep='\t', engine='python', on_bad_lines='skip', skiprows=[1])
        except Exception as e:
            st.error(f"Error al leer el archivo de sesiones '{uploaded_file.name}': {e}")
            return None
    return None

@st.cache_data
def load_users_data(uploaded_file):
    """Carga el archivo de conversaciones de usuarios."""
    if uploaded_file:
        try:
            return pd.read_csv(uploaded_file, sep='\t', engine='python', on_bad_lines='skip')
        except Exception as e:
            st.error(f"Error al leer el archivo de usuarios '{uploaded_file.name}': {e}")
            return None
    return None

def validate_dataframes(df_sessions, df_users):
    """Valida que los dataframes cargados tengan las columnas necesarias para el análisis."""
    required_cols_sessions = [
        'Id Sesión', 'Nombre Agente', 'Fecha/tiempo Inicio Sesión', 'Cola',
        'Conversaciones cerradas', 'Conversación con agente', 'Espera agente',
        'Cantidad de respuestas', 'Transferencias realizadas', 'Abandonada por usuario',
        'Tiempo medio de respuesta' # <--- NUEVA COLUMNA AÑADIDA A LA VALIDACIÓN
    ]
    required_cols_users = ['Id Sesión', 'Tipificación', 'Mensajes Agente']

    # Función auxiliar para verificar columnas faltantes
    def check_missing_cols(df, required_cols, filename):
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            st.error(
                f"El archivo '{filename}' parece ser incorrecto o tener un formato inesperado. "
                f"Faltan las siguientes columnas clave: {', '.join(missing)}"
            )
            return False
        return True

    is_sessions_valid = check_missing_cols(df_sessions, required_cols_sessions, "Sesiones de Agentes")
    is_users_valid = check_missing_cols(df_users, required_cols_users, "Conversaciones de Usuarios")

    return is_sessions_valid and is_users_valid


@st.cache_data
def clean_and_prepare_data(_df_sessions, _df_users):
    """Limpia, transforma y une ambos dataframes para el análisis completo."""
    # --- Limpieza y conversión de tipos en df_sessions ---
    time_cols_sessions = ['Conversación con agente', 'Espera agente']
    count_cols_sessions = [
        'Conversaciones cerradas', 'Cantidad de respuestas', 'Transferencias realizadas',
        'Abandonada por usuario'
    ]

    for col in time_cols_sessions + count_cols_sessions:
        if col in _df_sessions.columns:
            _df_sessions[col] = pd.to_numeric(_df_sessions[col].replace('-', pd.NA), errors='coerce').fillna(0)

    # --- NUEVA SECCIÓN: Limpieza de la columna de tiempo de respuesta ---
    # Se convierte a numérico, los '-' se vuelven NaN (Not a Number), que serán ignorados en los cálculos de promedio.
    if 'Tiempo medio de respuesta' in _df_sessions.columns:
        _df_sessions['Tiempo medio de respuesta'] = pd.to_numeric(
            _df_sessions['Tiempo medio de respuesta'].replace('-', pd.NA),
            errors='coerce'
        )

    # --- Limpieza y conversión de tipos en df_users ---
    count_cols_users = ['Mensajes Agente', 'Mensajes Usuario', 'Mensajes Bot']
    for col in count_cols_users:
       if col in _df_users.columns:
           _df_users[col] = pd.to_numeric(_df_users[col].replace('-', pd.NA), errors='coerce').fillna(0)

    # --- Preparación de Fechas ---
    _df_sessions['Fecha/tiempo Inicio Sesión'] = pd.to_datetime(_df_sessions['Fecha/tiempo Inicio Sesión'], errors='coerce')
    _df_sessions.dropna(subset=['Fecha/tiempo Inicio Sesión'], inplace=True)
    _df_sessions['Fecha'] = _df_sessions['Fecha/tiempo Inicio Sesión'].dt.date

    # --- Unión de los dataframes ---
    cols_to_merge = ['Id Sesión', 'Tipificación', 'Mensajes Agente', 'Mensajes Usuario', 'Mensajes Bot']
    df_merged = pd.merge(
        _df_sessions,
        _df_users[cols_to_merge],
        on='Id Sesión',
        how='left',
        suffixes=('_session', '_user')
    )
    df_merged['Cola'] = df_merged['Cola'].fillna('Sin Cola').str.strip()

    # --- MEJORA: Unificación y Traducción de Colas y Tipificaciones ---
    # Diccionarios para traducción
    queue_translations = {
        '_default_': 'Default Queue',
        'default': 'Default Queue',
        'atencionAlCliente': 'Atención al cliente'
    }
    typification_translations = {
        'abandoned-by-user': 'Sin respuesta del cliente',
        'finished': 'Finalizado',
        'order-placed': 'Venta finalizada',
        'inactividad-agente': 'Sin respuesta asesor',
        'order-booked': 'Reserva Realizada'
    }

    # Aplicar traducciones
    df_merged['Cola'] = df_merged['Cola'].replace(queue_translations)
    df_merged['Tipificación_user'] = df_merged['Tipificación_user'].replace(typification_translations)

    return df_merged

# --- Título del Dashboard ---
st.title("🚀 Dashboard Avanzado de Productividad de Agentes")
st.markdown("Análisis integral del rendimiento, carga de trabajo y eficiencia operativa del equipo de atención.")

# --- Carga de Archivos en la Barra Lateral ---
st.sidebar.header("Carga de Archivos")

# MEJORA 1: Instrucciones y enlaces para la descarga de archivos.
st.sidebar.subheader("1. Archivo de Conversaciones")
st.sidebar.markdown(
    """
    Descarga desde: [Dashboard de Usuarios](https://go.botmaker.com/#/dashboards/userAndSessions)
    1. Filtra el periodo de interés.
    2. Presiona en **'Descargar usuarios'**.
    3. Importa el archivo **'users...'**
    """,
    unsafe_allow_html=True
)
uploaded_users = st.sidebar.file_uploader(
    "Sube el archivo de usuarios (users...)",
    type=['tsv', 'csv'],
    key="users_uploader",
    label_visibility="collapsed"
)

st.sidebar.divider()

st.sidebar.subheader("2. Archivo de Sesiones de Agentes")
st.sidebar.markdown(
    """
    Descarga desde: [Dashboard Tiempo Real](https://go.botmaker.com/#/dashboards/oprealtime)
    1. Filtra el periodo de interés.
    2. Presiona en **'Descargar por conversación'**.
    3. Importa el archivo **'operatorsSessions...'**
    """,
    unsafe_allow_html=True
)
uploaded_operators_sessions = st.sidebar.file_uploader(
    "Sube el archivo de sesiones (operatorsSessions...)",
    type=['tsv', 'csv'],
    key="sessions_uploader",
    label_visibility="collapsed"
)


# --- Lógica Principal del Dashboard ---
if uploaded_users and uploaded_operators_sessions:
    df_users_raw = load_users_data(uploaded_users)
    df_sessions_raw = load_sessions_data(uploaded_operators_sessions)

    if df_users_raw is not None and df_sessions_raw is not None:
        if validate_dataframes(df_sessions_raw, df_users_raw):
            st.sidebar.success("✅ ¡Archivos cargados y validados!")

            df_procesado = clean_and_prepare_data(df_sessions_raw.copy(), df_users_raw.copy())

            # --- Header con Filtros ---
            st.markdown(
                """
                <style>
                    .sticky-filter {
                        position: sticky;
                        top: 0;
                        z-index: 999;
                        background-color: #ffffff;
                        padding-top: 0.5rem;
                        padding-bottom: 0.5rem;
                    }
                    [data-theme="dark"] .sticky-filter {
                        background-color: #0e1117;
                    }
                </style>
                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="sticky-filter">', unsafe_allow_html=True)
            st.header("🔍 Filtros de Análisis")
            with st.expander("Selecciona los filtros para acotar el análisis", expanded=True):
                col1, col2, col3 = st.columns(3)

                # Filtro de Agentes
                lista_agentes = sorted(df_procesado['Nombre Agente'].unique())
                agentes_seleccionados = col1.multiselect(
                    "Agentes", options=lista_agentes, default=lista_agentes,
                    help="Selecciona los agentes a incluir en el análisis."
                )

                # Filtro de Colas de Atención
                lista_colas = sorted(df_procesado['Cola'].unique())
                colas_seleccionadas = col2.multiselect(
                    "Colas de Atención", options=lista_colas, default=lista_colas,
                    help="Filtra por las colas de atención. Ayuda a comparar el rendimiento en diferentes áreas (ej. Ventas vs. Soporte)."
                )

                # Filtro de Fechas
                min_fecha = df_procesado['Fecha'].min()
                max_fecha = df_procesado['Fecha'].max()
                fecha_seleccionada = col3.date_input(
                    "Rango de Fechas", value=(min_fecha, max_fecha),
                    min_value=min_fecha, max_value=max_fecha,
                    help="Selecciona el rango de fechas para el análisis."
                )
            st.markdown('</div>', unsafe_allow_html=True)

            # --- Aplicar Filtros ---
            if len(fecha_seleccionada) != 2:
                st.warning("Por favor, selecciona un rango de fechas válido (inicio y fin).")
                st.stop()

            df_filtrado = df_procesado[
                (df_procesado['Nombre Agente'].isin(agentes_seleccionados)) &
                (df_procesado['Cola'].isin(colas_seleccionadas)) &
                (df_procesado['Fecha'] >= fecha_seleccionada[0]) &
                (df_procesado['Fecha'] <= fecha_seleccionada[1])
            ]

            if df_filtrado.empty:
                st.error("No se encontraron datos para los filtros seleccionados. Por favor, ajusta tu selección.")
            else:
                # --- KPIs Principales ---
                st.header("📊 Métricas Clave del Periodo")
                st.markdown("Un vistazo rápido a los indicadores más importantes de la operación según tu selección.")

                # Cálculos de KPIs
                total_conversations = df_filtrado['Conversaciones cerradas'].sum()
                total_abandons = df_filtrado['Abandonada por usuario'].sum()
                abandon_rate = (total_abandons / total_conversations * 100) if total_conversations > 0 else 0
                total_transfers = df_filtrado['Transferencias realizadas'].sum()
                avg_handle_time_seconds = df_filtrado['Conversación con agente'].mean()
                
                # --- NUEVO CÁLCULO DE KPI ---
                avg_response_time_seconds = df_filtrado['Tiempo medio de respuesta'].mean()
                avg_response_time_hours = (avg_response_time_seconds / 3600) if pd.notna(avg_response_time_seconds) else 0

                # Se cambia a 5 columnas para el nuevo KPI
                kpi_cols = st.columns(5)
                kpi_cols[0].metric(label="Total Conversaciones Atendidas", value=f"{int(total_conversations):,}")
                kpi_cols[1].metric(
                    label="Tasa de Abandono (Usuario)",
                    value=f"{abandon_rate:.1f}%",
                    help="Porcentaje de conversaciones que fueron abandonadas por el usuario del total de conversaciones atendidas. Un valor alto puede indicar largos tiempos de espera."
                )
                kpi_cols[2].metric(
                    label="Total Transferencias",
                    value=f"{int(total_transfers):,}",
                    help="Número total de veces que los agentes transfirieron una conversación a otra cola o agente."
                )
                kpi_cols[3].metric(
                    label="Tiempo Promedio Conversación (AHT)",
                    value=f"{avg_handle_time_seconds / 60:.1f} min" if pd.notna(avg_handle_time_seconds) else "N/A",
                    help="Average Handle Time: Tiempo promedio total que un agente dedica a una conversación activa."
                )
                # --- NUEVO WIDGET DE KPI ---
                kpi_cols[4].metric(
                    label="Tiempo Medio de Respuesta",
                    value=f"{avg_response_time_hours:.2f} hrs" if avg_response_time_hours > 0 else "N/A",
                    help="Tiempo promedio que tarda un agente en enviar su primera respuesta en una conversación, medido en horas. Se ignoran las conversaciones sin respuesta."
                )

                st.divider()

                # --- Análisis Temporal ---
                st.header("🗓️ Evolución Temporal")
                daily_volume = df_filtrado.groupby('Fecha').agg(
                    total_conversations=('Conversaciones cerradas', 'sum'),
                    avg_handle_time=('Conversación con agente', 'mean')
                ).reset_index()

                fig_daily = px.line(
                    daily_volume, x='Fecha', y='total_conversations',
                    title='Volumen de Conversaciones por Día',
                    labels={'Fecha': 'Día', 'total_conversations': 'Nº de Conversaciones'},
                    markers=True
                )
                fig_daily.update_layout(showlegend=False)
                st.plotly_chart(fig_daily, use_container_width=True, theme="streamlit")
                st.info(
                    "**¿Cómo interpretar este gráfico?** Este gráfico muestra el número de conversaciones **iniciadas** cada día, basándose en la 'Fecha/tiempo Inicio Sesión'. Es una métrica clave para entender la demanda entrante y los picos de trabajo, independientemente de si la conversación se resuelve el mismo día o en días posteriores."
                )

                st.divider()

                # --- Análisis de Rendimiento por Agente ---
                st.header("🧑‍💻 Análisis de Rendimiento por Agente")
                agent_performance = df_filtrado.groupby('Nombre Agente').agg(
                    total_conversations=('Conversaciones cerradas', 'sum'),
                    avg_handle_time=('Conversación con agente', 'mean'),
                    avg_response_time=('Tiempo medio de respuesta', 'mean'),
                    total_transfers=('Transferencias realizadas', 'sum'),
                    total_messages=('Mensajes Agente', 'sum')
                ).reset_index().sort_values(by='total_conversations', ascending=False)

                chart_cols = st.columns(3)
                with chart_cols[0]:
                    st.subheader("Conversaciones Atendidas por Agente")
                    fig_convs = px.bar(
                        agent_performance, x='Nombre Agente', y='total_conversations',
                        title="Total de Conversaciones por Agente",
                        labels={'Nombre Agente': 'Agente', 'total_conversations': 'Nº de Conversaciones'},
                        text='total_conversations', color='Nombre Agente'
                    )
                    fig_convs.update_traces(textposition='outside')
                    fig_convs.update_layout(showlegend=False)
                    st.plotly_chart(fig_convs, use_container_width=True, theme="streamlit")
                    st.info("**¿Qué significa esto?** Muestra la cantidad total de conversaciones que cada agente ha cerrado en el periodo seleccionado. Ayuda a entender la distribución de la carga de trabajo.")

                with chart_cols[1]:
                    st.subheader("Tiempo Promedio de Conversación (AHT)")
                    fig_aht = px.bar(
                        agent_performance, x='Nombre Agente', y=agent_performance['avg_handle_time'] / 60,
                        title="Tiempo Promedio por Conversación (Minutos)",
                        labels={'Nombre Agente': 'Agente', 'y': 'Tiempo Promedio (min)'},
                        text=(agent_performance['avg_handle_time'] / 60).round(1),
                        color='Nombre Agente'
                    )
                    if pd.notna(avg_handle_time_seconds):
                        fig_aht.add_hline(
                            y=avg_handle_time_seconds / 60, line_dash="dot",
                            annotation_text=f"Promedio Equipo: {avg_handle_time_seconds/60:.1f} min",
                            annotation_position="bottom right"
                        )
                    fig_aht.update_layout(showlegend=False)
                    st.plotly_chart(fig_aht, use_container_width=True, theme="streamlit")
                    st.info("**¿Qué significa esto?** Mide el tiempo promedio que un agente dedica a una conversación. Un AHT más bajo suele indicar mayor eficiencia. La línea punteada muestra el promedio de todo el equipo para una fácil comparación.")

                with chart_cols[2]:
                    st.subheader("Tiempo Medio de Respuesta por Agente")
                    fig_response = px.bar(
                        agent_performance,
                        x='Nombre Agente',
                        y=agent_performance['avg_response_time'] / 3600,
                        title="Tiempo Medio de Respuesta (Horas)",
                        labels={'Nombre Agente': 'Agente', 'y': 'Tiempo (hrs)'},
                        text=(agent_performance['avg_response_time'] / 3600).round(2),
                        color='Nombre Agente'
                    )
                    if pd.notna(avg_response_time_hours) and avg_response_time_hours > 0:
                        fig_response.add_hline(
                            y=avg_response_time_hours, line_dash="dot",
                            annotation_text=f"Promedio Equipo: {avg_response_time_hours:.2f} hrs",
                            annotation_position="bottom right",
                        )
                    fig_response.update_layout(showlegend=False)
                    st.plotly_chart(fig_response, use_container_width=True, theme="streamlit")
                    st.info("**¿Qué significa esto?** Refleja el tiempo promedio que demora cada agente en enviar su primera respuesta. Valores más bajos indican una atención inicial más rápida.")

                st.divider()

                # --- Matriz de Eficiencia vs. Carga de Trabajo ---
                st.header("🗺️ Matriz de Eficiencia vs. Carga de Trabajo")
                fig_scatter = px.scatter(
                    agent_performance,
                    x='total_conversations',
                    y=agent_performance['avg_handle_time'] / 60,
                    size='total_messages',
                    color='Nombre Agente',
                    hover_name='Nombre Agente',
                    size_max=60,
                    title='Carga de Trabajo vs. Tiempo de Manejo',
                    labels={"total_conversations": "Número de Conversaciones Atendidas", "y": "Tiempo Promedio de Conversación (minutos)"}
                )
                fig_scatter.update_layout(showlegend=True, legend_title_text='Agentes')
                st.plotly_chart(fig_scatter, use_container_width=True, theme="streamlit")
                st.info(
                    """
                    **¿Cómo leer este gráfico?**
                    - **Eje Horizontal (Más a la derecha):** Agentes que manejan más conversaciones (mayor carga de trabajo).
                    - **Eje Vertical (Más arriba):** Agentes que dedican, en promedio, más tiempo a cada conversación.
                    - **Tamaño de la burbuja:** Representa la cantidad total de **mensajes enviados** por el agente, un indicador del esfuerzo de comunicación.
                    """
                )

                st.divider()

                # --- Análisis de Tipificaciones ---
                st.header("🏷️ Resultados de las Conversaciones (Tipificaciones)")
                tipificaciones = df_filtrado['Tipificación_user'].dropna().value_counts().reset_index()
                tipificaciones.columns = ['Tipificación', 'Cantidad']

                if not tipificaciones.empty:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Distribución General de Tipificaciones")
                        fig_tipif_bar = px.bar(
                            tipificaciones.sort_values('Cantidad', ascending=True),
                            x='Cantidad', y='Tipificación', orientation='h',
                            title='Conteo Total por Tipificación', text='Cantidad'
                        )
                        fig_tipif_bar.update_layout(showlegend=False, yaxis_title=None)
                        st.plotly_chart(fig_tipif_bar, use_container_width=True, theme="streamlit")
                        st.info(
                            "**¿Qué significa esto?** Este gráfico muestra el resultado final de las conversaciones. Es más fácil de leer que un gráfico de torta y permite comparar rápidamente las categorías más comunes."
                        )

                    with col2:
                        st.subheader("Tipificaciones por Agente")
                        tipif_by_agent = df_filtrado.groupby(['Nombre Agente', 'Tipificación_user']).size().reset_index(name='Cantidad')
                        fig_stacked_bar = px.bar(
                            tipif_by_agent, x='Nombre Agente', y='Cantidad',
                            color='Tipificación_user', title='Composición de Resultados por Agente',
                            labels={'Nombre Agente': 'Agente', 'Cantidad': 'Nº de Conversaciones', 'Tipificación_user': 'Tipificación'}
                        )
                        st.plotly_chart(fig_stacked_bar, use_container_width=True, theme="streamlit")
                        st.info(
                            "**¿Qué significa esto?** Compara cómo se distribuyen los resultados de las conversaciones entre los diferentes agentes. Ayuda a identificar si ciertos agentes se especializan o tienen mejores resultados en tipos específicos de interacciones."
                        )
                else:
                    st.info("No hay datos de tipificación disponibles para el periodo y filtros seleccionados.")

else:
    # MEJORA 2: Mostrar video instructivo si no hay archivos cargados.
    st.info("👋 ¡Bienvenido! Sube los archivos de 'Usuarios' y 'Sesiones de Agentes' para comenzar el análisis.")
    
    # Opcional: Mostrar un placeholder o instrucciones más detalladas si no hay video.
    st.image("https://placehold.co/1200x400/e8e8e8/4f4f4f?text=Por+favor+cargue+los+archivos+en+el+panel+izquierdo", use_column_width=True)

