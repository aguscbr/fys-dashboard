"""
README - Dashboard de Fábrica de Pinceles y Pinceletas (Streamlit)

Requisitos:
- Python 3.9+
- Librerías: streamlit, pandas, plotly, openpyxl (opcional para Excel)

Instalación rápida:
1) Crear y activar entorno virtual (opcional pero recomendado)
   - Windows PowerShell:
       python -m venv .venv
       .venv\\Scripts\\Activate.ps1
2) Instalar dependencias:
       pip install streamlit pandas plotly openpyxl
3) Ejecutar la app:
       streamlit run dashboard_fabrica_pinceles.py

Notas:
- La aplicación crea una carpeta ./data con CSVs iniciales si no existen.
- Autenticación simple (usuario/contraseña hardcodeada) al inicio.
- Importar/Exportar permite trabajar con CSV y Excel (si openpyxl está instalado).
- Los operarios pueden registrar entradas, ajustar stock y registrar producción.
- Se validan stocks para no permitir valores negativos.
"""

# ==========================
# Imports
# ==========================
import io
import os
from pathlib import Path
from datetime import datetime, date, timedelta

import pandas as pd
import streamlit as st
import plotly.express as px

# ==========================
# Configuración general de la app
# ==========================
st.set_page_config(page_title="Fábrica de Pinceles", page_icon="🖌️", layout="wide")

DATA_DIR = Path("data")
FILES = {
    "catalogo": DATA_DIR / "materials_catalog.csv",
    "stock_mp": DATA_DIR / "stock_actual.csv",
    "movimientos": DATA_DIR / "stock_movimientos.csv",
    "productos": DATA_DIR / "stock_productos.csv",
    "produccion": DATA_DIR / "produccion.csv",
    "pedidos": DATA_DIR / "pedidos.csv",
    "despachos": DATA_DIR / "despachos.csv",
}

USERS = {
    # Autenticación muy básica (hardcodeada)
    "admin": "admin123",
    "operario": "operario123",
}

# Colores por categoría
COLOR_TIPO = {
    "Mango": "#1f77b4",
    "Cerda": "#2ca02c",
    "Chapita": "#ff7f0e",
    "Manguito pinceleta": "#8c564b",
    "Chapita pinceleta": "#e377c2",
    "Cerda pinceleta": "#7f7f7f",
}

# ==========================
# Utilidades de datos
# ==========================

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def build_default_catalog() -> pd.DataFrame:
    medidas = ["7", "10", "15", "20", "25", "30"]
    filas = []
    # Mangos: medidas x virola 1/2
    for m in medidas:
        for v in ["virola 1", "virola 2"]:
            filas.append({"tipo": "Mango", "variante": f"{m} - {v}", "stock_minimo": 50})
    # Cerda (normal)
    for m in medidas:
        filas.append({"tipo": "Cerda", "variante": m, "stock_minimo": 50})
    # Chapitas (normal)
    for m in medidas:
        filas.append({"tipo": "Chapita", "variante": m, "stock_minimo": 50})
    # Pinceletas
    for color in ["blanco", "gris"]:
        filas.append({"tipo": "Manguito pinceleta", "variante": color, "stock_minimo": 30})
    for m in ["40", "50"]:
        filas.append({"tipo": "Chapita pinceleta", "variante": m, "stock_minimo": 30})
    filas.append({"tipo": "Cerda pinceleta", "variante": "estándar", "stock_minimo": 30})
    df = pd.DataFrame(filas)
    df["stock_minimo"] = df["stock_minimo"].astype(int)
    return df


def init_files():
    ensure_data_dir()
    if not FILES["catalogo"].exists():
        df = build_default_catalog()
        df.to_csv(FILES["catalogo"], index=False)
    if not FILES["stock_mp"].exists():
        cat = pd.read_csv(FILES["catalogo"])  # tipo, variante, stock_minimo
        stock = cat.copy()
        stock["stock_actual"] = 0
        stock["ultima_entrada"] = pd.NaT
        stock["proveedor_mas_frecuente"] = ""
        stock.to_csv(FILES["stock_mp"], index=False)
    if not FILES["movimientos"].exists():
        cols = [
            "fecha",
            "tipo_movimiento",
            "tipo",
            "variante",
            "cantidad",
            "proveedor",
            "documento",
            "observaciones",
            "usuario",
        ]
        pd.DataFrame(columns=cols).to_csv(FILES["movimientos"], index=False)
    if not FILES["productos"].exists():
        # Estructura por variante de producto terminado
        pd.DataFrame(columns=["tipo_producto", "variante_producto", "stock_actual"]).to_csv(FILES["productos"], index=False)
    if not FILES["produccion"].exists():
        cols = ["fecha", "tipo_producto", "cantidad", "usuario", "nota"]
        pd.DataFrame(columns=cols).to_csv(FILES["produccion"], index=False)
    if not FILES["pedidos"].exists():
        cols = [
            "id",
            "fecha",
            "cliente",
            "tipo_producto",
            "variante_producto",
            "cantidad",
            "fecha_entrega",
            "estado",
            "nota",
        ]
        pd.DataFrame(columns=cols).to_csv(FILES["pedidos"], index=False)
    if not FILES["despachos"].exists():
        cols = [
            "id_despacho",
            "fecha",
            "pedido_id",
            "cliente",
            "tipo_producto",
            "variante_producto",
            "cantidad",
            "nota",
            "usuario",
        ]
        pd.DataFrame(columns=cols).to_csv(FILES["despachos"], index=False)


def read_df(path: Path) -> pd.DataFrame:
    if not path.exists():
        init_files()
    df = pd.read_csv(path)
    # Normalización básica para evitar desalineaciones por espacios o tipos
    try:
        if path == FILES["catalogo"] or path == FILES["stock_mp"]:
            if "tipo" in df.columns:
                df["tipo"] = df["tipo"].astype(str).str.strip()
            if "variante" in df.columns:
                df["variante"] = df["variante"].astype(str).str.strip()
        if path == FILES["movimientos"]:
            for col in ["tipo", "variante", "tipo_movimiento", "proveedor", "documento", "observaciones", "usuario"]:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
    except Exception:
        pass
    return df


def save_df(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False)


def add_movimiento(fecha: datetime, tipo_mov: str, tipo: str, variante: str, cantidad: int,
                   proveedor: str = "", documento: str = "", observaciones: str = "", usuario: str = ""):
    mov = read_df(FILES["movimientos"])
    fila = {
        "fecha": pd.to_datetime(fecha).strftime("%Y-%m-%d %H:%M:%S"),
        "tipo_movimiento": tipo_mov,  # ENTRADA | SALIDA | AJUSTE
        "tipo": tipo,
        "variante": variante,
        "cantidad": int(cantidad),
        "proveedor": proveedor,
        "documento": documento,
        "observaciones": observaciones,
        "usuario": usuario,
    }
    mov = pd.concat([mov, pd.DataFrame([fila])], ignore_index=True)
    save_df(mov, FILES["movimientos"])


def actualizar_stock(tipo: str, variante: str, delta: int, proveedor: str = "", es_entrada: bool = False):
    stock = read_df(FILES["stock_mp"])
    mask = (stock["tipo"] == tipo) & (stock["variante"] == variante)
    if not mask.any():
        st.warning("La combinación Tipo/Variante no existe en catálogo. Agregándola con stock mínimo 0.")
        nuevo = pd.DataFrame([
            {
                "tipo": tipo,
                "variante": variante,
                "stock_minimo": 0,
                "stock_actual": 0,
                "ultima_entrada": pd.NaT,
                "proveedor_mas_frecuente": proveedor or "",
            }
        ])
        stock = pd.concat([stock, nuevo], ignore_index=True)
        mask = (stock["tipo"] == tipo) & (stock["variante"] == variante)
    # Validar coincidencia única
    idxs = stock.index[mask].tolist()
    if len(idxs) != 1:
        st.error(f"Hay {len(idxs)} filas coincidiendo con {tipo} - {variante}. Revise duplicados en 'Stock Actual'.")
        return False, None
    idx = idxs[0]
    nuevo_stock = int(stock.at[idx, "stock_actual"]) + int(delta)
    if nuevo_stock < 0:
        return False, int(stock.at[idx, "stock_actual"])  # no permitir negativo
    stock.at[idx, "stock_actual"] = nuevo_stock
    if es_entrada:
        stock.at[idx, "ultima_entrada"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if proveedor:
            # cálculo simple del proveedor más frecuente
            mov = read_df(FILES["movimientos"])
            provs = (
                mov[(mov["tipo"] == tipo) & (mov["variante"] == variante) & (mov["tipo_movimiento"] == "ENTRADA")]
                ["proveedor"].value_counts()
            )
            if not provs.empty:
                stock.at[idx, "proveedor_mas_frecuente"] = provs.index[0]
    save_df(stock, FILES["stock_mp"])
    return True, nuevo_stock


# ==========================
# Autenticación
# ==========================

def login_ui():
    st.title("🖌️ Fábrica de Pinceles - Dashboard")
    st.subheader("Inicio de sesión")
    with st.form("login_form", clear_on_submit=False):
        user = st.text_input("Usuario", value="")
        pwd = st.text_input("Contraseña", type="password", value="")
        submitted = st.form_submit_button("Ingresar")
        if submitted:
            if user in USERS and USERS[user] == pwd:
                st.session_state["auth_user"] = user
                st.success("Ingreso exitoso")
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")


# ==========================
# Componentes UI
# ==========================

def sidebar_menu():
    st.sidebar.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/Paintbrush-icon.png/64px-Paintbrush-icon.png",
        width=48,
    )
    st.sidebar.title("Panel")
    st.sidebar.write(f"Usuario: {st.session_state.get('auth_user','-')}")
    pagina = st.sidebar.radio(
        "Navegación",
        [
            "Dashboard",
            "Pedidos",
            "Entradas de Materia Prima",
            "Stock Actual",
            "Producción / Salidas",
            "Stock Producto Terminado",
            "Importar / Exportar",
        ],
        index=0,
    )
    st.sidebar.markdown("---")
    st.sidebar.caption("FYS - Gestión simple de pinceles")
    return pagina


def resumen_stock_cards(stock_df: pd.DataFrame):
    totales = stock_df.groupby("tipo")["stock_actual"].sum().reset_index()
    cols = st.columns(max(3, len(totales)))
    for i, (_, row) in enumerate(totales.iterrows()):
        with cols[i % len(cols)]:
            st.metric(label=row["tipo"], value=int(row["stock_actual"]))


def grafico_barras_stock(stock_df: pd.DataFrame):
    total_tipo = stock_df.groupby("tipo", as_index=False)["stock_actual"].sum()
    total_tipo["color"] = total_tipo["tipo"].map(COLOR_TIPO)
    fig = px.bar(total_tipo, x="tipo", y="stock_actual", color="tipo",
                 color_discrete_map=COLOR_TIPO, title="Stock por tipo (total)")
    st.plotly_chart(fig, use_container_width=True)


def alertas_stock_bajo(stock_df: pd.DataFrame):
    bajos = stock_df[stock_df["stock_actual"] < stock_df["stock_minimo"]]
    if bajos.empty:
        st.success("No hay alertas de stock bajo.")
        return
    st.warning("Materiales con stock bajo:")
    st.dataframe(bajos[["tipo", "variante", "stock_actual", "stock_minimo"]], use_container_width=True)


def grafico_evolucion(movs: pd.DataFrame):
    if movs.empty:
        st.info("Sin datos históricos de movimientos.")
        return
    movs = movs.copy()
    movs["fecha"] = pd.to_datetime(movs["fecha"], errors="coerce")
    desde = datetime.now() - timedelta(days=30)
    movs = movs[movs["fecha"] >= desde]
    if movs.empty:
        st.info("No hay movimientos en los últimos 30 días.")
        return
    sign = movs["tipo_movimiento"].map({"ENTRADA": 1, "SALIDA": -1, "AJUSTE": 1}).fillna(0)
    movs["delta"] = movs["cantidad"].astype(int) * sign
    diario = movs.groupby([pd.Grouper(key="fecha", freq="D"), "tipo"], as_index=False)["delta"].sum()
    diario = diario.rename(columns={"delta": "variacion"})
    fig = px.line(diario, x="fecha", y="variacion", color="tipo", title="Variación diaria de stock (últimos 30 días)")
    st.plotly_chart(fig, use_container_width=True)


# ==========================
# Páginas
# ==========================

def page_dashboard():
    stock = read_df(FILES["stock_mp"])  # tipo, variante, stock_minimo, stock_actual, ultima_entrada, proveedor_mas_frecuente
    movs = read_df(FILES["movimientos"])  # historial
    try:
        pedidos_df = read_df(FILES["pedidos"]).copy()
    except Exception:
        pedidos_df = pd.DataFrame()
    try:
        prods_df = read_df(FILES["productos"]).copy()
    except Exception:
        prods_df = pd.DataFrame()

    st.header("Dashboard Principal")
    st.caption("Resumen general con filtros por fecha y cliente")

    # Filtros globales
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        desde = st.date_input("Desde", value=(date.today() - timedelta(days=30)), key="dash_desde")
    with c2:
        hasta = st.date_input("Hasta", value=date.today(), key="dash_hasta")
    with c3:
        clientes = sorted(pedidos_df["cliente"].dropna().astype(str).unique().tolist()) if not pedidos_df.empty else []
        cliente_sel = st.selectbox("Cliente", [""] + clientes, index=0)
    with c4:
        tipo_mp = st.selectbox("Tipo MP", [""] + sorted(stock["tipo"].dropna().astype(str).unique().tolist()) if not stock.empty else [""], index=0)

    # Aplicar filtros a copias de datos
    movs_f = movs.copy()
    if not movs_f.empty:
        movs_f["fecha"] = pd.to_datetime(movs_f["fecha"], errors="coerce")
        movs_f = movs_f[(movs_f["fecha"] >= pd.to_datetime(desde)) & (movs_f["fecha"] <= pd.to_datetime(hasta) + pd.Timedelta(days=1))]
    pedidos_f = pedidos_df.copy()
    if not pedidos_f.empty and cliente_sel:
        pedidos_f = pedidos_f[pedidos_f["cliente"].astype(str) == cliente_sel]

    # Tabs de vistas
    tabs = st.tabs(["Resumen", "Stock MP", "Terminados", "Pedidos", "Producción"])

    # Tab Resumen
    with tabs[0]:
        st.subheader("KPIs")
        cK1, cK2, cK3, cK4 = st.columns(4)
        total_mp = int(stock["stock_actual"].sum()) if "stock_actual" in stock.columns and not stock.empty else 0
        total_prod = int(prods_df["stock_actual"].sum()) if not prods_df.empty and "stock_actual" in prods_df.columns else 0
        pedidos_abiertos = 0
        if not pedidos_f.empty and "estado" in pedidos_f.columns:
            pedidos_abiertos = int(pedidos_f[pedidos_f["estado"].isin(["pendiente", "confirmado", "en_produccion"])].shape[0])
        ult_sem = movs_f[movs_f["tipo_movimiento"].isin(["ENTRADA", "SALIDA"])] if not movs_f.empty else pd.DataFrame()
        prod_sem = 0
        try:
            prod_hist = read_df(FILES["produccion"]).copy()
            if not prod_hist.empty:
                prod_hist["fecha"] = pd.to_datetime(prod_hist["fecha"], errors="coerce")
                desde7 = pd.Timestamp.today().normalize() - pd.Timedelta(days=7)
                prod_sem = int(prod_hist[prod_hist["fecha"] >= desde7]["cantidad"].sum())
        except Exception:
            pass
        with cK1:
            st.metric("Stock MP total", total_mp)
        with cK2:
            st.metric("Stock terminados", total_prod)
        with cK3:
            st.metric("Pedidos abiertos", pedidos_abiertos)
        with cK4:
            st.metric("Producido 7 días", prod_sem)

        st.markdown("---")
        cA, cB = st.columns([2, 1])
        with cA:
            st.subheader("Stock por tipo (MP)")
            grafico_barras_stock(stock if not tipo_mp else stock[stock["tipo"].astype(str) == tipo_mp])
        with cB:
            st.subheader("Alertas")
            alertas_stock_bajo(stock)

    # Tab Stock MP
    with tabs[1]:
        st.subheader("Materias Primas")
        st.caption("Filtre por tipo/variante y revise mínimos y últimas entradas")
        tipo_opt = st.selectbox("Tipo", [""] + sorted(stock["tipo"].astype(str).unique().tolist()) if not stock.empty else [""], index=0, key="tabmp_tipo")
        var_opt = ""
        if tipo_opt:
            vs = sorted(stock[stock["tipo"].astype(str) == tipo_opt]["variante"].astype(str).unique().tolist())
            var_opt = st.selectbox("Variante", [""] + vs, index=0, key="tabmp_var")
        df_mp = stock.copy()
        if tipo_opt:
            df_mp = df_mp[df_mp["tipo"].astype(str) == tipo_opt]
        if var_opt:
            df_mp = df_mp[df_mp["variante"].astype(str) == var_opt]
        st.dataframe(df_mp.sort_values(["tipo", "variante"]).reset_index(drop=True), use_container_width=True)

    # Tab Terminados
    with tabs[2]:
        st.subheader("Productos Terminados")
        if prods_df.empty:
            st.info("Sin productos terminados registrados.")
        else:
            tsel = st.selectbox("Tipo producto", [""] + sorted(prods_df["tipo_producto"].astype(str).unique().tolist()), index=0, key="tabprod_tipo")
            vsel = ""
            if tsel:
                vsel = st.selectbox("Variante", [""] + sorted(prods_df[prods_df["tipo_producto"].astype(str) == tsel]["variante_producto"].astype(str).unique().tolist()), index=0, key="tabprod_var")
            dfp = prods_df.copy()
            if tsel:
                dfp = dfp[dfp["tipo_producto"].astype(str) == tsel]
            if vsel:
                dfp = dfp[dfp["variante_producto"].astype(str) == vsel]
            st.dataframe(dfp.sort_values(["tipo_producto", "variante_producto"]).reset_index(drop=True), use_container_width=True)

    # Tab Pedidos
    with tabs[3]:
        st.subheader("Pedidos")
        if pedidos_f.empty:
            st.info("Sin pedidos para los filtros actuales.")
        else:
            ests = ["", "pendiente", "confirmado", "en_produccion", "completado", "cancelado"]
            est_sel = st.selectbox("Estado", ests, index=0, key="tabped_est")
            tipo_sel = st.selectbox("Tipo", [""] + sorted(pedidos_f["tipo_producto"].astype(str).unique().tolist()), index=0, key="tabped_tipo")
            dfpeds = pedidos_f.copy()
            if est_sel:
                dfpeds = dfpeds[dfpeds["estado"] == est_sel]
            if tipo_sel:
                dfpeds = dfpeds[dfpeds["tipo_producto"].astype(str) == tipo_sel]
            # KPIs de pedidos
            cpa, cpb, cpc = st.columns(3)
            with cpa:
                st.metric("Tot. pedidos", int(dfpeds.shape[0]))
            with cpb:
                atras = 0
                try:
                    dfpeds["fecha_entrega"] = pd.to_datetime(dfpeds["fecha_entrega"], errors="coerce")
                    atras = int(dfpeds[(dfpeds["estado"].isin(["pendiente", "confirmado"])) & (dfpeds["fecha_entrega"] < pd.Timestamp.today().normalize())].shape[0])
                except Exception:
                    pass
                st.metric("Vencidos", atras)
            with cpc:
                prox7 = 0
                try:
                    prox7 = int(dfpeds[(dfpeds["estado"].isin(["pendiente", "confirmado"])) & (dfpeds["fecha_entrega"] >= pd.Timestamp.today().normalize()) & (dfpeds["fecha_entrega"] <= pd.Timestamp.today().normalize() + pd.Timedelta(days=7))].shape[0])
                except Exception:
                    pass
                st.metric("Vencen 7 días", prox7)
            st.dataframe(dfpeds.sort_values(["estado", "fecha_entrega"], na_position="last"), use_container_width=True)

    # Tab Producción
    with tabs[4]:
        st.subheader("Producción")
        try:
            prod_hist = read_df(FILES["produccion"]).copy()
        except Exception:
            prod_hist = pd.DataFrame()
        if prod_hist.empty:
            st.info("Sin registros de producción.")
        else:
            prod_hist["fecha"] = pd.to_datetime(prod_hist["fecha"], errors="coerce")
            d_ini = pd.to_datetime(desde)
            d_fin = pd.to_datetime(hasta) + pd.Timedelta(days=1)
            prod_f = prod_hist[(prod_hist["fecha"] >= d_ini) & (prod_hist["fecha"] <= d_fin)]
            tsel = st.selectbox("Tipo producto", [""] + sorted(prod_f["tipo_producto"].dropna().astype(str).unique().tolist()), index=0, key="tabprod2_tipo")
            if tsel:
                prod_f = prod_f[prod_f["tipo_producto"].astype(str) == tsel]
            st.dataframe(prod_f.sort_values("fecha", ascending=False), use_container_width=True)


def page_entradas():
    st.header("Gestión de Materia Prima - Entradas")
    catalogo = read_df(FILES["catalogo"])  # tipo, variante, stock_minimo

    # Selección de tipo fuera del formulario para que cambie dinámicamente los campos
    tipo = st.selectbox("Tipo de materia prima", sorted(catalogo["tipo"].unique().tolist()), key="entrada_tipo")

    with st.form("entrada_form"):
        medidas_std = ["7", "10", "15", "20", "25", "30"]
        if tipo == "Mango":
            virolas = ["virola 1", "virola 2"]
            m_sel = st.selectbox("Medida", [""] + medidas_std, key="entrada_mango_medida")
            v_sel = st.selectbox("Virola", [""] + virolas, key="entrada_mango_virola")
            variante = f"{m_sel} - {v_sel}" if m_sel and v_sel else ""
        elif tipo == "Cerda":
            m_sel = st.selectbox("Milímetros de cerda", [""] + medidas_std, key="entrada_cerda_mm")
            variante = m_sel if m_sel else ""
        elif tipo == "Chapita":
            m_sel = st.selectbox("Medida", [""] + medidas_std, key="entrada_chapita_medida")
            variante = m_sel if m_sel else ""
        elif tipo == "Manguito pinceleta":
            color = st.selectbox("Color de manguito", [""] + ["blanco", "gris"], key="entrada_manguito_color")
            variante = color if color else ""
        elif tipo == "Chapita pinceleta":
            m_sel = st.selectbox("Medida chapita pinceleta", [""] + ["40", "50"], key="entrada_chapita_p_medida")
            variante = m_sel if m_sel else ""
        elif tipo == "Cerda pinceleta":
            variante = st.selectbox("Variante", [""] + ["estándar"], key="entrada_cerda_p_variante")
        else:
            # Fallback a lista del catálogo si aparece un tipo nuevo
            variantes = sorted(catalogo[catalogo["tipo"] == tipo]["variante"].unique().tolist())
            variante = st.selectbox("Variante", [""] + variantes, key="entrada_variante")
        # Mostrar destino exacto para claridad
        st.caption(f"Destino: {tipo} - {variante}")
        cantidad = st.number_input("Cantidad recibida", min_value=1, step=1, value=10)
        fecha = st.date_input("Fecha", value=date.today())
        proveedor = st.text_input("Proveedor", value="")
        documento = st.text_input("N° remito/factura (opcional)", value="")
        obs = st.text_area("Observaciones", value="")
        submitted = st.form_submit_button("Registrar entrada")
        if submitted:
            tipo_s = str(tipo).strip()
            variante_s = str(variante).strip()
            if not variante_s:
                st.error("Seleccione una variante válida antes de registrar.")
                st.stop()
            # Validación contra catálogo (debe existir exactamente una fila)
            cat_mask = (catalogo["tipo"].astype(str).str.strip() == tipo_s) & (catalogo["variante"].astype(str).str.strip() == variante_s)
            count_cat = int(cat_mask.sum())
            if count_cat == 0:
                st.error(f"La variante seleccionada no existe en el catálogo: {tipo_s} - {variante_s}")
                st.stop()
            if count_cat > 1:
                st.error(f"Variantes duplicadas en catálogo para {tipo_s} - {variante_s}. Corrija el catálogo antes de continuar.")
                st.stop()
            ok, nuevo = actualizar_stock(tipo_s, variante_s, delta=int(cantidad), proveedor=proveedor, es_entrada=True)
            if ok:
                add_movimiento(datetime.combine(fecha, datetime.now().time()), "ENTRADA", tipo_s, variante_s, int(cantidad), proveedor, documento, obs, st.session_state.get("auth_user",""))
                st.success(f"Entrada registrada en: {tipo_s} - {variante_s}. Nuevo stock: {nuevo}")
            else:
                st.error("No se pudo actualizar el stock.")

    st.markdown("---")
    st.subheader("Histórico de entradas")
    movs = read_df(FILES["movimientos"])
    if movs.empty:
        st.info("Sin movimientos.")
        return
    movs = movs[movs["tipo_movimiento"] == "ENTRADA"].copy()
    colf1, colf2, colt = st.columns(3)
    with colf1:
        d_ini = st.date_input("Desde", value=date.today() - timedelta(days=30))
    with colf2:
        d_fin = st.date_input("Hasta", value=date.today())
    with colt:
        tipo_sel = st.multiselect("Filtrar por tipo", sorted(catalogo["tipo"].unique().tolist()))
    movs["fecha"] = pd.to_datetime(movs["fecha"], errors="coerce")
    movs = movs[(movs["fecha"] >= pd.to_datetime(d_ini)) & (movs["fecha"] <= pd.to_datetime(d_fin) + pd.Timedelta(days=1))]
    if tipo_sel:
        movs = movs[movs["tipo"].isin(tipo_sel)]
    st.dataframe(movs.sort_values("fecha", ascending=False), use_container_width=True)


def editable_stock_table():
    stock = read_df(FILES["stock_mp"])  # tipo, variante, stock_minimo, stock_actual, ultima_entrada, proveedor_mas_frecuente
    st.subheader("Stock actual de materias primas")
    st.caption("Edite el stock mínimo recomendado y realice ajustes manuales. No se permite stock negativo.")

    # Filtros para navegación
    with st.expander("Filtros", expanded=True):
        tipos_all = sorted(stock["tipo"].astype(str).unique().tolist())
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            tipo_f = st.selectbox("Tipo", ["Todos"] + tipos_all, index=0, key="stk_f_tipo")
        with c2:
            if tipo_f and tipo_f != "Todos":
                variantes_opts = sorted(stock[stock["tipo"].astype(str) == tipo_f]["variante"].astype(str).unique().tolist())
            else:
                variantes_opts = sorted(stock["variante"].astype(str).unique().tolist())
            variante_f = st.selectbox("Variante", ["Todos"] + variantes_opts, index=0, key="stk_f_variante")
        with c3:
            buscar = st.text_input("Buscar (tipo/variante)", value="", key="stk_f_buscar")
        solo_bajo = st.checkbox("Solo stock bajo", value=False, key="stk_f_bajo")

    # Edición rápida: permitir ajustar stock_actual (+/-) mediante formulario por fila seleccionada
    with st.expander("Ajuste manual de stock (rotura, error de conteo, etc.)"):
        tipos = sorted(stock["tipo"].unique().tolist())
        tipo = st.selectbox("Tipo", tipos, key="aj_tipo")
        variantes = stock[stock["tipo"] == tipo]["variante"].unique().tolist()
        variante = st.selectbox("Variante", variantes, key="aj_var")
        delta = st.number_input("Ajuste (+ entra / - sale)", value=0, step=1, min_value=-100000, max_value=100000, key="aj_delta")
        obs = st.text_input("Motivo/observación", value="Ajuste manual")
        if st.button("Aplicar ajuste", type="primary"):
            ok, nuevo = actualizar_stock(tipo, variante, delta=int(delta))
            if ok:
                mov_tipo = "AJUSTE" if delta >= 0 else "SALIDA"  # para analítica
                add_movimiento(datetime.now(), mov_tipo, tipo, variante, abs(int(delta)), "", "", obs, st.session_state.get("auth_user",""))
                st.success(f"Ajuste aplicado. Nuevo stock: {nuevo}")
                st.rerun()
            else:
                st.error("El ajuste provocaría stock negativo. Operación cancelada.")

    # Herramientas para duplicados (tipo, variante)
    with st.expander("Detectar y resolver duplicados (tipo + variante)", expanded=False):
        dups = (
            stock.assign(_cnt=1)
            .groupby(["tipo", "variante"], as_index=False)["_cnt"].count()
        )
        dups = dups[dups["_cnt"] > 1]
        if dups.empty:
            st.caption("No se detectaron duplicados.")
        else:
            st.warning("Se detectaron duplicados. Puede fusionarlos sumando el stock.")
            st.dataframe(dups, use_container_width=True)
            if st.button("Fusionar duplicados (sumar stock y dejar una fila)"):
                base = read_df(FILES["stock_mp"]).copy()
                # Agrupar y mantener mínimos/última y proveedor de forma razonable
                agg = base.groupby(["tipo", "variante"], as_index=False).agg({
                    "stock_minimo": "max",
                    "stock_actual": "sum",
                    "ultima_entrada": "max",
                    "proveedor_mas_frecuente": "first",
                })
                save_df(agg, FILES["stock_mp"])
                st.success("Duplicados fusionados correctamente.")
                st.rerun()

    # Edición de stock_minimo por tabla editable
    edit_cols = ["stock_minimo"]
    show_cols = ["tipo", "variante", "stock_actual", "stock_minimo", "ultima_entrada", "proveedor_mas_frecuente"]
    stock_show = stock[show_cols].copy()
    # Aplicar filtros
    if 'tipo_f' in locals() and tipo_f and tipo_f != "Todos":
        stock_show = stock_show[stock_show["tipo"].astype(str) == tipo_f]
    if 'variante_f' in locals() and variante_f and variante_f != "Todos":
        stock_show = stock_show[stock_show["variante"].astype(str) == variante_f]
    if 'buscar' in locals() and buscar:
        patt = buscar.lower()
        stock_show = stock_show[stock_show.apply(lambda r: patt in str(r['tipo']).lower() or patt in str(r['variante']).lower(), axis=1)]
    if 'solo_bajo' in locals() and solo_bajo:
        stock_show = stock_show[stock_show["stock_actual"].astype(int) < stock_show["stock_minimo"].astype(int)]
    edited = st.data_editor(stock_show, use_container_width=True, num_rows="dynamic", disabled=[c for c in show_cols if c not in edit_cols])

    if st.button("Guardar cambios de mínimos"):
        # Sincronizar stock_minimo editado
        base = read_df(FILES["stock_mp"])
        merged = base.drop(columns=["stock_minimo"]).merge(
            edited[["tipo", "variante", "stock_minimo"]], on=["tipo", "variante"], how="left"
        )
        merged["stock_minimo"] = merged["stock_minimo"].fillna(0).astype(int)
        save_df(merged, FILES["stock_mp"])
        st.success("Cambios guardados")
        st.rerun()



def page_stock_actual():
    st.header("Stock Actual")
    editable_stock_table()


def page_produccion():
    st.header("Producción / Salida de Materia Prima")
    st.caption("Registre producción terminada y descuente materias primas manualmente si corresponde.")

    productos = read_df(FILES["productos"])  # tipo_producto, variante_producto (opcional), stock_actual
    catalogo = read_df(FILES["catalogo"])  # para materias primas

    # Selector fuera del form para que el cambio de tipo re-renderice los campos dinámicos
    tipos_prod = productos["tipo_producto"].dropna().unique().tolist()
    # Asegurar que opciones básicas existan
    for base in ["pincel normal", "pinceleta"]:
        if base not in tipos_prod:
            tipos_prod.append(base)
    tipo_prod = st.selectbox("Tipo de producto terminado", tipos_prod, key="prod_tipo_producto")

    with st.form("prod_form"):
        medidas_std = ["7", "10", "15", "20", "25", "30"]
        variante_producto = ""
        # Si es pincel normal, permitir elegir medida/virola para automatizar consumo
        if tipo_prod == "pincel normal":
            virolas = ["virola 1", "virola 2"]
            m_sel = st.selectbox("Medida del pincel", medidas_std, key="prod_pincel_medida")
            v_sel = st.selectbox("Virola del pincel", virolas, key="prod_pincel_virola")
            variante_producto = f"{m_sel} - {v_sel}"
        elif tipo_prod == "pinceleta":
            # Variante por color y chapita (mostrar etiquetas en plural y 'del N') pero mapear a valores del catálogo
            color_label = st.selectbox("Color (pinceletas)", ["blancas", "grises"], key="prod_pinceleta_color")
            chapita_label = st.selectbox("Medida (pinceletas)", ["del 40", "del 50"], key="prod_pinceleta_chapita")
            color = "blanco" if color_label == "blancas" else "gris"
            chapita_p = "40" if chapita_label.endswith("40") else "50"
            variante_producto = f"{color} - {chapita_p}"
        cant = st.number_input("Cantidad producida", min_value=1, step=1, value=10)
        auto_desc = False
        if tipo_prod == "pincel normal":
            auto_desc = st.checkbox("Descontar materias primas automáticamente (mango y chapita)", value=True)
        if tipo_prod == "pinceleta":
            auto_desc = st.checkbox("Descontar materias primas automáticamente (manguito, chapita y cerda)", value=True)
        descontar_mp = st.checkbox("Descontar materias primas manualmente")
        items = []
        if descontar_mp:
            st.markdown("### Materias primas a descontar")
            # Permitimos agregar hasta N líneas sencillas
            for i in range(3):
                with st.expander(f"Ítem MP #{i+1}", expanded=(i == 0)):
                    tipo = st.selectbox(f"Tipo MP #{i+1}", [""] + sorted(catalogo["tipo"].unique().tolist()), key=f"mp_tipo_{i}")
                    if tipo:
                        variantes = catalogo[catalogo["tipo"] == tipo]["variante"].unique().tolist()
                    else:
                        variantes = []
                    variante = st.selectbox(f"Variante MP #{i+1}", [""] + variantes, key=f"mp_var_{i}")
                    cant_mp = st.number_input(f"Cantidad MP #{i+1}", min_value=0, step=1, value=0, key=f"mp_cant_{i}")
                    items.append((tipo, variante, int(cant_mp)))
        nota = st.text_input("Nota/observaciones", value="")
        submitted = st.form_submit_button("Registrar producción")
        if submitted:
            # 1) Registrar producción en tabla produccion
            prod = read_df(FILES["produccion"])  # fecha, tipo_producto, cantidad, usuario, nota
            fila = {
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tipo_producto": tipo_prod,
                "cantidad": int(cant),
                "usuario": st.session_state.get("auth_user", ""),
                "nota": nota,
            }
            if tipo_prod == "pincel normal" and variante_producto:
                fila["variante_producto"] = variante_producto
            prod = pd.concat([prod, pd.DataFrame([fila])], ignore_index=True)
            save_df(prod, FILES["produccion"]) 
            # 2) Si corresponde, armar consumo automático
            auto_items = []
            if tipo_prod == "pincel normal" and auto_desc and variante_producto:
                # Consumir 1 Mango medida-virola y 1 Chapita medida por unidad
                medida_sel = variante_producto.split(" - ")[0]
                mango_var = variante_producto
                chapita_var = medida_sel
                auto_items = [("Mango", mango_var, int(cant)), ("Chapita", chapita_var, int(cant))]
            elif tipo_prod == "pinceleta" and auto_desc and variante_producto:
                # Variante_producto ej: "blanco - 40" => consumir 1 Manguito (color), 1 Chapita pinceleta (40/50) y 1 Cerda pinceleta (estándar)
                color_sel, chapita_sel = variante_producto.split(" - ")
                auto_items = [
                    ("Manguito pinceleta", color_sel, int(cant)),
                    ("Chapita pinceleta", chapita_sel, int(cant)),
                    ("Cerda pinceleta", "estándar", int(cant)),
                ]

            # Unir con items manuales válidos
            manual_validos = [(t, v, c) for (t, v, c) in items if t and v and c > 0]
            all_items = auto_items + manual_validos

            # 3) Validar stock suficiente antes de aplicar
            insuf = []
            stock_df = read_df(FILES["stock_mp"])
            for (t, v, c) in all_items:
                mask = (stock_df["tipo"].astype(str).str.strip() == str(t).strip()) & (stock_df["variante"].astype(str).str.strip() == str(v).strip())
                if not mask.any():
                    insuf.append(f"No existe en stock: {t} - {v}")
                else:
                    disp = int(stock_df.loc[mask, "stock_actual"].iloc[0])
                    if disp < int(c):
                        insuf.append(f"Stock insuficiente para {t} - {v} (disp {disp} < req {c})")
            if insuf:
                st.error("No se registró la producción por falta de stock:\n" + "\n".join(insuf))
                return

            # 4) Aplicar descuentos y registrar movimientos
            for (t, v, c) in all_items:
                ok, _ = actualizar_stock(t, v, delta=-int(c))
                if ok:
                    add_movimiento(datetime.now(), "SALIDA", t, v, int(c), "", "", f"Producción {tipo_prod}", st.session_state.get("auth_user",""))
                else:
                    st.error(f"Fallo al descontar {t} - {v}. Operación interrumpida.")
                    return

            # 5) Actualizar stock de producto terminado por variante
            prods = read_df(FILES["productos"]).copy()
            # Migración: si no existe columna variante_producto, crearla
            if "variante_producto" not in prods.columns:
                prods["variante_producto"] = ""
            mask = (prods["tipo_producto"].astype(str).str.strip() == str(tipo_prod).strip()) & (
                prods["variante_producto"].astype(str).str.strip() == str(variante_producto).strip()
            )
            if not mask.any():
                prods = pd.concat([
                    prods,
                    pd.DataFrame([{ "tipo_producto": tipo_prod, "variante_producto": variante_producto, "stock_actual": 0 }])
                ], ignore_index=True)
                mask = (prods["tipo_producto"].astype(str).str.strip() == str(tipo_prod).strip()) & (
                    prods["variante_producto"].astype(str).str.strip() == str(variante_producto).strip()
                )
            idx = prods.index[mask][0]
            prods.at[idx, "stock_actual"] = int(prods.at[idx, "stock_actual"]) + int(cant)
            save_df(prods, FILES["productos"]) 
            st.success("Producción registrada correctamente.")

    st.markdown("---")
    st.subheader("Historial de producción")
    prod = read_df(FILES["produccion"]).copy()
    if prod.empty:
        st.info("Sin registros de producción.")
    else:
        st.dataframe(prod.sort_values("fecha", ascending=False), use_container_width=True)



def page_stock_producto():
    st.header("Stock de Producto Terminado")
    prods = read_df(FILES["productos"]).copy()
    if prods.empty:
        st.info("Sin productos terminados registrados.")
        return

    # Filtros por tipo y variante
    tipos = sorted(prods["tipo_producto"].astype(str).unique().tolist())
    c1, c2 = st.columns(2)
    with c1:
        tipo_sel = st.selectbox("Filtrar por tipo", [""] + tipos, index=0, key="prod_filtro_tipo")
    with c2:
        variantes_opts = sorted(prods[prods["tipo_producto"].astype(str) == tipo_sel]["variante_producto"].astype(str).unique().tolist()) if tipo_sel else []
        var_sel = st.selectbox("Filtrar por variante", [""] + variantes_opts, index=0, key="prod_filtro_var")

    df_show = prods.copy()
    if tipo_sel:
        df_show = df_show[df_show["tipo_producto"].astype(str) == tipo_sel]
    if var_sel:
        df_show = df_show[df_show["variante_producto"].astype(str) == var_sel]
    st.dataframe(df_show.sort_values(["tipo_producto", "variante_producto"]).reset_index(drop=True), use_container_width=True)

    # Ajuste manual de stock de terminados
    with st.expander("Ajuste manual de stock de terminados"):
        t_aj = st.selectbox("Tipo de producto", tipos, key="prod_aj_tipo")
        vars_aj = sorted(prods[prods["tipo_producto"].astype(str) == t_aj]["variante_producto"].astype(str).unique().tolist())
        v_aj = st.selectbox("Variante", vars_aj, key="prod_aj_var")
        delta = st.number_input("Ajuste (+ suma / - resta)", value=0, step=1, min_value=-100000, max_value=100000, key="prod_aj_delta")
        if st.button("Aplicar ajuste a terminados", type="primary"):
            base = read_df(FILES["productos"]).copy()
            mask = (base["tipo_producto"].astype(str).str.strip() == str(t_aj).strip()) & (base["variante_producto"].astype(str).str.strip() == str(v_aj).strip())
            if not mask.any():
                st.error("No se encontró la variante seleccionada en productos terminados.")
            else:
                idx = base.index[mask][0]
                nuevo_stock = int(base.at[idx, "stock_actual"]) + int(delta)
                if nuevo_stock < 0:
                    st.error("El ajuste provocaría stock negativo. Operación cancelada.")
                else:
                    base.at[idx, "stock_actual"] = nuevo_stock
                    save_df(base, FILES["productos"])
                    st.success(f"Ajuste aplicado. Nuevo stock de terminados: {nuevo_stock}")
                    st.rerun()


# ==========================
# Pedidos
# ==========================

def compute_mp_needs(tipo_prod: str, variante_producto: str, cantidad: int):
    items = []
    if tipo_prod == "pincel normal" and variante_producto:
        medida_sel = variante_producto.split(" - ")[0]
        mango_var = variante_producto
        chapita_var = medida_sel
        items = [("Mango", mango_var, int(cantidad)), ("Chapita", chapita_var, int(cantidad))]
    elif tipo_prod == "pinceleta" and variante_producto:
        try:
            color_sel, chapita_sel = variante_producto.split(" - ")
        except ValueError:
            color_sel, chapita_sel = "", ""
        if color_sel and chapita_sel:
            items = [
                ("Manguito pinceleta", color_sel, int(cantidad)),
                ("Chapita pinceleta", chapita_sel, int(cantidad)),
                ("Cerda pinceleta", "estándar", int(cantidad)),
            ]
    return items


def page_pedidos():
    st.header("Pedidos de Clientes")
    st.caption("Cree, edite y gestione pedidos. Si falta stock de MP se alerta, pero no se bloquea el alta.")

    pedidos = read_df(FILES["pedidos"])
    productos = read_df(FILES["productos"])  # para opciones de tipos

    with st.expander("Nuevo pedido", expanded=False):
        tipos_prod = productos["tipo_producto"].dropna().unique().tolist()
        for base in ["pincel normal", "pinceleta"]:
            if base not in tipos_prod:
                tipos_prod.append(base)
        tipo_prod = st.selectbox("Tipo de producto", tipos_prod, key="ped_tipo")
        variante_producto = ""
        medidas_std = ["7", "10", "15", "20", "25", "30"]
        if tipo_prod == "pincel normal":
            virolas = ["virola 1", "virola 2"]
            m_sel = st.selectbox("Medida del pincel", medidas_std, key="ped_pincel_medida")
            v_sel = st.selectbox("Virola del pincel", virolas, key="ped_pincel_virola")
            variante_producto = f"{m_sel} - {v_sel}"
        elif tipo_prod == "pinceleta":
            color_label = st.selectbox("Color (pinceletas)", ["blancas", "grises"], key="ped_pinceleta_color")
            chapita_label = st.selectbox("Medida (pinceletas)", ["del 40", "del 50"], key="ped_pinceleta_chapita")
            color = "blanco" if color_label == "blancas" else "gris"
            chapita_p = "40" if chapita_label.endswith("40") else "50"
            variante_producto = f"{color} - {chapita_p}"

        c1, c2, c3 = st.columns(3)
        with c1:
            cliente = st.text_input("Cliente", key="ped_cliente")
        with c2:
            cant = st.number_input("Cantidad", min_value=1, step=1, value=10, key="ped_cant")
        with c3:
            f_entrega = st.date_input("Fecha entrega", value=date.today(), key="ped_fent")
        nota = st.text_input("Nota (opcional)", key="ped_nota")

        needs = compute_mp_needs(tipo_prod, variante_producto, int(cant))
        if needs:
            stock_df = read_df(FILES["stock_mp"]) 
            insuf = []
            for (t, v, c) in needs:
                mask = (stock_df["tipo"].astype(str).str.strip() == str(t).strip()) & (stock_df["variante"].astype(str).str.strip() == str(v).strip())
                if not mask.any():
                    insuf.append(f"No existe en stock: {t} - {v}")
                else:
                    disp = int(stock_df.loc[mask, "stock_actual"].iloc[0])
                    if disp < int(c):
                        insuf.append(f"Insuficiente {t} - {v} (disp {disp} < req {c})")
            if insuf:
                st.warning("Stock de MP potencialmente insuficiente para este pedido:\n" + "\n".join(insuf))

        if st.button("Agregar pedido", type="primary"):
            pedidos = read_df(FILES["pedidos"])  # recargar
            nuevo_id = int(pedidos["id"].max()) + 1 if ("id" in pedidos.columns and not pedidos.empty) else 1
            fila = {
                "id": nuevo_id,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cliente": cliente,
                "tipo_producto": tipo_prod,
                "variante_producto": variante_producto,
                "cantidad": int(cant),
                "fecha_entrega": pd.to_datetime(f_entrega).strftime("%Y-%m-%d"),
                "estado": "pendiente",
                "nota": nota,
            }
            pedidos = pd.concat([pedidos, pd.DataFrame([fila])], ignore_index=True)
            save_df(pedidos, FILES["pedidos"]) 
            st.success("Pedido agregado.")
            st.rerun()

    st.markdown("---")
    st.subheader("Listado de pedidos")
    pedidos = read_df(FILES["pedidos"]) 
    if pedidos.empty:
        st.info("No hay pedidos registrados.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        estados = ["todos", "pendiente", "confirmado", "en_produccion", "completado", "cancelado"]
        est_f = st.selectbox("Estado", estados, index=0)
    with c2:
        tipo_f = st.selectbox("Tipo", ["Todos"] + sorted(pedidos["tipo_producto"].astype(str).unique().tolist()), index=0)
    with c3:
        buscar = st.text_input("Buscar cliente/variante", value="")

    df_show = pedidos.copy()
    def calc_disp(row):
        items = compute_mp_needs(row.get("tipo_producto", ""), row.get("variante_producto", ""), int(row.get("cantidad", 0)))
        stock_df = read_df(FILES["stock_mp"]) 
        faltas = []
        for (t, v, c) in items:
            mask = (stock_df["tipo"].astype(str).str.strip() == str(t).strip()) & (stock_df["variante"].astype(str).str.strip() == str(v).strip())
            if not mask.any():
                faltas.append(f"{t}-{v}:0/{c}")
            else:
                disp = int(stock_df.loc[mask, "stock_actual"].iloc[0])
                if disp < int(c):
                    faltas.append(f"{t}-{v}:{disp}/{c}")
        return "OK" if not faltas else "Falta: " + ", ".join(faltas)

    df_show["disponibilidad_mp"] = df_show.apply(calc_disp, axis=1)

    if est_f != "todos":
        df_show = df_show[df_show["estado"] == est_f]
    if tipo_f != "Todos":
        df_show = df_show[df_show["tipo_producto"] == tipo_f]
    if buscar:
        patt = buscar.lower()
        df_show = df_show[df_show.apply(lambda r: patt in str(r["cliente"]).lower() or patt in str(r["variante_producto"]).lower(), axis=1)]

    # Tabla de pedidos (editable) inmediatamente después de los filtros
    st.caption("Edite el estado/fecha/nota y guarde cambios.")
    editable_cols = ["estado", "fecha_entrega", "nota"]
    view_cols = ["id", "fecha", "cliente", "tipo_producto", "variante_producto", "cantidad", "fecha_entrega", "estado", "nota", "disponibilidad_mp"]
    edited = st.data_editor(
        df_show[view_cols],
        use_container_width=True,
        num_rows="dynamic",
        disabled=[c for c in view_cols if c not in editable_cols],
        hide_index=True,
        key="pedidos_editor"
    )

    if st.button("Guardar cambios de pedidos"):
        base = read_df(FILES["pedidos"]).copy()
        base = base.drop(columns=["estado", "fecha_entrega", "nota"]).merge(
            edited[["id", "estado", "fecha_entrega", "nota"]], on="id", how="left"
        )
        for col in ["estado", "fecha_entrega", "nota"]:
            if col not in base.columns:
                base[col] = ""
        save_df(base, FILES["pedidos"]) 
        st.success("Pedidos actualizados.")
        st.rerun()

    st.markdown("---")
    st.subheader("Acciones por pedido (producción y despacho)")
    if not df_show.empty:
        for _, r in df_show.sort_values("fecha", ascending=False).iterrows():
            pid = int(r["id"])
            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 2, 2])
            with c1:
                st.caption(f"Pedido #{pid}")
                st.text(f"{r['cliente']}")
            with c2:
                st.text(f"{r['tipo_producto']}")
                st.text(f"{r['variante_producto']}")
            with c3:
                st.text(f"Cant pedida: {int(r['cantidad'])}")
                st.text(f"Estado: {r['estado']}")
            # Producción por fila
            with c4:
                st.markdown("**Producción**")
                modo_prod = st.radio(f"Modo prod #{pid}", ["Completo", "Parcial"], key=f"prod_row_modo_{pid}", horizontal=True)
                qty_prod = 0
                if modo_prod == "Parcial":
                    qty_prod = st.number_input(f"Cant a producir #{pid}", min_value=0, step=1, value=0, key=f"prod_row_qty_{pid}")
                if st.button("Generar producción", key=f"prod_row_btn_{pid}"):
                    pedidos_base = read_df(FILES["pedidos"]).copy()
                    rowb = pedidos_base[pedidos_base["id"] == pid]
                    if rowb.empty:
                        st.warning(f"Pedido {pid} no encontrado.")
                        st.rerun()
                    rb = rowb.iloc[0]
                    tipo_producto = str(rb["tipo_producto"]).strip()
                    variante_producto = str(rb.get("variante_producto", "")).strip()
                    solicitado = int(rb["cantidad"])
                    qty = solicitado if modo_prod == "Completo" else int(qty_prod)
                    if qty <= 0:
                        st.warning("Cantidad a producir inválida.")
                        st.rerun()
                    needs = compute_mp_needs(tipo_producto, variante_producto, int(qty))
                    stock_df = read_df(FILES["stock_mp"]).copy()
                    insuf = []
                    for (t, v, c) in needs:
                        mask = (stock_df["tipo"].astype(str).str.strip() == str(t).strip()) & (stock_df["variante"].astype(str).str.strip() == str(v).strip())
                        if not mask.any():
                            insuf.append(f"No existe en stock: {t} - {v}")
                        else:
                            disp = int(stock_df.loc[mask, "stock_actual"].iloc[0])
                            if disp < int(c):
                                insuf.append(f"Stock insuficiente {t} - {v} (disp {disp} < req {c})")
                    if insuf:
                        st.warning("No se pudo generar producción por falta de MP:\n" + "\n".join(insuf))
                        st.rerun()
                    prod = read_df(FILES["produccion"]).copy()
                    fila = {
                        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "tipo_producto": tipo_producto,
                        "cantidad": int(qty),
                        "usuario": st.session_state.get("auth_user", ""),
                        "nota": f"Generado desde pedido {pid}",
                        "variante_producto": variante_producto,
                    }
                    prod = pd.concat([prod, pd.DataFrame([fila])], ignore_index=True)
                    save_df(prod, FILES["produccion"]) 
                    for (t, v, c) in needs:
                        ok, _ = actualizar_stock(str(t).strip(), str(v).strip(), delta=-int(c))
                        if ok:
                            add_movimiento(datetime.now(), "SALIDA", str(t).strip(), str(v).strip(), int(c), "", "", f"Producción desde pedido {pid}", st.session_state.get("auth_user", ""))
                        else:
                            st.warning(f"Fallo al descontar MP {t} - {v}.")
                            st.rerun()
                    prods = read_df(FILES["productos"]).copy()
                    if "variante_producto" not in prods.columns:
                        prods["variante_producto"] = ""
                    maskp = (prods["tipo_producto"].astype(str).str.strip() == tipo_producto) & (prods["variante_producto"].astype(str).str.strip() == variante_producto)
                    if not maskp.any():
                        prods = pd.concat(
                            [prods, pd.DataFrame([{"tipo_producto": tipo_producto, "variante_producto": variante_producto, "stock_actual": 0}])],
                            ignore_index=True,
                        )
                        maskp = (prods["tipo_producto"].astype(str).str.strip() == tipo_producto) & (prods["variante_producto"].astype(str).str.strip() == variante_producto)
                    idxp = prods.index[maskp][0]
                    prods.at[idxp, "stock_actual"] = int(prods.at[idxp, "stock_actual"]) + int(qty)
                    save_df(prods, FILES["productos"]) 
                    pedidos_base.loc[pedidos_base["id"] == pid, "estado"] = "en_produccion"
                    save_df(pedidos_base, FILES["pedidos"]) 
                    st.success(f"Producción generada para pedido {pid}.")
                    st.rerun()
            # Despacho por fila
            with c6:
                st.markdown("**Despacho**")
                modo_row = st.radio(f"Modo desp #{pid}", ["Completo", "Parcial"], key=f"desp_row_modo_{pid}", horizontal=True)
                qty_row = 0
                if modo_row == "Parcial":
                    qty_row = st.number_input(f"Cant a despachar #{pid}", min_value=0, step=1, value=0, key=f"desp_row_qty_{pid}")
                if st.button("Despachar", key=f"desp_row_btn_{pid}"):
                    pedidos_base = read_df(FILES["pedidos"]).copy()
                    rowb = pedidos_base[pedidos_base["id"] == pid]
                    if rowb.empty:
                        st.warning(f"Pedido {pid} no encontrado.")
                        st.rerun()
                    rb = rowb.iloc[0]
                    tipo_prod = str(rb["tipo_producto"]).strip()
                    variante_producto = str(rb.get("variante_producto", "")).strip()
                    solicitado = int(rb["cantidad"])
                    qty = solicitado if modo_row == "Completo" else int(qty_row)
                    if qty <= 0:
                        st.warning("Cantidad a despachar inválida.")
                        st.rerun()
                    prods = read_df(FILES["productos"]).copy()
                    if "variante_producto" not in prods.columns:
                        prods["variante_producto"] = ""
                    maskp = (prods["tipo_producto"].astype(str).str.strip() == tipo_prod) & (prods["variante_producto"].astype(str).str.strip() == variante_producto)
                    if not maskp.any():
                        st.warning(f"No hay stock de terminados para {tipo_prod} - {variante_producto}.")
                        st.rerun()
                    idxp = prods.index[maskp][0]
                    disp = int(prods.at[idxp, "stock_actual"])
                    if disp < qty:
                        st.warning(f"Stock de terminados insuficiente (disp {disp} < req {qty}).")
                        st.rerun()
                    prods.at[idxp, "stock_actual"] = disp - qty
                    desp = read_df(FILES["despachos"]) if FILES["despachos"].exists() else pd.DataFrame()
                    next_id = int(desp["id_despacho"].max()) + 1 if (not desp.empty and "id_despacho" in desp.columns) else 1
                    fila_d = {
                        "id_despacho": next_id,
                        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "pedido_id": int(pid),
                        "cliente": rb.get("cliente", ""),
                        "tipo_producto": tipo_prod,
                        "variante_producto": variante_producto,
                        "cantidad": qty,
                        "nota": "",
                        "usuario": st.session_state.get("auth_user", ""),
                    }
                    desp = pd.concat([desp, pd.DataFrame([fila_d])], ignore_index=True)
                    if modo_row == "Completo" and qty >= solicitado:
                        pedidos_base.loc[pedidos_base["id"] == pid, "estado"] = "completado"
                    else:
                        pedidos_base.loc[pedidos_base["id"] == pid, "estado"] = "confirmado"
                    save_df(prods, FILES["productos"]) 
                    save_df(desp, FILES["despachos"]) 
                    save_df(pedidos_base, FILES["pedidos"]) 
                    st.success(f"Pedido {pid} despachado.")
                    st.rerun()

    


# ==========================
# Importar / Exportar
# ==========================

def df_to_excel_bytes(dfs_dict: dict) -> bytes:
    try:
        import openpyxl  # noqa: F401
    except Exception:
        # Si no hay openpyxl, devolvemos None para bloquear exportación Excel
        return None
    from pandas import ExcelWriter
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in dfs_dict.items():
            df.to_excel(writer, sheet_name=name[:30], index=False)
    buf.seek(0)
    return buf.getvalue()


def page_import_export():
    st.header("Importar / Exportar")
    st.caption("Cargue o descargue datos en CSV o Excel.")

    # Exportar
    st.subheader("Exportar datos")
    cat = read_df(FILES["catalogo"]) 
    stock = read_df(FILES["stock_mp"]) 
    movs = read_df(FILES["movimientos"]) 
    prods = read_df(FILES["productos"]) 
    prod = read_df(FILES["produccion"]) 
    # Pedidos puede no existir en instalaciones previas
    try:
        peds = read_df(FILES["pedidos"]) 
    except Exception:
        peds = pd.DataFrame()

    colc1, colc2 = st.columns(2)
    with colc1:
        st.download_button("Descargar CSV - Catálogo", data=cat.to_csv(index=False).encode("utf-8"), file_name="catalogo.csv", mime="text/csv")
        st.download_button("Descargar CSV - Stock Materias Primas", data=stock.to_csv(index=False).encode("utf-8"), file_name="stock_mp.csv", mime="text/csv")
        st.download_button("Descargar CSV - Movimientos", data=movs.to_csv(index=False).encode("utf-8"), file_name="movimientos.csv", mime="text/csv")
    with colc2:
        st.download_button("Descargar CSV - Stock Productos", data=prods.to_csv(index=False).encode("utf-8"), file_name="stock_productos.csv", mime="text/csv")
        st.download_button("Descargar CSV - Producción", data=prod.to_csv(index=False).encode("utf-8"), file_name="produccion.csv", mime="text/csv")
        if not peds.empty:
            st.download_button("Descargar CSV - Pedidos", data=peds.to_csv(index=False).encode("utf-8"), file_name="pedidos.csv", mime="text/csv")
        # Excel (si openpyxl está disponible)
        excel_bytes = df_to_excel_bytes({
            "catalogo": cat,
            "stock_mp": stock,
            "movimientos": movs,
            "stock_productos": prods,
            "produccion": prod,
            "pedidos": peds,
        })
        if excel_bytes:
            st.download_button("Descargar TODO en Excel", data=excel_bytes, file_name="dashboard_pinceles.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("Instale 'openpyxl' para exportar a Excel: pip install openpyxl")

    st.markdown("---")
    # Importar
    st.subheader("Importar datos")
    st.caption("Puede reemplazar los archivos actuales. Se recomienda descargar un respaldo antes.")

    with st.expander("Importar Catálogo (tipo/variante/stock_minimo)" ):
        up = st.file_uploader("CSV o Excel", type=["csv", "xlsx"], key="up_cat")
        if up is not None:
            if up.name.endswith(".csv"):
                df = pd.read_csv(up)
            else:
                df = pd.read_excel(up)
            req = {"tipo", "variante", "stock_minimo"}
            if not req.issubset(df.columns):
                st.error(f"Faltan columnas requeridas: {req}")
            else:
                df["stock_minimo"] = df["stock_minimo"].fillna(0).astype(int)
                save_df(df, FILES["catalogo"])
                # sincronizar stock_mp con catálogo
                stock = read_df(FILES["stock_mp"]) 
                stock = stock.merge(df[["tipo", "variante", "stock_minimo"]], on=["tipo", "variante"], how="right", suffixes=("", "_new"))
                stock["stock_minimo"] = stock.get("stock_minimo_new", stock["stock_minimo"]) 
                if "stock_minimo_new" in stock.columns:
                    stock = stock.drop(columns=["stock_minimo_new"])
                stock["stock_actual"] = stock["stock_actual"].fillna(0).astype(int)
                stock["ultima_entrada"] = stock["ultima_entrada"].fillna("")
                stock["proveedor_mas_frecuente"] = stock["proveedor_mas_frecuente"].fillna("")
                save_df(stock, FILES["stock_mp"])
                st.success("Catálogo importado y stock sincronizado.")

    with st.expander("Importar Stock Materias Primas"):
        up = st.file_uploader("CSV o Excel", type=["csv", "xlsx"], key="up_stock")
        if up is not None:
            if up.name.endswith(".csv"):
                df = pd.read_csv(up)
            else:
                df = pd.read_excel(up)
            req = {"tipo", "variante", "stock_minimo", "stock_actual"}
            if not req.issubset(df.columns):
                st.error(f"Faltan columnas requeridas: {req}")
            else:
                df["stock_minimo"] = df["stock_minimo"].fillna(0).astype(int)
                df["stock_actual"] = df["stock_actual"].fillna(0).astype(int)
                # Validación no negativo
                if (df["stock_actual"] < 0).any():
                    st.error("Hay valores negativos en stock_actual. Corrija antes de importar.")
                else:
                    save_df(df, FILES["stock_mp"])
                    st.success("Stock de materias primas importado.")

    with st.expander("Importar Movimientos (reemplaza historial)"):
        up = st.file_uploader("CSV o Excel", type=["csv", "xlsx"], key="up_movs")
        if up is not None:
            if up.name.endswith(".csv"):
                df = pd.read_csv(up)
            else:
                df = pd.read_excel(up)
            req = {"fecha", "tipo_movimiento", "tipo", "variante", "cantidad"}
            if not req.issubset(df.columns):
                st.error(f"Faltan columnas requeridas: {req}")
            else:
                save_df(df, FILES["movimientos"])
                st.success("Movimientos importados.")

    with st.expander("Importar Stock de Productos"):
        up = st.file_uploader("CSV o Excel", type=["csv", "xlsx"], key="up_prod_stock")
        if up is not None:
            if up.name.endswith(".csv"):
                df = pd.read_csv(up)
            else:
                df = pd.read_excel(up)
            # Estructura por variante
            req = {"tipo_producto", "variante_producto", "stock_actual"}
            if not req.issubset(df.columns):
                st.error(f"Faltan columnas requeridas: {req}")
            else:
                df["tipo_producto"] = df["tipo_producto"].astype(str).str.strip()
                df["variante_producto"] = df["variante_producto"].astype(str).str.strip()
                df["stock_actual"] = df["stock_actual"].fillna(0).astype(int)
                if (df["stock_actual"] < 0).any():
                    st.error("Hay valores negativos en stock_actual de productos.")
                else:
                    save_df(df, FILES["productos"])
                    st.success("Stock de productos importado.")

    with st.expander("Importar Pedidos"):
        up = st.file_uploader("CSV o Excel", type=["csv", "xlsx"], key="up_pedidos")
        if up is not None:
            if up.name.endswith(".csv"):
                df = pd.read_csv(up)
            else:
                df = pd.read_excel(up)
            req = {"id", "fecha", "cliente", "tipo_producto", "variante_producto", "cantidad", "fecha_entrega", "estado", "nota"}
            if not req.issubset(df.columns):
                st.error(f"Faltan columnas requeridas: {req}")
            else:
                save_df(df, FILES["pedidos"]) 
                st.success("Pedidos importados.")


# ==========================
# Main
# ==========================

def main():
    init_files()
    if "auth_user" not in st.session_state:
        login_ui()
        return
    page = sidebar_menu()
    if page == "Dashboard":
        page_dashboard()
    elif page == "Pedidos":
        page_pedidos()
    elif page == "Entradas de Materia Prima":
        page_entradas()
    elif page == "Stock Actual":
        page_stock_actual()
    elif page == "Producción / Salidas":
        page_produccion()
    elif page == "Stock Producto Terminado":
        page_stock_producto()
    elif page == "Importar / Exportar":
        page_import_export()


if __name__ == "__main__":
    main()
