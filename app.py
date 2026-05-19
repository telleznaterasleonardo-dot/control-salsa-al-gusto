import streamlit as st
import requests
import pandas as pd
import re
import time
from datetime import datetime
import io

# Configuración de la página web
st.set_page_config(page_title="Salsa al Gusto - Control Panel", page_icon="🕺", layout="wide")

st.title("🕺 Control de Alumnos - Salsa al Gusto 💃")
st.markdown("Sube tu archivo de WhatsApp y pega tu Token de Entri para actualizar la base de datos en tiempo real.")

# --- BARRA LATERAL (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Configuración")
    token_entri = st.text_input("🔑 Pega tu Token de Entri (Bearer):", type="password", help="Pega aquí el texto larguísimo que sacas de Entri (F12).")
    st.markdown("---")
    archivo_subido = st.file_uploader("📂 Sube 'activos_whatsapp.txt' o el Excel", type=['txt', 'csv', 'xlsx'])

# 1. Configuración de conexión a Entri
url_base = 'https://entricontrol-api.entricontrol.com/public/api/members?sortField=internal_id&sortDirection=DESC&filter='

def obtener_ultimos_10_digitos(texto):
    if not texto:
        return ""
    digitos = re.sub(r'\D', '', str(texto))
    return digitos[-10:] if len(digitos) >= 10 else digitos

def procesar_txt_whatsapp(contenido_archivo):
    numeros_activos = set()
    contenido_limpio = contenido_archivo.replace(',', ' ').replace('"', ' ').replace('\n', ' ')
    elementos = contenido_limpio.split()
    for elemento in elementos:
        digitos = obtener_ultimos_10_digitos(elemento)
        if len(digitos) == 10:
            numeros_activos.add(digitos)
    return numeros_activos

# --- LÓGICA PRINCIPAL ---
if archivo_subido is not None and token_entri:
    if archivo_subido.name.endswith('.txt'):
        contenido = archivo_subido.read().decode("utf-8")
    else:
        df_temp = pd.read_excel(archivo_subido) if archivo_subido.name.endswith('.xlsx') else pd.read_csv(archivo_subido)
        contenido = df_temp.to_string()
        
    activos_whatsapp = procesar_txt_whatsapp(contenido)
    st.success(f"✅ ¡WhatsApp leído con éxito! Se detectaron {len(activos_whatsapp)} números activos.")
    
    if st.button("🚀 Sincronizar con Entri y Generar Reporte"):
        headers = {
            'accept': 'application/json, text/plain, */*',
            'authorization': f'{token_entri}' if token_entri.startswith('Bearer') else f'Bearer {token_entri}',
            'origin': 'https://www.entricontrol.com',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
        }
        
        todos_los_alumnos = []
        pagina_actual = 1
        ultima_pagina = 1 
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Conectando con la API de Entri...")
        
        error_conexion = False
        
        while pagina_actual <= ultima_pagina:
            url_paginada = f"{url_base}&page={pagina_actual}"
            respuesta = requests.get(url_paginada, headers=headers)
            
            if respuesta.status_code in [200, 201]:
                datos_json = respuesta.json()
                nodo_principal = datos_json.get('data', datos_json)
                
                if isinstance(nodo_principal, dict):
                    if pagina_actual == 1:
                        ultima_pagina = nodo_principal.get('last_page', 1)
                    alumnos_de_esta_pagina = nodo_principal.get('data', [])
                elif isinstance(nodo_principal, list):
                    alumnos_de_esta_pagina = nodo_principal
                    ultima_pagina = 1
                else:
                    alumnos_de_esta_pagina = []
                    
                todos_los_alumnos.extend(alumnos_de_esta_pagina)
                status_text.text(f"Descargando alumnos... Página {pagina_actual} de {ultima_pagina}")
                progress_bar.progress(min(pagina_actual / ultima_pagina, 1.0))
                pagina_actual += 1
                time.sleep(0.1)
            else:
                st.error(f"❌ Error de conexión (Código: {respuesta.status_code}). Verifica que tu Token sea nuevo y esté correcto.")
                error_conexion = True
                break
                
        progress_bar.empty()
        status_text.empty()
        
        if not error_conexion:
            filas_procesadas = []
            fecha_hoy = datetime.now().date()
            meses_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            mes_actual_nombre = meses_es[datetime.now().month - 1]
            
            for alumno in todos_los_alumnos:
                telefono = str(alumno.get('phone', alumno.get('cellphone', '0'))).strip()
                nombre_pila = str(alumno.get('name', alumno.get('nombre', ''))).strip()
                apellido = str(alumno.get('last_name', alumno.get('apellido', alumno.get('apellidos', '')))).strip()
                nombre_completo = f"{nombre_pila} {apellido}".strip()
                
                fecha_nac = alumno.get('manual_id', '') 
                clave_entri = alumno.get('internal_id', alumno.get('id', ''))
                
                cumple_este_mes = "¡Felicidades!" if (fecha_nac and mes_actual_nombre in str(fecha_nac).lower()) else ""
                
                fecha_original = alumno.get('last_payment_date', alumno.get('payment_date', alumno.get('updated_at', '')))
                ultima_visita = ""
                dias_sin_venir = ""
                estatus = "Sin datos"
                
                if fecha_original:
                    ultima_visita = str(fecha_original).split('T')[0] if 'T' in str(fecha_original) else str(fecha_original).strip()
                    try:
                        fecha_visita_dt = datetime.strptime(ultima_visita, "%Y-%m-%d").date()
                        dias_sin_venir = (fecha_hoy - fecha_visita_dt).days
                        if dias_sin_venir <= 7: estatus = "Activo"
                        elif dias_sin_venir <= 30: estatus = "En Riesgo"
                        else: estatus = "Inactivo"
                    except:
                        pass
                
                salio = 'SI' if (obtener_ultimos_10_digitos(telefono) not in activos_whatsapp and len(obtener_ultimos_10_digitos(telefono)) == 10) else ''
                
                filas_procesadas.append({
                    'Num de telefono': telefono,
                    'Nombre': nombre_completo,
                    'Fecha de nacimiento': fecha_nac,
                    '¿Cumpleaños este mes?': cumple_este_mes,
                    'Registro en entri': clave_entri,
                    'Ultima Visita': ultima_visita,
                    'Dias sin venir': dias_sin_venir,
                    'Estatus': estatus,
                    'SALIO DE GRUPO': salio
                })
                
            columnas_finales = [
                'Num de telefono', 'Nombre', 'Fecha de nacimiento', '¿Cumpleaños este mes?',
                'Registro en entri', 'Ultima Visita', 'Dias sin venir', 'Estatus', 'SALIO DE GRUPO'
            ]
            df_final = pd.DataFrame(filas_procesadas, columns=columnas_finales)
            
            # --- DESPLIEGUE DE MÉTRICAS ---
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Alumnos (Entri)", len(df_final))
            col2.metric("Alumnos Activos 🕺", len(df_final[df_final['Estatus'] == 'Activo']))
            col3.metric("En Riesgo ⚠️", len(df_final[df_final['Estatus'] == 'En Riesgo']))
            col4.metric("Fuera del Grupo", len(df_final[df_final['SALIO DE GRUPO'] == 'SI']))
            
            st.markdown("### 📋 Vista Previa de la Base de Datos")
            st.dataframe(df_final, use_container_width=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Control SAG')
            
            st.download_button(
                label="📥 Descargar Base de Datos Completa en Excel",
                data=buffer.getvalue(),
                file_name=f"Control_SAG_{fecha_hoy}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
else:
    st.info("💡 Sube tu archivo de WhatsApp y pega tu Token en el menú de la izquierda para comenzar.")