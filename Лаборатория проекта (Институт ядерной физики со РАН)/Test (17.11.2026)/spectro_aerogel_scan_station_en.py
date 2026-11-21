import os
import sys
import time
import math
import warnings
from datetime import datetime
import numpy as np 
import pyvisa
import threading
from ctypes import CDLL, c_bool, c_int

# Safe import of Thorlabs Kinesis
try:
    from pylablib.devices import Thorlabs
except Exception as e:
    print(f"[❌ IMPORT] Error loading pylablib: {e}")

# Global USB bus lock to prevent collisions
bus_lock = threading.Lock()

if os.name == 'nt':
    import msvcrt
else:
    import select

warnings.filterwarnings("ignore", category=UserWarning)


def create_session_log(message):

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
        parent_dir = os.path.dirname(script_dir)
        log_dir = os.path.join(parent_dir, "_logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "spectro_session.log")
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except:
        pass

# --- Final audio signal (track fragment) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
FINISH_MP3_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "_docs", "finish_signal_short.mp3"))
FINISH_START_SEC = 0.0    # 1:28
FINISH_DURATION_SEC = 21.0 # until 1:49

def play_finish_signal():
    """
    Plays an MP3 fragment upon scan completion.
    Runs in the background via pygame.mixer. If pygame is not installed
    or the file is missing, it silently skips (does not crash the program).
    """
    if not os.path.exists(FINISH_MP3_PATH):
        print(f"[🔔] Audio signal: file not found ({FINISH_MP3_PATH}), skipped.")
        print("    Please place the MP3 file at this path.")
        return
    try:
        import pygame
    except ImportError:
        print("[🔔] Audio signal: pygame is not installed, skipped.")
        print("   Install it using: pip install pygame")
        return
    try:
        # Initialize the mixer once. Repeated init() calls are safe.
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(FINISH_MP3_PATH)
        pygame.mixer.music.play(start=FINISH_START_SEC)
        print("[🔔] Final signal playing.")
    except Exception as e:
        print(f"[🔔] Audio signal: playback error: {e}")

def stop_finish_signal():
    """Stops the signal if it is still playing. Called from finally blocks."""
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()
    except Exception:
        pass

def test_finish_signal():
    """
    Audio signal self-check — without starting a scan.
    Usage:
        python spectro_aerogel_scan_station_corr.py --test-sound
    """
    print("=== AUDIO SIGNAL TEST ===")
    print(f"File: {FINISH_MP3_PATH}")
    print(f"Exists: {os.path.exists(FINISH_MP3_PATH)}")
    print(f"Fragment: {int(FINISH_START_SEC)//60}:{int(FINISH_START_SEC)%60:02d} – {int(FINISH_START_SEC+FINISH_DURATION_SEC)//60}:{int(FINISH_START_SEC+FINISH_DURATION_SEC)%60:02d}")

    try:
        import pygame
        print(f"pygame version: {pygame.version.ver}")
    except ImportError:
        print("❌ pygame IS NOT INSTALLED. Install it using: pip install pygame")
        return

    if not os.path.exists(FINISH_MP3_PATH):
        print(f"❌ File not found: {FINISH_MP3_PATH}")
        print("   Please rename your MP3 file to finish_signal.mp3 and place it in _docs/.")
        return

    print("\n▶ Starting playback...")
    play_finish_signal()

    print(f"⏳ Waiting {FINISH_DURATION_SEC:.0f} sec (fragment)...")
    time.sleep(FINISH_DURATION_SEC)

    print("⏹ Stopping...")
    stop_finish_signal()
    print("✅ Test complete. If you heard the audio fragment, everything works fine.")

VISA_ADDRESS = 'USB0::0x2A8D::0xBA01::MY61390232::0::INSTR'
DEFAULT_MAX_VOLTAGE = 200.0  

HORIZONTAL_STAGE_SN = "45530624"  
VERTICAL_STAGE_SN = "45529014"    
STEPS_PER_MM = 409600.0  
MAX_TRAVEL_MM = 300.0

AEROGEL_START_X = 0.0   
AEROGEL_START_Y = 65.0  
AEROGEL_LENGTH_CM = 10.0  
AEROGEL_WIDTH_CM  = 10.0  
MARGIN_START_MM = 15.0    
MARGIN_END_MM   = 15.0    

POINTS_LARGE = 5          
NUM_MEASUREMENTS = 20      
DELAY_BETWEEN_READS = 0.1  
STABILIZATION_DELAY = 3.0  

ACCEL_STEPS = 115000
DEVICE_UNIT_PER_MM_S = 21987328
HOMING_SPEED_STEPS = 5 * DEVICE_UNIT_PER_MM_S
SCAN_SPEED_STEPS = 10 * DEVICE_UNIT_PER_MM_S

DLL_DIR = r"C:\Users\Ladmin\Documents\dark-box_thorlabs_ms3504i\_docs\MS3504i_Files"
DLL_PATH = os.path.join(DLL_DIR, "devctrl.dll")
WAVELENGTHS_FILE = "scan_wavelengths_aerogels.txt"

CALIBRATION_TABLE = [
    (18592, 240.0),  (20937, 270.0),  (22505, 290.0),  (24076, 310.0),
    (25651, 330.0),  (27231, 350.0),  (29605, 380.0),  (30398, 390.0),
    (31987, 410.0),  (35178, 450.0),  (39213, 500.0),  (43285, 550.0),
    (47390, 600.0),  (50719, 640.0),  (51556, 650.0),  (55785, 700.0)
]

global_devctrl = None
current_active_filter = None

class ScanInterrupted(Exception):
    pass

def wl_to_steps(target_wl):
    if target_wl < 240.0: target_wl = 240.0
    if target_wl > 700.0: target_wl = 700.0
    for i in range(len(CALIBRATION_TABLE) - 1):
        steps_a, wl_a = CALIBRATION_TABLE[i]
        steps_b, wl_b = CALIBRATION_TABLE[i+1]
        if wl_a <= target_wl <= wl_b:
            fraction = (target_wl - wl_a) / (wl_b - wl_a)
            return int(round(steps_a + fraction * (steps_b - steps_a)))
    return CALIBRATION_TABLE[0][0]

def get_filter_for_wl(wl):
    if wl < 390.0: return 1
    elif 390.0 <= wl <= 640.0: return 2
    else: return 3

def load_scan_wavelengths():
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
    wl_path = os.path.abspath(os.path.join(script_dir, "..", "_docs", WAVELENGTHS_FILE))
    points = []
    print(f"[CONFIG] Reading wavelengths from file: {wl_path}")
    try:
        with open(wl_path, "r", encoding="utf-8") as f:
            for line in f:
                clean = line.strip()
                if not clean or clean.startswith("#"): continue
                try: points.append(float(clean))
                except ValueError: pass
        print(f"[CONFIG] Spectrum points loaded: {len(points)}")
        return points
    except FileNotFoundError:
        print("[⚠️ WARNING] Spectrum file not found. Falling back to basic default mode.")
        return [450.0, 550.0, 650.0]

def mono_wait_for_device(timeout=20.0):
    start_time = time.time()
    while True:
        with bus_lock:
            if global_devctrl.IsOperationFinished():
                return True
        if (time.time() - start_time) > timeout:
            print("[⚠️ TIMEOUT] The device exceeded the movement time limit!")
            return False
        time.sleep(0.1)

def mono_connect():
    global global_devctrl
    with bus_lock:
        try:
            orig_cwd = os.getcwd()
            if not os.path.exists(DLL_DIR):
                print(f"[ERROR] DLL path does not exist: {DLL_DIR}")
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
        except Exception as e:
            print(f"[❌ MONOCHROMATOR DLL CRASH]: {e}")
            try:
                if global_devctrl is not None:
                    global_devctrl.FreeDevice()
            except Exception:
                pass
            global_devctrl = None
            return False

def mono_set_wavelength(target_wl):
    global current_active_filter
    req_filter = get_filter_for_wl(target_wl)
    need_filter_change = False
    
    with bus_lock:
        if not global_devctrl: return False
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
        if not global_devctrl: return
        if open_shutter:
            global_devctrl.OpenShutter(1)
        else:
            global_devctrl.CloseShutter(1)
    if not open_shutter:
        mono_wait_for_device()

def is_confirmed(user_input):
    return user_input.strip().lower() in ['', 'y', 'yes', 'д', 'да', 'у', 'н']

def select_axis():
    print("Select axis: [x] - Horizontal only, [y] - Vertical only, [b] - Both axes")
    ans = input("Your choice: ").strip().lower()
    if ans in ['x', 'х']: return 'x'
    if ans in ['y', 'у']: return 'y'
    if ans in ['b', 'о', 'o', 'б']: return 'both'
    return None

def keysight_set_voltage(voltage_val, force_high_voltage=False):
    try:
        volt_float = float(voltage_val)
        abs_volt = abs(volt_float)
    except ValueError:
        print(f"[⚠️ ERROR] Failed to recognize '{voltage_val}' as a number.")
        return False
    if abs_volt > DEFAULT_MAX_VOLTAGE and not force_high_voltage:
        print(f"[🔒 SAFETY LOCK] Voltage limit of {DEFAULT_MAX_VOLTAGE} V exceeded.")
        return False
    with bus_lock:
        rm = None; device = None
        try:
            rm = pyvisa.ResourceManager()
            device = rm.open_resource(VISA_ADDRESS)
            device.timeout = 5000
            device.write("*CLS")
            if abs_volt <= 21.0: range_cmd = "20"
            elif volt_float > 21.0: range_cmd = "1000"
            else: range_cmd = "-1000"
            device.write(f":SOUR:VOLT:RANG {range_cmd}")
            device.write(f":SOUR:VOLT:LEV {volt_float}")
            device.write(":OUTP:STAT ON")
            device.write(":SENS:FUNC 'CURR'")
            device.write(":SENS:CURR:RANG:AUTO ON")
            device.write(":INP:STAT ON")
            device.control_ren(6)
            print(f"✅ Voltage set on Keysight: {volt_float} V.")
            return True
        except Exception as e:
            print(f"[❌ Keysight ERROR]: {e}")
            return False
        finally:
            if device:
                try: device.close()
                except: pass
            if rm:
                try: rm.close()
                except: pass

def keysight_disable():
    with bus_lock:
        rm = None; device = None
        try:
            rm = pyvisa.ResourceManager()
            device = rm.open_resource(VISA_ADDRESS)
            device.timeout = 5000
            device.write(":SOUR:VOLT:LEV 0")
            device.write(":OUTP:STAT OFF")
            device.write(":INP:STAT OFF")
            device.control_ren(6)
            print("✅ Keysight safely disabled.")
        except Exception as e:
            print(f"[❌ ERROR disabling Keysight]: {e}")
        finally:
            if device:
                try: device.close()
                except: pass
            if rm:
                try: rm.close()
                except: pass

def keysight_check_status():
    with bus_lock: 
        rm = None; device = None
        try:
            rm = pyvisa.ResourceManager()
            device = rm.open_resource(VISA_ADDRESS)
            device.timeout = 20
            output_state = device.query(":OUTP:STAT?").strip()
            volt_level = float(device.query(":SOUR:VOLT:LEV?").strip())
            device.control_ren(6)
            return (output_state == "1" or output_state.upper() == "ON"), volt_level
        except:
            return False, 0.0
        finally:
            if device:
                try: device.close()
                except: pass
            if rm:
                try: rm.close()  
                except: pass

def safe_query_curr(device):
    """
    Safe single query of :MEAS:CURR? with a retry and buffer clear.
    Guarantees synchronization of the 'query-response' pair and prevents accumulation of -410.
    """
    last_err = None
    for attempt in range(2):
        try:
            res = device.query(":MEAS:CURR?").split(',')[0]
            return float(res)
        except Exception as e:
            last_err = e
            msg = str(e)
            if ("-410" in msg or "Query INTERRUPTED" in msg
                    or "timeout" in msg.lower() or "VI_ERROR" in msg):
                try:
                    device.clear()
                except Exception:
                    pass
                time.sleep(0.05)
                continue
            raise
    raise RuntimeError(f"Keysight: failed to get a correct response to :MEAS:CURR? ({last_err})")

def check_enter_pressed():
    if os.name == 'nt':
        if msvcrt.kbhit():
            char = msvcrt.getch()
            if char in (b'\r', b'\n'): return True
    return False

def flush_input_buffer():
    if os.name == 'nt':
        while msvcrt.kbhit(): msvcrt.getch()

def calculate_stats(data):
    n = len(data)
    if n == 0: return 0.0, 0.0
    mean = sum(data) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in data) / (n - 1)
        sem = math.sqrt(variance) / math.sqrt(n)
    else:
        sem = 0.0
    return mean, sem

def stop_all_stages(stage_x, stage_y):
    print("\n[⚠️ EMERGENCY STOP] Stopping motors...")
    if stage_x is not None: stage_x.stop()
    if stage_y is not None: stage_y.stop()

def wait_move_interruptible(stage_x, stage_y, target_x_mm=None, target_y_mm=None, interruptible=True):
    flush_input_buffer()
    time_to_sleep = 0.2
    try:
        if target_x_mm is not None and stage_x is not None:
            with bus_lock: curr_x = stage_x.get_position(scale=False) / STEPS_PER_MM
            dist_x = abs(target_x_mm - curr_x)
            time_x = (dist_x / 10.0) + 2.5 if dist_x > 0 else 0
            time_to_sleep = max(time_to_sleep, time_x)
        if target_y_mm is not None and stage_y is not None:
            with bus_lock: curr_y = stage_y.get_position(scale=False) / STEPS_PER_MM
            dist_y = abs(target_y_mm - curr_y)
            time_y = (dist_y / 10.0) + 2.5 if dist_y > 0 else 0
            time_to_sleep = max(time_to_sleep, time_y)
    except:
        time_to_sleep = 3.5
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
            if stable_count >= 4: break
        else:
            stable_count = 0
        last_x, last_y = curr_x, curr_y
        if interruptible and check_enter_pressed():
            with bus_lock: stop_all_stages(stage_x, stage_y)
            raise ScanInterrupted("Movement interrupted by the user!")

def check_is_homed(stage):
    if stage is None: return False
    with bus_lock:
        try: return "homed" in stage.get_status()
        except: return False

def force_stage_velocity(stage, name, min_vel, accel, max_vel):
    if stage is None: return False
    for attempt in range(5):
        try:
            with bus_lock:
                stage.setup_velocity(min_vel, accel, max_vel, scale=False)
                time.sleep(0.4)
                current_params = stage.get_velocity_parameters(scale=False)
            if current_params and abs(current_params[-1] - max_vel) < 100:
                return True
        except: pass
        time.sleep(0.6)
    return False

def generate_aerogel_grid():
    global AEROGEL_LENGTH_CM, AEROGEL_WIDTH_CM, POINTS_LARGE
    len_x_mm = AEROGEL_LENGTH_CM * 10.0
    len_y_mm = AEROGEL_WIDTH_CM * 10.0
    x_offsets = [MARGIN_START_MM + ((len_x_mm - MARGIN_END_MM - MARGIN_START_MM) / (POINTS_LARGE - 1)) * i for i in range(POINTS_LARGE)] if AEROGEL_LENGTH_CM >= 10.0 else [len_x_mm / 2.0]
    y_offsets = [MARGIN_START_MM + ((len_y_mm - MARGIN_END_MM - MARGIN_START_MM) / (POINTS_LARGE - 1)) * i for i in range(POINTS_LARGE)] if AEROGEL_WIDTH_CM >= 10.0 else [len_y_mm / 2.0]
    points = []
    for i, x_off in enumerate(x_offsets):
        current_y_offsets = y_offsets[::-1] if i % 2 != 0 else y_offsets
        for y_off in current_y_offsets:
            abs_x = AEROGEL_START_X + x_off
            abs_y = AEROGEL_START_Y + y_off
            if abs_x <= MAX_TRAVEL_MM and abs_y <= MAX_TRAVEL_MM:
                points.append((abs_x, abs_y))
    return points

def process_wavelength_data(wl, raw_points, i0_val, i0_sem, idark_val, idark_sem, ctrl_val=None, ctrl_sem=None):
    i0_corrected = i0_val - idark_val
    i0_corr_err = math.sqrt(i0_sem**2 + idark_sem**2)
    processed_lines = []
    processed_lines.append(f"\n# --- MATHEMATICAL NORMALIZATION FOR LINE {wl} nm ---")
    processed_lines.append("Wavelength_nm\tPoint_ID\tX_Pos_mm\tY_Pos_mm\tNorm_Current\tNorm_SEM_Error")
    
    first_raw, first_err = None, None
    for idx, x_mm, y_mm, val, sem in raw_points:
        if idx == 1:
            first_raw, first_err = val, sem
        i_corrected = val - idark_val
        i_corr_err = math.sqrt(sem**2 + idark_sem**2)
        if i0_corrected != 0:
            i_norm = i_corrected / i0_corrected
            if i_corrected != 0:
                i_norm_err = abs(i_norm) * math.sqrt((i_corr_err / i_corrected)**2 + (i0_corr_err / i0_corrected)**2)
            else:
                i_norm_err = 0.0
        else:
            i_norm, i_norm_err = 0.0, 0.0
        processed_lines.append(f"{wl}\tNORM_GRID_{idx}\t{x_mm:.3f}\t{y_mm:.3f}\t{i_norm:.6e}\t{i_norm_err:.6e}")
        
    if ctrl_val is not None and first_raw is not None:
        diff_raw = ctrl_val - first_raw
        diff_err = math.sqrt(ctrl_sem**2 + first_err**2)
        if first_raw != 0:
            diff_pct = (diff_raw / abs(first_raw)) * 100.0
            diff_pct_err = (diff_err / abs(first_raw)) * 100.0
        else:
            diff_pct, diff_pct_err = 0.0, 0.0
        processed_lines.append(f"\n# --- DRIFT ANALYSIS FOR {wl} nm (CONTROL vs POINT 1) ---")
        processed_lines.append(f"# Absolute current change: {diff_raw:.6e} ± {diff_err:.6e} A")
        processed_lines.append(f"# Relative drift: {diff_pct:.3f}% ± {diff_pct_err:.3f}%")
        
    processed_lines.append(f"# --- END OF PROCESSING FOR {wl} nm ---\n")
    return "\n".join(processed_lines) + "\n"

class SpectrumSummary:
    def __init__(self):
        self.records = []
    def add_wavelength_summary(self, wl, raw_points, i0_val, i0_sem, idark_val, idark_sem):
        i0_corrected = i0_val - idark_val
        i0_corr_err = math.sqrt(i0_sem**2 + idark_sem**2)
        if i0_corrected == 0:
            self.records.append((wl, 0.0, 0.0))
            return
        wl_transmissions = []
        wl_errors_sq = []
        for idx, x_mm, y_mm, val, sem in raw_points:
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

    def generate_table_text(self):
        lines = []
        lines.append("\n" + "#" * 74)
        lines.append("# FINAL SUMMARY TABLE OF SAMPLE TRANSMITTANCE SPECTRUM")
        lines.append("#" * 74)
        lines.append("Wavelength_nm\tIntegral_Transmittance\tIntegral_SEM_Error")
        for wl, t, err in self.records:
            lines.append(f"{wl:.1f}\t{t:.6e}\t{err:.6e}")
        lines.append("# --- END OF REPORT ---")
        return "\n".join(lines) + "\n"

def run_aerogel_scan(stage_x, stage_y):
    global AEROGEL_LENGTH_CM, AEROGEL_WIDTH_CM
    print("\n" + "="*50)
    print("🚀 SPECTRAL SCANNING (DYNAMIC SIZE)")
    print("="*50)
    
    if not global_devctrl:
        print("❌ Monochromator not connected! Press 5.")
        return
        
    is_on, current_v = keysight_check_status()
    if not is_on:
        print("❌ Keysight is OFF or NOT RESPONDING! Apply voltage first (Option 4).")
        return
        
    sample_name = input("Sample name: ").strip() or "unknown"
    wavelength_list = load_scan_wavelengths()

    try:
        user_l = input(f"Length in cm ({AEROGEL_LENGTH_CM} cm) or Enter: ").strip()
        if user_l: AEROGEL_LENGTH_CM = float(user_l)
        user_w = input(f"Width in cm ({AEROGEL_WIDTH_CM} cm) or Enter: ").strip()
        if user_w: AEROGEL_WIDTH_CM = float(user_w)
    except ValueError:
        print("[⚠️ WARNING] Invalid input. Keeping defaults.")

    grid_points = generate_aerogel_grid()
    if not grid_points or not wavelength_list:
        print("[ERROR] Grid or wavelength list is empty. Aborting.")
        return

    bad_points = [(x, y) for (x, y) in grid_points if not (0 <= x <= MAX_TRAVEL_MM and 0 <= y <= MAX_TRAVEL_MM)]
    if bad_points:
        print(f"❌ {len(bad_points)} points exceed the stage travel range of 0..{MAX_TRAVEL_MM} mm:")
        for (x, y) in bad_points[:5]:
            print(f"   - X={x:.1f}, Y={y:.1f}")
        if len(bad_points) > 5:
            print(f"   ... and {len(bad_points) - 5} more")
        print("   Please decrease the sample size or check MARGIN/AEROGEL_START values.")
        return
        
    spectrum_summary = SpectrumSummary()
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../_data')
    if not os.path.exists(data_dir): os.makedirs(data_dir)
        
    filename = os.path.join(data_dir, f"spectro_final_{sample_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

    create_session_log(f"Scan started: sample={sample_name}, grid_points={len(grid_points)}, wavelengths={len(wavelength_list)}")
    
    print("\n⏳ Step 1/3: Safe and gentle homing of stage motors...")
    with bus_lock:
        if stage_x: stage_x.setup_velocity(0, ACCEL_STEPS, HOMING_SPEED_STEPS, scale=False)
        if stage_y: stage_y.setup_velocity(0, ACCEL_STEPS, HOMING_SPEED_STEPS, scale=False)
    time.sleep(0.1)
    try:
        with bus_lock:
            if stage_x: stage_x.home(direction="-", force=True, sync=False)
            if stage_y: stage_y.home(direction="-", force=True, sync=False)
    except:
        with bus_lock:
            if stage_x: stage_x.home(force=True, sync=False)
            if stage_y: stage_y.home(force=True, sync=False)
    time.sleep(15.0)  
    wait_move_interruptible(stage_x, stage_y)
    print("✅ Stage base successfully zeroed.")
    
    force_stage_velocity(stage_x, "X", 0, ACCEL_STEPS, SCAN_SPEED_STEPS)
    force_stage_velocity(stage_y, "Y", 0, ACCEL_STEPS, SCAN_SPEED_STEPS)

    first_x = float(grid_points[0][0])
    first_y = float(grid_points[0][1])

    print(f"\n⏳ Step 2/3: Moving to initial point ({first_x:.2f}, {first_y:.2f}) mm...")
    with bus_lock:
        if stage_x: stage_x.move_to(int(first_x * STEPS_PER_MM), scale=False)
        time.sleep(0.4) 
        if stage_y: stage_y.move_to(int(first_y * STEPS_PER_MM), scale=False)
    wait_move_interruptible(stage_x, stage_y, target_x_mm=first_x, target_y_mm=first_y)

    print(f"\n📊 MAP GRID CONFIGURATION:")
    print(f"  🔹 Total measurement points: {len(grid_points)}")
    print(f"  🔹 Physical size calculation: {AEROGEL_LENGTH_CM} x {AEROGEL_WIDTH_CM} cm")

    flush_input_buffer()
    if not is_confirmed(input("\nPress [Enter] to START the snake-path scan, or any key to CANCEL: ")): 
        print("[🛑 CANCEL] Returning to main menu.")
        create_session_log("Scanning canceled by the user before launch.")
        return

    rm = None
    device = None
    try:
        rm = pyvisa.ResourceManager()
        device = rm.open_resource(VISA_ADDRESS)
        device.timeout = 5000
        try:
            device.clear()
        except Exception:
            pass
    except Exception as ke:
        print(f"[❌ FAILED TO OPEN KEYSIGHT VISA SESSION]: {ke}")
        try:
            if device: device.close()
        except: pass
        try:
            if rm: rm.close()
        except: pass
        return

    try:
        with open(filename, mode='w', encoding='utf-8') as f:
            f.write("# Comprehensive autonomous experimental log\n")
            f.write(f"# Aerogel block dimensions: {AEROGEL_LENGTH_CM}x{AEROGEL_WIDTH_CM} cm\n")
            f.write(f"# Voltage: {current_v} V\n")
            f.write("Wavelength_nm\tPoint_Type\tX_Pos_mm\tY_Pos_mm\tMean_Current(A)\tSEM_Error(A)\n")
            
            for wl in wavelength_list:
                print(f"\n🔮 WORKING LINE: {wl} nm")
                create_session_log(f"  Line {wl} nm: start")
                mono_set_wavelength(wl)
                mono_shutter(open_shutter=True)
                current_wl_raw_data = [] 
                
                for idx, (x_mm, y_mm) in enumerate(grid_points, 1):
                    print(f"  📍 [{wl}nm] Point {idx}/{len(grid_points)} -> X: {x_mm:.1f}, Y: {y_mm:.1f}")
                    with bus_lock:
                        if stage_x: stage_x.move_to(int(x_mm * STEPS_PER_MM), scale=False)
                        if stage_y: stage_y.move_to(int(y_mm * STEPS_PER_MM), scale=False)
                    wait_move_interruptible(stage_x, stage_y, target_x_mm=x_mm, target_y_mm=y_mm)
                    time.sleep(STABILIZATION_DELAY)
                    
                    current_readings = []
                    print(f"  [Measurement] Collecting currents... ", end="", flush=True)
                    
                    with bus_lock:
                        for _ in range(NUM_MEASUREMENTS):
                            try:
                                current_readings.append(safe_query_curr(device))
                            except Exception as e:
                                print(f"\n[⚠️ Keysight warn] {e}")
                            time.sleep(DELAY_BETWEEN_READS)
                    
                    if len(current_readings) == 0:
                        f.write(f"{wl}\tRAW_GRID_{idx}\t{x_mm:.3f}\t{y_mm:.3f}\tNaN\tNaN\n")
                        f.flush()
                        print("⚠️ All current measurements failed — NaN recorded.")
                        current_wl_raw_data.append((idx, x_mm, y_mm, float('nan'), float('nan')))
                    else:
                        mean_i, sem_i = calculate_stats(current_readings)
                        f.write(f"{wl}\tRAW_GRID_{idx}\t{x_mm:.3f}\t{y_mm:.3f}\t{mean_i:.6e}\t{sem_i:.6e}\n")
                        f.flush()
                        print(f"Done. Current = {mean_i:.5e} A")
                        current_wl_raw_data.append((idx, x_mm, y_mm, mean_i, sem_i))

                print(f"\n🔄 [{wl}nm] Returning to FIRST point for control verification...")
                with bus_lock:
                    if stage_x: stage_x.move_to(int(first_x * STEPS_PER_MM), scale=False)
                    if stage_y: stage_y.move_to(int(first_y * STEPS_PER_MM), scale=False)
                wait_move_interruptible(stage_x, stage_y, target_x_mm=first_x, target_y_mm=first_y)
                time.sleep(STABILIZATION_DELAY)

                current_readings = []
                print(f"  [Measurement] Collecting control current... ", end="", flush=True)
                with bus_lock:
                    for _ in range(NUM_MEASUREMENTS):
                        try:
                            current_readings.append(safe_query_curr(device))
                        except Exception as e:
                            print(f"\n[⚠️ Keysight warn] {e}")
                        time.sleep(DELAY_BETWEEN_READS)

                if len(current_readings) == 0:
                    ctrl_mean, ctrl_sem = float('nan'), float('nan')
                    f.write(f"{wl}\tCONTROL\t{first_x:.3f}\t{first_y:.3f}\tNaN\tNaN\n")
                    print("⚠️ Control current: all measurements failed — NaN.")
                else:
                    ctrl_mean, ctrl_sem = calculate_stats(current_readings)
                    f.write(f"{wl}\tCONTROL\t{first_x:.3f}\t{first_y:.3f}\t{ctrl_mean:.6e}\t{ctrl_sem:.6e}\n")
                    print(f"Done. Control Current = {ctrl_mean:.5e} A")
                f.flush()

                print(f"\n➡️ Moving to X=290 mm for reference beam measurement I_0...")
                with bus_lock:
                    if stage_x: stage_x.move_to(int(290.0 * STEPS_PER_MM), scale=False)
                wait_move_interruptible(stage_x, stage_y, target_x_mm=290.0, target_y_mm=first_y)
                time.sleep(STABILIZATION_DELAY)
                
                current_readings = []
                print(f"  [Measurement] Collecting reference current I_0... ", end="", flush=True)
                with bus_lock:
                    for _ in range(NUM_MEASUREMENTS):
                        try:
                            current_readings.append(safe_query_curr(device))
                        except Exception as e:
                            print(f"\n[⚠️ Keysight warn] {e}")
                        time.sleep(DELAY_BETWEEN_READS)
                
                if len(current_readings) == 0:
                    i0_mean, i0_sem = float('nan'), float('nan')
                    f.write(f"{wl}\tRAW_I_0\t290.000\t{first_y:.3f}\tNaN\tNaN\n")
                    print("⚠️ Reference current I_0: all measurements failed — NaN.")
                else:
                    i0_mean, i0_sem = calculate_stats(current_readings)
                    f.write(f"{wl}\tRAW_I_0\t290.000\t{first_y:.3f}\t{i0_mean:.6e}\t{i0_sem:.6e}\n")
                    print(f"Done. Reference Current I_0 = {i0_mean:.5e} A")
                f.flush()

                mono_shutter(open_shutter=False)
                time.sleep(0.5)
                
                current_readings = []
                print(f"  [Measurement] Collecting dark current I_dark... ", end="", flush=True)
                with bus_lock:
                    for _ in range(NUM_MEASUREMENTS):
                        try:
                            current_readings.append(safe_query_curr(device))
                        except Exception as e:
                            print(f"\n[⚠️ Keysight warn] {e}")
                        time.sleep(DELAY_BETWEEN_READS)
                
                if len(current_readings) == 0:
                    idark_mean, idark_sem = float('nan'), float('nan')
                    f.write(f"{wl}\tRAW_I_DARK\t290.000\t{first_y:.3f}\tNaN\tNaN\n")
                    print("⚠️ Dark current: all measurements failed — NaN.")
                else:
                    idark_mean, idark_sem = calculate_stats(current_readings)
                    f.write(f"{wl}\tRAW_I_DARK\t290.000\t{first_y:.3f}\t{idark_mean:.6e}\t{idark_sem:.6e}\n")
                    print(f"Done. Dark Current I_dark = {idark_mean:.5e} A")
                f.flush()

                math_output = process_wavelength_data(wl, current_wl_raw_data, i0_mean, i0_sem, idark_mean, idark_sem, ctrl_mean, ctrl_sem)
                f.write(math_output)
                spectrum_summary.add_wavelength_summary(wl, current_wl_raw_data, i0_mean, i0_sem, idark_mean, idark_sem)
                f.flush()
                create_session_log(f"  Line {wl} nm: complete")
                
            f.write(spectrum_summary.generate_table_text())
            f.flush()
            create_session_log("Scanning complete (all lines).")
            print("\n🎵 All lines successfully processed")
            play_finish_signal()
    except Exception as e:
        print(f"[❌ CRITICAL DATA LOGGING FAILURE]: {e}")
        create_session_log(f"Critical failure in run_aerogel_scan: {e}")
    finally:
        try:
            print("\n🅿️ Parking stage at (10.0, 10.0) mm...")
            with bus_lock:
                if stage_x: stage_x.move_to(int(10.0 * STEPS_PER_MM), scale=False)
                time.sleep(0.4)
                if stage_y: stage_y.move_to(int(10.0 * STEPS_PER_MM), scale=False)
            wait_move_interruptible(stage_x, stage_y, target_x_mm=10.0, target_y_mm=10.0, interruptible=False)
            print("🎉 Stage successfully parked.")
        except Exception as park_ex:
            print(f"⚠️ Auto-parking error: {park_ex}")

        try:
            if global_devctrl is not None:
                mono_shutter(open_shutter=False)
        except Exception:
            pass
        try:
            if device is not None:
                device.close()
        except Exception:
            pass
        try:
            if rm is not None:
                rm.close()
        except Exception:
            pass

def keysight_menu():
    while True:
        is_on, current_v = keysight_check_status()
        print("\n--- ⚡ KEYSIGHT PARAMETERS CONTROL ---")
        print(f"Output status: " + ("🟢 ON" if is_on else "🔴 OFF/NO CONNECTION") + f" | V: {current_v} V")
        print("1 - Set working voltage\n3 - DISABLE channel\n0 - Back")
        choice = input("Select command: ").strip()
        if choice == "1": 
            keysight_set_voltage(input("Voltage (V): ").strip(), False)
        elif choice == "3": 
            keysight_disable()
        elif choice == "0": 
            break

def main():
    global AEROGEL_LENGTH_CM, AEROGEL_WIDTH_CM, global_devctrl

    # --- Sound check: python ...py --test-sound ---
    if len(sys.argv) > 1 and sys.argv[1] == "--test-sound":
        test_finish_signal()
        return

    stage_x, stage_y = None, None
    print("=== STARTING AUTONOMOUS SPECTRAL SCANNING SYSTEM ===")

    print("\n" + "!" * 53)
    print("⚠️  ATTENTION! CRITICALLY IMPORTANT FOR BEAM STABILITY:")
    print("👉 Before beginning any measurements, the source lamp")
    print("   MUST BE WARMED UP FOR AT LEAST 45 MINUTES!")
    print("!" * 53)
    flush_input_buffer()
    input("Acknowledge lamp warm-up or press [Enter] to continue... ")

    create_session_log("Initializing station hardware equipment.")

    try:
        last_tl_err = None
        tl_connected = False
        for tl_attempt in range(3):
            try:
                with bus_lock:
                    stage_x = Thorlabs.KinesisMotor(HORIZONTAL_STAGE_SN, scale="step")
                    stage_y = Thorlabs.KinesisMotor(VERTICAL_STAGE_SN, scale="step")
                    stage_x.setup_velocity(0, ACCEL_STEPS, SCAN_SPEED_STEPS, scale=False)
                    stage_y.setup_velocity(0, ACCEL_STEPS, SCAN_SPEED_STEPS, scale=False)
                tl_connected = True
                break
            except Exception as tl_err:
                last_tl_err = tl_err
                stage_x, stage_y = None, None
                msg = str(tl_err)
                if ("Device Not Found" in msg or "D2XX" in msg) and tl_attempt < 2:
                    time.sleep(0.7)
                    continue
                break

        if tl_connected:
            print("✅ Thorlabs linear stages connected.")
        else:
            print(f"⚠️ Thorlabs stages NOT CONNECTED: {last_tl_err}")
            print("   Please check sequentially:")
            print("     1) 24V Power supply of Kinesis controllers is turned ON (green LED on the unit).")
            print("     2) USB Cables of both controllers are connected securely on both sides.")
            print("     3) Controllers are not currently occupied by Kinesis / Thorlabs APT software (close them if open).")
            print("     4) Try reconnecting the USB cables.")
            print("   The menu will still function, but options 1, 2, and 3 will be unavailable.")

        rm = device = None
        try:
            with bus_lock:
                rm = pyvisa.ResourceManager()
                device = None
                last_err = None
                for attempt in range(3):
                    try:
                        device = rm.open_resource(VISA_ADDRESS)
                        idn = device.query('*IDN?').strip()
                        break
                    except Exception as e:
                        last_err = e
                        msg = str(e)
                        if "-1073807264" in msg or "NCIC" in msg or "controller in charge" in msg:
                            try: device.clear()
                            except Exception: pass
                            try: device.close()
                            except Exception: pass
                            device = None
                            time.sleep(0.5)
                            continue
                        raise
                if device is None:
                    raise last_err if last_err else RuntimeError("Keysight: failed to open communication session")
            print("✅ Keysight Electrometer successfully connected.")
        except Exception as ke:
            msg = str(ke)
            if "-1073807264" in msg or "NCIC" in msg or "controller in charge" in msg:
                print("⚠️ Keysight Electrometer NOT CONNECTED: device is switched OFF or occupied by another software process.")
                print("   Please check sequentially:")
                print("     1) Power toggle switch on front panel of B2987B is ON (green indicator lit up).")
                print("     2) Keysight Connection Expert / Interactive IO is not holding a connection instance to this device.")
                print("     3) No other active instances of this program are running simultaneously.")
            else:
                print(f"⚠️ Keysight Electrometer NOT CONNECTED: {ke}")
        finally:
            try:
                if device is not None: device.close()
            except: pass
            try:
                if rm is not None: rm.close()
            except: pass

        if global_devctrl is not None:
            print("✅ Communication connection with SOL Instruments monochromator is active.")
        else:
            print("⚠️ SOL Instruments monochromator NOT CONNECTED. Press 5 in menu to establish connection.")

        while True:
            time.sleep(0.1)
            with bus_lock:
                pos_x = (stage_x.get_position(scale=False) / STEPS_PER_MM) if stage_x else 0.0
                pos_y = (stage_y.get_position(scale=False) / STEPS_PER_MM) if stage_y else 0.0
            mono_status = "🟢 CONNECTED" if global_devctrl is not None else "🔴 DISCONNECTED [Press 5]"

            stages_ok = (stage_x is not None) and (stage_y is not None)
            pos_line = (f"📍 Carriage current position coordinates -> X: {pos_x:.3f} mm | Y: {pos_y:.3f} mm"
                        if stages_ok else "📍 Linear stages: 🔴 NOT CONNECTED")

            print(f"\n=== SPECTRO-STATION MAIN CONTROL INTERFACE ===")
            print(pos_line)
            print(f"🔮 Monochromator SOL MS3504i status: {mono_status}")
            print("-----------------------------------------------------")
            if stages_ok:
                print("1 - Physical axis Homing procedure\n2 - RUN FULL MATRIX COMPLEX SCANNING SCHEDULE\n3 - Manual stage carriage positioning\n4 - Keysight parameters control menu\n5 - Connect SOL Instruments monochromator\n0 - Exit script and close session logs")
            else:
                print("1 - [unavailable: Thorlabs hardware missing]\n2 - [unavailable: Thorlabs hardware missing]\n3 - [unavailable: Thorlabs hardware missing]\n4 - Keysight parameters control menu\n5 - Connect SOL Instruments monochromator\n0 - Exit script and close session logs")

            choice = input("\nEnter command: ").strip()
            if choice == "1":
                if stage_x is None or stage_y is None:
                    print("⚠️ Thorlabs stages not connected — Homing sequence cannot be performed.")
                    continue
                axis = select_axis()
                if axis and is_confirmed(input("Execute Homing routine? (Enter=Yes): ")):
                    with bus_lock:
                        if stage_x: stage_x.setup_velocity(0, ACCEL_STEPS, HOMING_SPEED_STEPS, scale=False)
                        if stage_y: stage_y.setup_velocity(0, ACCEL_STEPS, HOMING_SPEED_STEPS, scale=False)
                    try:
                        with bus_lock:
                            if axis in ['x', 'both'] and stage_x: stage_x.home(direction="-", force=True, sync=False)
                            if axis in ['y', 'both'] and stage_y: stage_y.home(direction="-", force=True, sync=False)
                    except:
                        with bus_lock:
                            if axis in ['x', 'both'] and stage_x: stage_x.home(force=True, sync=False)
                            if axis in ['y', 'both'] and stage_y: stage_y.home(force=True, sync=False)
                    wait_move_interruptible(stage_x, stage_y)
                    print("Coordinate axes successfully zeroed.")
            elif choice == "2":
                if stage_x is None or stage_y is None:
                    print("⚠️ Thorlabs stages not connected — Scanning schedule cannot be initiated.")
                    continue
                run_aerogel_scan(stage_x, stage_y)
            elif choice == "3":
                if stage_x is None or stage_y is None:
                    print("⚠️ Thorlabs stages not connected — Manual position manipulation is disabled.")
                    continue
                axis = select_axis()
                if axis:
                    if global_devctrl is not None:
                        print("🔮 Automatically opening shutter for target beam aiming...")
                        mono_shutter(open_shutter=True)
                    val_x = input("Target Coordinate X (mm): ").strip()
                    val_y = input("Target Coordinate Y (mm): ").strip()
                    tx = float(val_x) if val_x else None
                    ty = float(val_y) if val_y else None
                    with bus_lock:
                        if tx and stage_x: stage_x.move_to(int(tx * STEPS_PER_MM), scale=False)
                        if ty and stage_y: stage_y.move_to(int(ty * STEPS_PER_MM), scale=False)
                    wait_move_interruptible(stage_x, stage_y, target_x_mm=tx, target_y_mm=ty)
                    print("[DONE] Manual movement target reached.")
                    if global_devctrl is not None:
                        mono_shutter(open_shutter=False)
            elif choice == "4":
                probe_ok = False
                probe_err = None
                _rm = _dev = None
                try:
                    with bus_lock:
                        _rm = pyvisa.ResourceManager()
                        _dev = _rm.open_resource(VISA_ADDRESS)
                        _dev.timeout = 2000
                        _dev.query('*IDN?')
                        probe_ok = True
                except Exception as _e:
                    probe_err = _e
                finally:
                    try:
                        if _dev is not None: _dev.close()
                    except: pass
                    try:
                        if _rm is not None: _rm.close()
                    except: pass

                if not probe_ok:
                    msg = str(probe_err) if probe_err else ""
                    if "-1073807264" in msg or "NCIC" in msg or "controller in charge" in msg:
                        print("⚠️ Keysight Electrometer is not responding (NCIC control fault).")
                        print("   Please check: 1) power toggle switch of B2987B is ON;")
                        print("              2) Keysight Connection Expert is not occupying the active device channel.")
                        print("   The control menu will open, but hardware queries/commands will fail until resolution.")
                    else:
                        print(f"⚠️ Keysight not responding: {probe_err}")
                keysight_menu()
            elif choice == "5":
                print("Establishing communication link with MS3504i device controller...")
                if mono_connect():
                    print("✅ SOL Instruments monochromator successfully initialized!")
                    create_session_log("Monochromator device successfully connected.")
                else:
                    print("❌ Failed to establish communication link with MS3504i monochromator hardware module.")
                    print("   Please check sequentially:")
                    print("     1) The hardware unit is powered ON (toggle switch on back panel, indicators on front panel).")
                    print("     2) Ethernet communication network cable between PC and monochromator is connected on both ends.")
                    print("     3) PC Network adapter settings share the exact identical subnet mask and gateway domain as the hardware unit.")
                    print("     4) Device channel is not currently occupied by alternative software suites (SOL Instruments, MS3504i software).")
                    create_session_log("Connection failure to MS3504i monochromator device.")
            elif choice == "0":
                create_session_log("Standard safe script closing initiated by user command.")
                print("Disabling Keysight electrometric power outputs...")
                break
    except Exception as err:
        print("\n🛑 CRITICAL SYSTEM EXECUTION EXCEPTION OCCURRED:")
        import traceback
        traceback.print_exc()
        input("\nPress Enter key to close this command terminal window...")
    finally:
        print("\nCleaning up open handles, active instances, and resources before final shutdown termination...")

        # Stop audio signal if it is still playing
        stop_finish_signal()

        if global_devctrl is not None:
            try:
                mono_shutter(open_shutter=False)
            except Exception:
                pass

        try:
            keysight_disable()
        except Exception as e:
            print(f"[⚠️ Failed to safely shut down Keysight outputs]: {e}")

        with bus_lock:
            if stage_x is not None:
                try:
                    stage_x.stop()
                except Exception:
                    pass
                try:
                    stage_x.close()
                except Exception as e:
                    print(f"[⚠️ Exception on closing stage_x handle instance]: {e}")
            if stage_y is not None:
                try:
                    stage_y.stop()
                except Exception:
                    pass
                try:
                    stage_y.close()
                except Exception as e:
                    print(f"[⚠️ Exception on closing stage_y handle instance]: {e}")
            if global_devctrl is not None:
                try:
                    global_devctrl.FreeDevice()
                except Exception as e:
                    print(f"[⚠️ Exception on calling FreeDevice monochromator API method]: {e}")
                global_devctrl = None

        try:
            rm_cleanup = pyvisa.ResourceManager()
            for res in rm_cleanup.list_opened_resources():
                try:
                    res.close()
                except Exception:
                    pass
            rm_cleanup.close()
        except Exception:
            pass
        try:
            pyvisa.highlevel.ResourceManager._instances.clear()
        except Exception:
            pass

        try:
            create_session_log("Execution session successfully terminated (clean or post-abort fallback).")
        except Exception:
            pass

        print("All hardware links to the USB communication system bus safely closed. Secure script exit accomplished.")

if __name__ == "__main__":
    main()