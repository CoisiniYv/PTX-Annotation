# 函数说明

生成时间: 2026-03-15 14:02:38
说明: 本文件未改动源码，基于静态解析自动生成。未显式注释的函数给出【推断】描述。

文件: `actions_mixin.py`
函数: `ActionsMixin._connect_canvas_signals`
签名: `def _connect_canvas_signals(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 在主窗口 __init__ 末尾调用一次，连接 canvas 的拖拽信号。

函数: `ActionsMixin._on_mask_file_dropped`
签名: `def _on_mask_file_dropped(self, path)`
输入: `path`
输出: 可能返回: `None`
功能: 处理从外部拖入画布的掩码文件（支持 png / nii / nii.gz）。

函数: `ActionsMixin.open_perf_settings`
签名: `def open_perf_settings(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】打开perfsettings。

函数: `ActionsMixin.closeEvent`
签名: `def closeEvent(self, event)`
输入: `event`
输出: 无显式返回（默认 `None`）
功能: 【推断】关闭事件。

函数: `ActionsMixin._contains_non_ascii`
签名: `def _contains_non_ascii(self, path)`
输入: `path`
输出: 可能返回: `False` / `True`
功能: 【推断】containsnonascii。

函数: `ActionsMixin._get_ascii_temp_root`
签名: `def _get_ascii_temp_root(self)`
输入: 无显式参数
输出: 可能返回: `candidate` / `None`
功能: 【推断】获取asciitemproot。

函数: `ActionsMixin._write_mask_file_compat`
签名: `def _write_mask_file_compat(self, save_path, mask_to_save, reference_mask_path=None)`
输入: `save_path`?`mask_to_save`?`reference_mask_path`
输出: 可能返回: `write_mask_file(save_path, mask_to_save, reference_mask_path=reference_mask_path)` / `(ok, err)` / `(True, None)` / `(False, f'NIfTI 临时写出成功，但移动到目标路径失败: {e}')`
功能: 【推断】写入maskfilecompat。

函数: `ActionsMixin._split_known_image_ext`
签名: `def _split_known_image_ext(self, path)`
输入: `path`
输出: 可能返回: `(path[:-len(ext)], ext)` / `(path, '')`
功能: 【推断】splitknownimageext。

函数: `ActionsMixin._ensure_export_path_ext`
签名: `def _ensure_export_path_ext(self, path, fmt)`
输入: `path`?`fmt`
输出: 可能返回: `stem + '.png'` / `stem + '.jpg'` / `stem + '.nii.gz'` / `path`
功能: 【推断】ensure导出pathext。

函数: `ActionsMixin._get_export_mask_path`
签名: `def _get_export_mask_path(self, out_path, fmt)`
输入: `out_path`?`fmt`
输出: 可能返回: `stem + '_mask.nii.gz'` / `stem + '_mask.png'`
功能: 【推断】获取导出maskpath。

函数: `ActionsMixin._get_nifti_export_reference_path`
签名: `def _get_nifti_export_reference_path(self, entry)`
输入: `entry`
输出: 可能返回: `ref` / `orig` / `None`
功能: 【推断】获取nifti导出referencepath。

函数: `ActionsMixin._source_is_dicom_for_export`
签名: `def _source_is_dicom_for_export(self, entry)`
输入: `entry`
输出: 可能返回: `orig.endswith(('.dcm', '.dicom'))`
功能: 【推断】sourceisdicomfor导出。

函数: `ActionsMixin._mask_to_binary_uint8`
签名: `def _mask_to_binary_uint8(self, mask, shape=None)`
输入: `mask`?`shape`
输出: 可能返回: `np.zeros((1, 1), dtype=np.uint8)` / `np.zeros(shape, dtype=np.uint8)` / `np.asarray([[value]], dtype=np.uint8)` / `np.full(shape, value, dtype=np.uint8)` / `np.ascontiguousarray(arr)`
功能: 【推断】masktobinaryuint8。

函数: `ActionsMixin._read_reference_image_2d`
签名: `def _read_reference_image_2d(self, reference_path)`
输入: `reference_path`
输出: 可能返回: `(ref_img, tmp_dir)`
功能: 【推断】读取referenceimage2d。

函数: `ActionsMixin._write_nifti_array_compat`
签名: `def _write_nifti_array_compat(self, save_path, arr, reference_image_path=None, binary=False)`
输入: `save_path`?`arr`?`reference_image_path`?`binary`
输出: 可能返回: `(False, f'导出数组无效: {e}')` / `(False, f'当前仅支持导出 2D NIfTI，实际数组形状为 {out_arr.shape}')` / `(False, f'创建 NIfTI 图像失败: {e}')` / `(True, None)` / `(False, f'写入 NIfTI 失败: {e}')`
功能: 【推断】写入niftiarraycompat。

函数: `ActionsMixin._export_image_file`
签名: `def _export_image_file(self, out_path, img, quality, reference_mask_path=None)`
输入: `out_path`?`img`?`quality`?`reference_mask_path`
输出: 可能返回: `(False, '导出图像为空')` / `self._write_nifti_array_compat(out_path, img, reference_image_path=reference_mask_path, binary=False)` / `(True, None)` / `(False, '导出图像失败')`
功能: 【推断】导出imagefile。

函数: `ActionsMixin.save_mask`
签名: `def save_mask(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】保存mask。

函数: `ActionsMixin.load_single_pair`
签名: `def load_single_pair(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】加载singlepair。

函数: `ActionsMixin.load_quick_preview`
签名: `def load_quick_preview(self, image_path)`
输入: `image_path`
输出: 可能返回: `None`
功能: 【推断】加载quickpreview。

函数: `ActionsMixin.export_current`
签名: `def export_current(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】导出current。

函数: `ActionsMixin._cleanup_empty_masks`
签名: `def _cleanup_empty_masks(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】cleanupemptymasks。

函数: `ActionsMixin._update_pneumo_label`
签名: `def _update_pneumo_label(self, val)`
输入: `val`
输出: 可能返回: `None`
功能: 【推断】更新pneumolabel。

函数: `ActionsMixin._update_status_ui`
签名: `def _update_status_ui(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】更新statusui。

函数: `ActionsMixin.prev_image`
签名: `def prev_image(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】previmage。

函数: `ActionsMixin.next_image`
签名: `def next_image(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】nextimage。

函数: `ActionsMixin.prev_case`
签名: `def prev_case(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】prevcase。

函数: `ActionsMixin.next_case`
签名: `def next_case(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】nextcase。

函数: `ActionsMixin.action_toggle_case_status`
签名: `def action_toggle_case_status(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 防止快捷键 Z 崩溃，可根据需要在此添加状态切换逻辑

文件: `all.py`
（无可解析函数）

文件: `app.py`
函数: `main`
签名: `def main()`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】main。

文件: `canvas.py`
函数: `Canvas.__init__`
签名: `def __init__(self, parent=None)`
输入: `parent`
输出: 无显式返回（默认 `None`）
功能: 初始化对象与默认状态。

函数: `Canvas.filter_type`
签名: `def filter_type(self)`
输入: 无显式参数
输出: 可能返回: `self._filter_type`
功能: 【推断】filtertype。

函数: `Canvas.filter_type`
签名: `def filter_type(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】filtertype。

函数: `Canvas.filter_strength`
签名: `def filter_strength(self)`
输入: 无显式参数
输出: 可能返回: `self._filter_strength`
功能: 【推断】filterstrength。

函数: `Canvas.filter_strength`
签名: `def filter_strength(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】filterstrength。

函数: `Canvas.brightness`
签名: `def brightness(self)`
输入: 无显式参数
输出: 可能返回: `self._brightness`
功能: 【推断】brightness。

函数: `Canvas.brightness`
签名: `def brightness(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】brightness。

函数: `Canvas.invert_view`
签名: `def invert_view(self)`
输入: 无显式参数
输出: 可能返回: `self._invert_view`
功能: 【推断】invertview。

函数: `Canvas.invert_view`
签名: `def invert_view(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】invertview。

函数: `Canvas.overlay_alpha`
签名: `def overlay_alpha(self)`
输入: 无显式参数
输出: 可能返回: `self._overlay_alpha`
功能: 【推断】overlayalpha。

函数: `Canvas.overlay_alpha`
签名: `def overlay_alpha(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】overlayalpha。

函数: `Canvas.window_center`
签名: `def window_center(self)`
输入: 无显式参数
输出: 可能返回: `self._window_center`
功能: 【推断】windowcenter。

函数: `Canvas.window_center`
签名: `def window_center(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】windowcenter。

函数: `Canvas.window_width`
签名: `def window_width(self)`
输入: 无显式参数
输出: 可能返回: `self._window_width`
功能: 【推断】windowwidth。

函数: `Canvas.window_width`
签名: `def window_width(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】windowwidth。

函数: `Canvas.tool`
签名: `def tool(self)`
输入: 无显式参数
输出: 可能返回: `self._tool`
功能: 【推断】tool。

函数: `Canvas.tool`
签名: `def tool(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】tool。

函数: `Canvas._mark_dirty`
签名: `def _mark_dirty(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】markdirty。

函数: `Canvas._update_color_table`
签名: `def _update_color_table(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】更新colortable。

函数: `Canvas._invalidate_empty_bg_cache`
签名: `def _invalidate_empty_bg_cache(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】invalidateemptybg缓存。

函数: `Canvas._ensure_empty_bg_cache`
签名: `def _ensure_empty_bg_cache(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】ensureemptybg缓存。

函数: `Canvas._update_bg_cache`
签名: `def _update_bg_cache(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】更新bg缓存。

函数: `Canvas._update_cursor`
签名: `def _update_cursor(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】更新cursor。

函数: `Canvas._animate_grid`
签名: `def _animate_grid(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】animategrid。

函数: `Canvas.fit_view`
签名: `def fit_view(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】fitview。

函数: `Canvas.load_image`
签名: `def load_image(self, img_bgr, mask, preserve_view=False, raw=None, window_center=None, window_width=None)`
输入: `img_bgr`?`mask`?`preserve_view`?`raw`?`window_center`?`window_width`
输出: 可能返回: `None`
功能: 【推断】加载image。

函数: `Canvas.resizeEvent`
签名: `def resizeEvent(self, event)`
输入: `event`
输出: 无显式返回（默认 `None`）
功能: 【推断】调整大小事件。

函数: `Canvas._push_undo`
签名: `def _push_undo(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】pushundo。

函数: `Canvas.undo`
签名: `def undo(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】undo。

函数: `Canvas.redo`
签名: `def redo(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】redo。

函数: `Canvas.view_to_img`
签名: `def view_to_img(self, pos)`
输入: `pos`
输出: 可能返回: `(x, y)`
功能: 【推断】viewtoimg。

函数: `Canvas._snap_pos`
签名: `def _snap_pos(self, x, y, r)`
输入: `x`?`y`?`r`
输出: 可能返回: `(x, y)` / `(x0 + max_loc[0], y0 + max_loc[1])`
功能: 【推断】snappos。

函数: `Canvas._apply_brush`
签名: `def _apply_brush(self, x, y)`
输入: `x`?`y`
输出: 可能返回: `None`
功能: 【推断】应用brush。

函数: `Canvas._apply_brush_stroke`
签名: `def _apply_brush_stroke(self, x, y)`
输入: `x`?`y`
输出: 可能返回: `None`
功能: 【推断】应用brushstroke。

函数: `Canvas._close_polygon`
签名: `def _close_polygon(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】关闭polygon。

函数: `Canvas.dragEnterEvent`
签名: `def dragEnterEvent(self, event)`
输入: `event`
输出: 可能返回: `None`
功能: 【推断】拖拽enter事件。

函数: `Canvas.dropEvent`
签名: `def dropEvent(self, event)`
输入: `event`
输出: 可能返回: `None`
功能: 【推断】拖放事件。

函数: `Canvas.paintEvent`
签名: `def paintEvent(self, event)`
输入: `event`
输出: 可能返回: `None`
功能: 【推断】绘制事件。

函数: `Canvas.mousePressEvent`
签名: `def mousePressEvent(self, event)`
输入: `event`
输出: 可能返回: `None`
功能: 【推断】鼠标press事件。

函数: `Canvas.keyPressEvent`
签名: `def keyPressEvent(self, event)`
输入: `event`
输出: 无显式返回（默认 `None`）
功能: 【推断】键盘press事件。

函数: `Canvas.mouseMoveEvent`
签名: `def mouseMoveEvent(self, event)`
输入: `event`
输出: 可能返回: `None`
功能: 【推断】鼠标move事件。

函数: `Canvas.mouseReleaseEvent`
签名: `def mouseReleaseEvent(self, event)`
输入: `event`
输出: 无显式返回（默认 `None`）
功能: 【推断】鼠标release事件。

函数: `Canvas.wheelEvent`
签名: `def wheelEvent(self, event)`
输入: `event`
输出: 无显式返回（默认 `None`）
功能: 【推断】滚轮事件。

文件: `constants.py`
函数: `endswith_any`
签名: `def endswith_any(value, suffixes)`
输入: `value`?`suffixes`
输出: 可能返回: `bool(value) and str(value).lower().endswith(suffixes)`
功能: 【推断】endswithany。

函数: `split_known_image_ext`
签名: `def split_known_image_ext(path)`
输入: `path`
输出: 可能返回: `(path[:-len(ext)], ext)` / `(path, '')`
功能: 【推断】splitknownimageext。

函数: `strip_known_image_ext`
签名: `def strip_known_image_ext(path)`
输入: `path`
输出: 可能返回: `split_known_image_ext(path)[0]`
功能: 【推断】stripknownimageext。

函数: `default_mask_filename`
签名: `def default_mask_filename(stem, ext=DEFAULT_MASK_BITMAP_EXT)`
输入: `stem`?`ext`
输出: 可能返回: `f'{stem}{DEFAULT_MASK_SUFFIX}{ext}'`
功能: 【推断】defaultmaskfilename。

函数: `default_mask_path`
签名: `def default_mask_path(parent_dir, stem, ext=DEFAULT_MASK_BITMAP_EXT)`
输入: `parent_dir`?`stem`?`ext`
输出: 可能返回: `os.path.join(parent_dir, default_mask_filename(stem, ext))`
功能: 【推断】defaultmaskpath。

文件: `data_mixin.py`
函数: `DataMixin._get_labels_json_path`
签名: `def _get_labels_json_path(self)`
输入: 无显式参数
输出: 可能返回: `self.task_json_path` / `''` / `os.path.join(self.orig_root, 'pneumothorax_labels.json')`
功能: 【推断】获取labelsjsonpath。

函数: `DataMixin._init_labels_cache`
签名: `def _init_labels_cache(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】初始化labels缓存。

函数: `DataMixin._schedule_labels_flush`
签名: `def _schedule_labels_flush(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】schedulelabelsflush。

函数: `DataMixin._flush_labels_cache`
签名: `def _flush_labels_cache(self, force=True)`
输入: `force`
输出: 可能返回: `None`
功能: 【推断】flushlabels缓存。

函数: `DataMixin._get_status_file_path`
签名: `def _get_status_file_path(self)`
输入: 无显式参数
输出: 可能返回: `os.path.join(self.orig_root, f'{base_name}_case_status.json')` / `os.path.join(self.orig_root, 'case_status.json')`
功能: 【推断】获取statusfilepath。

函数: `DataMixin._load_case_status`
签名: `def _load_case_status(self)`
输入: 无显式参数
输出: 可能返回: `json.load(f)` / `{}`
功能: 【推断】加载casestatus。

函数: `DataMixin._save_single_case_status`
签名: `def _save_single_case_status(self, case_name, status)`
输入: `case_name`?`status`
输出: 无显式返回（默认 `None`）
功能: 【推断】保存singlecasestatus。

函数: `DataMixin._save_task_case_status`
签名: `def _save_task_case_status(self, case_name, status)`
输入: `case_name`?`status`
输出: 可能返回: `None`
功能: 【推断】保存taskcasestatus。

函数: `DataMixin._reset_cache`
签名: `def _reset_cache(self, clear_cache=True, invalidate_prefetch=True)`
输入: `clear_cache`?`invalidate_prefetch`
输出: 无显式返回（默认 `None`）
功能: 【推断】reset缓存。

函数: `DataMixin._cache_get`
签名: `def _cache_get(self, key)`
输入: `key`
输出: 可能返回: `val` / `None`
功能: 【推断】缓存获取。

函数: `DataMixin._get_active_cache_max`
签名: `def _get_active_cache_max(self)`
输入: 无显式参数
输出: 可能返回: `self.ct_cache_max if self.scan_mode == ScanMode.CT_SEQUENCE else self.xray_cache_max`
功能: 【推断】获取active缓存max。

函数: `DataMixin._cache_set`
签名: `def _cache_set(self, key, value)`
输入: `key`?`value`
输出: 无显式返回（默认 `None`）
功能: 【推断】缓存设置。

函数: `DataMixin._alloc_mask`
签名: `def _alloc_mask(self, shape)`
输入: `shape`
输出: 可能返回: `np.zeros(shape, dtype=np.uint8)` / `self._get_mask_pool_view(shape)`
功能: 【推断】allocmask。

函数: `DataMixin._reset_mask_pool`
签名: `def _reset_mask_pool(self, max_shape)`
输入: `max_shape`
输出: 无显式返回（默认 `None`）
功能: 【推断】resetmaskpool。

函数: `DataMixin._get_mask_pool_view`
签名: `def _get_mask_pool_view(self, shape)`
输入: `shape`
输出: 可能返回: `np.zeros(shape, dtype=np.uint8)` / `view`
功能: 【推断】获取maskpoolview。

函数: `DataMixin._release_cache_entry`
签名: `def _release_cache_entry(self, key, img, mask)`
输入: `key`?`img`?`mask`
输出: 无显式返回（默认 `None`）
功能: 【推断】release缓存entry。

函数: `DataMixin._split_compound_ext`
签名: `def _split_compound_ext(path_str)`
输入: `path_str`
输出: 可能返回: `split_known_image_ext(path_str)`
功能: 【推断】splitcompoundext。

函数: `DataMixin._strip_compound_ext`
签名: `def _strip_compound_ext(cls, path_str)`
输入: `path_str`
输出: 可能返回: `strip_known_image_ext(path_str)`
功能: 【推断】stripcompoundext。

函数: `DataMixin._is_nifti_file`
签名: `def _is_nifti_file(path_str)`
输入: `path_str`
输出: 可能返回: `endswith_any(path_str, NIFTI_EXTENSIONS)`
功能: 【推断】isniftifile。

函数: `DataMixin._get_xray_mask_stem`
签名: `def _get_xray_mask_stem(cls, path_str)`
输入: `path_str`
输出: 可能返回: `os.path.basename(cls._strip_compound_ext(path_str or ''))`
功能: 【推断】获取xraymaskstem。

函数: `DataMixin._is_generic_xray_mask_name`
签名: `def _is_generic_xray_mask_name(self, filename)`
输入: `filename`
输出: 可能返回: `bool(stem) and (stem == 'untitled' or stem.startswith('untitled') or re.fullmatch('\\d+', stem) is not None)`
功能: 【推断】isgenericxraymaskname。

函数: `DataMixin._is_xray_mask_sidecar`
签名: `def _is_xray_mask_sidecar(self, filename)`
输入: `filename`
输出: 可能返回: `True` / `False`
功能: 【推断】isxraymasksidecar。

函数: `DataMixin._iter_xray_source_filenames`
签名: `def _iter_xray_source_filenames(self, dir_path)`
输入: `dir_path`
输出: 可能返回: `[]` / `result`
功能: 【推断】iterxraysourcefilenames。

函数: `DataMixin._build_xray_dir_mask_map`
签名: `def _build_xray_dir_mask_map(self, src_dir, rel_dir='')`
输入: `src_dir`?`rel_dir`
输出: 可能返回: `{}` / `dict(cache[cache_key])` / `dict(mapping)`
功能: 【推断】构建xraydirmaskmap。

函数: `DataMixin._build_xray_dir_mask_map._candidate_paths`
签名: `def _candidate_paths(file_stem, rel_stem)`
输入: `file_stem`?`rel_stem`
输出: 可能返回: `[os.path.join(self.mask_root, base_rel + ext) for ext in exact_exts] + [os.path.join(self.mask_root, base_rel + '_mask' + ext) for ext in exact_exts]` / `[os.path.join(src_dir, file_stem + ext) for ext in exact_exts] + [os.path.join(src_dir, file_stem + '_mask' + ext) for ext in exact_exts]`
功能: 【推断】candidatepaths。

函数: `DataMixin._resolve_xray_mask_path`
签名: `def _resolve_xray_mask_path(self, orig_path, rel_src=None)`
输入: `orig_path`?`rel_src`
输出: 可能返回: `''` / `mapping.get(os.path.normpath(orig_path), '')`
功能: 【推断】解析xraymaskpath。

函数: `DataMixin._resolve_ct_mask_path`
签名: `def _resolve_ct_mask_path(self, orig_path, p_mask, rel_in_case)`
输入: `orig_path`?`p_mask`?`rel_in_case`
输出: 可能返回: `candidate` / `default_mask_path(p_mask, stem, DEFAULT_MASK_BITMAP_EXT)`
功能: CT 序列模式下搜索已有掩码（支持 NIfTI），找不到则回退为默认 PNG 路径。

函数: `DataMixin._build_prefetch_indices`
签名: `def _build_prefetch_indices(self, current_idx)`
输入: `current_idx`
输出: 可能返回: `[]` / `candidates[:self.ct_prefetch_count]`
功能: 【推断】构建预取indices。

函数: `DataMixin._next_prefetch_epoch`
签名: `def _next_prefetch_epoch(self)`
输入: 无显式参数
输出: 可能返回: `self._prefetch_epoch`
功能: 【推断】next预取epoch。

函数: `DataMixin._next_prefetch_worker_token`
签名: `def _next_prefetch_worker_token(self, kind)`
输入: `kind`
输出: 可能返回: `token`
功能: 【推断】next预取workertoken。

函数: `DataMixin._start_prefetch`
签名: `def _start_prefetch(self, current_idx)`
输入: `current_idx`
输出: 可能返回: `None`
功能: 【推断】启动预取。

函数: `DataMixin._prefetch_worker`
签名: `def _prefetch_worker(self, epoch, token, indices)`
输入: `epoch`?`token`?`indices`
输出: 可能返回: `None`
功能: 【推断】预取worker。

函数: `DataMixin._start_cross_case_prefetch`
签名: `def _start_cross_case_prefetch(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】启动crosscase预取。

函数: `DataMixin._collect_next_case_entries`
签名: `def _collect_next_case_entries(self, case_name, count)`
输入: `case_name`?`count`
输出: 可能返回: `[]` / `entries`
功能: 收集当前病例之后的 count 个病例的所有切片 Entry。

函数: `DataMixin._build_default_xray_mask_path`
签名: `def _build_default_xray_mask_path(self, orig_path)`
输入: `orig_path`
输出: 可能返回: `default_mask_path(mask_dir, stem, DEFAULT_MASK_BITMAP_EXT)`
功能: 【推断】构建defaultxraymaskpath。

函数: `DataMixin._build_xray_entry`
签名: `def _build_xray_entry(self, full_src, case_name, filename=None, rel_src=None, has_pneumo=None)`
输入: `full_src`?`case_name`?`filename`?`rel_src`?`has_pneumo`
输出: 可能返回: `ImageEntry(case_name=case_name, orig_path=full_src, mask_path=mask_path, filename=filename, has_mask=os.path.exists(mask_path), has_pneumothorax=has_pneumo)`
功能: 【推断】构建xrayentry。

函数: `DataMixin._build_xray_case_entries`
签名: `def _build_xray_case_entries(self, case_name)`
输入: `case_name`
输出: 可能返回: `[self._build_xray_entry(case_file_path, case_name=case_name, filename=os.path.basename(case_file_path), rel_src=case_name.replace('\\', '/'))]` / `[]` / `files`
功能: 【推断】构建xraycaseentries。

函数: `DataMixin._build_ct_case_entries`
签名: `def _build_ct_case_entries(self, case_name)`
输入: `case_name`
输出: 可能返回: `files`
功能: 【推断】构建ctcaseentries。

函数: `DataMixin._build_case_entries`
签名: `def _build_case_entries(self, case_name)`
输入: `case_name`
输出: 可能返回: `files` / `self._build_ct_case_entries(case_name)` / `self._build_xray_case_entries(case_name)`
功能: 【推断】构建caseentries。

函数: `DataMixin._expand_case_to_entries`
签名: `def _expand_case_to_entries(self, case_name)`
输入: `case_name`
输出: 可能返回: `[]` / `self._build_ct_case_entries(case_name)` / `self._build_xray_case_entries(case_name)`
功能: 把一个病例名展开成 ImageEntry 列表。

函数: `DataMixin._prefetch_case_worker`
签名: `def _prefetch_case_worker(self, epoch, token, entries)`
输入: `epoch`?`token`?`entries`
输出: 可能返回: `None`
功能: 【推断】预取caseworker。

函数: `DataMixin.select_orig_dir`
签名: `def select_orig_dir(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 选择原图目录

函数: `DataMixin.select_mask_dir`
签名: `def select_mask_dir(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 选择掩码目录

函数: `DataMixin.select_task_json`
签名: `def select_task_json(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】选择taskjson。

函数: `DataMixin.load_task_json`
签名: `def load_task_json(self, json_path)`
输入: `json_path`
输出: 可能返回: `None`
功能: 【推断】加载taskjson。

函数: `DataMixin._on_scan_cancelled`
签名: `def _on_scan_cancelled(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】处理扫描cancelled。

函数: `DataMixin._build_task_case_lists`
签名: `def _build_task_case_lists(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】构建taskcaselists。

函数: `DataMixin._internal_scan_worker`
签名: `def _internal_scan_worker(self, token, scan_mode, orig_root, mask_root, status_map, result_queue)`
输入: `token`?`scan_mode`?`orig_root`?`mask_root`?`status_map`?`result_queue`
输出: 无显式返回（默认 `None`）
功能: 【推断】internal扫描worker。

函数: `DataMixin._poll_scan_result`
签名: `def _poll_scan_result(self, token)`
输入: `token`
输出: 可能返回: `None`
功能: 【推断】poll扫描result。

函数: `DataMixin.refresh_lists`
签名: `def refresh_lists(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 完全解耦的目录扫描，根据UI选项智能处理

函数: `DataMixin._start_case_background_work`
签名: `def _start_case_background_work(self, case_name, thumb_token=None)`
输入: `case_name`?`thumb_token`
输出: 可能返回: `None`
功能: 【推断】启动casebackgroundwork。

函数: `DataMixin.load_case_sequence`
签名: `def load_case_sequence(self, item)`
输入: `item`
输出: 无显式返回（默认 `None`）
功能: 【推断】加载casesequence。

函数: `DataMixin._thumb_worker`
签名: `def _thumb_worker(self, entries, token)`
输入: `entries`?`token`
输出: 可能返回: `None`
功能: 后台线程：逐张生成缩略图并放入队列，由主线程消费。

函数: `DataMixin._build_thumb_icon`
签名: `def _build_thumb_icon(self, entry)`
输入: `entry`
输出: 可能返回: `QIcon()` / `QIcon(pix)`
功能: 优先复用缓存，降低缩略图线程对磁盘的重复读取。

函数: `DataMixin._drain_thumb_queue`
签名: `def _drain_thumb_queue(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 主线程定时器：批量消费队列，更新缩略图条目。

函数: `DataMixin.load_image_at_index`
签名: `def load_image_at_index(self, idx, start_background=True)`
输入: `idx`?`start_background`
输出: 可能返回: `None`
功能: 【推断】加载imageatindex。

函数: `DataMixin.on_slider_change`
签名: `def on_slider_change(self, value)`
输入: `value`
输出: 无显式返回（默认 `None`）
功能: 【推断】处理sliderchange。

函数: `DataMixin.action_toggle_case_status`
签名: `def action_toggle_case_status(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】action切换casestatus。

函数: `DataMixin.export_task_json`
签名: `def export_task_json(self)`
输入: 无显式参数
输出: 可能返回: `None`
功能: 【推断】导出taskjson。

文件: `icons.py`
函数: `IconFactory._base_icon`
签名: `def _base_icon(size=64)`
输入: `size`
输出: 可能返回: `(img, p)`
功能: 【推断】baseicon。

函数: `IconFactory.create_app_icon`
签名: `def create_app_icon()`
输入: 无显式参数
输出: 可能返回: `QIcon(QPixmap.fromImage(img))`
功能: 【推断】创建appicon。

函数: `IconFactory.create_invert_icon`
签名: `def create_invert_icon()`
输入: 无显式参数
输出: 可能返回: `QIcon(QPixmap.fromImage(img))`
功能: 【推断】创建inverticon。

函数: `IconFactory.create_tool_icon`
签名: `def create_tool_icon(text, color='#00f0ff', bg_shape='rect')`
输入: `text`?`color`?`bg_shape`
输出: 可能返回: `QIcon(QPixmap.fromImage(img))`
功能: 【推断】创建toolicon。

函数: `IconFactory.create_lock_icon`
签名: `def create_lock_icon(locked=True)`
输入: `locked`
输出: 可能返回: `QIcon(QPixmap.fromImage(img))`
功能: 【推断】创建lockicon。

函数: `IconFactory.create_magnet_icon`
签名: `def create_magnet_icon()`
输入: 无显式参数
输出: 可能返回: `QIcon(QPixmap.fromImage(img))`
功能: 【推断】创建magneticon。

函数: `IconFactory.create_eye_icon`
签名: `def create_eye_icon()`
输入: 无显式参数
输出: 可能返回: `QIcon(QPixmap.fromImage(img))`
功能: 【推断】创建eyeicon。

函数: `IconFactory.create_sun_icon`
签名: `def create_sun_icon()`
输入: 无显式参数
输出: 可能返回: `QIcon(QPixmap.fromImage(img))`
功能: 【推断】创建sunicon。

文件: `main_window.py`
函数: `MedicalLabelPro.__init__`
签名: `def __init__(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 初始化对象与默认状态。

函数: `MedicalLabelPro._coerce_int`
签名: `def _coerce_int(self, value, default, min_val=None, max_val=None)`
输入: `value`?`default`?`min_val`?`max_val`
输出: 可能返回: `default` / `v`
功能: 【推断】coerceint。

函数: `MedicalLabelPro._load_perf_settings`
签名: `def _load_perf_settings(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】加载perfsettings。

函数: `MedicalLabelPro._save_perf_settings`
签名: `def _save_perf_settings(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】保存perfsettings。

函数: `MedicalLabelPro.dragEnterEvent`
签名: `def dragEnterEvent(self, event)`
输入: `event`
输出: 无显式返回（默认 `None`）
功能: 【推断】拖拽enter事件。

函数: `MedicalLabelPro.dropEvent`
签名: `def dropEvent(self, event)`
输入: `event`
输出: 可能返回: `None`
功能: 【推断】拖放事件。

文件: `models.py`
（无可解析函数）

文件: `ui_mixin.py`
函数: `UiMixin._init_ui`
签名: `def _init_ui(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】初始化ui。

函数: `UiMixin._init_ui.create_group`
签名: `def create_group(title, widget)`
输入: `title`?`widget`
输出: 可能返回: `grp`
功能: 【推断】创建group。

函数: `UiMixin._init_toolbar`
签名: `def _init_toolbar(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】初始化toolbar。

函数: `UiMixin._init_shortcuts`
签名: `def _init_shortcuts(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】初始化shortcuts。

函数: `UiMixin._init_window_menu`
签名: `def _init_window_menu(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】初始化windowmenu。

函数: `UiMixin._show_load_help`
签名: `def _show_load_help(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】显示加载help。

函数: `UiMixin._init_file_menu`
签名: `def _init_file_menu(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】初始化filemenu。

函数: `UiMixin._on_viz_change`
签名: `def _on_viz_change(self, type_, val)`
输入: `type_`?`val`
输出: 无显式返回（默认 `None`）
功能: 【推断】处理vizchange。

函数: `UiMixin._toggle_smart_lock`
签名: `def _toggle_smart_lock(self, checked)`
输入: `checked`
输出: 无显式返回（默认 `None`）
功能: 【推断】切换smartlock。

函数: `UiMixin._change_scan_mode`
签名: `def _change_scan_mode(self, idx)`
输入: `idx`
输出: 无显式返回（默认 `None`）
功能: 【推断】change扫描mode。

函数: `UiMixin._adjust_alpha`
签名: `def _adjust_alpha(self, delta)`
输入: `delta`
输出: 无显式返回（默认 `None`）
功能: 【推断】adjustalpha。

文件: `utils.py`
函数: `smart_read_image`
签名: `def smart_read_image(path)`
输入: `path`
输出: 可能返回: `imread_unicode(path)` / `img`
功能: 【推断】smart读取image。

函数: `read_dicom_with_window`
签名: `def read_dicom_with_window(path)`
输入: `path`
输出: 可能返回: `None` / `(img_bgr, data, wc, ww, (min_val, max_val))`
功能: 【推断】读取dicomwithwindow。

函数: `get_dicom_metadata`
签名: `def get_dicom_metadata(path)`
输入: `path`
输出: 可能返回: `info`
功能: 【推断】获取dicommetadata。

函数: `get_dicom_metadata.get_val`
签名: `def get_val(tag, default='N/A')`
输入: `tag`?`default`
输出: 可能返回: `str(ds.get(tag, default))`
功能: 【推断】获取val。

函数: `imread_unicode`
签名: `def imread_unicode(path, flags=cv2.IMREAD_COLOR)`
输入: `path`?`flags`
输出: 可能返回: `None` / `cv2.imdecode(data, flags)`
功能: 【推断】imreadunicode。

函数: `imwrite_unicode`
签名: `def imwrite_unicode(path, img)`
输入: `path`?`img`
输出: 可能返回: `False` / `True`
功能: 【推断】imwriteunicode。

函数: `imwrite_with_quality`
签名: `def imwrite_with_quality(path, img, quality)`
输入: `path`?`img`?`quality`
输出: 可能返回: `False` / `True`
功能: 【推断】imwritewithquality。

函数: `_resize_mask_if_needed`
签名: `def _resize_mask_if_needed(mask, target_shape)`
输入: `mask`?`target_shape`
输出: 可能返回: `mask` / `cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)`
功能: 【推断】调整大小maskifneeded。

函数: `_sitk_force_2d`
签名: `def _sitk_force_2d(img, name)`
输入: `img`?`name`
输出: 可能返回: `img` / `sitk.Extract(img, extract_size, extract_index)`
功能: 【推断】sitkforce2d。

函数: `_has_non_ascii`
签名: `def _has_non_ascii(s)`
输入: `s`
输出: 可能返回: `False` / `True`
功能: 【推断】hasnonascii。

函数: `_safe_sitk_read_image`
签名: `def _safe_sitk_read_image(path)`
输入: `path`
输出: 可能返回: `(img, None)` / `(img, temp_dir)`
功能: 先直接读；如果失败且路径包含非 ASCII 字符，

函数: `_safe_sitk_write_image`
签名: `def _safe_sitk_write_image(img, target_path)`
输入: `img`?`target_path`
输出: 可能返回: `(True, None)` / `(False, f'目标目录不存在: {target_dir}')` / `(False, f'写入 NIfTI 失败: {e}')` / `(False, f'写入 NIfTI 失败: {e2}')`
功能: 先尝试直接写。

函数: `_read_nifti_mask_aligned`
签名: `def _read_nifti_mask_aligned(path, target_shape=None, reference_image_path=None)`
输入: `path`?`target_shape`?`reference_image_path`
输出: 可能返回: `(None, str(e))` / `(None, f'读取参考图像失败: {e}')` / `(None, f'掩码维度({mask_img.GetDimension()})与参考图像维度({ref_img.GetDimension()})不一致')` / `(None, f'NIfTI 掩码重采样失败: {e}')` / `(None, f'NIfTI 转数组失败: {e}')` / `(None, f'当前仅支持 2D 掩码，实际数组形状为 {arr.shape}')` / `(np.ascontiguousarray(mask), None)` / `(None, f'读取 NIfTI 失败: {e}')`
功能: 【推断】读取niftimaskaligned。

函数: `read_mask_file`
签名: `def read_mask_file(path, target_shape=None, reference_image_path=None)`
输入: `path`?`target_shape`?`reference_image_path`
输出: 可能返回: `(None, '读取掩码失败')` / `(np.ascontiguousarray(mask), None)` / `_read_nifti_mask_aligned(path, target_shape=target_shape, reference_image_path=reference_image_path)` / `(None, '不支持的掩码格式')`
功能: 【推断】读取maskfile。

函数: `binarize_mask`
签名: `def binarize_mask(mask, threshold)`
输入: `mask`?`threshold`
输出: 可能返回: `(np.asarray(mask) >= threshold).astype(np.uint8) * 255`
功能: 【推断】binarizemask。

函数: `natural_sort_key`
签名: `def natural_sort_key(s)`
输入: `s`
输出: 可能返回: `[int(text) if text.isdigit() else text.lower() for text in re.split('(\\d+)', s)]`
功能: 【推断】naturalsort键盘。

函数: `apply_tech_theme`
签名: `def apply_tech_theme(app)`
输入: `app`
输出: 无显式返回（默认 `None`）
功能: 深色科技主题

函数: `apply_light_theme`
签名: `def apply_light_theme(app)`
输入: `app`
输出: 无显式返回（默认 `None`）
功能: 浅色护眼主题

函数: `_apply_theme_qss`
签名: `def _apply_theme_qss(app, bg_color, panel_color, text_color, accent_color, border_color)`
输入: `app`?`bg_color`?`panel_color`?`text_color`?`accent_color`?`border_color`
输出: 无显式返回（默认 `None`）
功能: 通用的 QSS 注入逻辑

函数: `load_pneumo_labels`
签名: `def load_pneumo_labels(base_dirs)`
输入: `base_dirs`
输出: 可能返回: `data` / `{}`
功能: 【推断】加载pneumolabels。

函数: `is_dual_folder_mode`
签名: `def is_dual_folder_mode(orig_root, mask_root)`
输入: `orig_root`?`mask_root`
输出: 可能返回: `False` / `os.path.normcase(os.path.abspath(orig_root)) != os.path.normcase(os.path.abspath(mask_root))`
功能: 【推断】isdualfoldermode。

函数: `write_mask_file`
签名: `def write_mask_file(path, mask, reference_mask_path=None)`
输入: `path`?`mask`?`reference_mask_path`
输出: 可能返回: `(False, f'掩码数组无效: {e}')` / `(False, '保存位图掩码失败')` / `(True, None)` / `(False, f'创建 NIfTI 图像失败: {e}')` / `(False, f'保存 NIfTI 失败：当前掩码尺寸 {mask_bin.shape} 与参考掩码尺寸 {(ref_img_2d.GetSize()[1], ref_img_2d.GetSize()[0])} 不一致')` / `(False, f'读取参考掩码失败: {e}')` / `(False, err)` / `(False, '不支持的导出格式')`
功能: 【推断】写入maskfile。

文件: `widgets.py`
函数: `DicomInfoPanel.__init__`
签名: `def __init__(self, parent=None)`
输入: `parent`
输出: 无显式返回（默认 `None`）
功能: 初始化对象与默认状态。

函数: `DicomInfoPanel.clear`
签名: `def clear(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 清空表格内容（供模式切换时调用）。

函数: `DicomInfoPanel.update_info`
签名: `def update_info(self, path)`
输入: `path`
输出: 无显式返回（默认 `None`）
功能: 【推断】更新info。

函数: `VisualControlWidget.__init__`
签名: `def __init__(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 初始化对象与默认状态。

函数: `VisualControlWidget.set_window_controls`
签名: `def set_window_controls(self, center, width, min_val, max_val, enabled)`
输入: `center`?`width`?`min_val`?`max_val`?`enabled`
输出: 无显式返回（默认 `None`）
功能: 【推断】设置windowcontrols。

函数: `PrefetchSettingsDialog.__init__`
签名: `def __init__(self, parent=None, ct_prefetch_count=8, ct_cross_count=2, ct_cache_max=40, xray_prefetch_count=5, xray_cache_max=12)`
输入: `parent`?`ct_prefetch_count`?`ct_cross_count`?`ct_cache_max`?`xray_prefetch_count`?`xray_cache_max`
输出: 无显式返回（默认 `None`）
功能: 初始化对象与默认状态。

函数: `PrefetchSettingsDialog.get_values`
签名: `def get_values(self)`
输入: 无显式参数
输出: 可能返回: `{'ct_prefetch_count': self.spin_ct_prefetch.value(), 'ct_cross_count': self.spin_ct_cross.value(), 'ct_cache_max': self.spin_ct_cache.value(), 'xray_prefetch_count': self.spin_xray_prefetch.value(), 'xray_cache_max': self.spin_xray_cache.value()}`
功能: 【推断】获取values。

函数: `ExportSettingsDialog.__init__`
签名: `def __init__(self, parent=None, width=512, height=512, quality=95, default_path='')`
输入: `parent`?`width`?`height`?`quality`?`default_path`
输出: 无显式返回（默认 `None`）
功能: 初始化对象与默认状态。

函数: `ExportSettingsDialog.get_values`
签名: `def get_values(self)`
输入: 无显式参数
输出: 可能返回: `(self.spin_width.value(), self.spin_height.value(), self.spin_quality.value(), self.combo_format.currentText(), self.edit_path.text().strip(), self.check_invert.isChecked())`
功能: 【推断】获取values。

函数: `ExportSettingsDialog._browse_path`
签名: `def _browse_path(self)`
输入: 无显式参数
输出: 无显式返回（默认 `None`）
功能: 【推断】browsepath。
