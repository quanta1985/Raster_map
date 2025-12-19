import streamlit as st
import leafmap.foliumap as leafmap
import tempfile
import os
import rasterio

# --- CẤU HÌNH TRANG ---
st.set_page_config(layout="wide", page_title="Raster Viewer Pro")

# --- CSS TÙY CHỈNH (Để giao diện chuyên nghiệp hơn) ---
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stTextInput > label {
        font-weight: bold;
        color: #2c3e50;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR: CẤU HÌNH BẢN ĐỒ ---
with st.sidebar:
    st.title("🛰️ Cấu hình Bản đồ")
    st.markdown("---")
    
    # 1. Input Tên bản đồ
    map_title = st.text_input("Tên bản đồ (Map Title)", value="Bản đồ phân bố không gian")
    
    # 2. Chọn Basemap (Nền bản đồ)
    basemap_options = {
        "Open Street Map": "OpenStreetMap",
        "Vệ tinh (Satellite)": "HYBRID", # Google Satellite Hybrid
        "Sáng (Light Canvas)": "CartoDB.Positron"
    }
    selected_basemap = st.selectbox("Chọn nền bản đồ", list(basemap_options.keys()))

    # 3. Upload File (Chỉ 1 file duy nhất)
    st.markdown("### Upload dữ liệu")
    uploaded_file = st.file_uploader("Chọn file Raster (.tif)", type=["tif", "tiff"], accept_multiple_files=False)

    st.info("💡 Tip: File raster cần có hệ tọa độ tham chiếu (CRS) chính xác.")

# --- MAIN AREA: HIỂN THỊ ---
st.header(f"📍 {map_title}")

# Khởi tạo bản đồ
m = leafmap.Map(
    minimap_control=True, # Tự động thêm Minimap
    scale_control=True,   # Tự động thêm Scale bar
    fullscreen_control=True,
    draw_control=False
)

# Thêm Basemap dựa trên lựa chọn
m.add_basemap(basemap_options[selected_basemap])

# Xử lý hiển thị Raster
if uploaded_file is not None:
    # Streamlit giữ file trong RAM, Leafmap cần đường dẫn file thực tế
    # -> Ta ghi tạm file ra đĩa
    with tempfile.NamedTemporaryFile(delete=False, suffix=".tif") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_file_path = tmp_file.name

    try:
        # Đọc metadata để lấy thông tin bounds (tùy chọn hiển thị)
        with rasterio.open(tmp_file_path) as src:
            bounds = src.bounds
            
        # Thêm Raster vào bản đồ
        # Palettes: terrain, viridis, plasma, inferno, magma, cividis
        m.add_raster(
            tmp_file_path, 
            layer_name="Dữ liệu Raster", 
            palette="terrain", 
            opacity=0.7,
            add_legend=True  # Tự động tạo Legend dựa trên min/max value của raster
        )
        
        # Zoom đến khu vực có raster
        m.zoom_to_bounds(bounds)
        
        st.success("Đã load file thành công!")
        
    except Exception as e:
        st.error(f"Lỗi khi đọc file: {e}")
    finally:
        # Dọn dẹp file tạm (Best practice)
        # Lưu ý: Trên Windows đôi khi file đang được dùng sẽ không xóa được ngay, 
        # nhưng trên Linux/Streamlit Cloud thì ổn.
        try:
            os.remove(tmp_file_path)
        except:
            pass
else:
    # Nếu chưa upload, zoom về Việt Nam cho đẹp
    m.set_center(105.8, 21.0, 6) # Tọa độ Hà Nội/Việt Nam

# Render bản đồ ra Streamlit
m.to_streamlit(height=700)

# --- FOOTER ---
st.markdown("---")
st.markdown("**Tài liệu tham khảo:** Dữ liệu được xử lý và hiển thị tự động.")
