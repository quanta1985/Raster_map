import streamlit as st
import leafmap.foliumap as leafmap
import tempfile
import os
import rasterio
import rioxarray as rxr
import shutil

# --- CẤU HÌNH TRANG ---
st.set_page_config(layout="wide", page_title="Raster Viewer Pro")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    div[data-testid="stSidebarUserContent"] { padding-top: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# --- HÀM HỖ TRỢ ---
def get_utm_epsg(zone, is_north=True):
    """Tính mã EPSG dựa trên UTM Zone"""
    base = 32600 if is_north else 32700
    return base + zone

# --- SIDEBAR: CẤU HÌNH ---
with st.sidebar:
    st.title("🛰️ Cấu hình Bản đồ")
    
    # 1. Tên và Nền
    st.subheader("1. Giao diện")
    map_title = st.text_input("Tên bản đồ", value="Bản đồ phân bố")
    basemap_options = {
        "Open Street Map": "OpenStreetMap",
        "Vệ tinh (Satellite)": "HYBRID",
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

    # 3. Cấu hình Tọa độ (QUAN TRỌNG)
    st.subheader("3. Hệ tọa độ (CRS)")
    
    crs_mode = st.radio(
        "Loại tọa độ của file Input:",
        ("WGS84 (Kinh/Vĩ độ)", "UTM (Mét)", "Custom EPSG")
    )

    target_epsg = 4326 # Mặc định

    if crs_mode == "UTM (Mét)":
        col1, col2 = st.columns(2)
        with col1:
            utm_zone = st.number_input("UTM Zone", min_value=1, max_value=60, value=48, help="VN nằm chủ yếu ở zone 48, 49")
        with col2:
            hemisphere = st.selectbox("Bán cầu", ["Bắc (N)", "Nam (S)"])
        
        is_north = True if hemisphere == "Bắc (N)" else False
        target_epsg = get_utm_epsg(utm_zone, is_north)
        st.info(f"👉 Mã EPSG tự động: **{target_epsg}**")

    elif crs_mode == "Custom EPSG":
        target_epsg = st.number_input("Nhập mã EPSG", value=3405, help="Ví dụ: VN2000 nội bộ")
    
    else: # WGS84
        target_epsg = 4326
        st.caption("Sử dụng mặc định EPSG:4326")

    # 4. Hiển thị
    st.markdown("---")
    colormap = st.selectbox(
        "Bảng màu (Colormap)", 
        ["terrain", "spectral", "jet", "viridis", "plasma", "magma", "coolwarm"],
        index=0
    )
    opacity = st.slider("Độ trong suốt", 0.0, 1.0, 0.7)

# --- MAIN AREA ---
st.header(f"📍 {map_title}")

m = leafmap.Map(
    minimap_control=True,
    scale_control=True,
    fullscreen_control=True,
    draw_control=False
)
m.add_basemap(basemap_options[selected_basemap])

if uploaded_file is not None:
    # Xử lý file upload
    file_ext = uploaded_file.name.split('.')[-1]
    
    # Tạo thư mục tạm an toàn
    temp_dir = tempfile.mkdtemp()
    tmp_file_path = os.path.join(temp_dir, f"input.{file_ext}")
    
    with open(tmp_file_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    try:
        # BƯỚC 1: Đọc và gán tọa độ
        st.toast("Đang xử lý dữ liệu...", icon="⏳")
        
        # Dùng rioxarray để mở, nó xử lý tốt cả Tiff lẫn ASCII
        rds = rxr.open_rasterio(tmp_file_path)
        
        # Gán CRS nếu user chỉ định (quan trọng cho file ASCII thiếu header prj)
        # Lưu ý: write_crs chỉ gán metadata, không tính toán lại giá trị grid
        if rds.rio.crs is None or crs_mode != "Custom EPSG": 
             rds.rio.write_crs(f"EPSG:{target_epsg}", inplace=True)

        # BƯỚC 2: Reproject về WGS84 (EPSG:4326) để hiển thị trên web map
        # Leaflet chỉ làm việc tốt nhất với Lat/Lon. 
        # Nếu input là UTM, ta CẦN convert sang 4326 để khớp nền vệ tinh.
        rds_reprojected = rds.rio.reproject("EPSG:4326")
        
        # BƯỚC 3: Lưu thành GeoTIFF để add vào map
        output_path = os.path.join(temp_dir, "display.tif")
        rds_reprojected.rio.to_raster(output_path)
        
        # BƯỚC 4: Hiển thị
        # Lấy bounds để zoom
        with rasterio.open(output_path) as src:
            bounds = src.bounds
            
        m.add_raster(
            output_path, 
            layer_name=uploaded_file.name, 
            palette=colormap, 
            opacity=opacity,
            add_legend=True
        )
        m.zoom_to_bounds(bounds)
        
        st.success(f"Đã hiển thị file với hệ tọa độ EPSG:{target_epsg}")

    except Exception as e:
        st.error(f"❌ Lỗi xử lý: {e}")
        with st.expander("Xem chi tiết lỗi"):
            st.write(e)
            st.warning("""
            **Nguyên nhân phổ biến:**
            1. File ASCII thiếu header chuẩn (xllcorner, cellsize...).
            2. Chọn sai UTM Zone khiến tọa độ bị văng ra ngoài Trái Đất.
            3. File quá lớn gây tràn bộ nhớ.
            """)
    finally:
        # Dọn dẹp thư mục tạm
        # shutil.rmtree(temp_dir, ignore_errors=True) 
        # (Comment dòng trên nếu muốn debug, uncomment khi chạy thật)
        pass

else:
    # Zoom mặc định về Việt Nam
    m.set_center(105.8, 21.0, 6)

m.to_streamlit(height=700)
