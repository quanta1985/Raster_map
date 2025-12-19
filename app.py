import streamlit as st
import folium
from streamlit_folium import st_folium # Thư viện hiển thị map chuẩn nhất
from folium.raster_layers import ImageOverlay
import tempfile
import os
import rioxarray as rxr
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# --- CẤU HÌNH TRANG ---
st.set_page_config(layout="wide", page_title="Raster Viewer Pro")

# --- CSS ---
st.markdown("<style>.block-container {padding-top: 1rem;}</style>", unsafe_allow_html=True)

# --- HÀM HỖ TRỢ ---
def get_utm_epsg(zone, is_north=True):
    base = 32600 if is_north else 32700
    return base + zone

@st.cache_data
def process_data(file_path, target_epsg, colormap_name, opacity):
    """Xử lý dữ liệu: Đọc file -> Gán CRS -> Chuyển WGS84 -> Tô màu"""
    try:
        # 1. Đọc file
        rds = rxr.open_rasterio(file_path)
        
        # Xử lý NoData
        nodata = rds.rio.nodata if rds.rio.nodata is not None else -9999
        rds = rds.where(rds != nodata)
        rds.rio.write_nodata(np.nan, inplace=True)

        # 2. Gán hệ tọa độ (CRS)
        if rds.rio.crs is None:
            rds.rio.write_crs(f"EPSG:{target_epsg}", inplace=True)

        # 3. Chuyển sang WGS84 (Lat/Lon)
        # Đây là bước quan trọng nhất để vẽ lên bản đồ
        rds_wgs = rds.rio.reproject("EPSG:4326")

        # 4. Lấy Bounds (Khung tọa độ)
        # Rio trả về: (minx, miny, maxx, maxy) -> (Lon_min, Lat_min, Lon_max, Lat_max)
        b = rds_wgs.rio.bounds()
        # Folium cần: [[Lat_min, Lon_min], [Lat_max, Lon_max]]
        bounds = [[b[1], b[0]], [b[3], b[2]]]

        # 5. Tô màu dữ liệu (Colorize)
        data = rds_wgs.squeeze().values
        valid_mask = ~np.isnan(data)
        
        if not np.any(valid_mask):
            return None, None, "Dữ liệu toàn bộ là NaN (Rỗng)"

        vmin, vmax = np.nanmin(data[valid_mask]), np.nanmax(data[valid_mask])
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        cmap = plt.get_cmap(colormap_name)
        
        # Tạo ảnh RGBA
        colored_data = cmap(norm(data))
        colored_data[~valid_mask, 3] = 0 # Trong suốt ô NaN
        
        # Trả về kết quả
        return colored_data, bounds, None

    except Exception as e:
        return None, None, str(e)

# --- GIAO DIỆN: SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Cấu hình")
    
    # 1. Upload
    uploaded_file = st.file_uploader("Chọn file Raster (.asc, .tif)", type=["asc", "tif", "txt"])
    
    st.divider()

    # 2. CRS Config
    st.subheader("Hệ tọa độ Input")
    crs_option = st.selectbox("Loại tọa độ", ["UTM (Mét)", "VN-2000 (Custom)", "WGS84"])
    
    input_epsg = 32648 # Default UTM 48N
    
    if crs_option == "UTM (Mét)":
        c1, c2 = st.columns(2)
        zone = c1.number_input("Zone", 1, 60, 48)
        hemi = c2.selectbox("Bán cầu", ["Bắc (N)", "Nam (S)"])
        input_epsg = get_utm_epsg(zone, hemi == "Bắc (N)")
        st.caption(f"EPSG: {input_epsg}")
        
    elif crs_option == "VN-2000 (Custom)":
        input_epsg = st.number_input("Mã EPSG", value=3405)

    st.divider()
    
    # 3. Visual Config
    cmap = st.selectbox("Màu sắc", ["turbo", "jet", "viridis", "spectral"])
    alpha = st.slider("Độ mờ", 0.0, 1.0, 0.7)

# --- GIAO DIỆN: MAIN ---
st.title("🗺️ Raster Viewer (Streamlit-Folium)")

# Khởi tạo Map mặc định
m = folium.Map(location=[21.0, 105.8], zoom_start=6, tiles="OpenStreetMap")
folium.TileLayer('CartoDB positron', name="Bản đồ Sáng").add_to(m)
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri',
    name='Vệ tinh',
).add_to(m)

# Logic xử lý file
if uploaded_file:
    # Lưu file tạm
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    with st.spinner("Đang xử lý..."):
        img, bounds, err = process_data(tmp_path, input_epsg, cmap, alpha)

    if err:
        st.error(f"❌ Lỗi: {err}")
    else:
        # Debug Info (Rất quan trọng để check lỗi)
        with st.expander("ℹ️ Thông tin tọa độ (Debug)", expanded=True):
            st.write(f"**Bounds (WGS84):** {bounds}")
            st.write(f"**EPSG Input:** {input_epsg}")
            center_lat = (bounds[0][0] + bounds[1][0]) / 2
            center_lon = (bounds[0][1] + bounds[1][1]) / 2
            st.write(f"**Tâm Map:** {center_lat:.4f}, {center_lon:.4f}")

            # Cảnh báo nếu tọa độ bị sai (văng ra ngoài Việt Nam)
            if not (8 < center_lat < 24) or not (102 < center_lon < 110):
                st.warning("⚠️ Cảnh báo: Tọa độ có vẻ nằm ngoài Việt Nam. Hãy kiểm tra lại UTM Zone hoặc EPSG!")

        # Vẽ Raster lên Map
        ImageOverlay(
            image=img,
            bounds=bounds,
            opacity=alpha,
            name="Raster Layer"
        ).add_to(m)
        
        # Tự động Zoom vào vùng ảnh
        m.fit_bounds(bounds)

    # Dọn dẹp file tạm
    os.remove(tmp_path)

# --- RENDER MAP ---
folium.LayerControl().add_to(m)

# Dùng st_folium để hiển thị (Thay thế leafmap.to_streamlit)
# returned_objects=[] giúp map chạy mượt hơn, không reload lại trang khi di chuột
st_folium(m, width="100%", height=600, returned_objects=[])
