import asyncio
import json
import os

import streamlit as st
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# URL del servidor MCP (puedes sobreescribirla con OMDB_MCP_URL en entorno)
MCP_URL = os.getenv("OMDB_MCP_URL", "http://127.0.0.1:8000/mcp")


async def _call_mcp_tool_async(tool_name: str, arguments: dict | None = None):
    """
    Conecta al servidor MCP HTTP, inicializa sesión y llama al tool indicado.
    Devuelve el objeto ToolResult del SDK MCP.
    """
    async with streamablehttp_client(MCP_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments or {})
            return result


def call_mcp_tool(tool_name: str, arguments: dict | None = None):
    """
    Wrapper síncrono para Streamlit: hace asyncio.run() sobre la función async.
    """
    return asyncio.run(_call_mcp_tool_async(tool_name, arguments))


def unwrap_tool_result(result):
    """
    Intenta extraer un dict "bonito" del ToolResult.
    - Si el servidor devuelve JSON como texto, lo parseamos.
    - Si no, devolvemos el model_dump completo para inspección.
    """
    if hasattr(result, "model_dump"):
        data = result.model_dump(mode="json")

        # data["content"] suele ser una lista de bloques TextContent/JSON/etc.
        content = data.get("content") or []
        for part in content:
            text = part.get("text")
            if not text:
                continue
            # Intentamos parsear el texto como JSON estructurado
            try:
                return json.loads(text)
            except Exception:
                # No era JSON; seguimos probando otros bloques
                continue

        # Fallback: devolvemos todo el ToolResult serializado
        return data

    # Fallback muy básico
    return result


# ----------------- UI Streamlit -----------------

st.set_page_config(page_title="OMDb MCP Client", layout="wide")
st.title("Cliente OMDb vía MCP (Streamable HTTP)")

st.caption(f"Servidor MCP: `{MCP_URL}`")

tab_search, tab_details = st.tabs(["🔎 Buscar películas/series", "📄 Detalles por IMDb ID"])

with tab_search:
    st.subheader("Búsqueda OMDb (vía tool MCP `search_movies`)")

    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Título o palabra clave", value="Matrix")
    with col2:
        max_results = st.slider("Máx. resultados", min_value=1, max_value=10, value=5)

    col3, col4 = st.columns(2)
    with col3:
        media_type = st.selectbox(
            "Tipo",
            options=["(cualquiera)", "movie", "series", "episode"],
            index=0,
        )
    with col4:
        year = st.text_input("Año (opcional)", value="")

    if st.button("Buscar en OMDb"):
        if not query.strip():
            st.error("La búsqueda no puede estar vacía.")
        else:
            args: dict = {
                "query": query,
                "max_results": max_results,
            }

            if media_type != "(cualquiera)":
                args["media_type"] = media_type

            if year.strip():
                try:
                    args["year"] = int(year.strip())
                except ValueError:
                    st.warning("El año debe ser un número entero. Se omitirá.")

            with st.spinner("Llamando al tool MCP `search_movies`..."):
                try:
                    raw_result = call_mcp_tool("search_movies", args)
                    payload = unwrap_tool_result(raw_result)
                except Exception as e:
                    st.error(f"Error al llamar al servidor MCP: {e}")
                else:
                    st.success("Resultados recibidos del servidor MCP.")

                    # Intentamos mostrar tabla si tiene 'results'
                    if isinstance(payload, dict) and "results" in payload:
                        st.write(
                            f"Consulta: **{payload.get('query')}** · "
                            f"Total en OMDb: {payload.get('total_results')} · "
                            f"Mostrados: {payload.get('returned')}"
                        )

                        results = payload.get("results", [])
                        if results:
                            st.dataframe(results, use_container_width=True)
                        else:
                            st.info(payload.get("error") or "Sin resultados.")
                    else:
                        st.write("Respuesta completa (no estructurada):")
                        st.json(payload)


with tab_details:
    st.subheader("Detalles de película/serie (tool MCP `get_movie_details`)")

    imdb_id = st.text_input("IMDb ID (ej: tt0133093)", value="tt0133093")
    plot = st.selectbox("Nivel de detalle de sinopsis (plot)", options=["short", "full"], index=0)

    if st.button("Obtener detalles"):
        if not imdb_id.strip():
            st.error("Debes indicar un IMDb ID.")
        else:
            args = {
                "imdb_id": imdb_id.strip(),
                "plot": plot,
            }

            with st.spinner("Llamando al tool MCP `get_movie_details`..."):
                try:
                    raw_result = call_mcp_tool("get_movie_details", args)
                    payload = unwrap_tool_result(raw_result)
                except Exception as e:
                    st.error(f"Error al llamar al servidor MCP: {e}")
                else:
                    if isinstance(payload, dict):
                        st.success(f"Detalles de: {payload.get('title') or imdb_id}")
                        col_left, col_right = st.columns([2, 1])

                        with col_left:
                            st.markdown(f"**Título:** {payload.get('title')}")
                            st.markdown(f"**Año:** {payload.get('year')}")
                            st.markdown(f"**Tipo:** {payload.get('type')}")
                            st.markdown(f"**IMDb rating:** {payload.get('imdb_rating')} ({payload.get('imdb_votes')} votos)")
                            st.markdown(f"**Género:** {payload.get('genre')}")
                            st.markdown(f"**Director:** {payload.get('director')}")
                            st.markdown(f"**Actores:** {payload.get('actors')}")
                            st.markdown("**Sinopsis:**")
                            st.write(payload.get("plot"))

                        with col_right:
                            poster = payload.get("poster")
                            if poster and poster != "N/A":
                                st.image(poster, caption="Poster", use_container_width=True)
                            st.markdown("**Datos brutos:**")
                            st.json(payload)
                    else:
                        st.write("Respuesta completa (no estructurada):")
                        st.json(payload)
