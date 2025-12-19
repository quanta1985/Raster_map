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
st.set_page_config(layout="wide", page_title="Raster Viewer Pro 2.4")

# --- 1. HÀM XỬ LÝ (GIỮ NGUYÊN) ---
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
    
    # 1. Input
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

    # 2. Visuals
    with st.expander("🎨 2. Hiển thị & Legend", expanded=True):
        cmap_name = st.selectbox("Bảng màu", ["turbo", "jet", "viridis", "plasma", "Spectral", "RdYlGn"], index=0)
        opacity = st.slider("Độ trong suốt", 0.0, 1.0, 0.7)
        use_custom_range = st.checkbox("Tùy chỉnh khoảng giá trị")
        c_min, c_max = None, None
        if use_custom_range:
            col_min, col_max = st.columns(2)
            c_min = col_min.number_input("Min", value=0.0)
            c_max = col_max.number_input("Max", value=100.0)

    # 3. Tools (Đã thêm lại Checkbox Mouse Position)
    with st.expander("🛠️ 3. Công cụ Bản đồ", expanded=True):
        map_title_input = st.text_input("Tên bản đồ", value="Kết quả Phân tích")
        legend_title = st.text_input("Tên chú giải", value="Nồng độ (mg/m³)")
        
        c3, c4 = st.columns(2)
        show_minimap = c3.checkbox("MiniMap", value=True)
        show_fullscreen = c4.checkbox("Fullscreen", value=True)
        show_mouse_pos = st.checkbox("Hiện tọa độ chuột (Cursor)", value=True)

# --- 3. MAIN APP ---
if uploaded_file:
    # --- CSS FIX TITLE (QUAN TRỌNG) ---
    # Sử dụng {{ và }} để tránh lỗi conflict với f-string của Python
    st.markdown(f"""
        <style>
        .block-container {{
            padding-top: 3.5rem !important; 
            padding-bottom: 1rem;
        }}
        
        /* LEGEND CONTAINER */
        .leaflet-control-legend {{
            background-color: rgba(255, 255, 255, 0.6) !important; /* Trong suốt 40% */
            backdrop-filter: blur(8px) !important;
            -webkit-backdrop-filter: blur(8px) !important;
            border-radius: 10px !important;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1) !important;
            padding: 10px 15px 10px 15px !important;
            border: 1px solid rgba(255,255,255,0.4) !important;
        }}

        /* TẠO TITLE MỚI CHO LEGEND */
        .leaflet-control-legend::after {{
            content: "{legend_title}"; /* Nội dung từ biến Python */
            display: block;
            margin-top: 12px; /* Khoảng cách với thanh màu */
            text-align: center;
            font-weight: 800;
            font-size: 14px;
            color: #000;
            font-family: sans-serif;
            text-shadow: 0px 0px 2px rgba(255,255,255,0.8);
        }}

        /* Style số liệu trên thang màu */
        .leaflet-control-legend text {{
            font-size: 11px !important;
            font-weight: 700 !important;
            fill: #111 !important;
        }}
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

        st.subheader(f"📍 {map_title_input}")
        
        # Thống kê
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Min", f"{stats['min']:.2f}")
        col2.metric("Max", f"{stats['max']:.2f}")
        col3.metric("Mean", f"{stats['mean']:.2f}")
        col4.caption(f"Used Range: {stats['used_min']:.1f} - {stats['used_max']:.1f}")

        # Map setup
        center = [(bounds[0][0] + bounds[1][0])/2, (bounds[0][1] + bounds[1][1])/2]
        m = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap", control_scale=True)
        
        folium.TileLayer('CartoDB positron', name="Nền Sáng").add_to(m)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri', name='Vệ tinh'
        ).add_to(m)

        ImageOverlay(
            image=img,
            bounds=bounds,
            opacity=opacity,
            name="Raster Data"
        ).add_to(m)

        # Legend
        hex_colors = get_hex_colors(cmap_name)
        colormap = cm.LinearColormap(
            colors=hex_colors,
            vmin=stats['used_min'],
            vmax=stats['used_max'],
            caption='' # Ẩn caption mặc định để dùng CSS ::after
        )
        m.add_child(colormap)

        # Add Controls
        if show_minimap: MiniMap(toggle_display=True, position='bottomright').add_to(m)
        if show_fullscreen: Fullscreen().add_to(m)
        if show_mouse_pos: MousePosition().add_to(m) # Đã thêm lại

        m.fit_bounds(bounds)
        folium.LayerControl().add_to(m)
        st_folium(m, width="100%", height=700, returned_objects=[])

else:
    st.info("👈 Vui lòng upload file Raster.")
    m = folium.Map(location=[16.0, 106.0], zoom_start=5)
    st_folium(m, width="100%", height=500)

st.markdown("---")
st.caption("**Raster Viewer Pro v2.4** | Fix: Legend Title & Tools")
