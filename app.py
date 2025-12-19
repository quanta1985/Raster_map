import streamlit as st
import leafmap.foliumap as leafmap
import tempfile
import os
import rasterio
import rioxarray as rxr
import numpy as np
import shutil

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
    colormap = st.selectbox(
        "Bảng màu (Colormap)", 
        ["terrain", "spectral", "jet", "viridis", "plasma", "magma", "coolwarm", "RdYlGn"],
        index=2
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
    # Xử lý tên file và extension
    file_ext = uploaded_file.name.split('.')[-1]
    
    # Tạo thư mục tạm an toàn
    temp_dir = tempfile.mkdtemp()
    tmp_file_path = os.path.join(temp_dir, f"input.{file_ext}")
    
    # Ghi file ra đĩa
    with open(tmp_file_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    try:
        st.toast("Đang xử lý dữ liệu...", icon="⏳")
        
        # BƯỚC 1: Đọc file bằng xarray/rioxarray
        rds = rxr.open_rasterio(tmp_file_path)
        
        # --- XỬ LÝ NODATA (-9999) ---
        # Lấy giá trị nodata từ file hoặc mặc định là -9999
        nodata_val = rds.rio.nodata
        if nodata_val is None:
            nodata_val = -9999 

        # Masking: Chuyển các giá trị == nodata_val thành NaN (Not a Number)
        # Để khi vẽ lên bản đồ nó sẽ trong suốt
        rds = rds.where(rds != nodata_val)
        rds.rio.write_nodata(np.nan, inplace=True)
        # ----------------------------

        # BƯỚC 2: Gán hệ tọa độ (CRS)
        # Nếu file text/ascii thường mất CRS, ta gán cứng từ input user
        if rds.rio.crs is None or crs_mode != "WGS84 (Kinh/Vĩ độ)": 
             rds.rio.write_crs(f"EPSG:{target_epsg}", inplace=True)

        # BƯỚC 3: Chuyển đổi về WGS84 (EPSG:4326) để vẽ lên Web Map
        # Leaflet yêu cầu toạ độ Kinh độ/Vĩ độ
        rds_reprojected = rds.rio.reproject("EPSG:4326")
        
        # BƯỚC 4: Xuất ra GeoTIFF để hiển thị
        output_path = os.path.join(temp_dir, "display.tif")
        rds_reprojected.rio.to_raster(output_path)
        
        # BƯỚC 5: Hiển thị lên bản đồ
        # Lấy khung bao (bounds) để zoom tới
        with rasterio.open(output_path) as src:
            bounds = src.bounds
            
        m.add_raster(
            output_path, 
            layer_name=uploaded_file.name, 
            palette=colormap, 
            opacity=opacity,
            add_legend=True,
            nodata=np.nan # Báo cho leafmap biết NaN là trong suốt
        )
        
        m.zoom_to_bounds(bounds)
        st.success(f"✅ Đã tải thành công! (Loại bỏ giá trị nền: {nodata_val})")
        st.caption(f"Hệ tọa độ gốc: EPSG:{target_epsg} | Tự động chuyển về WGS84 để hiển thị.")

    except Exception as e:
        st.error("❌ Lỗi xử lý file!")
        with st.expander("Xem chi tiết lỗi kỹ thuật"):
            st.write(e)
            st.warning("""
            **Gợi ý khắc phục:**
            1. Kiểm tra header của file TXT (phải có: ncols, nrows, xllcorner...).
            2. Kiểm tra UTM Zone: Nếu bản đồ bay ra biển, hãy thử đổi Zone hoặc Bán cầu.
            3. Reboot App: Nếu gặp lỗi module, hãy thử Reboot lại App trên Streamlit.
            """)
    finally:
        # Có thể dọn dẹp file tạm ở đây nếu cần thiết
        pass

else:
    # Zoom mặc định về Việt Nam
    m.set_center(105.8, 21.0, 6)

# Render bản đồ
m.to_streamlit(height=700)

# --- FOOTER ---
st.markdown("---")
st.markdown("© 2025 Raster Viewer Tool. Powered by Streamlit & Leafmap.")
