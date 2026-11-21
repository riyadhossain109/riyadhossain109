import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import threading
import time
import os
from PIL import Image, ImageDraw

# --- Global Appearance Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- Translation Dictionary ---
TRANSLATIONS = {
    "EN": {
        "win_title": "Master Spectro-Aerogel Station Autonomous Cockpit",
        "banner_title": "AEROGEL MASTER SPECTRAL SCANNER MAIN CONTROL STATION",
        "grid_title": " Stage Grid Configuration ",
        "x0": "Start X0 (mm):", "y0": "Start Y0 (mm):",
        "length": "Sample Length (cm):", "width": "Sample Width (cm):",
        "density": "Density (N x N Matrix):", "btn_draw_map": "Update & Draw Stage Map",
        "keysight_title": " Keysight Electrometer Settings ",
        "n_meas": "Samples Count (N_meas):", "delta_t": "Read Delay [Delta t] (s):",
        "settle": "Stage Settle Delay (s):", "btn_apply_bus": "Apply Bus Metrics",
        "mono_title": " Monochromator Spectrum Setup ",
        "rb_manual": "Manual Array Input (nm):", "rb_range": "Range Loop Sweeper Mode:",
        "start": "Start:", "end": "End:", "step": "Step:",
        "rb_file": "TXT Configuration File:", "btn_browse": "Browse TXT",
        "btn_load": "Verify & Load Channels",
        "channels_loaded": "Channels Loaded: {count}\nArray Profiles:\n{arr}",
        "stage_box_title": " Live Kinematics Stage Trajectory Mapping ",
        "stage_plot_title": "Live Stage Matrix Trajectory Profile Map",
        "spec_box_title": " Real-Time Transmission Curve Spectrogram Plotter ",
        "spec_plot_title": "Live Real-Time Reduced Spectrograph Profile",
        "spec_xlabel": "Optical Light Wavelength (nm)",
        "spec_ylabel": "Transmittance Ratio (I_corrected / I0_corrected)",
        "spec_legend_main": "Sample Transmittance", "spec_legend_node": "Active Wavelength node",
        "est_title": " Session Pre-Run Metrics Estimation ",
        "btn_recompute": "Re-Compute Run Estimation Profile",
        "est_summary": "--- PRE-RUN PERFORMANCE DATA ---\nTotal Map Nodes     : {pts} points\nSpectral Line Tracks: {wl} entries\nTime per Coordinates: {nt:.2f} s\nTotal Vector Nodes  : {vec} logs\n--------------------------------\nESTIMATED TIMELINE  : {h:02d}h:{m:02d}m:{s:02d}s\n",
        "mon_title": " Live Process Monitoring & Execution Tracker Engine ",
        "status_standby": "Active Optical Line: STANDBY (--- nm)",
        "status_running": "Active Optical Line: RUNNING ({w} nm)",
        "status_done": "Active Optical Line: RUN METRIC PIPELINE COMPLETED",
        "status_aborted": "Active Optical Line: OPERATIONS HALTED BY OPERATOR",
        "node_ready": "Spatial Trajectory Point: Node 0 / 0 Ready",
        "node_proc": "Spatial Trajectory Point: Node {i} / {t} Processing...",
        "btn_launch": "LAUNCH EXPERIMENT", "btn_abort": "ABORT ACTIVE RUN SESSION",
        "msg_env_warn_title": "Envelope Warning", "msg_env_warn": "Calculated nodes violate physical 300mm envelope travel boundaries.",
        "msg_success_title": "Success", "msg_success": "Keysight parameters committed onto Active System Variables.",
        "msg_val_err_title": "Validation Error", "msg_val_err": "Check values profiles compatibility formats.",
        "log_init": "== INITIALIZING INTEGRATED SCAN MATRIX EXPERIMENT RUN MAP ==",
        "log_wl": "\n🔮 [WAVELENGTH STEP] Tuning Monochromator filterwheel to: {wl} nm...",
        "log_node": "📍 [{wl}nm] Node {idx}/{tot} -> Coordinates: X={x:.1f}, Y={y:.1f}",
        "log_done": "\n🎉 [FINISHED] Automation execution finalized. Session written to disk logs.",
        "log_abort": "\n⚠️ [ABORTED] Hardware monitoring loop manually disconnected."
    },
    "RU": {
        "win_title": "Автономная станция спектроскопии аэрогелей",
        "banner_title": "ГЛАВНАЯ СТАНЦИЯ УПРАВЛЕНИЯ СПЕКТРАЛЬНЫМ СКАНЕРОМ АЭРОГЕЛЕЙ",
        "grid_title": " Конфигурация координатной сетки ",
        "x0": "Начало X0 (мм):", "y0": "Начало Y0 (мм):",
        "length": "Длина образца (см):", "width": "Ширина образца (см):",
        "density": "Плотность (Матрица N x N):", "btn_draw_map": "Обновить и построить карту",
        "keysight_title": " Настройки электрометра Keysight ",
        "n_meas": "Число замеров (N_meas):", "delta_t": "Задержка чтения [Delta t] (с):",
        "settle": "Время стабилизации (с):", "btn_apply_bus": "Применить параметры шины",
        "mono_title": " Настройка спектра монохроматора ",
        "rb_manual": "Ручной ввод массива (нм):", "rb_range": "Режим развертки диапазона:",
        "start": "Старт:", "end": "Стоп:", "step": "Шаг:",
        "rb_file": "Файл конфигурации TXT:", "btn_browse": "Обзор TXT",
        "btn_load": "Проверить и загрузить каналы",
        "channels_loaded": "Загружено каналов: {count}\nПрофиль массива:\n{arr}",
        "stage_box_title": " Кинематика и траектория движения стола ",
        "stage_plot_title": "Карта траектории сканирования матрицы",
        "spec_box_title": " Построитель кривой пропускания в реальном времени ",
        "spec_plot_title": "Спектрограмма пропускания в реальном времени",
        "spec_xlabel": "Длина волны оптического излучения (нм)",
        "spec_ylabel": "Коэффициент пропускания (I_корр / I0_корр)",
        "spec_legend_main": "Пропускание образца", "spec_legend_node": "Активная длина волны",
        "est_title": " Предварительный расчет времени сессии ",
        "btn_recompute": "Пересчитать профиль времени",
        "est_summary": "--- ПРЕДВАРИТЕЛЬНЫЕ ДАННЫЕ ---\nВсего узлов карты   : {pts} точек\nСпектральных линий  : {wl} шт.\nВремя на координату : {nt:.2f} с\nВсего векторов      : {vec} записей\n--------------------------------\nРАСЧЕТНОЕ ВРЕМЯ     : {h:02d}ч:{m:02d}м:{s:02d}с\n",
        "mon_title": " Мониторинг процесса и трекер выполнения ",
        "status_standby": "Оптическая линия: ОЖИДАНИЕ (--- нм)",
        "status_running": "Оптическая линия: ВЫПОЛНЕНИЕ ({w} нм)",
        "status_done": "Оптическая линия: СКАНИРОВАНИЕ ЗАВЕРШЕНО",
        "status_aborted": "Оптическая линия: ОСТАНОВЛЕНО ОПЕРАТОРОМ",
        "node_ready": "Точка траектории: Узел 0 / 0 Готов",
        "node_proc": "Точка траектории: Узел {i} / {t} Обработка...",
        "btn_launch": "ЗАПУСТИТЬ ЭКСПЕРИМЕНТ", "btn_abort": "ПРЕРВАТЬ ТЕКУЩИЙ ЗАПУСК",
        "msg_env_warn_title": "Предупреждение границ", "msg_env_warn": "Расчетные узлы выходят за пределы физического хода 300 мм.",
        "msg_success_title": "Успешно", "msg_success": "Параметры Keysight сохранены в системные переменные.",
        "msg_val_err_title": "Ошибка проверки", "msg_val_err": "Проверьте правильность введенных числовых форматов.",
        "log_init": "== ИНИЦИАЛИЗАЦИЯ МАТРИЧНОГО СКАНИРОВАНИЯ ЭКСПЕРИМЕНТА ==",
        "log_wl": "\n🔮 [ШАГ ДЛИНЫ ВОЛНЫ] Настройка монохроматора на: {wl} нм...",
        "log_node": "📍 [{wl}нм] Узел {idx}/{tot} -> Координаты: X={x:.1f}, Y={y:.1f}",
        "log_done": "\n🎉 [ЗАВЕРШЕНО] Выполнение автоматизации завершено. Логи записаны на диск.",
        "log_abort": "\n⚠️ [ПРЕРВАНО] Цикл мониторинга оборудования остановлен вручную."
    }
}

class UnifiedSpectroStationDashboard:
    def __init__(self, root):
        self.root = root
        self.lang = "RU"  # Default language ("EN" or "RU")
        self.root.geometry("1500x900")
        
        # --- Core Shared Variables (Data Sync Bridge) ---
        self.MAX_TRAVEL_MM = 300.0
        self.wavelengths_list = [350.0, 420.0, 450.0, 660.0]
        self.selected_file_path = "scan_wavelengths_aerogels.txt"
        self.num_measurements = 20
        self.delay_between_reads = 0.1
        self.stabilization_delay = 3.0
        
        # Simulation execution state flags
        self.is_scanning = False
        self.scan_thread = None
        self.last_plotted_wl = []
        self.last_plotted_t = []


        # --- Top Banner Header ---
        top_banner = ctk.CTkFrame(self.root, height=60, corner_radius=0, fg_color="#0f172a")
        top_banner.pack(fill=tk.X, side=tk.TOP)

        # Configure layout row and column grid maps inside the header bar
        top_banner.grid_columnconfigure(0, weight=0)  # Logo column stays a fixed size
        top_banner.grid_columnconfigure(1, weight=1)  # Title column expands to fill the remaining area
        top_banner.grid_columnconfigure(2, weight=0)  # Language switcher column stays a fixed size

        # 1. Dynamically render a 3D Shaded Blue Prism Triangle directly into memory
        try:
            # Create a crisp high-res template area
            raw_logo = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
            draw = ImageDraw.Draw(raw_logo)
            
            # Draws the 3D shaded polygon segments matching your target asset
            # Front Left Facet (Light ice blue)
            draw.polygon([(100, 20), (180, 50), (116, 180)], fill="#87ace0")
            
            # Front Right Facet (Deep sapphire blue)
            draw.polygon([(180, 50), (190, 20), (116, 180)], fill="#0f60b6")
            
            # Top Facet (Medium slate blue shading)
            draw.polygon([(100, 20), (190, 20), (180, 50)], fill="#5c8bc7")
            
            self.logo_img = ctk.CTkImage(light_image=raw_logo, dark_image=raw_logo, size=(45, 45))
            
            # 2. Place Logo Container inside Header Bar using grid
            logo_lbl = ctk.CTkLabel(top_banner, image=self.logo_img, text="")
            logo_lbl.grid(row=0, column=0, padx=(25, 15), pady=8, sticky="w")
        except Exception as e:
            print(f"Error initializing embedded image asset: {e}")

        
        # 3. Align Title Header next to the logo using layout grid positions
        self.title_lbl = ctk.CTkLabel(
            top_banner, 
            text="", 
            font=ctk.CTkFont(family="sans-serif", size=18, weight="bold"),
            text_color="#f8fafc"
        )
        self.title_lbl.grid(row=0, column=1, pady=16, sticky="w")

        # 4. Language Switcher Button (EN / RU)
        self.lang_switch = ctk.CTkSegmentedButton(
            top_banner,
            values=["EN", "RU"],
            command=self.change_language,
            width=100,
            height=30,
            font=ctk.CTkFont(weight="bold", size=12)
        )
        self.lang_switch.set(self.lang)
        self.lang_switch.grid(row=0, column=2, padx=25, pady=15, sticky="e")


                # Workspace Container Layout Splitter (Holds 3 main columns)
        workspace = ctk.CTkFrame(self.root, fg_color="transparent")
        workspace.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # =========================================================================
        # COLUMN 1: HARDWARE CONFIGURATION PANEL (LEFT)
        # =========================================================================
        col1 = ctk.CTkFrame(workspace, fg_color="transparent", width=340)
        col1.pack(side=tk.LEFT, fill=tk.Y, anchor="n", expand=False, padx=(0, 15))

        # Module 1A: Stage Kinematics / Grid Setup
        grid_frame = ctk.CTkFrame(col1)
        grid_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)
        
        self.grid_frame_lbl = ctk.CTkLabel(grid_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=35, corner_radius=6, text_color="#38bdf8")
        self.grid_frame_lbl.grid(row=0, column=0, columnspan=2, sticky="we", padx=15, pady=(10, 5))

        fields = [
            ("Start X0 (mm):", "10.0", "entry_x0"),
            ("Start Y0 (mm):", "75.0", "entry_y0"),
            ("Sample Length (cm):", "10.0", "entry_length"),
            ("Sample Width (cm):", "10.0", "entry_width"),
            ("Density (N x N Matrix):", "05", "entry_points")
        ]

        for i, (label_text, default_val, attr_name) in enumerate(fields, start=1):
            lbl = ctk.CTkLabel(grid_frame, text="", font=ctk.CTkFont(size=11))
            lbl.grid(row=i, column=0, sticky="w", padx=15, pady=5)
            setattr(self, f"lbl_{attr_name}", lbl)
            
            entry = ctk.CTkEntry(grid_frame, width=110, height=28, font=ctk.CTkFont(family="sans-serif", size=11))
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, padx=15, pady=5, sticky="e")
            setattr(self, attr_name, entry)

        self.grid_btn = ctk.CTkButton(grid_frame, text="", height=32, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.update_stage_plot)
        self.grid_btn.grid(row=6, column=0, columnspan=2, pady=(12, 5), padx=15, sticky="we")
        

        # Module 1C: Keysight Instrument Adjuster
        keysight_frame = ctk.CTkFrame(col1)
        keysight_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)
        
        self.keysight_frame_lbl = ctk.CTkLabel(keysight_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=35, corner_radius=6, text_color="#38bdf8")
        self.keysight_frame_lbl.grid(row=0, column=0, columnspan=2, sticky="we", padx=15, pady=(10, 5))

        k_fields = [
            ("Samples Count (N_meas):", "20", "entry_nmeas"),
            ("Read Delay [Delta t] (s):", "0.1", "entry_delta_t"),
            ("Stage Settle Delay (s):", "3.0", "entry_stabilize")
        ]

        for i, (label_text, default_val, attr_name) in enumerate(k_fields, start=1):
            lbl = ctk.CTkLabel(keysight_frame, text="", font=ctk.CTkFont(size=11))
            lbl.grid(row=i, column=0, sticky="w", padx=15, pady=6)
            setattr(self, f"lbl_{attr_name}", lbl)
            
            entry = ctk.CTkEntry(keysight_frame, width=110, height=28)
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, padx=15, pady=6, sticky="e")
            setattr(self, attr_name, entry)

        self.apply_btn = ctk.CTkButton(keysight_frame, text="", height=32, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.validate_keysight_metrics)
        self.apply_btn.grid(row=4, column=0, columnspan=2, pady=(12, 5), padx=15, sticky="we")


        # Module 1B: Monochromator Filterwheel Setup
        mono_frame = ctk.CTkFrame(col1)
        mono_frame.pack(fill=tk.X, expand=False, pady=(0, 15))

        self.mono_frame_lbl = ctk.CTkLabel(mono_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=35, corner_radius=6, text_color="#38bdf8")
        self.mono_frame_lbl.pack(fill=tk.X, padx=15, pady=(10, 5))

        self.mode_var = tk.StringVar(value="manual")
        
        self.rb1 = ctk.CTkRadioButton(mono_frame, text="", variable=self.mode_var, value="manual", font=ctk.CTkFont(weight="bold", size=11))
        self.rb1.pack(anchor="w", padx=15, pady=(10, 5))
        
        self.entry_manual = ctk.CTkEntry(mono_frame, height=28)
        self.entry_manual.insert(0, "300, 350, 400, 450, 500, 550")
        self.entry_manual.pack(fill=tk.X, padx=25, pady=(0, 10))

        self.rb2 = ctk.CTkRadioButton(mono_frame, text="", variable=self.mode_var, value="range", font=ctk.CTkFont(weight="bold", size=11))
        self.rb2.pack(anchor="w", padx=15, pady=5)
        
        range_sub = ctk.CTkFrame(mono_frame, fg_color="transparent")
        range_sub.pack(anchor="w", padx=25, pady=(0, 10))
        
        self.lbl_start = ctk.CTkLabel(range_sub, text="", font=ctk.CTkFont(size=10))
        self.lbl_start.grid(row=0, column=0, padx=2)
        self.entry_start = ctk.CTkEntry(range_sub, width=50, height=25); self.entry_start.insert(0, "240"); self.entry_start.grid(row=0, column=1, padx=4)
        
        self.lbl_end = ctk.CTkLabel(range_sub, text="", font=ctk.CTkFont(size=10))
        self.lbl_end.grid(row=0, column=2, padx=2)
        self.entry_end = ctk.CTkEntry(range_sub, width=50, height=25); self.entry_end.insert(0, "650"); self.entry_end.grid(row=0, column=3, padx=4)
        
        self.lbl_step = ctk.CTkLabel(range_sub, text="", font=ctk.CTkFont(size=10))
        self.lbl_step.grid(row=0, column=4, padx=2)
        self.entry_step = ctk.CTkEntry(range_sub, width=45, height=25); self.entry_step.insert(0, "20"); self.entry_step.grid(row=0, column=5, padx=4)

        self.rb3 = ctk.CTkRadioButton(mono_frame, text="", variable=self.mode_var, value="file", font=ctk.CTkFont(weight="bold", size=11))
        self.rb3.pack(anchor="w", padx=15, pady=5)
        
        file_sub = ctk.CTkFrame(mono_frame, fg_color="transparent")
        file_sub.pack(anchor="w", padx=25, pady=(0, 12))
        
        self.browse_btn = ctk.CTkButton(file_sub, text="", width=85, height=25, font=ctk.CTkFont(size=11), command=self.browse_flat_file)
        self.browse_btn.grid(row=0, column=0)
        
        self.lbl_filename = ctk.CTkLabel(file_sub, text="scan_wavelengths_aerogels.txt", font=ctk.CTkFont(size=10, slant="italic"), text_color="#94a3b8")
        self.lbl_filename.grid(row=0, column=1, padx=8)

        self.load_btn = ctk.CTkButton(mono_frame, text="", height=30, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.process_wavelengths_queue)
        self.load_btn.pack(fill=tk.X, padx=15, pady=5)
        
        self.txt_mono_preview = ctk.CTkTextbox(mono_frame, font=("sans-serif", 11), fg_color="#1e293b", height=80)
        self.txt_mono_preview.pack(fill=tk.X, expand=False, padx=15, pady=(5, 15))


        # =========================================================================
        # COLUMN 2: GRAPH PANEL (MIDDLE)
        # =========================================================================
        col2 = ctk.CTkFrame(workspace, fg_color="transparent")
        col2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=15)

        graphs_container = ctk.CTkFrame(col2, fg_color="transparent")
        graphs_container.pack(fill=tk.BOTH, expand=True)

        # Embedded Left Chart: Kinematic Stage Vector Nodes Path Mapping Box
        stage_box = ctk.CTkFrame(graphs_container)
        stage_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        
        self.stage_box_lbl = ctk.CTkLabel(stage_box, text="", font=ctk.CTkFont(weight="bold", size=15), fg_color="#334155", height=35, corner_radius=6, text_color="#f3faf9")
        self.stage_box_lbl.pack(fill=tk.X, padx=15, pady=(10, 0))
        
        self.fig_stage, self.ax_stage = plt.subplots(figsize=(5, 5), facecolor='#2a2d32')
        self.canvas_stage = FigureCanvasTkAgg(self.fig_stage, master=stage_box)
        self.canvas_stage.get_tk_widget().pack(fill=tk.NONE, expand=True, padx=10, pady=10)

        # Embedded Right Chart: Spectrograph Real-Time Processing Curve Plotter Box 
        spectro_box = ctk.CTkFrame(graphs_container)
        spectro_box.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(8, 0))
        
        self.spectro_box_lbl = ctk.CTkLabel(spectro_box, text="", font=ctk.CTkFont(weight="bold", size=15), fg_color="#334155", height=35, corner_radius=6, text_color="#f3faf9")
        self.spectro_box_lbl.pack(fill=tk.X, padx=15, pady=(10, 0))
        
        self.fig_spec, self.ax_spec = plt.subplots(figsize=(5, 5), facecolor='#2a2d32')
        self.canvas_spec = FigureCanvasTkAgg(self.fig_spec, master=spectro_box)
        self.canvas_spec.get_tk_widget().pack(fill=tk.NONE, expand=True, padx=10, pady=10)


        # =========================================================================
        # COLUMN 3: PARAMETERS, ESTIMATORS & LOGS PANEL (RIGHT)
        # =========================================================================
        col3 = ctk.CTkFrame(workspace, fg_color="transparent", width=360)
        col3.pack(side=tk.RIGHT, fill=tk.Y, anchor="n", expand=False, padx=(15, 0))

        # Session Pre-Run Metrics Estimation Frame
        estimator_frame = ctk.CTkFrame(col3)
        estimator_frame.pack(fill=tk.X, expand=False, pady=(0, 15))

        self.estimator_frame_lbl = ctk.CTkLabel(estimator_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=35, corner_radius=6, text_color="#38bdf8")
        self.estimator_frame_lbl.pack(fill=tk.X, padx=15, pady=(10, 5))
        
        self.calc_btn = ctk.CTkButton(estimator_frame, text="", height=32, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.compute_session_estimations)
        self.calc_btn.pack(fill=tk.X, padx=15, pady=(12, 8))
        
        self.txt_estimator_summary = ctk.CTkTextbox(estimator_frame, font=("Courier New", 11), fg_color="#1e293b", height=120)
        self.txt_estimator_summary.pack(fill=tk.X, expand=False, padx=15, pady=(0, 15))


        # Live Process Progress Monitor Progress Bar View Status Panel
        monitor_frame = ctk.CTkFrame(col3)
        monitor_frame.pack(fill=tk.BOTH, expand=True, ipady=5)
        
        self.monitor_frame_lbl = ctk.CTkLabel(monitor_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=35, corner_radius=6, text_color="#38bdf8")
        self.monitor_frame_lbl.pack(fill=tk.X, padx=15, pady=(10, 0))

        self.lbl_watch_wl = ctk.CTkLabel(monitor_frame, text="", font=ctk.CTkFont(weight="bold", size=12), fg_color="#334155", height=35, corner_radius=6, text_color="#e1f3fa")
        self.lbl_watch_wl.pack(fill=tk.X, padx=15, pady=(10, 6))

        self.lbl_watch_node = ctk.CTkLabel(monitor_frame, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.lbl_watch_node.pack(fill=tk.X, padx=15, pady=2)

        self.progress_bar = ctk.CTkProgressBar(monitor_frame, height=12, corner_radius=4)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill=tk.X, padx=15, pady=(2, 10))

        self.txt_terminal_log = ctk.CTkTextbox(monitor_frame, font=("Courier New", 11), fg_color="#090d16", text_color="#38bdf8", height=250)
        self.txt_terminal_log.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        
        
        # Master Launcher Automation Pipeline Execution Trigger Button
        self.btn_master_launch = ctk.CTkButton(
            col3, 
            text="", 
            height=45, 
            font=ctk.CTkFont(weight="bold", size=12), 
            fg_color="#dc2626", 
            hover_color="#b91c1c",
            command=self.trigger_master_experiment_pipeline
        )
        self.btn_master_launch.pack(fill=tk.X, pady=(0, 15))

        # Initial layout initialization setups
        self.apply_translations()
        self.reset_all_plots_canvas()
        self.process_wavelengths_queue()
        self.compute_session_estimations()

    def t(self, key, **kwargs):
        text = TRANSLATIONS[self.lang].get(key, key)
        return text.format(**kwargs) if kwargs else text

    def change_language(self, selected_lang):
        self.lang = selected_lang
        self.apply_translations()
        self.update_stage_plot()
        self.process_wavelengths_queue()
        self.compute_session_estimations()

    def apply_translations(self):
        self.root.title(self.t("win_title"))
        self.title_lbl.configure(text=self.t("banner_title"))
        self.grid_frame_lbl.configure(text=self.t("grid_title"))
        self.lbl_entry_x0.configure(text=self.t("x0"))
        self.lbl_entry_y0.configure(text=self.t("y0"))
        self.lbl_entry_length.configure(text=self.t("length"))
        self.lbl_entry_width.configure(text=self.t("width"))
        self.lbl_entry_points.configure(text=self.t("density"))
        self.grid_btn.configure(text=self.t("btn_draw_map"))
        self.keysight_frame_lbl.configure(text=self.t("keysight_title"))
        self.lbl_entry_nmeas.configure(text=self.t("n_meas"))
        self.lbl_entry_delta_t.configure(text=self.t("delta_t"))
        self.lbl_entry_stabilize.configure(text=self.t("settle"))
        self.apply_btn.configure(text=self.t("btn_apply_bus"))
        self.mono_frame_lbl.configure(text=self.t("mono_title"))
        self.rb1.configure(text=self.t("rb_manual"))
        self.rb2.configure(text=self.t("rb_range"))
        self.rb3.configure(text=self.t("rb_file"))
        self.browse_btn.configure(text=self.t("btn_browse"))
        self.load_btn.configure(text=self.t("btn_load"))
        self.stage_box_lbl.configure(text=self.t("stage_box_title"))
        self.spectro_box_lbl.configure(text=self.t("spec_box_title"))
        self.estimator_frame_lbl.configure(text=self.t("est_title"))
        self.calc_btn.configure(text=self.t("btn_recompute"))
        self.monitor_frame_lbl.configure(text=self.t("mon_title"))
        if not self.is_scanning:
            self.lbl_watch_wl.configure(text=self.t("status_standby"))
            self.lbl_watch_node.configure(text=self.t("node_ready"))
            self.btn_master_launch.configure(text=self.t("btn_launch"))
        else:
            self.btn_master_launch.configure(text=self.t("btn_abort"))

            
    def reset_all_plots_canvas(self):
        # Resets both plotting graph targets into a modern matte dark-mode theme look.
        self.ax_stage.clear()
        self.ax_stage.set_facecolor('#1e1e24')
        self.ax_stage.tick_params(colors='white', labelsize=8)
        self.ax_stage.set_xlim(-15, self.MAX_TRAVEL_MM + 15)
        self.ax_stage.set_ylim(-15, self.MAX_TRAVEL_MM + 15)
        self.ax_stage.grid(True, linestyle=":", alpha=0.3, color='gray')
        self.fig_stage.tight_layout()
        self.canvas_stage.draw()


        self.ax_spec.clear()
        self.ax_spec.set_facecolor('#1e1e24')
        self.ax_spec.tick_params(colors='white', labelsize=8)
        self.ax_spec.set_xlim(200, 750)
        self.ax_spec.set_ylim(-0.05, 1.05)
        self.ax_spec.set_xlabel(self.t("spec_xlabel"), fontsize=8, color='white', fontweight='bold')
        self.ax_spec.set_ylabel(self.t("spec_ylabel"), fontsize=8, color='white', fontweight='bold')
        self.ax_spec.grid(True, linestyle=":", alpha=0.3, color='gray')
        self.fig_spec.tight_layout()
        self.canvas_spec.draw()

        try:
            x0 = float(self.entry_x0.get())
            num_points = int(self.entry_points.get())
            if num_points > 0:
                self.root.after(10, self.update_stage_plot)
        except (AttributeError, ValueError):
            pass

    def generate_grid_nodes_array(self, x0, y0, len_x_mm, len_y_mm, num_points):
        #Generates raster array layout mapping trajectory pathways coordinates.
        margin_start, margin_end = 15.0, 15.0
        x_offsets = [margin_start + ((len_x_mm - margin_end - margin_start) / (num_points - 1)) * i for i in range(num_points)]
        y_offsets = [margin_start + ((len_y_mm - margin_end - margin_start) / (num_points - 1)) * i for i in range(num_points)]
        points = []
        for i, x_off in enumerate(x_offsets):
            current_y_offsets = y_offsets[::-1] if i % 2 != 0 else y_offsets
            for y_off in current_y_offsets:
                points.append((x0 + x_off, y0 + y_off))
        return points

    def update_stage_plot(self):
        #Validates bounding fields inputs envelopes parameters boundaries templates.
        try:
            x0, y0 = float(self.entry_x0.get()), float(self.entry_y0.get())
            len_x_mm, len_y_mm = float(self.entry_length.get()) * 10.0, float(self.entry_width.get()) * 10.0
            num_points = int(self.entry_points.get())

            grid_points = self.generate_grid_nodes_array(x0, y0, len_x_mm, len_y_mm, num_points)
            if any(x > self.MAX_TRAVEL_MM or y > self.MAX_TRAVEL_MM or x < 0 or y < 0 for x, y in grid_points):
                messagebox.showerror(self.t("msg_env_warn_title"), self.t("msg_env_warn"))
                return

            self.ax_stage.clear()
            self.ax_stage.set_facecolor('#1e1e24')
            self.ax_stage.tick_params(colors='white', labelsize=8)
            self.ax_stage.set_xlim(-15, self.MAX_TRAVEL_MM + 15)
            self.ax_stage.set_ylim(-15, self.MAX_TRAVEL_MM + 15)
            self.ax_stage.grid(True, linestyle=':', alpha=0.3, color='gray')
            self.ax_stage.set_title(self.t("stage_plot_title"), fontsize=9, fontweight="bold", color='#38bdf8')

            self.ax_stage.add_patch(plt.Rectangle((x0, y0), len_x_mm, len_y_mm, fill=True, facecolor="#065f46", edgecolor="#10b981", alpha=0.4))
            self.ax_stage.add_patch(plt.Rectangle((0, 0), self.MAX_TRAVEL_MM, self.MAX_TRAVEL_MM, fill=False, edgecolor="#ef4444", linestyle="--", linewidth=1.2))

            if grid_points:
                pts = np.array(grid_points)
                self.ax_stage.plot(pts[:, 0], pts[:, 1], color="#38bdf8", linestyle="-", linewidth=1.2)
                self.ax_stage.scatter(pts[:, 0], pts[:, 1], color="#ffffff", s=18, zorder=5)
                self.ax_stage.scatter(pts[:, 0], pts[:, 1], color="#f59e0b", s=50, edgecolors='black', zorder=6)

            self.fig_stage.tight_layout()
            self.canvas_stage.draw()
            self.compute_session_estimations()
        except ValueError:
            pass

    def browse_flat_file(self):
        #Loads path directories locations via dynamic OS fileDialog window systems.
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if file_path:
            self.selected_file_path = file_path
            self.lbl_filename.configure(text=os.path.basename(file_path), text_color="white")
            self.mode_var.set("file")

    def process_wavelengths_queue(self):
        #Parses configurations entries into specific array pipelines indexes vectors.
        mode = self.mode_var.get()
        try:
            if mode == "manual":
                self.wavelengths_list = [float(x.strip()) for x in self.entry_manual.get().split(",") if x.strip()]
            elif mode == "range":
                start, end, step = float(self.entry_start.get()), float(self.entry_end.get()), float(self.entry_step.get())
                if step <= 0:
                    raise ValueError("Step must be positive.")
                self.wavelengths_list = [round(x, 2) for x in list(np.arange(start, end + 0.1, step))]
            elif mode == "file":
                if not os.path.exists(self.selected_file_path):
                    self.wavelengths_list = [450.0, 550.0, 650.0]
                else:
                    self.wavelengths_list = []
                    with open(self.selected_file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            clean = line.strip()
                            if not clean or clean.startswith("#"):
                                continue
                            try:
                                self.wavelengths_list.append(float(clean))
                            except:
                                pass

            self.wavelengths_list = [wl for wl in self.wavelengths_list if 240.0 <= wl <= 700.0]

            self.txt_mono_preview.delete("1.0", tk.END)
            self.txt_mono_preview.insert(tk.END, self.t("channels_loaded", count=len(self.wavelengths_list), arr=self.wavelengths_list))
            self.compute_session_estimations()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def validate_keysight_metrics(self):
        #Commits system configurations memory configurations variables arrays.
        try:
            self.num_measurements = int(self.entry_nmeas.get())
            self.delay_between_reads = float(self.entry_delta_t.get())
            self.stabilization_delay = float(self.entry_stabilize.get())
            if self.num_measurements <= 0 or self.delay_between_reads < 0 or self.stabilization_delay < 0:
                raise ValueError()
            messagebox.showinfo(self.t("msg_success_title"), self.t("msg_success"))
            self.compute_session_estimations()
        except:
            messagebox.showerror(self.t("msg_val_err_title"), self.t("msg_val_err"))

    def compute_session_estimations(self):
        #Pre-calculates theoretical matrix scan run times statistics models profiles.
        try:
            density = int(self.entry_points.get())
            wl_count = len(self.wavelengths_list)
            total_pts = density * density
            node_time = (self.num_measurements * self.delay_between_reads) + self.stabilization_delay
            total_sec = (total_pts * wl_count * node_time) + (wl_count * 5.0)

            h, m, s = int(total_sec // 3600), int((total_sec % 3600) // 60), int(total_sec % 60)

            self.txt_estimator_summary.delete("1.0", tk.END)
            self.txt_estimator_summary.insert(
                tk.END,
                self.t("est_summary", pts=total_pts, wl=wl_count, nt=node_time, vec=total_pts * wl_count, h=h, m=m, s=s)
            )
        except:
            pass

    def trigger_master_experiment_pipeline(self):
        #Asynchronously triggers active worker execution tracking thread matrices safety loops.
        if not self.is_scanning:
            self.is_scanning = True
            self.last_plotted_wl = []
            self.last_plotted_t = []
            self.btn_master_launch.configure(text=self.t("btn_abort"), fg_color="#b91c1c", hover_color="#991b1b")
            self.txt_terminal_log.delete("1.0", tk.END)
            self.reset_all_plots_canvas()

            self.scan_thread = threading.Thread(target=self.integrated_hardware_loop_worker)
            self.scan_thread.daemon = True
            self.scan_thread.start()
        else:
            self.is_scanning = False

    def integrated_hardware_loop_worker(self):
        #Simulates actual live process logging telemetry streams loop parameters indexes.
        x0, y0 = float(self.entry_x0.get()), float(self.entry_y0.get())
        len_x_mm = float(self.entry_length.get()) * 10.0
        len_y_mm = float(self.entry_width.get()) * 10.0
        num_points = int(self.entry_points.get())
        grid_nodes = self.generate_grid_nodes_array(x0, y0, len_x_mm, len_y_mm, num_points)

        total_steps = len(self.wavelengths_list) * len(grid_nodes)
        step_counter = 0

        plotted_wl, plotted_transmittance = [], []
        i_dark, i_0 = 1.0e-11, 5.5e-09

        self.append_terminal_msg(self.t("log_init"))

        for wl in self.wavelengths_list:
            if not self.is_scanning:
                break
            self.root.after(0, lambda w=wl: self.lbl_watch_wl.configure(text=self.t("status_running", w=w), text_color="#f59e0b"))
            self.append_terminal_msg(self.t("log_wl", wl=wl))
            time.sleep(1.0)

            cumulative_nodes_t_ratios = []

            for idx, (x, y) in enumerate(grid_nodes, 1):
                if not self.is_scanning:
                    break
                step_counter += 1
                pct = (step_counter / total_steps)

                self.root.after(0, lambda i=idx, tot=len(grid_nodes): self.lbl_watch_node.configure(text=self.t("node_proc", i=i, t=tot)))
                self.root.after(0, lambda p=pct: self.progress_bar.set(p))

                self.append_terminal_msg(self.t("log_node", wl=wl, idx=idx, tot=len(grid_nodes), x=x, y=y))

                base_curve_t = 1.0 / (1.0 + np.exp(-(wl - 360.0) / 45.0))
                mock_current = i_dark + (base_curve_t * (i_0 - i_dark)) + np.random.normal(0, 1.5e-11)

                t_ratio = (mock_current - i_dark) / (i_0 - i_dark)
                cumulative_nodes_t_ratios.append(t_ratio)

                time.sleep(self.delay_between_reads * self.num_measurements + 0.1)

            if self.is_scanning:
                mean_transmittance_channel = sum(cumulative_nodes_t_ratios) / len(cumulative_nodes_t_ratios)
                plotted_wl.append(wl)
                plotted_transmittance.append(mean_transmittance_channel)
                self.last_plotted_wl = list(plotted_wl)
                self.last_plotted_t = list(plotted_transmittance)

                self.root.after(0, lambda w=list(plotted_wl), t=list(plotted_transmittance): self.render_live_spectrogram_curve(w, t))

        self.is_scanning = False
        self.root.after(0, lambda: self.btn_master_launch.configure(text=self.t("btn_launch"), fg_color="#dc2626", hover_color="#b91c1c"))
        if step_counter == total_steps:
            self.root.after(0, lambda: self.lbl_watch_wl.configure(text=self.t("status_done"), text_color="#10b981"))
            self.append_terminal_msg(self.t("log_done"))
        else:
            self.root.after(0, lambda: self.lbl_watch_wl.configure(text=self.t("status_aborted"), text_color="#ef4444"))
            self.append_terminal_msg(self.t("log_abort"))

    def render_live_spectrogram_curve(self, wl_arr, t_arr):
        if not plt.fignum_exists(self.fig_spec.number):
            return
        self.ax_spec.clear()
        self.ax_spec.set_facecolor('#1e1e24')
        self.ax_spec.tick_params(colors='white', labelsize=8)
        self.ax_spec.set_xlabel(self.t("spec_xlabel"), fontsize=8, fontweight="bold", color='white')
        self.ax_spec.set_ylabel(self.t("spec_ylabel"), fontsize=8, fontweight="bold", color='white')
        self.ax_spec.grid(True, linestyle=":", alpha=0.3, color='gray')
        self.ax_spec.set_title(self.t("spec_plot_title"), fontsize=9, fontweight="bold", color='#2dd4bf')

        self.ax_spec.plot(wl_arr, t_arr, color="#0ea5e9", linestyle="-", linewidth=2.5, label=self.t("spec_legend_main"))
        self.ax_spec.scatter(wl_arr, t_arr, color="#ffffff", s=25, zorder=5)
        if wl_arr:
            self.ax_spec.scatter(wl_arr[-1], t_arr[-1], color="#ef4444", s=60, edgecolors="white", zorder=6, label=self.t("spec_legend_node"))

        leg = self.ax_spec.legend(loc="upper left", fontsize=8)
        leg.get_frame().set_facecolor('#2a2d32')
        leg.get_frame().set_edgecolor('none')
        for text in leg.get_texts():
            text.set_color('white')

        self.fig_spec.tight_layout()
        self.canvas_spec.draw()

    def append_terminal_msg(self, text):
        self.root.after(0, lambda: self.txt_terminal_log.insert(tk.END, text + "\n"))
        self.root.after(0, lambda: self.txt_terminal_log.see(tk.END))


if __name__ == "__main__":
    main_window_root = ctk.CTk()
    dashboard_app = UnifiedSpectroStationDashboard(main_window_root)
    main_window_root.mainloop()
