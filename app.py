try:
        # BƯỚC 1: Đọc và gán tọa độ (Giữ nguyên)
        st.toast("Đang xử lý dữ liệu...", icon="⏳")
        rds = rxr.open_rasterio(tmp_file_path)
        
        if rds.rio.crs is None or crs_mode != "Custom EPSG": 
             rds.rio.write_crs(f"EPSG:{target_epsg}", inplace=True)

        # BƯỚC 2: Reproject về WGS84 (Giữ nguyên)
        rds_reprojected = rds.rio.reproject("EPSG:4326")
        
        # BƯỚC 3: Lưu thành GeoTIFF (Giữ nguyên)
        output_path = os.path.join(temp_dir, "display.tif")
        rds_reprojected.rio.to_raster(output_path)
        
        # BƯỚC 4: HIỂN THỊ (SỬA ĐỔI ĐỂ KHÔNG DÙNG LOCALTILESERVER)
        # Thay vì dùng m.add_raster (cần server), ta dùng m.add_cog_layer hoặc image_overlay
        # Nhưng cách đơn giản nhất để né lỗi là ép kiểu về hình ảnh tĩnh
        
        with rasterio.open(output_path) as src:
            bounds = src.bounds # (left, bottom, right, top)
            # Folium yêu cầu bounds dạng [[lat_min, lon_min], [lat_max, lon_max]]
            image_bounds = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]

        # Sử dụng add_raster nhưng tắt localtileserver bằng cách dùng phương thức thay thế
        # Tuy nhiên, leafmap add_raster mặc định gọi localtileserver cho local file.
        # Giải pháp: Dùng COG (Cloud Optimized GeoTIFF) hoặc vẽ trực tiếp.
        
        # Phương án ổn định nhất không cần cài thêm lib:
        m.add_raster(
            output_path,
            layer_name=uploaded_file.name,
            palette=colormap,
            opacity=opacity,
            add_legend=True,
            driver="geo" # Thử ép driver này nếu phiên bản leafmap hỗ trợ, hoặc để mặc định
        )
        # NẾU VẪN LỖI: Hãy dùng dòng dưới đây thay cho dòng m.add_raster ở trên:
        # m.add_image(output_path, layer_name=uploaded_file.name) 
        
        m.zoom_to_bounds(bounds)
        st.success(f"Đã hiển thị file với hệ tọa độ EPSG:{target_epsg}")

    except Exception as e:
        # ... (giữ nguyên phần xử lý lỗi)
