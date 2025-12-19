import streamlit as st
import leafmap.foliumap as leafmap
import tempfile
import os
import rioxarray as rxr
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from folium.raster_layers import ImageOverlay

# --- CẤU HÌNH TRANG ---
st.set_page_config(layout="wide", page_title="Raster Viewer Pro")

# --- CSS TÙY CHỈNH ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    div[data-testid="stSidebarUserContent"] { padding-top: 1rem; }
    .stAlert { font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# --- HÀM HỖ TRỢ ---
def get_utm_epsg(zone, is_north=True):
    """Tính mã EPSG dựa trên UTM Zone"""
    base = 32600 if is_north else 32700
    return base + zone

@st.cache_data
def process_raster(file_path, target_epsg, colormap_name):
    """
    Hàm xử lý số liệu nặng: Đọc file -> Reproject -> Tô màu
    Dùng cache để không phải chạy lại khi user chỉ zoom map.
    """
    try:
        # 1. Đọc file
        rds = rxr.open_rasterio(file_path)
        
        # Xử lý NoData
        nodata_val = rds.rio.nodata if rds.rio.nodata is not None else -9999
        rds = rds.where(rds != nodata_val)
        rds.rio.write_nodata(np.nan, inplace=True)

        # 2. Gán CRS nếu thiếu
        if rds.rio.crs is None:
            rds.rio.write_crs(f"EPSG:{target_epsg}", inplace=True)

        # 3. Reproject sang WGS84 (EPSG:4326)
        rds_wgs = rds.rio.reproject("EPSG:4326")
        
        # 4. Lấy dữ liệu và Bounds
        data = rds_wgs.squeeze().values
        bounds = [
            [rds_wgs.rio.bounds()[1], rds_wgs.rio.bounds()[0]], # miny, minx
            [rds_wgs.rio.bounds()[3], rds_wgs.rio.bounds()[2]]  # maxy, maxx
        ]

        # 5. Tô màu (Colorize) -> Tạo ảnh RGBA
        valid_mask = ~np.isnan(data)
        if not np.any(valid_mask):
            return None, None, "Dữ liệu toàn bộ là NaN"
            
        vmin, vmax = np.nanmin(data[valid_mask]), np.nanmax(data[valid_mask])
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        cmap = plt.get_cmap(colormap_name)
        
        colored_data = cmap(norm(data))
        # Set alpha = 0 cho các ô NaN
        colored_data[~valid_mask, 3] = 0 
        
        return colored_data, bounds, None

    except Exception as e:
        return None, None, str(e)

# --- SIDEBAR: CẤU HÌNH ---
with st.sidebar:
    st.title("🛰️ Cấu hình Bản đồ")
    
    # 1. Tên và Nền
    st.subheader("1. Giao diện")
    map_title = st.text_input("Tên bản đồ", value="Kết quả Mô hình Không khí")
    basemap_options = {
        "Vệ tinh (Satellite)": "HYBRID",
        "Open Street Map": "OpenStreetMap",
        "Địa hình (Terrain)": "Esri.WorldTerrain",
        "Sáng (Light)": "CartoDB.Positron"
    }
    selected_basemap = st.selectbox("Chọn nền", list(basemap_options.keys()))
    
    st.markdown("---")

    # 2. Upload
    st.subheader("2. Dữ liệu Input")
    uploaded_file = st.file_uploader(
        "Upload Raster (.txt, .asc, .tif)", 
        type=["txt", "asc", "tif", "tiff"], 
        accept_multiple_files=False
    )
    
    st.markdown("---")

    # 3. Cấu hình Tọa độ
    st.subheader("3. Hệ tọa độ (CRS)")
    
    crs_mode = st.radio(
        "Loại tọa độ của file Input:",
        ("UTM (Mét)", "WGS84 (Kinh/Vĩ độ)", "Custom EPSG")
    )

    target_epsg = 4326 # Giá trị khởi tạo

    if crs_mode == "UTM (Mét)":
        col1, col2 = st.columns(2)
        with col1:
            utm_zone = st.number_input("UTM Zone", min_value=1, max_value=60, value=48, help="VN: Miền Nam=48, Bắc=48/49")
        with col2:
            hemisphere = st.selectbox("Bán cầu", ["Bắc (N)", "Nam (S)"])
        
        is_north = True if hemisphere == "Bắc (N)" else False
        target_epsg = get_utm_epsg(utm_zone, is_north)
        st.info(f"👉 Mã EPSG: **{target_epsg}**")

    elif crs_mode == "Custom EPSG":
        target_epsg = st.number_input("Nhập mã EPSG", value=3405, help="Ví dụ: VN2000 nội bộ")
    
    else: # WGS84
        target_epsg = 4326
        st.caption("Sử dụng mặc định EPSG:4326")

    # 4. Hiển thị
    st.markdown("---")
    # Tên màu trùng với Matplotlib
    colormap = st.selectbox(
        "Bảng màu (Colormap)", 
        ["turbo", "jet", "viridis", "plasma", "magma", "coolwarm", "RdYlGn", "Spectral"],
        index=0
    )
    opacity = st.slider("Độ trong suốt", 0.0, 1.0, 0.7)

# --- MAIN AREA ---
st.header(f"📍 {map_title}")

# Khởi tạo Map
m = leafmap.Map(
    minimap_control=True,
    scale_control=True,
    fullscreen_control=True,
    draw_control=False
)
m.add_basemap(basemap_options[selected_basemap])

if uploaded_file is not None:
    # 1. Lưu file tạm (Cần thiết để rioxarray đọc)
    file_ext = uploaded_file.name.split('.')[-1]
    temp_dir = tempfile.mkdtemp()
    tmp_file_path = os.path.join(temp_dir, f"input.{file_ext}")
    
    with open(tmp_file_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    # 2. Xử lý dữ liệu (Gọi hàm đã cache)
    with st.spinner("Đang xử lý dữ liệu và tạo lớp phủ..."):
        img_data, bounds, error_msg = process_raster(tmp_file_path, target_epsg, colormap)

    if error_msg:
        st.error(f"❌ Lỗi: {error_msg}")
    else:
        # 3. Vẽ lên bản đồ bằng ImageOverlay (Siêu bền, không cần TileServer)
        ImageOverlay(
            image=img_data,
            bounds=bounds,
            opacity=opacity,
            name=uploaded_file.name
        ).add_to(m)

        m.zoom_to_bounds(bounds)
        
        # Hiển thị thông tin thành công
