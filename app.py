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
    st.markdown("---")
    st.subheader("🕵️ Filtros Avanzados (Histórico)")
    st.markdown("Cruza el historial de pagos con la lista de alumnos. (Tarda un poco más)")
    buscar_kids = st.checkbox("👧👦 Identificar KIDS")
    buscar_pole = st.checkbox("💃 Identificar POLE DANCE")
    
# Variable para saber si debemos hacer el escaneo lento
escaneo_profundo = buscar_kids or buscar_pole

# 1. Configuración de conexión a Entri
url_base_members = 'https://entricontrol-api.entricontrol.com/public/api/members?sortField=internal_id&sortDirection=DESC&filter='
url_base_payments = 'https://entricontrol-api.entricontrol.com/public/api/payments?sortField=payments.created_at&sortDirection=DESC&pagination=true'

def obtener_ultimos_10_digitos(texto):
    if not texto:
        return ""
    texto_str = str(texto).strip()
    if texto_str.endswith('.0'):
        texto_str = texto_str[:-2]
        
    digitos = re.sub(r'\D', '', texto_str)
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
    
    archivo_subido.seek(0)
    if archivo_subido.name.endswith('.xlsx'):
        df_temp = pd.read_excel(archivo_subido, dtype=str)
        contenido = df_temp.to_csv(index=False)
    else:
        contenido = archivo_subido.read().decode("utf-8", errors="ignore")
        
    activos_whatsapp = procesar_txt_whatsapp(contenido)
    st.success(f"✅ ¡WhatsApp leído con éxito! Se detectaron {len(activos_whatsapp)} números activos.")
    
    if st.button("🚀 Sincronizar con Entri y Generar Reporte"):
        headers = {
            'accept': 'application/json, text/plain, */*',
            'authorization': f'{token_entri}' if token_entri.startswith('Bearer') else f'Bearer {token_entri}',
            'origin': 'https://www.entricontrol.com',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
        }
        
        error_conexion = False
        ids_de_ninos = set()
        ids_de_pole = set()
        
        progress_bar = st.progress(0)
        status_text = st.empty()

        # ==========================================
        # FASE 1: Buscar IDs Históricos (Pagos)
        # ==========================================
        if escaneo_profundo:
            pagina_pagos = 1
            ultima_pagos = 1
            status_text.text("Fase 1/2: Analizando historial de pagos para ubicar clases especiales...")
            
            while pagina_pagos <= ultima_pagos:
                url_pagos_paginada = f"{url_base_payments}&page={pagina_pagos}"
                resp_pagos = requests.get(url_pagos_paginada, headers=headers)
                
                if resp_pagos.status_code in [200, 201]:
                    datos_pagos = resp_pagos.json().get('data', resp_pagos.json())
                    if isinstance(datos_pagos, dict):
                        if pagina_pagos == 1:
                            ultima_pagos = datos_pagos.get('last_page', 1)
                        registros_pagos = datos_pagos.get('data', [])
                    elif isinstance(datos_pagos, list):
                        registros_pagos = datos_pagos
                        ultima_pagos = 1
                    else:
                        registros_pagos = []
                    
                    for pago in registros_pagos:
                        pago_str = str(pago).upper()
                        alumno_info = pago.get('member', pago)
                        id_alumno = str(alumno_info.get('internal_id', alumno_info.get('id', pago.get('member_id', ''))))
                        
                        if buscar_kids and "KIDS" in pago_str:
                            ids_de_ninos.add(id_alumno)
                            
                        # El nuevo filtro caza cualquier paquete que contenga la palabra "POLE"
                        if buscar_pole and "POLE" in pago_str:
                            ids_de_pole.add(id_alumno)
                            
                    progress_bar.progress(min(pagina_pagos / ultima_pagos, 1.0))
                    pagina_pagos += 1
                    time.sleep(0.05)
                else:
                    st.error(f"❌ Error en la conexión de pagos (Código: {resp_pagos.status_code}).")
                    error_conexion = True
                    break

        # ==========================================
        # FASE 2: Descargar Lista General de Alumnos
        # ==========================================
        if not error_conexion:
            todos_los_alumnos = []
            pagina_actual = 1
            ultima_pagina = 1 
            
            progress_bar.progress(0)
            status_text.text("Fase 2/2: Descargando lista general de alumnos...")
            
            while pagina_actual <= ultima_pagina:
                url_paginada = f"{url_base_members}&page={pagina_actual}"
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
                    time.sleep(0.05)
                else:
                    st.error(f"❌ Error de conexión (Código: {respuesta.status_code}). Verifica que tu Token sea nuevo.")
                    error_conexion = True
                    break

        progress_bar.empty()
        status_text.empty()
        
        # ==========================================
        # FASE 3: Cruzar la Información y Armar Tabla
        # ==========================================
        if not error_conexion:
            filas_procesadas = []
            fecha_hoy = datetime.now().date()
            meses_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            mes_actual_nombre = meses_es[datetime.now().month - 1]
            
            for alumno in todos_los_alumnos:
                clave_entri = str(alumno.get('internal_id', alumno.get('id', '')))
                
                # Evaluamos los filtros que encendiste
                if buscar_kids:
                    es_kid_texto = "SI" if clave_entri in ids_de_ninos else "NO"
                else:
                    es_kid_texto = "No analizado"
                    
                if buscar_pole:
                    es_pole_texto = "SI" if clave_entri in ids_de_pole else "NO"
                else:
                    es_pole_texto = "No analizado"

                telefono_bruto = str(alumno.get('phone', alumno.get('cellphone', '0'))).strip()
                telefono_limpio = obtener_ultimos_10_digitos(telefono_bruto)
                
                nombre_pila = str(alumno.get('name', alumno.get('nombre', ''))).strip()
                apellido = str(alumno.get('last_name', alumno.get('apellido', alumno.get('apellidos', '')))).strip()
                nombre_completo = f"{nombre_pila} {apellido}".strip()
                
                fecha_nac = alumno.get('manual_id', '') 
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
                
                salio = 'SI' if (telefono_limpio not in activos_whatsapp and len(telefono_limpio) == 10) else ''
                
                filas_procesadas.append({
                    'Num de telefono': telefono_limpio, 
                    'Nombre': nombre_completo,
                    '¿Es Kid?': es_kid_texto,
                    '¿Pole Dance?': es_pole_texto,
                    'Fecha de nacimiento': fecha_nac,
                    '¿Cumpleaños este mes?': cumple_este_mes,
                    'Registro en entri': clave_entri,
                    'Ultima Visita': ultima_visita,
                    'Dias sin venir': dias_sin_venir,
                    'Estatus': estatus,
                    'SALIO DE GRUPO': salio
                })
                
            columnas_base = [
                'Num de telefono', 'Nombre', '¿Es Kid?', '¿Pole Dance?', 'Fecha de nacimiento', '¿Cumpleaños este mes?',
                'Registro en entri', 'Ultima Visita', 'Dias sin venir', 'Estatus', 'SALIO DE GRUPO'
            ]
            df_final = pd.DataFrame(filas_procesadas, columns=columnas_base)
            
            mask_validos = df_final['Num de telefono'].str.len() == 10
            mask_duplicados = df_final.duplicated(subset=['Num de telefono'], keep=False)
            
            df_final['¿Num Duplicado?'] = ''
            df_final.loc[mask_validos & mask_duplicados, '¿Num Duplicado?'] = 'SI'
            
            columnas_ordenadas = [
                'Num de telefono', '¿Num Duplicado?', 'Nombre', '¿Es Kid?', '¿Pole Dance?', 'Fecha de nacimiento', 
                '¿Cumpleaños este mes?', 'Registro en entri', 'Ultima Visita', 'Dias sin venir', 
                'Estatus', 'SALIO DE GRUPO'
            ]
            df_final = df_final[columnas_ordenadas]
            
            # --- DESPLIEGUE DE MÉTRICAS ---
            st.markdown("### 📊 Reporte General de Alumnos")
            
            # Ajustamos las métricas dinámicamente según lo que activaste
            metricas_a_mostrar = [
                ("Total Alumnos", len(df_final)),
                ("Activos 🕺", len(df_final[df_final['Estatus'] == 'Activo'])),
                ("En Riesgo ⚠️", len(df_final[df_final['Estatus'] == 'En Riesgo']))
            ]
            
            # Insertamos las métricas extra solo si activaste su respectivo checkbox
            if buscar_kids:
                metricas_a_mostrar.insert(1, ("KIDS 👧👦", len(df_final[df_final['¿Es Kid?'] == 'SI'])))
            if buscar_pole:
                metricas_a_mostrar.insert(1, ("Pole Dance 💃", len(df_final[df_final['¿Pole Dance?'] == 'SI'])))
                
            metricas_a_mostrar.append(("Fuera del Grupo", len(df_final[df_final['SALIO DE GRUPO'] == 'SI'])))
            metricas_a_mostrar.append(("Repetidos 👯", len(df_final[df_final['¿Num Duplicado?'] == 'SI'])))
            
            cols = st.columns(len(metricas_a_mostrar))
            for idx, (titulo, valor) in enumerate(metricas_a_mostrar):
                cols[idx].metric(titulo, valor)
            
            st.markdown("### 📋 Vista Previa de la Base de Datos")
            st.dataframe(df_final, use_container_width=True, hide_index=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Control SAG')
            
            st.download_button(
                label="📥 Descargar Base de Datos en Excel",
                data=buffer.getvalue(),
                file_name=f"Control_SAG_{fecha_hoy}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
else:
    st.info("💡 Sube tu archivo de WhatsApp y pega tu Token en el menú de la izquierda para comenzar.")