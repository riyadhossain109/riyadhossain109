import os
import sys
import time
import math
import threading
import warnings
from datetime import datetime
from ctypes import CDLL, c_bool, c_int

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from PIL import Image, ImageDraw
import pyvisa

try:
    from pylablib.devices import Thorlabs
except Exception as e:
    print(f"[❌ IMPORT] Error loading pylablib: {e}")

warnings.filterwarnings("ignore", category=UserWarning)

import ctypes

# Force Windows native LoadLibrary to search Keysight & IVI folders inside frozen .exe
_VISA_DIRS = [
    r"C:\Program Files\Keysight\IO Libraries Suite\bin",
    r"C:\Program Files\IVI Foundation\VISA\Win64\Bin",
    r"C:\Program Files\IVI Foundation\VISA\Win64\ktvisa",
    r"C:\Program Files (x86)\Keysight\IO Libraries Suite\bin",
    r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\Bin",
    r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\ktvisa",
]

for _vdir in _VISA_DIRS:
    if os.path.exists(_vdir):
        os.environ["PATH"] = _vdir + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_vdir)
            except Exception:
                pass

# SetDllDirectoryW restores standard Windows sub-DLL resolution for visa64/ktvisa32
try:
    if os.path.exists(r"C:\Program Files\IVI Foundation\VISA\Win64\Bin"):
        ctypes.windll.kernel32.SetDllDirectoryW(r"C:\Program Files\IVI Foundation\VISA\Win64\Bin")
    elif os.path.exists(r"C:\Program Files\Keysight\IO Libraries Suite\bin"):
        ctypes.windll.kernel32.SetDllDirectoryW(r"C:\Program Files\Keysight\IO Libraries Suite\bin")
except Exception:
    pass


def get_visa_rm():
    errors = []
    # Check 64-bit vs 32-bit Python
    import struct
    arch = struct.calcsize("P") * 8
    
    candidates = [
        "@ivi",
        r"C:\Windows\System32\visa64.dll",
        r"C:\Windows\System32\ktvisa32.dll",
        r"C:\Program Files\IVI Foundation\VISA\Win64\Bin\visa64.dll",
        r"C:\Program Files\IVI Foundation\VISA\Win64\Bin\ktvisa32.dll",
        r"C:\Program Files\Keysight\IO Libraries Suite\bin\ktvisa32.dll",
    ]
    for backend in candidates:
        if not backend.startswith("@") and not os.path.exists(backend):
            errors.append(f"{backend} (NOT FOUND)")
            continue
        try:
            rm = pyvisa.ResourceManager(backend)
            res = rm.list_resources()
            if res:
                return rm
            errors.append(f"{backend} loaded but 0 resources found")
            rm.close()
        except Exception as e:
            errors.append(f"{backend} -> {type(e).__name__}: {e}")
    raise RuntimeError(f"[Python {arch}-bit] " + " | ".join(errors))





# =========================================================================
# HARDWARE CONSTANTS & ADDRESSES
# =========================================================================

VISA_ADDRESS = 'USB0::0x2A8D::0xBA01::MY61390232::0::INSTR'
DEFAULT_MAX_VOLTAGE = 200.0

HORIZONTAL_STAGE_SN = "45530624"
VERTICAL_STAGE_SN = "45529014"
STEPS_PER_MM = 409600.0
MAX_TRAVEL_MM = 300.0

ACCEL_STEPS = 115000
DEVICE_UNIT_PER_MM_S = 21987328
HOMING_SPEED_STEPS = 5 * DEVICE_UNIT_PER_MM_S
SCAN_SPEED_STEPS = 10 * DEVICE_UNIT_PER_MM_S

DLL_DIR = r"C:\Users\Ladmin\Documents\dark-box_thorlabs_ms3504i\_docs\MS3504i_Files"
DLL_PATH = os.path.join(DLL_DIR, "devctrl.dll")

CALIBRATION_TABLE = [
    (18592, 240.0), (20937, 270.0), (22505, 290.0), (24076, 310.0),
    (25651, 330.0), (27231, 350.0), (29605, 380.0), (30398, 390.0),
    (31987, 410.0), (35178, 450.0), (39213, 500.0), (43285, 550.0),
    (47390, 600.0), (50719, 640.0), (51556, 650.0), (55785, 700.0)
]

if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()

def resource_path(relative_path):
    """Get absolute path to bundled assets inside PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(SCRIPT_DIR, relative_path)

FINISH_MP3_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "_docs", "finish_signal_short.mp3"))

FINISH_START_SEC = 0.0

bus_lock = threading.Lock()
global_devctrl = None
current_active_filter = None

# =========================================================================
# TRANSLATION DICTIONARY (EN / RU)
# =========================================================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

TRANSLATIONS = {
    "EN": {
        "win_title": "Master Spectro-Aerogel Station Autonomous Cockpit",
        "banner_title": "AEROGEL MASTER SPECTRAL SCANNER MAIN CONTROL STATION",
        "hw_title": " Hardware Control & Connection ",
        "btn_connect_hw": "Connect All Hardware",
        "btn_home_stages": "Home X/Y Stages",
        "volt_lbl": "Bias Voltage (V):",
        "btn_volt_on": "Apply V",
        "btn_volt_off": "OFF",
        "sample_lbl": "Sample Name:",
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
        "msg_success_title": "Success", "msg_success": "Parameters updated successfully.",
        "msg_val_err_title": "Validation Error", "msg_val_err": "Check values compatibility formats.",
        "log_init": "== INITIALIZING INTEGRATED SCAN MATRIX EXPERIMENT RUN MAP ==",
        "log_wl": "\n🔮 [WAVELENGTH STEP] Tuning Monochromator to: {wl} nm...",
        "log_node": "📍 [{wl}nm] Node {idx}/{tot} -> X={x:.1f}, Y={y:.1f} | I={curr:.4e} A",
        "log_done": "\n🎉 [FINISHED] Scan finalized and saved to disk.",
        "log_abort": "\n⚠️ [ABORTED] Execution halted by operator. Parking stage..."
    },
    "RU": {
        "win_title": "Автономная станция спектроскопии аэрогелей",
        "banner_title": "ГЛАВНАЯ СТАНЦИЯ УПРАВЛЕНИЯ СПЕКТРАЛЬНЫМ СКАНЕРОМ АЭРОГЕЛЕЙ",
        "hw_title": " Управление оборудованием и связь ",
        "btn_connect_hw": "Подключить приборы",
        "btn_home_stages": "Калибровка осей (Home)",
        "volt_lbl": "Напряжение (В):",
        "btn_volt_on": "Подать V",
        "btn_volt_off": "ВЫКЛ",
        "sample_lbl": "Имя образца:",
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
        "msg_success_title": "Успешно", "msg_success": "Параметры успешно применены.",
        "msg_val_err_title": "Ошибка проверки", "msg_val_err": "Проверьте правильность введенных числовых форматов.",
        "log_init": "== ИНИЦИАЛИЗАЦИЯ МАТРИЧНОГО СКАНИРОВАНИЯ ЭКСПЕРИМЕНТА ==",
        "log_wl": "\n🔮 [ШАГ ДЛИНЫ ВОЛНЫ] Настройка монохроматора на: {wl} нм...",
        "log_node": "📍 [{wl}нм] Узел {idx}/{tot} -> X={x:.1f}, Y={y:.1f} | I={curr:.4e} А",
        "log_done": "\n🎉 [ЗАВЕРШЕНО] Сканирование завершено и сохранено на диск.",
        "log_abort": "\n⚠️ [ПРЕРВАНО] Выполнение остановлено. Парковка стола..."
    }
}

# =========================================================================
# HARDWARE & MATH HELPER FUNCTIONS
# =========================================================================
def create_session_log(message):
    try:
        parent_dir = os.path.dirname(SCRIPT_DIR)
        log_dir = os.path.join(parent_dir, "_logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "spectro_session.log")
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass

def play_finish_signal():
    if not os.path.exists(FINISH_MP3_PATH):
        return
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(FINISH_MP3_PATH)
        pygame.mixer.music.play(start=FINISH_START_SEC)
    except Exception:
        pass

def stop_finish_signal():
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()
    except Exception:
        pass

def wl_to_steps(target_wl):
    target_wl = max(240.0, min(700.0, target_wl))
    for i in range(len(CALIBRATION_TABLE) - 1):
        steps_a, wl_a = CALIBRATION_TABLE[i]
        steps_b, wl_b = CALIBRATION_TABLE[i + 1]
        if wl_a <= target_wl <= wl_b:
            fraction = (target_wl - wl_a) / (wl_b - wl_a)
            return int(round(steps_a + fraction * (steps_b - steps_a)))
    return CALIBRATION_TABLE[0][0]

def get_filter_for_wl(wl):
    if wl < 390.0:
        return 1
    elif 390.0 <= wl <= 640.0:
        return 2
    return 3

def mono_wait_for_device(timeout=20.0):
    start_time = time.time()
    while True:
        with bus_lock:
            if global_devctrl and global_devctrl.IsOperationFinished():
                return True
        if (time.time() - start_time) > timeout:
            return False
        time.sleep(0.1)

def mono_connect():
    global global_devctrl
    with bus_lock:
        try:
            orig_cwd = os.getcwd()
            if not os.path.exists(DLL_DIR):
                return False
            os.chdir(DLL_DIR)
            if sys.version_info >= (3, 8):
                os.add_dll_directory(DLL_DIR)
            global_devctrl = CDLL(DLL_PATH)
            global_devctrl.InitDevice.restype = c_bool
            global_devctrl.CheckConnection.restype = c_bool
            global_devctrl.SetFilterControl.argtypes = [c_int]
            global_devctrl.SetFilterControl.restype = c_bool
            global_devctrl.SetPermissionMessageBox.argtypes = [c_bool]
            global_devctrl.IsOperationFinished.restype = c_bool
            global_devctrl.GetDeviceCurrentStepPosition.argtypes = [c_int]
            global_devctrl.GetDeviceCurrentStepPosition.restype = c_int
            global_devctrl.MoveBySteps.argtypes = [c_int, c_int]
            global_devctrl.MoveBySteps.restype = c_bool
            global_devctrl.SetFilter.argtypes = [c_int]
            global_devctrl.SetFilter.restype = c_bool
            global_devctrl.OpenShutter.argtypes = [c_int]
            global_devctrl.OpenShutter.restype = c_bool
            global_devctrl.CloseShutter.argtypes = [c_int]
            global_devctrl.CloseShutter.restype = c_bool
            global_devctrl.FreeDevice.restype = None

            if not global_devctrl.InitDevice() or not global_devctrl.CheckConnection():
                try:
                    global_devctrl.FreeDevice()
                except Exception:
                    pass
                global_devctrl = None
                os.chdir(orig_cwd)
                return False
            global_devctrl.SetPermissionMessageBox(False)
            global_devctrl.SetFilterControl(0)
            os.chdir(orig_cwd)
            return True
        except Exception:
            global_devctrl = None
            return False

def mono_set_wavelength(target_wl):
    global current_active_filter
    req_filter = get_filter_for_wl(target_wl)
    need_filter_change = False
    with bus_lock:
        if not global_devctrl:
            return False
        if req_filter != current_active_filter:
            need_filter_change = True
            global_devctrl.SetFilter(req_filter)
    if need_filter_change:
        mono_wait_for_device()
        current_active_filter = req_filter

    with bus_lock:
        curr_steps = global_devctrl.GetDeviceCurrentStepPosition(4)
        target_steps = wl_to_steps(target_wl)
        delta = target_steps - curr_steps
        if delta == 0:
            global_devctrl.MoveBySteps(4, 10)
    if delta == 0:
        mono_wait_for_device()
        with bus_lock:
            curr_steps = global_devctrl.GetDeviceCurrentStepPosition(4)
            delta = target_steps - curr_steps

    with bus_lock:
        success = global_devctrl.MoveBySteps(4, delta)
    if success:
        mono_wait_for_device()
        return True
    return False

def mono_shutter(open_shutter=True):
    with bus_lock:
        if not global_devctrl:
            return
        if open_shutter:
            global_devctrl.OpenShutter(1)
        else:
            global_devctrl.CloseShutter(1)
    if not open_shutter:
        mono_wait_for_device()

def keysight_set_voltage(voltage_val):
    try:
        volt_float = float(voltage_val)
        abs_volt = abs(volt_float)
    except ValueError:
        return False, "Invalid number"
    if abs_volt > DEFAULT_MAX_VOLTAGE:
        return False, f"Exceeds safety limit ({DEFAULT_MAX_VOLTAGE} V)"
    with bus_lock:
        rm = device = None
        try:
            rm = get_visa_rm()
            device = rm.open_resource(VISA_ADDRESS)
            device.timeout = 5000
            device.write("*CLS")
            range_cmd = "20" if abs_volt <= 21.0 else ("1000" if volt_float > 21.0 else "-1000")
            device.write(f":SOUR:VOLT:RANG {range_cmd}")
            device.write(f":SOUR:VOLT:LEV {volt_float}")
            device.write(":OUTP:STAT ON")
            device.write(":SENS:FUNC 'CURR'")
            device.write(":SENS:CURR:RANG:AUTO ON")
            device.write(":INP:STAT ON")
            device.control_ren(6)
            return True, f"{volt_float} V"
        except Exception as e:
            return False, str(e)
        finally:
            if device:
                try: device.close()
                except Exception: pass
            if rm:
                try: rm.close()
                except Exception: pass

def keysight_disable():
    with bus_lock:
        rm = device = None
        try:
            rm = get_visa_rm()
            device = rm.open_resource(VISA_ADDRESS)
            device.timeout = 5000
            device.write(":SOUR:VOLT:LEV 0")
            device.write(":OUTP:STAT OFF")
            device.write(":INP:STAT OFF")
            device.control_ren(6)
            return True
        except Exception:
            return False
        finally:
            if device:
                try: device.close()
                except Exception: pass
            if rm:
                try: rm.close()
                except Exception: pass

def keysight_check_status():
    with bus_lock:
        rm = device = None
        try:
            rm = get_visa_rm()
            device = rm.open_resource(VISA_ADDRESS)
            device.timeout = 500
            output_state = device.query(":OUTP:STAT?").strip()
            volt_level = float(device.query(":SOUR:VOLT:LEV?").strip())
            device.control_ren(6)
            return (output_state == "1" or output_state.upper() == "ON"), volt_level
        except Exception:
            return False, 0.0
        finally:
            if device:
                try: device.close()
                except Exception: pass
            if rm:
                try: rm.close()
                except Exception: pass

def safe_query_curr(device):
    last_err = None
    for _ in range(2):
        try:
            res = device.query(":MEAS:CURR?").split(',')[0]
            return float(res)
        except Exception as e:
            last_err = e
            msg = str(e)
            if any(k in msg for k in ["-410", "Query INTERRUPTED", "timeout", "VI_ERROR"]):
                try:
                    device.clear()
                except Exception:
                    pass
                time.sleep(0.05)
                continue
            raise
    raise RuntimeError(f"Keysight read failed: {last_err}")

def calculate_stats(data):
    n = len(data)
    if n == 0:
        return float('nan'), float('nan')
    mean = sum(data) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in data) / (n - 1)
        sem = math.sqrt(variance) / math.sqrt(n)
    else:
        sem = 0.0
    return mean, sem

def force_stage_velocity(stage, min_vel, accel, max_vel):
    if stage is None:
        return False
    for _ in range(5):
        try:
            with bus_lock:
                stage.setup_velocity(min_vel, accel, max_vel, scale=False)
                time.sleep(0.3)
                current_params = stage.get_velocity_parameters(scale=False)
            if current_params and abs(current_params[-1] - max_vel) < 100:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False

def wait_stage_move(stage_x, stage_y, target_x_mm=None, target_y_mm=None):
    time_to_sleep = 0.2
    try:
        if target_x_mm is not None and stage_x is not None:
            with bus_lock:
                curr_x = stage_x.get_position(scale=False) / STEPS_PER_MM
            dist_x = abs(target_x_mm - curr_x)
            if dist_x > 0:
                time_to_sleep = max(time_to_sleep, (dist_x / 10.0) + 2.0)
        if target_y_mm is not None and stage_y is not None:
            with bus_lock:
                curr_y = stage_y.get_position(scale=False) / STEPS_PER_MM
            dist_y = abs(target_y_mm - curr_y)
            if dist_y > 0:
                time_to_sleep = max(time_to_sleep, (dist_y / 10.0) + 2.0)
    except Exception:
        time_to_sleep = 3.0

    if time_to_sleep > 0.5:
        time.sleep(time_to_sleep - 0.3)

    with bus_lock:
        last_x = stage_x.get_position(scale=False) if stage_x is not None else 0
        last_y = stage_y.get_position(scale=False) if stage_y is not None else 0
    stable_count = 0
    while True:
        time.sleep(0.1)
        with bus_lock:
            curr_x = stage_x.get_position(scale=False) if stage_x is not None else 0
            curr_y = stage_y.get_position(scale=False) if stage_y is not None else 0
        if curr_x == last_x and curr_y == last_y:
            stable_count += 1
            if stable_count >= 4:
                break
        else:
            stable_count = 0
        last_x, last_y = curr_x, curr_y

def process_wavelength_data(wl, raw_points, i0_val, i0_sem, idark_val, idark_sem, ctrl_val=None, ctrl_sem=None):
    i0_corrected = i0_val - idark_val
    i0_corr_err = math.sqrt(i0_sem**2 + idark_sem**2)
    lines = [
        f"\n# --- MATHEMATICAL NORMALIZATION FOR LINE {wl} nm ---",
        "Wavelength_nm\tPoint_ID\tX_Pos_mm\tY_Pos_mm\tNorm_Current\tNorm_SEM_Error"
    ]
    first_raw, first_err = None, None
    for idx, x_mm, y_mm, val, sem in raw_points:
        if idx == 1:
            first_raw, first_err = val, sem
        i_corrected = val - idark_val
        i_corr_err = math.sqrt(sem**2 + idark_sem**2)
        if i0_corrected != 0 and not math.isnan(i0_corrected):
            i_norm = i_corrected / i0_corrected
            if i_corrected != 0 and not math.isnan(i_corrected):
                i_norm_err = abs(i_norm) * math.sqrt((i_corr_err / i_corrected)**2 + (i0_corr_err / i0_corrected)**2)
            else:
                i_norm_err = 0.0
        else:
            i_norm, i_norm_err = float('nan'), float('nan')
        lines.append(f"{wl}\tNORM_GRID_{idx}\t{x_mm:.3f}\t{y_mm:.3f}\t{i_norm:.6e}\t{i_norm_err:.6e}")

    if ctrl_val is not None and first_raw is not None and not math.isnan(ctrl_val) and not math.isnan(first_raw):
        diff_raw = ctrl_val - first_raw
        diff_err = math.sqrt(ctrl_sem**2 + first_err**2)
        diff_pct = (diff_raw / abs(first_raw)) * 100.0 if first_raw != 0 else 0.0
        diff_pct_err = (diff_err / abs(first_raw)) * 100.0 if first_raw != 0 else 0.0
        lines.append(f"\n# --- DRIFT ANALYSIS FOR {wl} nm (CONTROL vs POINT 1) ---")
        lines.append(f"# Absolute current change: {diff_raw:.6e} ± {diff_err:.6e} A")
        lines.append(f"# Relative drift: {diff_pct:.3f}% ± {diff_pct_err:.3f}%")

    lines.append(f"# --- END OF PROCESSING FOR {wl} nm ---\n")
    return "\n".join(lines) + "\n"

class SpectrumSummary:
    def __init__(self):
        self.records = []

    def add_wavelength_summary(self, wl, raw_points, i0_val, i0_sem, idark_val, idark_sem):
        i0_corrected = i0_val - idark_val
        i0_corr_err = math.sqrt(i0_sem**2 + idark_sem**2)
        if i0_corrected == 0 or math.isnan(i0_corrected):
            self.records.append((wl, float('nan'), float('nan')))
            return 0.0
        wl_transmissions = []
        wl_errors_sq = []
        for idx, x_mm, y_mm, val, sem in raw_points:
            if math.isnan(val):
                continue
            i_corrected = val - idark_val
            i_corr_err = math.sqrt(sem**2 + idark_sem**2)
            i_norm = i_corrected / i0_corrected
            if i_corrected != 0:
                i_norm_err = abs(i_norm) * math.sqrt((i_corr_err / i_corrected)**2 + (i0_corr_err / i0_corrected)**2)
            else:
                i_norm_err = 0.0
            wl_transmissions.append(i_norm)
            wl_errors_sq.append(i_norm_err**2)
        mean_t = sum(wl_transmissions) / len(wl_transmissions) if wl_transmissions else 0.0
        mean_t_err = math.sqrt(sum(wl_errors_sq)) / len(wl_transmissions) if wl_errors_sq else 0.0
        self.records.append((wl, mean_t, mean_t_err))
        return mean_t

    def generate_table_text(self):
        lines = [
            "\n" + "#" * 74,
            "# FINAL SUMMARY TABLE OF SAMPLE TRANSMITTANCE SPECTRUM",
            "#" * 74,
            "Wavelength_nm\tIntegral_Transmittance\tIntegral_SEM_Error"
        ]
        for wl, t, err in self.records:
            lines.append(f"{wl:.1f}\t{t:.6e}\t{err:.6e}")
        lines.append("# --- END OF REPORT ---")
        return "\n".join(lines) + "\n"

# =========================================================================
# MAIN GUI & AUTONOMOUS HARDWARE STATION CLASS
# =========================================================================
class UnifiedSpectroStationDashboard:
    def __init__(self, root):
        self.root = root
        self.lang = "RU"
        self.root.geometry("1540x920")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Hardware & Execution State
        self.MAX_TRAVEL_MM = MAX_TRAVEL_MM
        self.stage_x = None
        self.stage_y = None
        self.keysight_connected = False
        self.mono_connected = False

        self.wavelengths_list = [350.0, 420.0, 450.0, 660.0]
        self.selected_file_path = "scan_wavelengths_aerogels.txt"
        self.num_measurements = 20
        self.delay_between_reads = 0.1
        self.stabilization_delay = 3.0

        self.is_scanning = False
        self.scan_thread = None
        self.last_plotted_wl = []
        self.last_plotted_t = []

        # --- Top Banner Header ---
        top_banner = ctk.CTkFrame(self.root, height=60, corner_radius=0, fg_color="#0f172a")
        top_banner.pack(fill=tk.X, side=tk.TOP)
        top_banner.grid_columnconfigure(0, weight=0)
        top_banner.grid_columnconfigure(1, weight=1)
        top_banner.grid_columnconfigure(2, weight=0)

        # Set window titlebar & taskbar icon (.ico)
        try:
            self.root.iconbitmap(resource_path("app_icon.ico"))
        except Exception:
            pass

        # Load your .png logo in the top banner
        try:
            raw_logo = Image.open(resource_path("logo.png"))
            self.logo_img = ctk.CTkImage(light_image=raw_logo, dark_image=raw_logo, size=(45, 45))
            logo_lbl = ctk.CTkLabel(top_banner, image=self.logo_img, text="")
            logo_lbl.grid(row=0, column=0, padx=(25, 15), pady=8, sticky="w")
        except Exception:
            pass


        self.title_lbl = ctk.CTkLabel(
            top_banner, text="", font=ctk.CTkFont(family="sans-serif", size=18, weight="bold"), text_color="#f8fafc"
        )
        self.title_lbl.grid(row=0, column=1, pady=16, sticky="w")

        self.lang_switch = ctk.CTkSegmentedButton(
            top_banner, values=["EN", "RU"], command=self.change_language, width=100, height=30,
            font=ctk.CTkFont(weight="bold", size=12)
        )
        self.lang_switch.set(self.lang)
        self.lang_switch.grid(row=0, column=2, padx=25, pady=15, sticky="e")

        # --- Workspace Splitter ---
        workspace = ctk.CTkFrame(self.root, fg_color="transparent")
        workspace.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # =========================================================================
        # COLUMN 1: HARDWARE & GRID CONFIGURATION (LEFT - SCROLLABLE)
        # =========================================================================
        col1 = ctk.CTkScrollableFrame(workspace, fg_color="transparent", width=350)
        col1.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 10))

        # Module 1H: Direct Hardware Control
        hw_frame = ctk.CTkFrame(col1)
        hw_frame.pack(fill=tk.X, pady=(0, 12), ipady=5)

        self.hw_frame_lbl = ctk.CTkLabel(hw_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=32, corner_radius=6, text_color="#38bdf8")
        self.hw_frame_lbl.pack(fill=tk.X, padx=12, pady=(8, 6))

        status_row = ctk.CTkFrame(hw_frame, fg_color="transparent")
        status_row.pack(pady=(0, 6))

        ctk.CTkLabel(status_row, text="Stages:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8").pack(side=tk.LEFT)
        self.dot_stages = ctk.CTkLabel(status_row, text="●", font=ctk.CTkFont(size=14, weight="bold"), text_color="#22c55e")
        self.dot_stages.pack(side=tk.LEFT, padx=(3, 8))

        ctk.CTkLabel(status_row, text="|  Keysight:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8").pack(side=tk.LEFT)
        self.dot_keysight = ctk.CTkLabel(status_row, text="●", font=ctk.CTkFont(size=14, weight="bold"), text_color="#22c55e")
        self.dot_keysight.pack(side=tk.LEFT, padx=(3, 8))

        ctk.CTkLabel(status_row, text="|  Mono:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8").pack(side=tk.LEFT)
        self.dot_mono = ctk.CTkLabel(status_row, text="●", font=ctk.CTkFont(size=14, weight="bold"), text_color="#22c55e")
        self.dot_mono.pack(side=tk.LEFT, padx=(3, 0))


        hw_btn_row = ctk.CTkFrame(hw_frame, fg_color="transparent")
        hw_btn_row.pack(fill=tk.X, padx=12, pady=4)
        self.btn_connect_hw = ctk.CTkButton(hw_btn_row, text="", height=30, font=ctk.CTkFont(weight="bold", size=11), fg_color="#0284c7", hover_color="#0369a1", command=self.connect_all_hardware_async)
        self.btn_connect_hw.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.btn_home_stages = ctk.CTkButton(hw_btn_row, text="", height=30, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.home_stages_async)
        self.btn_home_stages.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

        volt_row = ctk.CTkFrame(hw_frame, fg_color="transparent")
        volt_row.pack(fill=tk.X, padx=12, pady=6)
        self.lbl_volt = ctk.CTkLabel(volt_row, text="", font=ctk.CTkFont(size=11))
        self.lbl_volt.pack(side=tk.LEFT)
        self.entry_voltage = ctk.CTkEntry(volt_row, width=65, height=26)
        self.entry_voltage.insert(0, "100.0")
        self.entry_voltage.pack(side=tk.LEFT, padx=6)
        self.btn_volt_on = ctk.CTkButton(volt_row, text="", width=65, height=26, font=ctk.CTkFont(weight="bold", size=11), fg_color="#059669", hover_color="#047857", command=self.apply_voltage_cmd)
        self.btn_volt_on.pack(side=tk.LEFT, padx=2)
        self.btn_volt_off = ctk.CTkButton(volt_row, text="", width=45, height=26, font=ctk.CTkFont(weight="bold", size=11), fg_color="#b91c1c", hover_color="#991b1b", command=self.disable_voltage_cmd)
        self.btn_volt_off.pack(side=tk.LEFT, padx=2)

        sample_row = ctk.CTkFrame(hw_frame, fg_color="transparent")
        sample_row.pack(fill=tk.X, padx=12, pady=(2, 6))
        self.lbl_sample = ctk.CTkLabel(sample_row, text="", font=ctk.CTkFont(size=11))
        self.lbl_sample.pack(side=tk.LEFT)
        self.entry_sample_name = ctk.CTkEntry(sample_row, height=26)
        self.entry_sample_name.insert(0, "aerogel_sample_01")
        self.entry_sample_name.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(8, 0))

        # Module 1A: Stage Kinematics / Grid Setup
        grid_frame = ctk.CTkFrame(col1)
        grid_frame.pack(fill=tk.X, pady=(0, 12), ipady=5)

        self.grid_frame_lbl = ctk.CTkLabel(grid_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=32, corner_radius=6, text_color="#38bdf8")
        self.grid_frame_lbl.grid(row=0, column=0, columnspan=2, sticky="we", padx=12, pady=(8, 5))

        fields = [
            ("Start X0 (mm):", "0.0", "entry_x0"),
            ("Start Y0 (mm):", "0.0", "entry_y0"),
            ("Sample Length (cm):", "10.0", "entry_length"),
            ("Sample Width (cm):", "10.0", "entry_width"),
            ("Density (N x N Matrix):", "05", "entry_points")
        ]
        for i, (_, default_val, attr_name) in enumerate(fields, start=1):
            lbl = ctk.CTkLabel(grid_frame, text="", font=ctk.CTkFont(size=11))
            lbl.grid(row=i, column=0, sticky="w", padx=12, pady=4)
            setattr(self, f"lbl_{attr_name}", lbl)
            entry = ctk.CTkEntry(grid_frame, width=100, height=26, font=ctk.CTkFont(size=11))
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, padx=12, pady=4, sticky="e")
            setattr(self, attr_name, entry)

        self.grid_btn = ctk.CTkButton(grid_frame, text="", height=30, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.update_stage_plot)
        self.grid_btn.grid(row=6, column=0, columnspan=2, pady=(10, 4), padx=12, sticky="we")

        # Module 1C: Keysight Instrument Adjuster
        keysight_frame = ctk.CTkFrame(col1)
        keysight_frame.pack(fill=tk.X, pady=(0, 12), ipady=5)

        self.keysight_frame_lbl = ctk.CTkLabel(keysight_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=32, corner_radius=6, text_color="#38bdf8")
        self.keysight_frame_lbl.grid(row=0, column=0, columnspan=2, sticky="we", padx=12, pady=(8, 5))

        k_fields = [
            ("Samples Count (N_meas):", "10", "entry_nmeas"),
            ("Read Delay [Delta t] (s):", "0.1", "entry_delta_t"),
            ("Stage Settle Delay (s):", "1.0", "entry_stabilize")
        ]
        for i, (_, default_val, attr_name) in enumerate(k_fields, start=1):
            lbl = ctk.CTkLabel(keysight_frame, text="", font=ctk.CTkFont(size=11))
            lbl.grid(row=i, column=0, sticky="w", padx=12, pady=4)
            setattr(self, f"lbl_{attr_name}", lbl)
            entry = ctk.CTkEntry(keysight_frame, width=100, height=26)
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, padx=12, pady=4, sticky="e")
            setattr(self, attr_name, entry)

        self.apply_btn = ctk.CTkButton(keysight_frame, text="", height=30, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.validate_keysight_metrics)
        self.apply_btn.grid(row=4, column=0, columnspan=2, pady=(10, 4), padx=12, sticky="we")

        # Module 1B: Monochromator Filterwheel Setup
        mono_frame = ctk.CTkFrame(col1)
        mono_frame.pack(fill=tk.X, expand=False, pady=(0, 12))

        self.mono_frame_lbl = ctk.CTkLabel(mono_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=32, corner_radius=6, text_color="#38bdf8")
        self.mono_frame_lbl.pack(fill=tk.X, padx=12, pady=(8, 5))

        self.mode_var = tk.StringVar(value="manual")
        self.rb1 = ctk.CTkRadioButton(mono_frame, text="", variable=self.mode_var, value="manual", font=ctk.CTkFont(weight="bold", size=11))
        self.rb1.pack(anchor="w", padx=12, pady=(8, 4))
        self.entry_manual = ctk.CTkEntry(mono_frame, height=26)
        self.entry_manual.insert(0, "300, 350, 400, 450, 500, 550")
        self.entry_manual.pack(fill=tk.X, padx=20, pady=(0, 8))

        self.rb2 = ctk.CTkRadioButton(mono_frame, text="", variable=self.mode_var, value="range", font=ctk.CTkFont(weight="bold", size=11))
        self.rb2.pack(anchor="w", padx=12, pady=4)
        range_sub = ctk.CTkFrame(mono_frame, fg_color="transparent")
        range_sub.pack(anchor="w", padx=20, pady=(0, 8))

        self.lbl_start = ctk.CTkLabel(range_sub, text="", font=ctk.CTkFont(size=10))
        self.lbl_start.grid(row=0, column=0, padx=2)
        self.entry_start = ctk.CTkEntry(range_sub, width=48, height=24); self.entry_start.insert(0, "240"); self.entry_start.grid(row=0, column=1, padx=3)
        self.lbl_end = ctk.CTkLabel(range_sub, text="", font=ctk.CTkFont(size=10))
        self.lbl_end.grid(row=0, column=2, padx=2)
        self.entry_end = ctk.CTkEntry(range_sub, width=48, height=24); self.entry_end.insert(0, "650"); self.entry_end.grid(row=0, column=3, padx=3)
        self.lbl_step = ctk.CTkLabel(range_sub, text="", font=ctk.CTkFont(size=10))
        self.lbl_step.grid(row=0, column=4, padx=2)
        self.entry_step = ctk.CTkEntry(range_sub, width=42, height=24); self.entry_step.insert(0, "20"); self.entry_step.grid(row=0, column=5, padx=3)

        self.rb3 = ctk.CTkRadioButton(mono_frame, text="", variable=self.mode_var, value="file", font=ctk.CTkFont(weight="bold", size=11))
        self.rb3.pack(anchor="w", padx=12, pady=4)
        file_sub = ctk.CTkFrame(mono_frame, fg_color="transparent")
        file_sub.pack(anchor="w", padx=20, pady=(0, 10))
        self.browse_btn = ctk.CTkButton(file_sub, text="", width=80, height=24, font=ctk.CTkFont(size=11), command=self.browse_flat_file)
        self.browse_btn.grid(row=0, column=0)
        self.lbl_filename = ctk.CTkLabel(file_sub, text="scan_wavelengths_aerogels.txt", font=ctk.CTkFont(size=10, slant="italic"), text_color="#94a3b8")
        self.lbl_filename.grid(row=0, column=1, padx=6)

        self.load_btn = ctk.CTkButton(mono_frame, text="", height=28, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.process_wavelengths_queue)
        self.load_btn.pack(fill=tk.X, padx=12, pady=4)
        self.txt_mono_preview = ctk.CTkTextbox(mono_frame, font=("sans-serif", 11), fg_color="#1e293b", height=70)
        self.txt_mono_preview.pack(fill=tk.X, expand=False, padx=12, pady=(4, 12))

        # =========================================================================
        # COLUMN 2: GRAPH PANEL (MIDDLE)
        # =========================================================================
        col2 = ctk.CTkFrame(workspace, fg_color="transparent")
        col2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        graphs_container = ctk.CTkFrame(col2, fg_color="transparent")
        graphs_container.pack(fill=tk.BOTH, expand=True)

        stage_box = ctk.CTkFrame(graphs_container)
        stage_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self.stage_box_lbl = ctk.CTkLabel(stage_box, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#334155", height=35, corner_radius=6, text_color="#f3faf9")
        self.stage_box_lbl.pack(fill=tk.X, padx=12, pady=(10, 0))
        self.fig_stage, self.ax_stage = plt.subplots(figsize=(5, 5), facecolor='#2a2d32')
        self.canvas_stage = FigureCanvasTkAgg(self.fig_stage, master=stage_box)
        self.canvas_stage.get_tk_widget().pack(fill=tk.NONE, expand=True, padx=10, pady=10)

        spectro_box = ctk.CTkFrame(graphs_container)
        spectro_box.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))
        self.spectro_box_lbl = ctk.CTkLabel(spectro_box, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#334155", height=35, corner_radius=6, text_color="#f3faf9")
        self.spectro_box_lbl.pack(fill=tk.X, padx=12, pady=(10, 0))
        self.fig_spec, self.ax_spec = plt.subplots(figsize=(5, 5), facecolor='#2a2d32')
        self.canvas_spec = FigureCanvasTkAgg(self.fig_spec, master=spectro_box)
        self.canvas_spec.get_tk_widget().pack(fill=tk.NONE, expand=True, padx=10, pady=10)

        # =========================================================================
        # COLUMN 3: ESTIMATORS & LIVE LOGS PANEL (RIGHT)
        # =========================================================================
        col3 = ctk.CTkFrame(workspace, fg_color="transparent", width=360)
        col3.pack(side=tk.RIGHT, fill=tk.Y, expand=False, padx=(10, 0))

        estimator_frame = ctk.CTkFrame(col3)
        estimator_frame.pack(fill=tk.X, expand=False, pady=(0, 12))
        self.estimator_frame_lbl = ctk.CTkLabel(estimator_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=35, corner_radius=6, text_color="#38bdf8")
        self.estimator_frame_lbl.pack(fill=tk.X, padx=12, pady=(10, 5))
        self.calc_btn = ctk.CTkButton(estimator_frame, text="", height=30, font=ctk.CTkFont(weight="bold", size=11), fg_color="#334155", hover_color="#475569", command=self.compute_session_estimations)
        self.calc_btn.pack(fill=tk.X, padx=12, pady=(8, 6))
        self.txt_estimator_summary = ctk.CTkTextbox(estimator_frame, font=("Courier New", 11), fg_color="#1e293b", height=115)
        self.txt_estimator_summary.pack(fill=tk.X, expand=False, padx=12, pady=(0, 12))

        monitor_frame = ctk.CTkFrame(col3)
        monitor_frame.pack(fill=tk.BOTH, expand=True, ipady=5)
        self.monitor_frame_lbl = ctk.CTkLabel(monitor_frame, text="", font=ctk.CTkFont(weight="bold", size=14), fg_color="#1e293b", height=35, corner_radius=6, text_color="#38bdf8")
        self.monitor_frame_lbl.pack(fill=tk.X, padx=12, pady=(10, 0))
        self.lbl_watch_wl = ctk.CTkLabel(monitor_frame, text="", font=ctk.CTkFont(weight="bold", size=12), fg_color="#334155", height=34, corner_radius=6, text_color="#e1f3fa")
        self.lbl_watch_wl.pack(fill=tk.X, padx=12, pady=(8, 6))
        self.lbl_watch_node = ctk.CTkLabel(monitor_frame, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.lbl_watch_node.pack(fill=tk.X, padx=12, pady=2)
        self.progress_bar = ctk.CTkProgressBar(monitor_frame, height=12, corner_radius=4)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill=tk.X, padx=12, pady=(2, 8))
        self.txt_terminal_log = ctk.CTkTextbox(monitor_frame, font=("Courier New", 11), fg_color="#090d16", text_color="#38bdf8", height=220)
        self.txt_terminal_log.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        self.btn_master_launch = ctk.CTkButton(
            col3, text="", height=45, font=ctk.CTkFont(weight="bold", size=12),
            fg_color="#dc2626", hover_color="#b91c1c", command=self.trigger_master_experiment_pipeline
        )
        self.btn_master_launch.pack(fill=tk.X, pady=(10, 5))

        # Initialize UI State
        self.apply_translations()
        self.reset_all_plots_canvas()
        self.process_wavelengths_queue()
        self.compute_session_estimations()

    # =========================================================================
    # TRANSLATION METHODS
    # =========================================================================
    def t(self, key, **kwargs):
        text = TRANSLATIONS[self.lang].get(key, key)
        return text.format(**kwargs) if kwargs else text

    def change_language(self, selected_lang):
        self.lang = selected_lang
        self.apply_translations()
        self.update_stage_plot()
        self.process_wavelengths_queue()
        self.compute_session_estimations()
        if self.last_plotted_wl:
            self.render_live_spectrogram_curve(self.last_plotted_wl, self.last_plotted_t)
        else:
            self.ax_spec.set_xlabel(self.t("spec_xlabel"), fontsize=8, color='white', fontweight='bold')
            self.ax_spec.set_ylabel(self.t("spec_ylabel"), fontsize=8, color='white', fontweight='bold')
            self.fig_spec.tight_layout()
            self.canvas_spec.draw()

    def apply_translations(self):
        self.root.title(self.t("win_title"))
        self.title_lbl.configure(text=self.t("banner_title"))
        self.hw_frame_lbl.configure(text=self.t("hw_title"))
        self.btn_connect_hw.configure(text=self.t("btn_connect_hw"))
        self.btn_home_stages.configure(text=self.t("btn_home_stages"))
        self.lbl_volt.configure(text=self.t("volt_lbl"))
        self.btn_volt_on.configure(text=self.t("btn_volt_on"))
        self.btn_volt_off.configure(text=self.t("btn_volt_off"))
        self.lbl_sample.configure(text=self.t("sample_lbl"))
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
        self.lbl_start.configure(text=self.t("start"))
        self.lbl_end.configure(text=self.t("end"))
        self.lbl_step.configure(text=self.t("step"))
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

    # =========================================================================
    # HARDWARE CONTROL BUTTON HANDLERS
    # =========================================================================
    def update_hw_status_banner(self):
        s_color = "#facc15" if (self.stage_x and self.stage_y) else "#22c55e"
        k_color = "#facc15" if self.keysight_connected else "#22c55e"
        m_color = "#facc15" if self.mono_connected else "#22c55e"
        self.root.after(0, lambda: self.dot_stages.configure(text_color=s_color))
        self.root.after(0, lambda: self.dot_keysight.configure(text_color=k_color))
        self.root.after(0, lambda: self.dot_mono.configure(text_color=m_color))


    def connect_all_hardware_async(self):
        threading.Thread(target=self._connect_all_hardware_worker, daemon=True).start()

    def _connect_all_hardware_worker(self):
        self.append_terminal_msg("🔌 Connecting to hardware devices...")
        # 1. Thorlabs Stages
        try:
            with bus_lock:
                self.stage_x = Thorlabs.KinesisMotor(HORIZONTAL_STAGE_SN, scale="step")
                self.stage_y = Thorlabs.KinesisMotor(VERTICAL_STAGE_SN, scale="step")
                self.stage_x.setup_velocity(0, ACCEL_STEPS, SCAN_SPEED_STEPS, scale=False)
                self.stage_y.setup_velocity(0, ACCEL_STEPS, SCAN_SPEED_STEPS, scale=False)
            self.append_terminal_msg("✅ Thorlabs X/Y stages connected.")
        except Exception as e:
            self.stage_x, self.stage_y = None, None
            self.append_terminal_msg(f"⚠️ Thorlabs stages offline: {e}")

        # 2. Keysight Electrometer
        rm = dev = None
        try:
            with bus_lock:
                rm = get_visa_rm()
                dev = rm.open_resource(VISA_ADDRESS)
                dev.timeout = 2000
                idn = dev.query('*IDN?').strip()
            self.keysight_connected = True
            self.append_terminal_msg(f"✅ Keysight connected: {idn}")
        except Exception as e:
            self.keysight_connected = False
            self.append_terminal_msg(f"⚠️ Keysight offline: {e}")
        finally:
            if dev:
                try: dev.close()
                except Exception: pass
            if rm:
                try: rm.close()
                except Exception: pass

        # 3. Monochromator MS3504i
        if mono_connect():
            self.mono_connected = True
            self.append_terminal_msg("✅ SOL MS3504i Monochromator connected.")
        else:
            self.mono_connected = False
            self.append_terminal_msg("⚠️ SOL MS3504i Monochromator offline.")

        self.update_hw_status_banner()

    def home_stages_async(self):
        if not (self.stage_x and self.stage_y):
            messagebox.showwarning("Hardware", "Thorlabs stages are not connected.")
            return
        threading.Thread(target=self._home_stages_worker, daemon=True).start()

    def _home_stages_worker(self):
        self.append_terminal_msg("⏳ Homing X/Y stages...")
        with bus_lock:
            self.stage_x.setup_velocity(0, ACCEL_STEPS, HOMING_SPEED_STEPS, scale=False)
            self.stage_y.setup_velocity(0, ACCEL_STEPS, HOMING_SPEED_STEPS, scale=False)
            try:
                self.stage_x.home(direction="-", force=True, sync=False)
                self.stage_y.home(direction="-", force=True, sync=False)
            except Exception:
                self.stage_x.home(force=True, sync=False)
                self.stage_y.home(force=True, sync=False)
        time.sleep(10.0)
        wait_stage_move(self.stage_x, self.stage_y)
        force_stage_velocity(self.stage_x, 0, ACCEL_STEPS, SCAN_SPEED_STEPS)
        force_stage_velocity(self.stage_y, 0, ACCEL_STEPS, SCAN_SPEED_STEPS)
        self.append_terminal_msg("✅ Stage axes successfully homed to (0, 0) mm.")

    def apply_voltage_cmd(self):
        ok, msg = keysight_set_voltage(self.entry_voltage.get().strip())
        if ok:
            self.keysight_connected = True
            self.update_hw_status_banner()
            self.append_terminal_msg(f"⚡ Keysight Bias Voltage ON: {msg}")
        else:
            messagebox.showerror("Keysight Error", msg)

    def disable_voltage_cmd(self):
        if keysight_disable():
            self.append_terminal_msg("🔌 Keysight Voltage disabled (0 V / OFF).")

    # =========================================================================
    # PLOTTING & GRID METHODS
    # =========================================================================
    def reset_all_plots_canvas(self):
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
            num_points = int(self.entry_points.get())
            if num_points > 0:
                self.root.after(10, self.update_stage_plot)
        except (AttributeError, ValueError):
            pass

    def generate_grid_nodes_array(self, x0, y0, len_x_mm, len_y_mm, num_points):
        margin_start, margin_end = 15.0, 15.0
        if num_points <= 1:
            return [(x0 + len_x_mm / 2.0, y0 + len_y_mm / 2.0)]
        x_offsets = [margin_start + ((len_x_mm - margin_end - margin_start) / (num_points - 1)) * i for i in range(num_points)]
        y_offsets = [margin_start + ((len_y_mm - margin_end - margin_start) / (num_points - 1)) * i for i in range(num_points)]
        points = []
        for i, x_off in enumerate(x_offsets):
            current_y_offsets = y_offsets[::-1] if i % 2 != 0 else y_offsets
            for y_off in current_y_offsets:
                points.append((x0 + x_off, y0 + y_off))
        return points

    def update_stage_plot(self):
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
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if file_path:
            self.selected_file_path = file_path
            self.lbl_filename.configure(text=os.path.basename(file_path), text_color="white")
            self.mode_var.set("file")

    def process_wavelengths_queue(self):
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
                            except Exception:
                                pass

            self.wavelengths_list = [wl for wl in self.wavelengths_list if 240.0 <= wl <= 700.0]
            self.txt_mono_preview.delete("1.0", tk.END)
            self.txt_mono_preview.insert(tk.END, self.t("channels_loaded", count=len(self.wavelengths_list), arr=self.wavelengths_list))
            self.compute_session_estimations()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def validate_keysight_metrics(self):
        try:
            self.num_measurements = int(self.entry_nmeas.get())
            self.delay_between_reads = float(self.entry_delta_t.get())
            self.stabilization_delay = float(self.entry_stabilize.get())
            if self.num_measurements <= 0 or self.delay_between_reads < 0 or self.stabilization_delay < 0:
                raise ValueError()
            messagebox.showinfo(self.t("msg_success_title"), self.t("msg_success"))
            self.compute_session_estimations()
        except Exception:
            messagebox.showerror(self.t("msg_val_err_title"), self.t("msg_val_err"))

    def compute_session_estimations(self):
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
        except Exception:
            pass

    # =========================================================================
    # INTEGRATED AUTONOMOUS HARDWARE + SIMULATION SCANNING ENGINE
    # =========================================================================
    def trigger_master_experiment_pipeline(self):
        if not self.is_scanning:
            self.is_scanning = True
            self.last_plotted_wl = []
            self.last_plotted_t = []
            self.btn_master_launch.configure(text=self.t("btn_abort"), fg_color="#b91c1c", hover_color="#991b1b")
            self.txt_terminal_log.delete("1.0", tk.END)
            self.reset_all_plots_canvas()

            self.scan_thread = threading.Thread(target=self.integrated_hardware_loop_worker, daemon=True)
            self.scan_thread.start()
        else:
            self.is_scanning = False

    def integrated_hardware_loop_worker(self):
        x0, y0 = float(self.entry_x0.get()), float(self.entry_y0.get())
        len_x_mm = float(self.entry_length.get()) * 10.0
        len_y_mm = float(self.entry_width.get()) * 10.0
        num_points = int(self.entry_points.get())
        sample_name = self.entry_sample_name.get().strip() or "aerogel_sample"
        grid_nodes = self.generate_grid_nodes_array(x0, y0, len_x_mm, len_y_mm, num_points)

        hw_active = (self.stage_x is not None) and (self.stage_y is not None) and self.mono_connected
        mode_label = "REAL HARDWARE MODE" if hw_active else "SIMULATION MODE (Hardware offline)"
        self.append_terminal_msg(f"{self.t('log_init')}\n[{mode_label}]")
        create_session_log(f"Experiment started ({mode_label}): sample={sample_name}, nodes={len(grid_nodes)}")

        # Prepare Output Data File
        data_dir = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "_data"))
        os.makedirs(data_dir, exist_ok=True)
        filename = os.path.join(data_dir, f"spectro_final_{sample_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        spectrum_summary = SpectrumSummary()

        # Open VISA Session if Keysight is connected
        rm = device = None
        current_v = 0.0
        if self.keysight_connected:
            is_on, current_v = keysight_check_status()
            try:
                rm = get_visa_rm()
                device = rm.open_resource(VISA_ADDRESS)
                device.timeout = 5000
                device.clear()
            except Exception as e:
                self.append_terminal_msg(f"⚠️ Keysight VISA warning: {e}")
                device = None

        total_steps = len(self.wavelengths_list) * len(grid_nodes)
        step_counter = 0
        plotted_wl, plotted_transmittance = [], []
        first_x, first_y = grid_nodes[0]

        try:
            if hw_active:
                force_stage_velocity(self.stage_x, 0, ACCEL_STEPS, SCAN_SPEED_STEPS)
                force_stage_velocity(self.stage_y, 0, ACCEL_STEPS, SCAN_SPEED_STEPS)

            with open(filename, mode="w", encoding="utf-8") as f:
                f.write("# Comprehensive autonomous experimental log\n")
                f.write(f"# Mode: {mode_label}\n")
                f.write(f"# Aerogel dimensions: {len_x_mm/10.0}x{len_y_mm/10.0} cm | Voltage: {current_v} V\n")
                f.write("Wavelength_nm\tPoint_Type\tX_Pos_mm\tY_Pos_mm\tMean_Current(A)\tSEM_Error(A)\n")

                for wl in self.wavelengths_list:
                    if not self.is_scanning:
                        break
                    self.root.after(0, lambda w=wl: self.lbl_watch_wl.configure(text=self.t("status_running", w=w), text_color="#f59e0b"))
                    self.append_terminal_msg(self.t("log_wl", wl=wl))

                    if hw_active:
                        mono_set_wavelength(wl)
                        mono_shutter(open_shutter=True)
                    else:
                        time.sleep(0.5)

                    current_wl_raw_data = []

                    for idx, (x_mm, y_mm) in enumerate(grid_nodes, 1):
                        if not self.is_scanning:
                            break
                        step_counter += 1
                        pct = step_counter / total_steps
                        self.root.after(0, lambda i=idx, tot=len(grid_nodes): self.lbl_watch_node.configure(text=self.t("node_proc", i=i, t=tot)))
                        self.root.after(0, lambda p=pct: self.progress_bar.set(p))

                        if hw_active:
                            with bus_lock:
                                self.stage_x.move_to(int(x_mm * STEPS_PER_MM), scale=False)
                                self.stage_y.move_to(int(y_mm * STEPS_PER_MM), scale=False)
                            wait_stage_move(self.stage_x, self.stage_y, target_x_mm=x_mm, target_y_mm=y_mm)
                            time.sleep(self.stabilization_delay)

                        readings = []
                        if device is not None:
                            with bus_lock:
                                for _ in range(self.num_measurements):
                                    try:
                                        readings.append(safe_query_curr(device))
                                    except Exception:
                                        pass
                                    time.sleep(self.delay_between_reads)
                            mean_i, sem_i = calculate_stats(readings)
                        else:
                            # Simulation fallback reading
                            i_dark_sim, i_0_sim = 1.0e-11, 5.5e-09
                            base_t = 1.0 / (1.0 + np.exp(-(wl - 360.0) / 45.0))
                            sim_vals = [i_dark_sim + base_t * (i_0_sim - i_dark_sim) + np.random.normal(0, 1.5e-11) for _ in range(max(3, self.num_measurements))]
                            mean_i, sem_i = calculate_stats(sim_vals)
                            time.sleep(min(0.3, self.delay_between_reads * self.num_measurements))

                        f.write(f"{wl}\tRAW_GRID_{idx}\t{x_mm:.3f}\t{y_mm:.3f}\t{mean_i:.6e}\t{sem_i:.6e}\n")
                        f.flush()
                        current_wl_raw_data.append((idx, x_mm, y_mm, mean_i, sem_i))
                        self.append_terminal_msg(self.t("log_node", wl=wl, idx=idx, tot=len(grid_nodes), x=x_mm, y=y_mm, curr=mean_i))

                    if not self.is_scanning:
                        break

                    # Control Point Measurement (Return to first node)
                    if hw_active:
                        with bus_lock:
                            self.stage_x.move_to(int(first_x * STEPS_PER_MM), scale=False)
                            self.stage_y.move_to(int(first_y * STEPS_PER_MM), scale=False)
                        wait_stage_move(self.stage_x, self.stage_y, target_x_mm=first_x, target_y_mm=first_y)
                        time.sleep(self.stabilization_delay)

                    if device is not None:
                        ctrl_reads = []
                        with bus_lock:
                            for _ in range(self.num_measurements):
                                try:
                                    ctrl_reads.append(safe_query_curr(device))
                                except Exception:
                                    pass
                                time.sleep(self.delay_between_reads)
                        ctrl_mean, ctrl_sem = calculate_stats(ctrl_reads)
                    else:
                        ctrl_mean, ctrl_sem = current_wl_raw_data[0][3], current_wl_raw_data[0][4]
                    f.write(f"{wl}\tCONTROL\t{first_x:.3f}\t{first_y:.3f}\t{ctrl_mean:.6e}\t{ctrl_sem:.6e}\n")

                    # Reference Beam Measurement I_0 (Move to X=290 mm)
                    if hw_active:
                        with bus_lock:
                            self.stage_x.move_to(int(290.0 * STEPS_PER_MM), scale=False)
                        wait_stage_move(self.stage_x, self.stage_y, target_x_mm=290.0, target_y_mm=first_y)
                        time.sleep(self.stabilization_delay)

                    if device is not None:
                        i0_reads = []
                        with bus_lock:
                            for _ in range(self.num_measurements):
                                try:
                                    i0_reads.append(safe_query_curr(device))
                                except Exception:
                                    pass
                                time.sleep(self.delay_between_reads)
                        i0_mean, i0_sem = calculate_stats(i0_reads)
                    else:
                        i0_mean, i0_sem = 5.5e-09, 1.0e-12
                    f.write(f"{wl}\tRAW_I_0\t290.000\t{first_y:.3f}\t{i0_mean:.6e}\t{i0_sem:.6e}\n")

                    # Dark Current Measurement I_dark (Close Shutter)
                    if hw_active:
                        mono_shutter(open_shutter=False)
                        time.sleep(0.5)

                    if device is not None:
                        idark_reads = []
                        with bus_lock:
                            for _ in range(self.num_measurements):
                                try:
                                    idark_reads.append(safe_query_curr(device))
                                except Exception:
                                    pass
                                time.sleep(self.delay_between_reads)
                        idark_mean, idark_sem = calculate_stats(idark_reads)
                    else:
                        idark_mean, idark_sem = 1.0e-11, 1.0e-13
                    f.write(f"{wl}\tRAW_I_DARK\t290.000\t{first_y:.3f}\t{idark_mean:.6e}\t{idark_sem:.6e}\n")

                    # Normalize Data & Update Live Spectrogram
                    math_output = process_wavelength_data(wl, current_wl_raw_data, i0_mean, i0_sem, idark_mean, idark_sem, ctrl_mean, ctrl_sem)
                    f.write(math_output)
                    mean_t_channel = spectrum_summary.add_wavelength_summary(wl, current_wl_raw_data, i0_mean, i0_sem, idark_mean, idark_sem)
                    f.flush()

                    plotted_wl.append(wl)
                    plotted_transmittance.append(mean_t_channel)
                    self.last_plotted_wl = list(plotted_wl)
                    self.last_plotted_t = list(plotted_transmittance)
                    self.root.after(0, lambda w=list(plotted_wl), t=list(plotted_transmittance): self.render_live_spectrogram_curve(w, t))

                f.write(spectrum_summary.generate_table_text())
                f.flush()

        except Exception as e:
            self.append_terminal_msg(f"❌ [CRITICAL ERROR]: {e}")
        finally:
            # Safe Park Stage at (10, 10) mm
            if hw_active:
                try:
                    mono_shutter(open_shutter=False)
                    with bus_lock:
                        self.stage_x.move_to(int(10.0 * STEPS_PER_MM), scale=False)
                        self.stage_y.move_to(int(10.0 * STEPS_PER_MM), scale=False)
                    wait_stage_move(self.stage_x, self.stage_y, target_x_mm=10.0, target_y_mm=10.0)
                    self.append_terminal_msg("🅿️ Stage safely parked at (10.0, 10.0) mm.")
                except Exception as pe:
                    self.append_terminal_msg(f"⚠️ Parking warning: {pe}")

            if device:
                try: device.close()
                except Exception: pass
            if rm:
                try: rm.close()
                except Exception: pass

            completed = (step_counter == total_steps and self.is_scanning)
            self.is_scanning = False
            self.root.after(0, lambda: self.btn_master_launch.configure(text=self.t("btn_launch"), fg_color="#dc2626", hover_color="#b91c1c"))
            if completed:
                self.root.after(0, lambda: self.lbl_watch_wl.configure(text=self.t("status_done"), text_color="#10b981"))
                self.append_terminal_msg(f"{self.t('log_done')}\n📄 Saved: {filename}")
                play_finish_signal()
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

    def on_closing(self):
        """Safe cleanup of all hardware handles when closing the window."""
        self.is_scanning = False
        stop_finish_signal()
        try:
            if global_devctrl is not None:
                mono_shutter(open_shutter=False)
                global_devctrl.FreeDevice()
        except Exception:
            pass
        try:
            keysight_disable()
        except Exception:
            pass
        with bus_lock:
            if self.stage_x:
                try:
                    self.stage_x.stop()
                    self.stage_x.close()
                except Exception:
                    pass
            if self.stage_y:
                try:
                    self.stage_y.stop()
                    self.stage_y.close()
                except Exception:
                    pass
        self.root.destroy()


if __name__ == "__main__":
    main_window_root = ctk.CTk()
    dashboard_app = UnifiedSpectroStationDashboard(main_window_root)
    main_window_root.mainloop()
