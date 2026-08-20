"""
Herramienta de Búsqueda de Tienda Más Conveniente
==================================================
Dado un listado de productos y la ubicación del usuario (municipio),
recomienda la tienda o combinación mínima de tiendas para armar el pedido.
"""

import streamlit as st
import pandas as pd
from itertools import combinations

# ============================================================
# CONFIGURACIÓN DE TIENDAS Y DISTANCIAS
# ============================================================

# Municipio donde está ubicada cada tienda
TIENDAS_INFO = {
    "LAS TRINITARIAS": {"municipio": "Baruta"},
    "LA GRANJA": {"municipio": "Libertador"},
    "CHACAITO": {"municipio": "Chacao"},
    "TAMANACO": {"municipio": "Baruta"},
    "LA TRINIDAD": {"municipio": "Baruta"},
    "PUENTE YANES": {"municipio": "Libertador"},
    "Fru Fru CCCT": {"municipio": "Chacao"},
}

# Tiendas a excluir del análisis (no son puntos de venta)
TIENDAS_EXCLUIDAS = ["CENTRO DE DISTRIBUCION BOLEITA"]

# Distancias aproximadas entre municipios (en km, simplificado)
# Menor número = más cerca
DISTANCIAS = {
    "Libertador": {"Libertador": 0, "Chacao": 5, "Baruta": 8, "Sucre": 6, "El Hatillo": 12},
    "Chacao": {"Libertador": 5, "Chacao": 0, "Baruta": 4, "Sucre": 4, "El Hatillo": 8},
    "Baruta": {"Libertador": 8, "Chacao": 4, "Baruta": 0, "Sucre": 7, "El Hatillo": 5},
    "Sucre": {"Libertador": 6, "Chacao": 4, "Baruta": 7, "Sucre": 0, "El Hatillo": 10},
    "El Hatillo": {"Libertador": 12, "Chacao": 8, "Baruta": 5, "Sucre": 10, "El Hatillo": 0},
}

MUNICIPIOS = list(DISTANCIAS.keys())


def get_distancia(municipio_usuario: str, tienda_nombre: str) -> float:
    """Obtiene la distancia entre el municipio del usuario y la tienda."""
    municipio_tienda = TIENDAS_INFO.get(tienda_nombre, {}).get("municipio", "Libertador")
    return DISTANCIAS[municipio_usuario][municipio_tienda]


# ============================================================
# CARGA DE DATOS
# ============================================================

@st.cache_data
def cargar_inventario():
    """Carga y preprocesa el archivo de inventario."""
    df = pd.read_excel("input/Archivo inv.xlsx")
    # Excluir centros de distribución
    df = df[~df["TIENDA_NOMBRE"].isin(TIENDAS_EXCLUIDAS)]
    # Filtrar solo productos con stock disponible
    df_stock = df[df["CANT_INVF"] > 0].copy()
    # Limpiar REFPRO (convertir a string)
    df_stock["REFPRO"] = df_stock["REFPRO"].astype(str).str.strip()
    df_stock["CODPRO"] = df_stock["CODPRO"].astype(str).str.strip()
    return df_stock


# ============================================================
# LÓGICA DE BÚSQUEDA
# ============================================================

def buscar_productos(df: pd.DataFrame, codigos: list) -> dict:
    """
    Busca productos por CODPRO o REFPRO.
    Retorna un dict: {codigo_buscado: DataFrame con tiendas que lo tienen}
    """
    resultados = {}
    for codigo in codigos:
        codigo_limpio = codigo.strip()
        if not codigo_limpio:
            continue
        # Buscar en CODPRO y REFPRO
        mask = (df["CODPRO"] == codigo_limpio) | (df["REFPRO"] == codigo_limpio)
        encontrados = df[mask]
        if not encontrados.empty:
            # Agrupar por tienda (sumar stock si hay múltiples registros del mismo producto)
            por_tienda = encontrados.groupby("TIENDA_NOMBRE").agg(
                stock_total=("CANT_INVF", "sum"),
                pvp=("PVP", "first"),
                nombre_producto=("NOMPRO", "first"),
            ).reset_index()
            resultados[codigo_limpio] = por_tienda
        else:
            resultados[codigo_limpio] = pd.DataFrame()
    return resultados


def encontrar_mejor_opcion(resultados: dict, municipio_usuario: str) -> dict:
    """
    Encuentra la tienda o combinación mínima de tiendas más conveniente.
    
    Prioridad:
    1. Tienda más cercana que tenga TODOS los productos
    2. Tienda lejana que tenga TODOS los productos
    3. Menor combinación de tiendas que cubra todos los productos (priorizando cercanía)
    """
    if not resultados:
        return {"tipo": "sin_busqueda", "mensaje": "No se ingresaron productos."}

    # Verificar productos no encontrados
    no_encontrados = [cod for cod, df in resultados.items() if df.empty]
    encontrados = {cod: df for cod, df in resultados.items() if not df.empty}

    if not encontrados:
        return {"tipo": "no_disponible", "mensaje": "Ninguno de los productos está disponible.", "no_encontrados": no_encontrados}

    # Obtener tiendas que tienen cada producto
    productos_por_tienda = {}
    todas_las_tiendas = set()
    
    for codigo, df_tienda in encontrados.items():
        tiendas_con_producto = set(df_tienda["TIENDA_NOMBRE"].tolist())
        productos_por_tienda[codigo] = tiendas_con_producto
        todas_las_tiendas.update(tiendas_con_producto)

    codigos_encontrados = set(encontrados.keys())

    # --- Opción 1 y 2: Una sola tienda con todos los productos ---
    tiendas_completas = []
    for tienda in todas_las_tiendas:
        productos_en_tienda = {cod for cod, tiendas in productos_por_tienda.items() if tienda in tiendas}
        if productos_en_tienda == codigos_encontrados:
            distancia = get_distancia(municipio_usuario, tienda)
            tiendas_completas.append((tienda, distancia))

    if tiendas_completas:
        # Ordenar por distancia (más cercana primero)
        tiendas_completas.sort(key=lambda x: x[1])
        mejor_tienda = tiendas_completas[0][0]
        return {
            "tipo": "tienda_unica",
            "tienda": mejor_tienda,
            "distancia": tiendas_completas[0][1],
            "todas_opciones": tiendas_completas,
            "productos": encontrados,
            "no_encontrados": no_encontrados,
        }

    # --- Opción 3: Menor combinación de tiendas ---
    mejor_combinacion = None
    mejor_distancia_total = float("inf")
    
    tiendas_lista = list(todas_las_tiendas)
    
    # Probar combinaciones de 2, 3, ... tiendas
    for n in range(2, len(tiendas_lista) + 1):
        encontro_combinacion = False
        for combo in combinations(tiendas_lista, n):
            # Verificar si esta combinación cubre todos los productos
            productos_cubiertos = set()
            for tienda in combo:
                for cod, tiendas in productos_por_tienda.items():
                    if tienda in tiendas:
                        productos_cubiertos.add(cod)
            
            if productos_cubiertos == codigos_encontrados:
                # Calcular distancia total de la combinación
                distancia_total = sum(get_distancia(municipio_usuario, t) for t in combo)
                if distancia_total < mejor_distancia_total:
                    mejor_distancia_total = distancia_total
                    mejor_combinacion = combo
                    encontro_combinacion = True
        
        if encontro_combinacion:
            break  # Ya encontramos la menor cantidad de tiendas

    if mejor_combinacion:
        # Asignar qué productos comprar en cada tienda
        asignacion = {tienda: [] for tienda in mejor_combinacion}
        productos_asignados = set()
        
        # Primero asignar productos que solo están en una tienda de la combinación
        for codigo in codigos_encontrados:
            tiendas_disponibles = [t for t in mejor_combinacion if t in productos_por_tienda[codigo]]
            if len(tiendas_disponibles) == 1:
                asignacion[tiendas_disponibles[0]].append(codigo)
                productos_asignados.add(codigo)
        
        # Luego asignar los restantes a la tienda más cercana
        for codigo in codigos_encontrados - productos_asignados:
            tiendas_disponibles = [t for t in mejor_combinacion if t in productos_por_tienda[codigo]]
            tienda_mas_cercana = min(tiendas_disponibles, key=lambda t: get_distancia(municipio_usuario, t))
            asignacion[tienda_mas_cercana].append(codigo)

        return {
            "tipo": "combinacion",
            "combinacion": mejor_combinacion,
            "asignacion": asignacion,
            "distancia_total": mejor_distancia_total,
            "productos": encontrados,
            "no_encontrados": no_encontrados,
        }

    return {
        "tipo": "no_disponible",
        "mensaje": "No se encontró combinación de tiendas que cubra todos los productos.",
        "no_encontrados": no_encontrados,
    }


# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

st.set_page_config(page_title="Buscador de Tienda Conveniente", page_icon="🛒", layout="wide")

st.title("🛒 Buscador de Tienda Más Conveniente")
st.markdown("Ingresá los códigos o referencias de los productos que necesitás y te recomendamos la mejor tienda para hacer tu pedido.")

# Cargar datos
df_inventario = cargar_inventario()

# --- Sidebar ---
st.sidebar.header("📍 Tu ubicación")
municipio = st.sidebar.selectbox("Municipio", MUNICIPIOS, index=0)

st.sidebar.markdown("---")
st.sidebar.header("📦 Productos")
st.sidebar.markdown("Ingresá códigos (CODPRO) o referencias (REFPRO), uno por línea:")

productos_input = st.sidebar.text_area(
    "Códigos / Referencias",
    height=200,
    placeholder="Ejemplo:\n1957461\n4989568102202\n106794-00",
)

buscar = st.sidebar.button("🔍 Buscar tienda", type="primary", use_container_width=True)

# --- Resultados ---
if buscar and productos_input.strip():
    codigos = [c.strip() for c in productos_input.strip().split("\n") if c.strip()]
    
    with st.spinner("Buscando disponibilidad..."):
        resultados = buscar_productos(df_inventario, codigos)
        recomendacion = encontrar_mejor_opcion(resultados, municipio)

    st.markdown("---")

    if recomendacion["tipo"] == "tienda_unica":
        st.success(f"✅ **Recomendación: {recomendacion['tienda']}** (a ~{recomendacion['distancia']} km)")
        st.markdown("Esta tienda tiene **todos** los productos que buscás.")
        
        # Mostrar detalle de productos
        st.subheader("📋 Detalle del pedido")
        datos_tabla = []
        for codigo, df_prod in recomendacion["productos"].items():
            fila = df_prod[df_prod["TIENDA_NOMBRE"] == recomendacion["tienda"]].iloc[0]
            datos_tabla.append({
                "Código": codigo,
                "Producto": fila["nombre_producto"],
                "Stock": int(fila["stock_total"]),
                "PVP ($)": f"{fila['pvp']:.2f}",
            })
        st.table(pd.DataFrame(datos_tabla))

        # Mostrar alternativas
        if len(recomendacion["todas_opciones"]) > 1:
            with st.expander("🏪 Otras tiendas con todos los productos"):
                for tienda, dist in recomendacion["todas_opciones"][1:]:
                    st.write(f"- **{tienda}** (~{dist} km)")

    elif recomendacion["tipo"] == "combinacion":
        st.warning(f"⚠️ Ninguna tienda tiene todos los productos. Se necesitan **{len(recomendacion['combinacion'])} tiendas**:")
        
        for tienda in recomendacion["combinacion"]:
            distancia = get_distancia(municipio, tienda)
            productos_tienda = recomendacion["asignacion"][tienda]
            
            st.subheader(f"🏪 {tienda} (~{distancia} km)")
            datos_tabla = []
            for codigo in productos_tienda:
                df_prod = recomendacion["productos"][codigo]
                fila = df_prod[df_prod["TIENDA_NOMBRE"] == tienda].iloc[0]
                datos_tabla.append({
                    "Código": codigo,
                    "Producto": fila["nombre_producto"],
                    "Stock": int(fila["stock_total"]),
                    "PVP ($)": f"{fila['pvp']:.2f}",
                })
            st.table(pd.DataFrame(datos_tabla))

    elif recomendacion["tipo"] == "no_disponible":
        st.error(f"❌ {recomendacion['mensaje']}")

    # Productos no encontrados
    if recomendacion.get("no_encontrados"):
        st.markdown("---")
        st.warning("⚠️ Los siguientes códigos no se encontraron en el inventario:")
        for cod in recomendacion["no_encontrados"]:
            st.write(f"- `{cod}`")

elif buscar:
    st.info("Ingresá al menos un código o referencia de producto.")
else:
    # Estado inicial
    st.info("👈 Seleccioná tu municipio y los productos que necesitás en el panel izquierdo.")
    
    with st.expander("ℹ️ ¿Cómo funciona?"):
        st.markdown("""
        1. **Seleccioná tu municipio** en el panel izquierdo
        2. **Ingresá los códigos** de producto (CODPRO) o referencias (REFPRO), uno por línea
        3. **Hacé clic en Buscar** y te recomendamos la mejor opción:
           - Si una tienda cercana tiene todo → te la recomendamos
           - Si solo una tienda lejana tiene todo → te indicamos cuál
           - Si ninguna tiene todo → te damos la menor combinación de tiendas
        """)
    
    with st.expander("🏪 Tiendas disponibles"):
        tiendas_df = pd.DataFrame([
            {"Tienda": nombre, "Municipio": info["municipio"]}
            for nombre, info in TIENDAS_INFO.items()
        ])
        st.table(tiendas_df)
