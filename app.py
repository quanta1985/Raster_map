import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.raster_layers import ImageOverlay
from folium.plugins import MiniMap, Fullscreen, MousePosition
from folium import Element
import branca.colormap as cm
import tempfile
import os
import rioxarray as rxr
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# --- CẤU HÌNH TRANG ---
st.set_page_config(layout="wide", page_title="Raster Viewer Pro 2.0")

# --- CSS CAO CẤP (Làm đẹp Legend & UI) ---
st.markdown("""
    <style>
    /* Làm gọn padding của Streamlit */
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    
    /* Style cho Metric (Min/Max/Mean) */
    div[data-testid="stMetricValue"] {font-size: 1.1rem; color: #0068c9;}
    
    /* CSS QUAN TRỌNG: Làm Legend nổi bật trên nền bản đồ */
    .leaflet-control-legend {
        background-color: rgba(255, 255, 255, 0.9) !important; /* Nền trắng mờ */
        border-radius: 8px !important;
        padding: 10px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
        border: 2px solid #e0e0e0 !important;
        font-size: 14px !important;
        font-weight: bold !important;
        color: #333 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. HÀM XỬ LÝ DỮ LIỆU GỐC (NẶNG -> CẦN CACHE) ---
@st.cache_data
def load_and_reproject(file_path, target_epsg):
    """Bước 1: Đọc file và Reproject sang WGS84 (Chạy 1 lần duy nhất)"""
    try:
        rds = rxr.open_rasterio(file_path)
        
        # Xử lý NoData
        nodata = rds.rio.nodata if rds.rio.nodata is not None else -9999
        rds = rds.where(rds != nodata)
        rds.rio.write_nodata(np.nan, inplace=True)

        if rds.rio.crs is None:
            rds.rio.write_crs(f"EPSG:{target_epsg}", inplace=True)

        # Reproject sang WGS84
        rds_wgs = rds.rio.reproject("EPSG:4326")
        
        # Trả về numpy array và bounds
        data = rds_wgs.squeeze().values
        b = rds_wgs.rio.bounds()
        bounds = [[b[1], b[0]], [b[3], b[2]]] # Folium format
        
        return data, bounds, None
    except Exception as e:
        return None, None, str(e)

# --- 2. HÀM TÔ MÀU (NHẸ -> KHÔNG CACHE ĐỂ CHỈNH MÀU NHANH) ---
def colorize_raster(data, colormap_name, opacity, custom_min=None, custom_max=None):
    """Bước 2: Biến số liệu thành ảnh màu dựa trên input user"""
    valid_mask = ~np.isnan(data)
    if not np.any(valid_mask):
        return None, None
    
    # Xác định Min/Max (Tự động hoặc Custom)
    d_min = float(np.nanmin(data[valid_mask]))
    d_max = float(np.nanmax(data[valid_mask]))
    d_mean = float(np.nanmean(data[valid_mask]))

    # Nếu user nhập Custom, ưu tiên dùng Custom, nhưng giữ giới hạn an toàn
    vmin = custom_min if custom_min is not None else d_min
    vmax = custom_max if custom_max is not None else d_max

    # Tạo Norm và Color Map
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = plt.get_cmap(colormap_name)
    
    img_colored = cmap(norm(data))
    img_colored[~valid_mask, 3] = 0 # Alpha = 0
    
    stats = {"min": d_min, "max": d_max, "mean": d_mean, "used_min": vmin, "used_max": vmax}
    return img_colored, stats

def get_hex_colors(cmap_name, n_steps=20):
    cmap = plt.get_cmap(cmap_name)
    return [mcolors.to_hex(cmap(i)) for i in np.linspace(0, 1, n_steps)]

# --- GIAO DIỆN SIDEBAR ---
with st.sidebar:
    st.header("🎛️ Control Panel")
    
    # --- Tab 1: Data ---
    with st.expander("📁 1. Dữ liệu Input", expanded=True):
        uploaded_file = st.file_uploader("Chọn file Raster", type=["asc", "tif", "txt"])
        crs_mode = st.selectbox("Hệ tọa độ", ["UTM (Mét)", "WGS84", "Custom EPSG"])
        
        input_epsg = 32648
        if crs_mode == "UTM (Mét)":
            c1, c2 = st.columns(2)
            z = c1.number_input("Zone", 48, 60, 48)
            h = c2.selectbox("Bán cầu", ["Bắc", "Nam"])
            input_epsg = 32600 + z if h == "Bắc" else 32700 + z

    # --- Tab 2: Visualization ---
    with st.expander("🎨 2. Hiển thị & Legend", expanded=True):
        cmap_name = st.selectbox("Bảng màu", ["turbo", "jet", "viridis", "plasma", "Spectral", "RdYlGn"], index=0)
        opacity = st.slider("Độ trong suốt", 0.0, 1.0, 0.7)
        
        # Tùy chọn Custom Min/Max
        use_custom_range = st.checkbox("Tùy chỉnh khoảng giá trị (Min/Max)")
        c_min, c_max = None, None
        if use_custom_range:
            col_min, col_max = st.columns(2)
            c_min = col_min.number_input("Min Legend", value=0.0)
            c_max = col_max.number_input("Max Legend", value=100.0)

    # --- Tab 3: Map Tools ---
    with st.expander("🛠️ 3. Công cụ Bản đồ", expanded=False):
        map_title_input = st.text_input("Tên bản đồ", value="Kết quả Phân tích")
        legend_title = st.text_input("Tên chú giải", value="Nồng độ (mg/m³)")
        show_minimap = st.checkbox("Hiện MiniMap", value=True)
        show_fullscreen = st.checkbox("Nút Fullscreen", value=True)
        show_mouse_pos = st.checkbox("Hiện tọa độ chuột", value=True)

# --- MAIN AREA ---
if uploaded_file:
    # 1. Xử lý file tạm
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    
    # 2. Load Data (Có Cache)
    with st.spinner("Đang xử lý dữ liệu thô..."):
        raw_data, bounds, err = load_and_reproject(tmp_path, input_epsg)
    os.remove(tmp_path) # Xóa file ngay sau khi load vào RAM

    if err:
        st.error(f"❌ Lỗi: {err}")
    else:
        # 3. Tô màu (Không Cache - Fast)
        img, stats = colorize_raster(raw_data, cmap_name, opacity, c_min, c_max)

        # --- DASHBOARD HEADER ---
        st.subheader(f"📍 {map_title_input}")
        
        # Hiển thị thống kê đẹp mắt
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Min (Data)", f"{stats['min']:.2f}")
        m2.metric("Max (Data)", f"{stats['max']:.2f}")
        m3.metric("Mean", f"{stats['mean']:.2f}")
        m4.caption(f"Legend Range:\n{stats['used_min']:.1f} - {stats['used_max']:.1f}")

        # --- TẠO BẢN ĐỒ ---
        # Tính tâm bản đồ
        center = [(bounds[0][0] + bounds[1][0])/2, (bounds[0][1] + bounds[1][1])/2]
        m = folium.Map(
            location=center, 
            zoom_start=11, 
            tiles="OpenStreetMap",
            control_scale=True # Thước tỷ lệ
        )

        # Các lớp nền
        folium.TileLayer('CartoDB positron', name="Nền Sáng").add_to(m)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri', name='Vệ tinh'
        ).add_to(m)

        # Layer Raster
        ImageOverlay(
            image=img,
            bounds=bounds,
            opacity=opacity,
            name="Dữ liệu Raster"
        ).add_to(m)

        # --- CÁC CÔNG CỤ TÙY CHỌN ---
        # 1. Legend (Chú giải)
        hex_colors = get_hex_colors(cmap_name)
        colormap = cm.LinearColormap(
            colors=hex_colors,
            vmin=stats['used_min'],
            vmax=stats['used_max'],
            caption=legend_title
        )
        m.add_child(colormap)

        # 2. Minimap
        if show_minimap:
            MiniMap(toggle_display=True, position='bottomright').add_to(m)
        
        # 3. Fullscreen
        if show_fullscreen:
            Fullscreen().add_to(m)

        # 4. Mouse Position (Tọa độ chuột)
        if show_mouse_pos:
            MousePosition().add_to(m)

        # Tự động zoom
        m.fit_bounds(bounds)
        folium.LayerControl().add_to(m)

        # Render
        st_folium(m, width="100%", height=700, returned_objects=[])

else:
    # Màn hình chờ
    st.info("👈 Vui lòng upload file Raster từ thanh bên trái.")
    m = folium.Map(location=[16.0, 106.0], zoom_start=5)
    st_folium(m, width="100%", height=500)

# --- FOOTER ---
st.markdown("---")
st.markdown("**Raster Viewer Pro v2.0** | Optimized for Performance & Visibility")
