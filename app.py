import streamlit as st
import leafmap.foliumap as leafmap
import tempfile
import os
import rasterio
import rioxarray as rxr

# --- CẤU HÌNH TRANG ---
st.set_page_config(layout="wide", page_title="ASCII Raster Viewer")

# --- CSS TÙY CHỈNH ---
# Sử dụng st.markdown một lần duy nhất và đảm bảo cú pháp đúng để tránh hiển thị raw text
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    div[data-testid="stSidebarUserContent"] {
        padding-top: 2rem;
    }
    .stAlert {
        font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR: CẤU HÌNH ---
with st.sidebar:
    st.title("🛰️ Cấu hình Bản đồ")
    st.markdown("---")
    
    map_title = st.text_input("Tên bản đồ", value="Bản đồ số liệu ASCII")
    
    # Chọn Basemap
    basemap_options = {
        "Open Street Map": "OpenStreetMap",
        "Vệ tinh (Satellite)": "HYBRID",
        "Sáng (Light Canvas)": "CartoDB.Positron",
        "Địa hình (Terrain)": "Esri.WorldTerrain"
    }
    selected_basemap = st.selectbox("Chọn nền bản đồ", list(basemap_options.keys()))

    st.markdown("### Upload dữ liệu")
    # Cho phép upload .txt và .asc
    uploaded_file = st.file_uploader(
        "Chọn file Raster (.txt, .asc)", 
        type=["txt", "asc"], 
        accept_multiple_files=False
    )
    
    # --- CẤU HÌNH QUAN TRỌNG CHO ASCII ---
    st.markdown("### 🌐 Hệ tọa độ (CRS)")
    st.caption("File ASCII thường thiếu thông tin CRS. Hãy nhập mã EPSG để định vị đúng.")
    epsg_code = st.number_input(
        "Mã EPSG (Ví dụ: 4326 là WGS84, 3405 là VN2000)", 
        value=4326, 
        step=1
    )

    colormap = st.selectbox(
        "Bảng màu (Colormap)", 
        ["terrain", "spectral", "coolwarm", "viridis", "plasma", "magma"]
    )

# --- MAIN AREA ---
st.header(f"📍 {map_title}")

# Khởi tạo bản đồ
m = leafmap.Map(
    minimap_control=True,
    scale_control=True,
    fullscreen_control=True,
    draw_control=False
)
m.add_basemap(basemap_options[selected_basemap])

if uploaded_file is not None:
    # Lấy extension của file upload (txt hoặc asc)
    file_ext = uploaded_file.name.split('.')[-1]
    
    # Tạo file tạm với đúng đuôi file để rasterio nhận diện driver
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_file_path = tmp_file.name

    try:
        # Xử lý gán CRS cho file ASCII
        # Đọc bằng rioxarray để dễ gán CRS
        rds = rxr.open_rasterio(tmp_file_path)
        
        # Nếu file chưa có CRS, gán CRS từ input của user
        if rds.rio.crs is None:
            rds.rio.write_crs(f"EPSG:{epsg_code}", inplace=True)
            
        # Lưu lại thành GeoTIFF tạm thời để Leafmap hiển thị tốt nhất
        # (Leafmap xử lý GeoTIFF ổn định hơn ASCII thuần trên web)
        tif_path = tmp_file_path + ".converted.tif"
        rds.rio.to_raster(tif_path)
        
        # Thêm vào bản đồ
        m.add_raster(
            tif_path, 
            layer_name=uploaded_file.name, 
            palette=colormap, 
            opacity=0.7,
            add_legend=True
        )
        
        # Zoom đến phạm vi dữ liệu
        # Cần mở file TIF vừa convert để lấy bounds chuẩn
        with rasterio.open(tif_path) as src:
            bounds = src.bounds
            m.zoom_to_bounds(bounds)

        st.success(f"Đã load file '{uploaded_file.name}' thành công với EPSG:{epsg_code}")
        
    except Exception as e:
        st.error(f"⚠️ Lỗi xử lý file: {e}")
        st.markdown("""
        **Gợi ý sửa lỗi:**
        1. Kiểm tra cấu trúc file TXT/ASCII (phải có header chuẩn: ncols, nrows, xllcorner...).
        2. Kiểm tra lại mã EPSG (Hệ tọa độ).
        """)
        
    finally:
        # Dọn dẹp
        try:
            os.remove(tmp_file_path)
            if os.path.exists(tmp_file_path + ".converted.tif"):
                os.remove(tmp_file_path + ".converted.tif")
        except:
            pass
else:
    m.set_center(105.8, 21.0, 6)

# Render
m.to_streamlit(height=700)

# --- FOOTER ---
st.markdown("---")
st.markdown("**Tài liệu tham khảo:**")
st.markdown("- Dữ liệu được trích xuất và hiển thị từ file nguồn người dùng cung cấp.")
