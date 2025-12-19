import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.raster_layers import ImageOverlay
from folium.plugins import MiniMap, Fullscreen, MousePosition
import branca.colormap as cm
import tempfile
import os
import rioxarray as rxr
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# --- CẤU HÌNH TRANG ---
st.set_page_config(layout="wide", page_title="Raster Viewer Pro 2.9")

# --- 1. HÀM XỬ LÝ SỐ LIỆU ---
@st.cache_data
def load_and_reproject(file_path, target_epsg):
    try:
        rds = rxr.open_rasterio(file_path)
        nodata = rds.rio.nodata if rds.rio.nodata is not None else -9999
        rds = rds.where(rds != nodata)
        rds.rio.write_nodata(np.nan, inplace=True)

        if rds.rio.crs is None:
            rds.rio.write_crs(f"EPSG:{target_epsg}", inplace=True)

        rds_wgs = rds.rio.reproject("EPSG:4326")
        data = rds_wgs.squeeze().values
        b = rds_wgs.rio.bounds()
        bounds = [[b[1], b[0]], [b[3], b[2]]]
        return data, bounds, None
    except Exception as e:
        return None, None, str(e)

def colorize_raster(data, colormap_name, opacity, custom_min=None, custom_max=None):
    valid_mask = ~np.isnan(data)
    if not np.any(valid_mask):
        return None, None
    
    d_min, d_max = float(np.nanmin(data[valid_mask])), float(np.nanmax(data[valid_mask]))
    d_mean = float(np.nanmean(data[valid_mask]))

    vmin = custom_min if custom_min is not None else d_min
    vmax = custom_max if custom_max is not None else d_max

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = plt.get_cmap(colormap_name)
    
    img_colored = cmap(norm(data))
    img_colored[~valid_mask, 3] = 0
    
    stats = {"min": d_min, "max": d_max, "mean": d_mean, "used_min": vmin, "used_max": vmax}
    return img_colored, stats

def get_hex_colors(cmap_name, n_steps=20):
    cmap = plt.get_cmap(cmap_name)
    return [mcolors.to_hex(cmap(i)) for i in np.linspace(0, 1, n_steps)]

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("🎛️ Control Panel")
    
    with st.expander("📁 1. Dữ liệu Input", expanded=True):
        uploaded_file = st.file_uploader("Chọn file Raster", type=["asc", "tif", "txt"])
        crs_mode = st.selectbox("Hệ tọa độ", ["UTM (Mét)", "WGS84", "Custom EPSG"])
        input_epsg = 32648
        if crs_mode == "UTM (Mét)":
            c1, c2 = st.columns(2)
            z = c1.number_input("Zone", 48, 60, 48)
            h = c2.selectbox("Bán cầu", ["Bắc", "Nam"])
            input_epsg = 32600 + z if h == "Bắc" else 32700 + z
        elif crs_mode == "Custom EPSG":
            input_epsg = st.number_input("Mã EPSG", value=3405)

    with st.expander("🎨 2. Hiển thị & Legend", expanded=True):
        cmap_name = st.selectbox("Bảng màu", ["turbo", "jet", "viridis", "plasma", "Spectral", "RdYlGn"], index=0)
        opacity = st.slider("Độ trong suốt", 0.0, 1.0, 0.7)
        use_custom_range = st.checkbox("Tùy chỉnh khoảng giá trị")
        c_min, c_max = None, None
        if use_custom_range:
            col_min, col_max = st.columns(2)
            c_min = col_min.number_input("Min", value=0.0)
            c_max = col_max.number_input("Max", value=100.0)

    with st.expander("🛠️ 3. Thông tin Bản đồ", expanded=True):
        map_title_input = st.text_input("Tên bản đồ", value="Kết quả Phân tích")
        map_subtitle_input = st.text_input("Mô tả (Subtitle)", value="Phân bố nồng độ bụi PM2.5 trung bình 24h")
        
        c3, c4 = st.columns(2)
        show_minimap = c3.checkbox("MiniMap", value=True)
        show_fullscreen = c4.checkbox("Fullscreen", value=True)
        show_mouse_pos = st.checkbox("Hiện tọa độ chuột", value=True)

# --- 3. MAIN APP ---
if uploaded_file:
    # CSS TÙY CHỈNH
    st.markdown("""
        <style>
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 1rem;
        }
        
        /* --- 1. CHỈNH SIZE CHỮ MIN/MAX/MEAN --- */
        /* Label (Chữ Min, Max...) */
        div[data-testid="stMetricLabel"] {
            font-size: 14px !important;
            font-weight: 500 !important;
        }
        /* Value (Số liệu) - Giảm xuống 18px cho hài hòa */
        div[data-testid="stMetricValue"] {
            font-size: 18px !important; 
            font-weight: 600 !important;
            color: #0068c9 !important;
        }

        /* --- 2. LEGEND BACKGROUND TRẮNG --- */
        .leaflet-control-legend {
            background-color: #ffffff !important; /* TRẮNG TUYỆT ĐỐI */
            border-radius: 8px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
            padding: 10px 15px !important;
            border: 1px solid rgba(0,0,0,0.1) !important;
        }

        /* Font số liệu Monospace */
        .leaflet-control-legend text {
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important; 
            font-size: 11px !important;
            font-weight: 700 !important;
            fill: #000 !important;
            font-variant-numeric: tabular-nums !important;
        }
        
        .leaflet-control-legend line {
            stroke: #333 !important;
            stroke-width: 1.2px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    
    with st.spinner("Đang xử lý dữ liệu..."):
        raw_data, bounds, err = load_and_reproject(tmp_path, input_epsg)
    os.remove(tmp_path)

    if err:
        st.error(f"❌ Lỗi: {err}")
    else:
        img, stats = colorize_raster(raw_data, cmap_name, opacity, c_min, c_max)

        # Header
        st.subheader(f"📍 {map_title_input}")
        if map_subtitle_input:
            st.markdown(f"**{map_subtitle_input}**")
        
        # Stats
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Min", f"{stats['min']:.2f}")
        col2.metric("Max", f"{stats['max']:.2f}")
        col3.metric("Mean", f"{stats['mean']:.2f}")
        col4.caption(f"Dải màu: {stats['used_min']:.1f} - {stats['used_max']:.1f}")

        # Map Setup
        center = [(bounds[0][0] + bounds[1][0])/2, (bounds[0][1] + bounds[1][1])/2]
        m = folium.Map(
            location=center, 
            zoom_start=11, 
            tiles="CartoDB positron", 
            control_scale=True
        )
        
        folium.TileLayer('OpenStreetMap', name="Bản đồ đường phố").add_to(m)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri', name='Vệ tinh'
        ).add_to(m)

        ImageOverlay(
            image=img,
            bounds=bounds,
            opacity=opacity,
            name="Lớp dữ liệu"
        ).add_to(m)

        # Legend
        hex_colors = get_hex_colors(cmap_name)
        colormap = cm.LinearColormap(
            colors=hex_colors,
            vmin=stats['used_min'],
            vmax=stats['used_max'],
            caption=''
        )
        m.add_child(colormap)

        # Controls
        if show_minimap: MiniMap(toggle_display=True, position='bottomright').add_to(m)
        if show_fullscreen: Fullscreen().add_to(m)
        if show_mouse_pos: MousePosition().add_to(m)

        m.fit_bounds(bounds)
        folium.LayerControl().add_to(m)
        
        st_folium(m, width="100%", height=550, returned_objects=[])

else:
    st.info("👈 Vui lòng upload file Raster.")
    m = folium.Map(location=[16.0, 106.0], zoom_start=5, tiles="CartoDB positron")
    st_folium(m, width="100%", height=500)

st.markdown("---")
st.caption("**Raster Viewer Pro v2.9** | quantrananh.humg@gmail.com)
