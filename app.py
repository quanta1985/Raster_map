import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.raster_layers import ImageOverlay
from folium.plugins import MiniMap, Fullscreen
import branca.colormap as cm  # Thư viện quan trọng để vẽ Legend
import tempfile
import os
import rioxarray as rxr
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# --- CẤU HÌNH TRANG ---
st.set_page_config(layout="wide", page_title="Environmental Raster Viewer")

# --- CSS TÙY CHỈNH (Giao diện sạch sẽ hơn) ---
st.markdown("""
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
    div[data-testid="stMetricValue"] {font-size: 1.2rem;}
    </style>
    """, unsafe_allow_html=True)

# --- HÀM HỖ TRỢ ---
def get_utm_epsg(zone, is_north=True):
    base = 32600 if is_north else 32700
    return base + zone

def get_hex_colors(cmap_name, n_steps=20):
    """Chuyển đổi Matplotlib Colormap sang danh sách mã Hex cho Folium Legend"""
    cmap = plt.get_cmap(cmap_name)
    return [mcolors.to_hex(cmap(i)) for i in np.linspace(0, 1, n_steps)]

@st.cache_data
def process_data(file_path, target_epsg, colormap_name, opacity):
    try:
        # 1. Đọc file
        rds = rxr.open_rasterio(file_path)
        
        # Xử lý NoData
        nodata = rds.rio.nodata if rds.rio.nodata is not None else -9999
        rds = rds.where(rds != nodata)
        rds.rio.write_nodata(np.nan, inplace=True)

        # 2. Gán CRS nếu thiếu
        if rds.rio.crs is None:
            rds.rio.write_crs(f"EPSG:{target_epsg}", inplace=True)

        # 3. Reproject sang WGS84
        rds_wgs = rds.rio.reproject("EPSG:4326")

        # 4. Lấy dữ liệu & Thống kê
        data = rds_wgs.squeeze().values
        valid_mask = ~np.isnan(data)
        
        if not np.any(valid_mask):
            return None, None, None, "Dữ liệu toàn bộ là NaN (Rỗng)"

        # Tính toán thống kê
        stats = {
            "min": float(np.nanmin(data[valid_mask])),
            "max": float(np.nanmax(data[valid_mask])),
            "mean": float(np.nanmean(data[valid_mask]))
        }

        # 5. Tô màu ảnh (Image Creation)
        norm = mcolors.Normalize(vmin=stats["min"], vmax=stats["max"])
        cmap = plt.get_cmap(colormap_name)
        colored_data = cmap(norm(data))
        colored_data[~valid_mask, 3] = 0 # Alpha = 0 cho NaN
        
        # 6. Lấy Bounds
        b = rds_wgs.rio.bounds()
        bounds = [[b[1], b[0]], [b[3], b[2]]]

        return colored_data, bounds, stats, None

    except Exception as e:
        return None, None, None, str(e)

# --- SIDEBAR: CẤU HÌNH ---
with st.sidebar:
    st.title("🎛️ Control Panel")
    
    with st.expander("📁 1. Input Data", expanded=True):
        uploaded_file = st.file_uploader("Upload Raster", type=["asc", "tif", "txt"])
        
        crs_option = st.selectbox("Hệ tọa độ gốc", ["UTM (Mét)", "WGS84", "Custom"])
        input_epsg = 32648
        if crs_option == "UTM (Mét)":
            c1, c2 = st.columns(2)
            z = c1.number_input("Zone", 48, 60, 48)
            h = c2.selectbox("Bán cầu", ["Bắc", "Nam"])
            input_epsg = get_utm_epsg(z, h == "Bắc")
        elif crs_option == "Custom":
            input_epsg = st.number_input("EPSG Code", value=3405)

    with st.expander("🎨 2. Visualization", expanded=True):
        col_list = ["turbo", "jet", "viridis", "plasma", "magma", "Spectral", "RdYlGn"]
        cmap_name = st.selectbox("Bảng màu", col_list, index=0)
        opacity = st.slider("Độ trong suốt", 0.0, 1.0, 0.7)
        legend_title = st.text_input("Đơn vị (Legend Title)", value="Concentration (mg/m³)")

    st.info("💡 Hướng dẫn: Upload file .asc hoặc .tif, chọn đúng hệ tọa độ UTM để hiển thị chính xác.")

# --- MAIN AREA ---
st.subheader("🌏 Environmental Impact Map")

# Logic chính
if uploaded_file:
    # Xử lý file tạm
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    with st.spinner("Processing raster data..."):
        img, bounds, stats, err = process_data(tmp_path, input_epsg, cmap_name, opacity)
    
    # Xóa file tạm ngay sau khi xử lý xong
    os.remove(tmp_path)

    if err:
        st.error(f"❌ Error: {err}")
    else:
        # 1. Hiển thị Dashboard Thống kê (Làm cho app trông Pro hơn)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Min Value", f"{stats['min']:.2f}")
        c2.metric("Max Value", f"{stats['max']:.2f}")
        c3.metric("Mean Value", f"{stats['mean']:.2f}")
        c4.success(f"CRS: EPSG:{input_epsg} → WGS84")

        # 2. Tạo Map (Thêm control_scale=True để hiện thước tỷ lệ)
        m = folium.Map(
            location=[(bounds[0][0] + bounds[1][0])/2, (bounds[0][1] + bounds[1][1])/2],
            zoom_start=10,
            tiles="OpenStreetMap",
            control_scale=True  # <--- HIỆN THƯỚC TỶ LỆ (SCALE BAR)
        )

        # Thêm các lớp nền khác nhau
        folium.TileLayer('CartoDB positron', name="Light Map").add_to(m)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri', name='Satellite Image'
        ).add_to(m)

        # 3. Vẽ Raster Layer
        ImageOverlay(
            image=img,
            bounds=bounds,
            opacity=opacity,
            name="Analysis Result"
        ).add_to(m)
        
        m.fit_bounds(bounds)

        # 4. TẠO LEGEND (CHÚ GIẢI)
        # Tạo danh sách màu Hex từ Matplotlib colormap đã chọn
        hex_colors = get_hex_colors(cmap_name)
        
        colormap = cm.LinearColormap(
            colors=hex_colors,
            vmin=stats['min'],
            vmax=stats['max'],
            caption=legend_title
        )
        m.add_child(colormap) # Thêm Legend vào Map

        # 5. THÊM MINIMAP
        minimap = MiniMap(
            tile_layer='CartoDB positron',
            position='bottomright',
            toggle_display=True,
            width=150, height=150
        )
        m.add_child(minimap)
        
        # 6. THÊM NÚT FULLSCREEN
        Fullscreen().add_to(m)

        # 7. Render Map
        folium.LayerControl().add_to(m)
        st_folium(m, width="100%", height=650, returned_objects=[])

else:
    # Màn hình chờ khi chưa upload
    st.info("👈 Please upload a raster file from the sidebar to begin.")
    
    # Map demo vị trí VN
    m = folium.Map(location=[16.0, 106.0], zoom_start=5, control_scale=True)
    st_folium(m, width="100%", height=500)

# --- FOOTER ---
st.markdown("---")
st.caption("© 2025 Spatial Analysis Dashboard | Powered by Streamlit & Folium")
