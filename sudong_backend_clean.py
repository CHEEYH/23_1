
"""
Sudong V4 - Screwdriver Monitor & Controller

Purpose:
This program controls and monitors an automated screwdriver system.
It communicates with:
1. A Sudong screwdriver controller
2. A bit selector device
3. A local client application through a TCP command server

Main functions:
- Connect to the screwdriver and receive live tightening data
- Connect to the bit selector and verify the correct bit is picked
- Load screw recipes from JSON files
- Calculate preset parameters based on screw size, length, and torque
- Write tightening presets to the screwdriver without interrupting live monitoring
- Start and stop screw recording sessions
- Detect tightening result (OK / NG) from live packets
- Save torque and speed graphs for each screw
- Export collected screw results to CSV files
- Show a compact Tkinter corner UI with device status and result display
- Send standardized status/result messages back to an external client

In short:
This script is the main backend + UI controller for a screwdriver station.
It manages recipe loading, bit validation, live monitoring, result logging,
preset writing, and communication between the hardware and external software.
"""

import os
import re
import csv
import json
import time
import socket
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple

import tkinter as tk
import tkinter.font as tkfont

import matplotlib
import matplotlib.pyplot as plt
import ctypes
matplotlib.use("Agg")

# =========================================================
# CONFIG
# =========================================================
SCREW_HOST = "192.168.1.18"
SCREW_PORT = 1200
SCREW_TIMEOUT = 1.0

BIT_SELECTOR_HOST    = "192.168.1.17"
BIT_SELECTOR_PORT    = 1200
BIT_SELECTOR_TIMEOUT = 1.0

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5001

RECIPE_ROOT_FOLDER = (
    r"C:\Users\PC_AI_DS\Desktop"
    r"\Xlent\23_1\recipes"
)
OUTPUT_FOLDER = (
    r"C:\Users\PC_AI_DS\Desktop"
    r"\Xlent\23_1\Collected"
)

ENABLE_STREAM_COMMAND = b"\x01\x00"
ENABLE_STREAM_DATA    = b"\x01\x00"
STOP_COMMAND          = b"\x05\x00"
# STOP_DATA             = b"\x00"

DEFAULT_GROUP_NO    = 1
DEFAULT_TORQUE_UNIT = 0

SELECTOR_MATCH_WAIT_SEC    = None
SELECTOR_ALL_BACK_WAIT_SEC = 10.0

DEBUG          = True
DEBUG_RAW_RX   = False
DEBUG_LIVE_PKT = False
DEBUG_SELECTOR = True

SIZE_TO_SELECTOR_BIT = {
    "M2": 1, "M3": 2, "M4": 3, "M5": 4, "M6": 5, "M8": 6,
}

THREAD_PITCH_MM = {
    "M2": 0.40, "M2.5": 0.45, "M3": 0.50, "M4": 0.70,
    "M5": 0.80, "M6": 1.00, "M8": 1.25,
}

CUSTOM_DEFAULT_TOTAL_ANGLE = 720
CUSTOM_STEP1_ANGLE = 30
CUSTOM_STEP2_RATIO = 0.70
CUSTOM_STEP3_RATIO = 0.15
CUSTOM_SPEED_STEP1 = 100
CUSTOM_SPEED_STEP2 = 200
CUSTOM_SPEED_STEP3 = 150
CUSTOM_SPEED_STEP4 = 100
PRESET_STEP_SETTLE_SEC = 0.15
PRESET_ACK_RETRIES = 2


# =========================================================
# GLOBAL STATE
# =========================================================
data_lock         = threading.Lock()
preset_write_lock = threading.Lock()
selector_lock     = threading.RLock()
selector_condition = threading.Condition(selector_lock)

# ── preset-write in-progress flag (suppresses disconnect alert) ──
_preset_writing = False

current_product_id   = ""
current_recipe_path  = ""
current_recipe_name  = ""

all_recipe_screws  = []
current_screw_index = -1

current_size         = ""
current_length       = ""
current_torque       = 0.0
current_screw_count  = 0
current_screw_block_id   = ""
current_screw_block_name = ""

session_product_id    = ""
session_csv_path      = ""
session_started_at    = ""
recipe_sequence_active = False
current_recipe_set_no  = 0
recipe_set_counters    = {}
ui_root = None

recording      = False
latest_packet  = None
client_conn    = None

current_cycle_torque  = []
current_cycle_speed   = []
current_cycle_packets = []

result_rows = []

prev_tightened_state = None
screw_counter   = 0
live_worker     = None
selector_worker = None
server_thread   = None

screwdriver_connected          = False
last_screwdriver_status_text   = "DISCONNECTED"
screwdriver_seen_connected     = False
screwdriver_disconnect_alerted = False

selector_connected       = False
last_selector_status_text = "DISCONNECTED"

stable_zero_speed_count = 0
last_locking_angle      = 0
cycle_completed         = False

latest_selector_status      = None
latest_selector_bits        = [None, None, None, None, None, None]
current_expected_selector_bit  = None
current_wrong_selector_bits    = set()
current_selector_bit           = None
current_missing_selector_bits  = set()
selector_has_been_correct        = False
selector_missing_during_recording = False
selector_missing_error_sent       = False
selector_expected_error           = False
selector_stop_wait_active         = False
selector_stop_wait_message        = ""
selector_buzzer_active            = False

# selector change confirmation state
selector_last_stable_bits    = None
selector_pending_bits        = None
selector_pending_same_count  = 0

corner_monitor = None

# =========================================================
# BUZZER COMMANDS
# =========================================================
BUZZER_ON_FRAME  = bytes.fromhex("55 AA 07 02 11 00 01 23 B2 0D 0A")
BUZZER_OFF_FRAME = bytes.fromhex("55 AA 07 02 11 00 00 E2 72 0D 0A")

# send once when selector connects / reconnects
READ_SELECTOR_STATUS_ON_CONNECT_FRAME = bytes.fromhex(
    "55 AA 07 02 10 00 01 72 72 0D 0A"
)

def wait_for_selector_event(
    expected_bit: int,
    timeout_sec: Optional[float] = None,
    previous_wrong_bits: Optional[set] = None,
):
    """
    Return:
      ("OK", expected_bit, active_wrong_bits)
      ("WRONG", wrong_bit, active_wrong_bits)   # only for a newly appeared wrong bit
      ("CLEAR", None, [])                       # all wrong bits released
      ("TIMEOUT", None, active_wrong_bits)
    """
    expected_bit = int(expected_bit)
    if not (1 <= expected_bit <= 6):
        raise ValueError(f"Expected selector bit out of range: {expected_bit}")

    seen_wrong_bits = set(previous_wrong_bits or set())
    deadline = None if timeout_sec is None else (time.time() + timeout_sec)

    with selector_condition:
        while True:
            bits = latest_selector_bits[:]
            active_bits = [i + 1 for i, v in enumerate(bits) if v == 1]
            active_wrong_bits = [b for b in active_bits if b != expected_bit]

            # keep only still-active wrong bits
            seen_wrong_bits &= set(active_wrong_bits)

            # correct bit taken and no wrong bits active
            if expected_bit in active_bits and not active_wrong_bits:
                return ("OK", expected_bit, active_wrong_bits)

            # new wrong bit appears
            new_wrong_bits = [b for b in active_wrong_bits if b not in seen_wrong_bits]
            if new_wrong_bits:
                wrong_bit = new_wrong_bits[0]
                seen_wrong_bits.add(wrong_bit)
                return ("WRONG", wrong_bit, active_wrong_bits)

            # previously wrong, now all wrong bits cleared
            if previous_wrong_bits and not active_wrong_bits:
                return ("CLEAR", None, [])

            if deadline is None:
                selector_condition.wait(timeout=0.2)
                continue

            remaining = deadline - time.time()
            if remaining <= 0:
                return ("TIMEOUT", None, active_wrong_bits)

            selector_condition.wait(timeout=min(remaining, 0.2))

def send_buzzer_frame(frame: bytes):
    global selector_worker

    worker = selector_worker
    if worker is None or not worker.is_alive():
        log_error("[BUZZER] selector worker not running")
        return False

    client = getattr(worker, "client", None)
    if client is None or client.sock is None:
        log_error("[BUZZER] selector client not connected")
        return False

    try:
        with selector_lock:
            client.send_frame(frame)
        log_debug(f"[BUZZER] sent: {frame.hex(' ').upper()}")
        return True
    except Exception as e:
        log_error(f"[BUZZER] send failed: {e}")
        return False

def send_buzzer_on():
    return send_buzzer_frame(BUZZER_ON_FRAME)

def send_buzzer_off():
    return send_buzzer_frame(BUZZER_OFF_FRAME)

def sync_selector_buzzer(force: bool = False):
    """Keep buzzer in sync with current selector error/wait states."""
    global selector_buzzer_active

    with selector_lock:
        bits = latest_selector_bits[:]
        expected_bit = current_expected_selector_bit
        wrong_bits = set(current_wrong_selector_bits)
        missing_bits = set(current_missing_selector_bits)
        stop_wait_active = bool(selector_stop_wait_active)
        expected_error = bool(selector_expected_error)

    active_bits = {i + 1 for i, v in enumerate(bits) if v == 1}

    should_buzz = False
    if wrong_bits and any(b in active_bits for b in wrong_bits):
        should_buzz = True
    elif missing_bits and any(b in active_bits for b in missing_bits):
        should_buzz = True
    elif stop_wait_active and bool(active_bits):
        should_buzz = True
    elif expected_error and expected_bit is not None and expected_bit not in active_bits:
        should_buzz = True

    if force or should_buzz != selector_buzzer_active:
        ok = send_buzzer_on() if should_buzz else send_buzzer_off()
        if ok:
            selector_buzzer_active = should_buzz

    return should_buzz



def send_selector_read_request():
    """
    Send one selector read request immediately.
    Used for connect/reconnect and confirm-read after bit change detected.
    """
    global selector_worker

    worker = selector_worker
    if worker is None or not worker.is_alive():
        log_error("[SELECTOR] worker not running for read request")
        return False

    client = getattr(worker, "client", None)
    if client is None or client.sock is None:
        log_error("[SELECTOR] client not connected for read request")
        return False

    try:
        with selector_lock:
            client.send_frame(cmd_read_selector_status())
        log_debug("[SELECTOR] Sent read-status request")
        return True
    except Exception as e:
        log_error(f"[SELECTOR] read request send failed: {e}")
        return False


def send_selector_read_on_connect():
    global selector_worker

    worker = selector_worker
    if worker is None or not worker.is_alive():
        log_error("[SELECTOR] worker not running for read-on-connect")
        return False

    client = getattr(worker, "client", None)
    if client is None or client.sock is None:
        log_error("[SELECTOR] client not connected for read-on-connect")
        return False

    try:
        with selector_lock:
            client.send_frame(READ_SELECTOR_STATUS_ON_CONNECT_FRAME)
        log_debug("[SELECTOR] Sent read-status-on-connect frame")
        return True
    except Exception as e:
        log_error(f"[SELECTOR] read-on-connect send failed: {e}")
        return False


# =========================================================
# DEBUG HELPERS
# =========================================================
def log_debug(msg: str):
    if DEBUG:
        print(msg)

def log_error(msg: str):
    print(msg)

def popup_error(title: str, message: str):
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except Exception:
        print(f"[POPUP_FALLBACK] {title}: {message}")

def async_popup_error(title: str, message: str):
    def _show():
        popup_error(title, message)
    try:
        threading.Thread(target=_show, daemon=True).start()
    except Exception:
        popup_error(title, message)


# =========================================================
# SCREWDRIVER NOTIFICATIONS
# =========================================================
def notify_screwdriver_connected():
    global screwdriver_seen_connected, screwdriver_disconnect_alerted
    was_lost = screwdriver_disconnect_alerted
    screwdriver_seen_connected     = True
    screwdriver_disconnect_alerted = False
    try:
        send_result_to_client_text("INFO,SCREWDRIVER_CONNECTED")
    except Exception:
        pass
    if was_lost:
        log_debug("[LIVE] Screwdriver connection restored")

def notify_screwdriver_disconnected(reason: str):
    global screwdriver_disconnect_alerted
    # ── Do NOT alert while a preset write is in progress ──
    if _preset_writing:
        return
    reason_text = str(reason or "Disconnected")
    if not screwdriver_seen_connected:
        return
    if screwdriver_disconnect_alerted:
        return
    screwdriver_disconnect_alerted = True
    try:
        send_result_to_client_text("ERROR,SCREWDRIVER_DISCONNECTED")
    except Exception:
        pass
    async_popup_error(
        "Screwdriver Disconnected",
        f"Screwdriver connection lost.\n\nReason: {reason_text}",
    )


def notify_selector_connected():
    try:
        send_result_to_client_text("INFO,SELECTOR_CONNECTED")
    except Exception:
        pass


def notify_selector_disconnected():
    try:
        send_result_to_client_text("ERROR,SELECTOR_DISCONNECTED")
    except Exception:
        pass


# =========================================================
# CRC / FRAME HELPERS
# =========================================================
def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF

def append_crc(frame_wo_crc: bytes) -> bytes:
    crc = crc16_modbus(frame_wo_crc)
    return frame_wo_crc + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

def build_frame(command: bytes, data: bytes = b"") -> bytes:
    if len(command) != 2:
        raise ValueError("command must be exactly 2 bytes")
    length  = 1 + 2 + len(data) + 2
    payload = b"\x55\xAA" + bytes([length]) + command + data
    return append_crc(payload) + b"\x0D\x0A"

def verify_frame(frame: bytes) -> bool:
    if len(frame) < 9:                    return False
    if frame[0:2] != b"\x55\xAA":        return False
    if frame[-2:] != b"\x0D\x0A":        return False
    recv_crc = frame[-4] | (frame[-3] << 8)
    return recv_crc == crc16_modbus(frame[:-4])

def extract_frames(buffer: bytes) -> Tuple[List[bytes], bytes]:
    frames = []
    i = 0
    while i <= len(buffer) - 9:
        if buffer[i] == 0x55 and buffer[i + 1] == 0xAA:
            length = buffer[i + 2]
            total  = 2 + length + 2
            if i + total <= len(buffer):
                frame = buffer[i:i + total]
                if frame[-2:] == b"\x0D\x0A":
                    frames.append(frame)
                    i += total
                    continue
            else:
                break
        i += 1
    return frames, buffer[i:]

def u16_le(data: bytes, offset: int) -> int:
    return data[offset] | (data[offset + 1] << 8)

def u16_to_le_bytes(value: int) -> bytes:
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


# =========================================================
# HELPER CONVERSIONS
# =========================================================
def torque_unit_text(v: int) -> str:
    return "kgf.cm" if v == 0 else "N.m"

def torque_from_raw(raw: int, unit: int) -> float:
    return raw / 100.0 if unit == 0 else raw / 1000.0

def encode_torque_value(torque: float, torque_unit: int) -> int:
    return int(round(torque * 100)) if torque_unit == 0 else int(round(torque * 1000))

def direction_text(v: int) -> str:
    return {0: "Forward", 1: "Reverse"}.get(v, f"?({v})")

def completed_text(v: int) -> str:
    return {0: "Not Done", 1: "Group Done", 2: "All Done"}.get(v, f"?({v})")

def tightened_state_text(v: int) -> str:
    return {0: "Tightening", 1: "OK", 2: "NG"}.get(v, f"?({v})")

def error_report_text(v: int) -> str:
    return {
        0: "none", 1: "slip-on", 2: "float lock",
        3: "poor torque", 4: "poor angle", 5: "released early",
    }.get(v, f"?({v})")

def mode_text(v: int) -> str:
    return {0: "Single", 1: "Batch"}.get(v, f"?({v})")

def normalize_length_text(length_text: str) -> str:
    txt = str(length_text).strip()
    if txt.endswith(".0"):
        txt = txt[:-2]
    return txt

def get_thread_pitch_mm(size: str) -> float:
    size = size.upper().strip()
    if size not in THREAD_PITCH_MM:
        raise ValueError(f"Unsupported screw size: {size}")
    return THREAD_PITCH_MM[size]

def length_to_turns(size: str, length_mm: float) -> float:
    return float(length_mm) / get_thread_pitch_mm(size)

def turns_to_angle(turns: float) -> int:
    return int(round(turns * 360))

def length_to_total_angle(size: str, length_mm: float) -> int:
    return turns_to_angle(length_to_turns(size, length_mm))

def build_recipe_from_length(size: str, length: str, final_torque: float, torque_unit: int = 0):
    length_mm   = float(normalize_length_text(length))
    pitch       = get_thread_pitch_mm(size)
    turns       = length_to_turns(size, length_mm)
    total_angle = length_to_total_angle(size, length_mm)
    step1_angle  = 30
    remain_angle = max(1, total_angle - step1_angle)
    step2_angle  = max(1, int(remain_angle * 0.70))
    step3_angle  = max(1, int(remain_angle * 0.15))
    step4_angle  = max(1, remain_angle - step2_angle - step3_angle)
    return {
        "pitch": pitch, "turns": round(turns, 3), "total_angle": total_angle,
        "step1_torque": round(final_torque * 0.10, 2), "step1_speed": 100,  "step1_angle": step1_angle,
        "step2_torque": round(final_torque * 0.20, 2), "step2_speed": 200,  "step2_angle": step2_angle,
        "step3_enable": 1,
        "step3_torque": round(final_torque * 0.30, 2), "step3_speed": 150,  "step3_angle": step3_angle,
        "step4_torque": round(final_torque,       2),  "step4_speed": 100,  "step4_angle": step4_angle,
    }

def build_recipe_for_custom(final_torque: float):
    total_angle = int(CUSTOM_DEFAULT_TOTAL_ANGLE)
    step1_angle = int(CUSTOM_STEP1_ANGLE)
    remain_angle = max(1, total_angle - step1_angle)
    step2_angle = max(1, int(remain_angle * CUSTOM_STEP2_RATIO))
    step3_angle = max(1, int(remain_angle * CUSTOM_STEP3_RATIO))
    step4_angle = max(1, remain_angle - step2_angle - step3_angle)
    return {
        "pitch": None,
        "turns": None,
        "total_angle": total_angle,
        "step1_torque": round(final_torque * 0.10, 2),
        "step1_speed": CUSTOM_SPEED_STEP1,
        "step1_angle": step1_angle,
        "step2_torque": round(final_torque * 0.20, 2),
        "step2_speed": CUSTOM_SPEED_STEP2,
        "step2_angle": step2_angle,
        "step3_enable": 1,
        "step3_torque": round(final_torque * 0.30, 2),
        "step3_speed": CUSTOM_SPEED_STEP3,
        "step3_angle": step3_angle,
        "step4_torque": round(final_torque, 2),
        "step4_speed": CUSTOM_SPEED_STEP4,
        "step4_angle": step4_angle,
    }


def get_recipe_by_spec(size: str, length: str, final_torque: float, torque_unit: int = 0):
    size_norm = size.upper().strip()
    if size_norm == "CUSTOM":
        return build_recipe_for_custom(final_torque)
    return build_recipe_from_length(size_norm, normalize_length_text(length), final_torque, torque_unit)


# =========================================================
# VALIDATION HELPERS
# =========================================================
def validate_group_limits(
    group_no, count_value, max_locking_angle, min_locking_angle,
    max_tightening_torque, min_tightening_torque,
    max_tightening_angle, min_tightening_angle,
    torque_unit=0, **kwargs,
):
    errors = []
    if not (1 <= group_no <= 50):     errors.append(f"Group out of range: {group_no}")
    if count_value < 1:               errors.append(f"Count value invalid: {count_value}")
    for name, value in [
        ("Max Locking Angle", max_locking_angle), ("Min Locking Angle", min_locking_angle),
        ("Max Tightening Angle", max_tightening_angle), ("Min Tightening Angle", min_tightening_angle),
    ]:
        if not (0 <= value <= 36000): errors.append(f"{name} out of range: {value}")
    for name, value in [
        ("Max Tightening Torque", max_tightening_torque), ("Min Tightening Torque", min_tightening_torque),
    ]:
        raw = encode_torque_value(value, torque_unit)
        if not (0 <= raw <= 65535):   errors.append(f"{name} raw out of range: {raw}")
    if max_locking_angle    < min_locking_angle:    errors.append("Max Locking Angle < Min")
    if max_tightening_angle < min_tightening_angle: errors.append("Max Tightening Angle < Min")
    if max_tightening_torque < min_tightening_torque: errors.append("Max Tightening Torque < Min")
    if errors: raise ValueError(" | ".join(errors))

def validate_four_step_limits(
    group_no, start_mode,
    initial_target_torque, initial_target_speed, initial_target_angle,
    tighten_target_torque, tighten_target_speed, tighten_target_angle,
    initial_tightening_mode,
    second_initial_target_torque, second_initial_target_speed, second_initial_target_angle,
    final_target_torque, final_target_speed, final_target_angle,
    torque_unit=0,
):
    errors = []
    if not (1 <= group_no <= 50):          errors.append(f"Group out of range: {group_no}")
    if start_mode not in (0, 1):           errors.append(f"Start Mode invalid: {start_mode}")
    if initial_tightening_mode not in (0,1): errors.append("Initial Tightening Mode invalid")
    for name, value in [
        ("Initial Target Angle", initial_target_angle), ("Tighten Target Angle", tighten_target_angle),
        ("Second Initial Target Angle", second_initial_target_angle), ("Final Target Angle", final_target_angle),
    ]:
        if not (1 <= value <= 36000): errors.append(f"{name} out of range: {value}")
    for name, value in [
        ("Initial Target Speed", initial_target_speed), ("Tighten Target Speed", tighten_target_speed),
        ("Second Initial Target Speed", second_initial_target_speed), ("Final Target Speed", final_target_speed),
    ]:
        if not (50 <= value <= 200): errors.append(f"{name} out of range: {value}")
    for name, value in [
        ("Initial Target Torque", initial_target_torque), ("Tighten Target Torque", tighten_target_torque),
        ("Second Initial Target Torque", second_initial_target_torque), ("Final Target Torque", final_target_torque),
    ]:
        if value < 0:
            errors.append(f"{name} negative"); continue
        raw = encode_torque_value(value, torque_unit)
        if not (0 <= raw <= 65535): errors.append(f"{name} raw out of range: {raw}")
    if errors: raise ValueError(" | ".join(errors))


# =========================================================
# RECIPE JSON HELPERS
# =========================================================
def load_all_screw_configs_from_recipe(recipe_json_path: str):
    if not os.path.exists(recipe_json_path):
        raise FileNotFoundError(f"Recipe JSON not found: {recipe_json_path}")
    with open(recipe_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    recipe_name = str(data.get("recipe", "")).strip()
    if not recipe_name:
        raise ValueError("Recipe name missing in recipe JSON")
    screw_list = []
    for block in data.get("blocks", []):
        if block.get("name") != "Screw":
            continue
        config       = block.get("config") or {}
        screw_type   = str(config.get("type",   "")).upper().strip()
        screw_length = normalize_length_text(str(config.get("length", "")).strip())
        screw_torque = float(config.get("torque", 0))
        screw_count  = int(config.get("count", 1))
        screw_bit_raw = str(config.get("bit", "")).strip()
        screw_bit = int(screw_bit_raw) if screw_bit_raw else None
        block_id     = str(config.get("block_id",   ""))
        block_name   = str(config.get("block_name", ""))
        if not screw_type:    raise ValueError(f"Screw type missing in block {block_id}")
        if not screw_length:  raise ValueError(f"Screw length missing in block {block_id}")
        if screw_torque <= 0: raise ValueError(f"Screw torque invalid in block {block_id}")
        if screw_bit is None:
            screw_bit = SIZE_TO_SELECTOR_BIT.get(screw_type)
        if screw_bit is None or not (1 <= screw_bit <= 6):
            raise ValueError(f"Screw Bit invalid in block {block_id}: {screw_bit_raw or screw_bit}")
        screw_list.append({
            "recipe_name": recipe_name, "type": screw_type, "length": screw_length,
            "torque": screw_torque, "count": screw_count, "bit": screw_bit,
            "block_id": block_id, "block_name": block_name,
            "position":  str(config.get("position",  "")),
            "position2": str(config.get("position2", "")),
            "uploaded_video_path": str(config.get("uploaded_video_path", "")),
            "raw_block": block, "raw_config": config,
        })
    if not screw_list:
        raise ValueError("No Screw blocks found in recipe JSON")
    return {"recipe_name": recipe_name, "screws": screw_list, "raw_data": data}

def load_recipe_into_memory(recipe_json_path: str):
    global current_recipe_path, current_recipe_name, current_product_id
    global all_recipe_screws, current_screw_index
    global session_product_id, session_csv_path, session_started_at
    global recipe_sequence_active, current_recipe_set_no, screw_counter, result_rows
    recipe_info = load_all_screw_configs_from_recipe(recipe_json_path)
    with data_lock:
        current_recipe_path  = recipe_json_path
        current_recipe_name  = recipe_info["recipe_name"]
        current_product_id   = current_recipe_name
        all_recipe_screws    = recipe_info["screws"]
        current_screw_index  = -1
        session_product_id   = ""
        session_csv_path     = ""
        session_started_at   = ""
        recipe_sequence_active = False
        current_recipe_set_no  = recipe_set_counters.get(current_recipe_name, 0)
        screw_counter = 0; result_rows = []
    log_debug(f"[RECIPE] Loaded: {current_recipe_name}  ({len(all_recipe_screws)} blocks)")
    return recipe_info

def is_recipe_name(text: str) -> bool:
    """
    Accept any recipe name from client, for example:
    - Speaker
    - A1.2.3
    - Xx.x.x
    - b1.2.3

    Reject:
    - empty text
    - reserved commands
    - unsafe path characters / traversal
    """
    value = str(text).strip()
    if not value:
        return False

    low = value.lower()
    if low in ("screw_start", "screw_stop"):
        return False

    if any(ch in value for ch in ('/', '\\', ':', '*', '?', '"', '<', '>', '|')):
        return False

    if ".." in value:
        return False

    return True


def find_recipe_folder_case_insensitive(recipe_name: str) -> str:
    """
    Find a folder under RECIPE_ROOT_FOLDER matching recipe_name
    without caring about uppercase/lowercase.
    Returns the actual folder name on disk.
    """
    target = str(recipe_name).strip().casefold()
    if not target:
        raise ValueError("Recipe name is empty")

    if not os.path.isdir(RECIPE_ROOT_FOLDER):
        raise FileNotFoundError(f"Recipe root folder not found: {RECIPE_ROOT_FOLDER}")

    for entry in os.listdir(RECIPE_ROOT_FOLDER):
        full = os.path.join(RECIPE_ROOT_FOLDER, entry)
        if os.path.isdir(full) and entry.casefold() == target:
            return entry

    raise FileNotFoundError(f"Recipe folder not found (case-insensitive): {recipe_name}")


def build_recipe_json_path(recipe_name: str) -> str:
    """
    Build:
    RECIPE_ROOT_FOLDER/<matched_folder>/flows/pipeline_flow.json
    using case-insensitive folder lookup.
    """
    matched_folder = find_recipe_folder_case_insensitive(recipe_name)
    return os.path.join(RECIPE_ROOT_FOLDER, matched_folder, "flows", "pipeline_flow.json")


def load_recipe_by_name(recipe_name: str):
    """
    Load recipe JSON by client-sent recipe name, case-insensitive.
    """
    recipe_name = str(recipe_name).strip()
    path = build_recipe_json_path(recipe_name)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Recipe JSON not found: {path}")

    return load_recipe_into_memory(path)

def set_current_screw_by_index(index: int):
    global current_screw_index, current_size, current_length, current_torque, current_selector_bit
    global current_screw_count, current_screw_block_id, current_screw_block_name
    with data_lock:
        if index < 0 or index >= len(all_recipe_screws):
            raise IndexError(f"Invalid screw index: {index}")
        s = all_recipe_screws[index]
        current_screw_index      = index
        current_size             = s["type"]
        current_length           = s["length"]
        current_torque           = s["torque"]
        current_selector_bit      = int(s.get("bit", SIZE_TO_SELECTOR_BIT.get(s["type"])))
        current_screw_count      = s["count"]
        current_screw_block_id   = s["block_id"]
        current_screw_block_name = s["block_name"]
    log_debug(
        f"[RECIPE] Screw idx={index} block={s['block_id']} {s['type']}x{s['length']} torque={s['torque']} bit={s.get('bit')}"
    )
    return s

def move_to_next_screw_block():
    global current_screw_index
    with data_lock:
        if not all_recipe_screws:
            raise RuntimeError("No screw blocks loaded")
        next_index = current_screw_index + 1
        if next_index >= len(all_recipe_screws):
            log_debug("[RECIPE] Already at last block")
            return None
    return set_current_screw_by_index(next_index)

def prepare_current_screw_from_recipe(conn=None):
    if current_screw_index < 0:
        raise RuntimeError("No current screw selected")

    screw_cfg = all_recipe_screws[current_screw_index]
    size_value = screw_cfg["type"]
    length_value = screw_cfg["length"]
    torque_value = screw_cfg["torque"]
    expected_bit = int(screw_cfg.get("bit", SIZE_TO_SELECTOR_BIT.get(size_value, 0)))

    if not (1 <= expected_bit <= 6):
        raise ValueError(f"UNSUPPORTED_SELECTOR_BIT,{expected_bit}")

    set_selector_guidance(expected_bit=expected_bit, wrong_bits=[])
    log_debug(f"[SELECTOR] Waiting for bit {expected_bit}…")

    already_reported_wrong = set()

    while True:
        result, bit_no, active_wrong_bits = wait_for_selector_event(
            expected_bit,
            None,
            previous_wrong_bits=already_reported_wrong
        )

        # keep UI guidance updated
        set_selector_guidance(expected_bit=expected_bit, wrong_bits=active_wrong_bits)
        sync_selector_buzzer()

        if result == "OK":
            apply_screw_preset_to_driver(size_value, length_value, torque_value)
            return True

        if result == "WRONG":
            if bit_no not in already_reported_wrong:
                already_reported_wrong.add(bit_no)
                log_error(
                    f"[ERROR] Wrong screw bit {bit_no} ({selector_bit_to_size(bit_no)}) for expected bit {expected_bit}"
                )
                if conn:
                    send_reply(conn, "ERROR,WRONG_SCREW")
            continue

        if result == "CLEAR":
            # clear remembered wrong bits so next wrong pickup can trigger again
            already_reported_wrong.clear()
            continue


# =========================================================
# DATA MODEL
# =========================================================
@dataclass
class Monitor81Packet:
    group_no: int; torque_unit: int; torque_raw: int; torque: float
    torque_unit_text: str; rotate_speed: int; locking_angle: int
    tightening_angle: int; time_ms: int; direction: int; direction_text: str
    remaining_number: int; entire_group_completed: int
    entire_group_completed_text: str; tightened_state: int
    tightened_state_text: str; error_report: int; error_report_text: str
    temp: int; max_torque_raw: int; max_torque: float
    min_torque_raw: int; min_torque: float
    max_tightening_angle: int; min_tightening_angle: int
    max_locking_angle: int; min_locking_angle: int
    mode: int; mode_text: str; batch: int; group: int
    raw_data_hex: str; frame_hex: str; create_time: str

@dataclass
class BitSelectorStatus:
    bit_1: int; bit_2: int; bit_3: int; bit_4: int; bit_5: int; bit_6: int
    frame_hex: str; create_time: str
    @property
    def bits(self):
        return (self.bit_1, self.bit_2, self.bit_3, self.bit_4, self.bit_5, self.bit_6)

def parse_81_00(frame: bytes) -> Monitor81Packet:
    data = frame[5:-4]
    if len(data) != 34:
        raise ValueError(f"Expected 34 bytes, got {len(data)}")
    g = data[0]; tu = data[1]; tr = u16_le(data, 2)
    return Monitor81Packet(
        group_no=g, torque_unit=tu, torque_raw=tr,
        torque=torque_from_raw(tr, tu), torque_unit_text=torque_unit_text(tu),
        rotate_speed=u16_le(data, 4),  locking_angle=u16_le(data, 6),
        tightening_angle=u16_le(data, 8), time_ms=u16_le(data, 10),
        direction=data[12], direction_text=direction_text(data[12]),
        remaining_number=u16_le(data, 13), entire_group_completed=data[15],
        entire_group_completed_text=completed_text(data[15]),
        tightened_state=data[16], tightened_state_text=tightened_state_text(data[16]),
        error_report=data[17], error_report_text=error_report_text(data[17]),
        temp=data[18], max_torque_raw=u16_le(data, 19),
        max_torque=torque_from_raw(u16_le(data, 19), tu),
        min_torque_raw=u16_le(data, 21), min_torque=torque_from_raw(u16_le(data, 21), tu),
        max_tightening_angle=u16_le(data, 23), min_tightening_angle=u16_le(data, 25),
        max_locking_angle=u16_le(data, 27),    min_locking_angle=u16_le(data, 29),
        mode=data[31], mode_text=mode_text(data[31]),
        batch=data[32], group=data[33],
        raw_data_hex=data.hex(" ").upper(), frame_hex=frame.hex(" ").upper(),
        create_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    )

def parse_selector_status(frame: bytes) -> BitSelectorStatus:
    data = frame[5:-4]
    if len(data) < 6:
        raise ValueError(f"Expected >= 6 bytes, got {len(data)}")
    return BitSelectorStatus(
        bit_1=data[0], bit_2=data[1], bit_3=data[2],
        bit_4=data[3], bit_5=data[4], bit_6=data[5],
        frame_hex=frame.hex(" ").upper(),
        create_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    )


# =========================================================
# CONNECTION STATUS HELPERS
# =========================================================
def set_screwdriver_connection_status(is_connected: bool, reason: str = ""):
    global screwdriver_connected, last_screwdriver_status_text
    new_text = ("CONNECTED" if is_connected else "DISCONNECTED") + (f" - {reason}" if reason else "")
    changed  = (screwdriver_connected != is_connected) or (last_screwdriver_status_text != new_text)
    screwdriver_connected        = is_connected
    last_screwdriver_status_text = new_text
    if changed:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [SCREWDRIVER] {new_text}")

def set_selector_connection_status(is_connected: bool, reason: str = ""):
    global selector_connected, last_selector_status_text
    old_connected = selector_connected
    new_text = ("CONNECTED" if is_connected else "DISCONNECTED") + (f" - {reason}" if reason else "")
    changed  = (selector_connected != is_connected) or (last_selector_status_text != new_text)
    selector_connected        = is_connected
    last_selector_status_text = new_text
    if changed:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [SELECTOR] {new_text}")
    if old_connected != is_connected:
        if is_connected:
            notify_selector_connected()
        else:
            notify_selector_disconnected()


# =========================================================
# TCP CLIENTS
# =========================================================
class SudongTCPClient:
    def __init__(self, host, port, timeout=1.0, affect_status=True):
        self.host = host; self.port = port; self.timeout = timeout
        self.affect_status = affect_status
        self.sock: Optional[socket.socket] = None
        self.buffer = b""

    def connect(self):
        self.close()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        s.connect((self.host, self.port))
        self.sock = s; self.buffer = b""
        log_debug(f"[TCP] Connected to {self.host}:{self.port}")
        if self.affect_status:
            set_screwdriver_connection_status(True, f"{self.host}:{self.port}")

    def close(self):
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except Exception: pass
            try: self.sock.close()
            except Exception: pass
            self.sock = None
        self.buffer = b""
        if self.affect_status:
            set_screwdriver_connection_status(False, "socket closed")

    def send_frame(self, frame: bytes):
        if not self.sock: raise ConnectionError("Screwdriver socket not connected")
        try: self.sock.sendall(frame)
        except (OSError, socket.timeout) as e: raise ConnectionError(f"send failed: {e}") from e

    def recv_frames(self) -> List[bytes]:
        if not self.sock: raise ConnectionError("Screwdriver socket not connected")
        try:    data = self.sock.recv(1024)
        except socket.timeout: raise
        except OSError as e: raise ConnectionError(f"recv failed: {e}") from e
        if not data: raise ConnectionError("Disconnected")
        self.buffer += data
        frames, self.buffer = extract_frames(self.buffer)
        if DEBUG_RAW_RX:
            for frame in frames: print("[RX]", frame.hex(" ").upper())
        return frames


class BitSelectorTCPClient:
    def __init__(self, host, port, timeout=1.0):
        self.host = host; self.port = port; self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.buffer = b""

    def connect(self):
        self.close()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        s.connect((self.host, self.port))
        self.sock = s; self.buffer = b""
        log_debug(f"[SELECTOR] Connected to {self.host}:{self.port}")
        set_selector_connection_status(True, f"{self.host}:{self.port}")

    def close(self):
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except Exception: pass
            try: self.sock.close()
            except Exception: pass
            self.sock = None
        self.buffer = b""
        set_selector_connection_status(False, "socket closed")

    def send_frame(self, frame: bytes):
        if not self.sock: raise ConnectionError("Selector socket not connected")
        try: self.sock.sendall(frame)
        except (OSError, socket.timeout) as e: raise ConnectionError(f"send failed: {e}") from e

    def recv_frames(self) -> List[bytes]:
        if not self.sock: raise ConnectionError("Selector socket not connected")
        try:    data = self.sock.recv(1024)
        except socket.timeout: raise
        except OSError as e: raise ConnectionError(f"recv failed: {e}") from e
        if not data: raise ConnectionError("Selector disconnected")
        self.buffer += data
        frames, self.buffer = extract_frames(self.buffer)
        return frames


# =========================================================
# FILE HELPERS
# =========================================================
def ensure_output_folder():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def sanitize_filename(text: str) -> str:
    text = (text or "").strip()
    if not text: return "NO_ID"
    for ch in '<>:"/\\|?*': text = text.replace(ch, "_")
    return text

def get_date_folder(date_text: str = None) -> str:
    ensure_output_folder()
    folder = os.path.join(OUTPUT_FOLDER, sanitize_filename(date_text or datetime.now().strftime("%Y-%m-%d")))
    os.makedirs(folder, exist_ok=True)
    return folder

def get_product_folder(product_id: str) -> str:
    folder = os.path.join(get_date_folder(), sanitize_filename(product_id or "NO_PRODUCT"))
    os.makedirs(folder, exist_ok=True)
    return folder

def build_session_base_name() -> str:
    product = sanitize_filename(current_product_id or "NO_PRODUCT")
    ts      = session_started_at or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    set_no  = current_recipe_set_no if current_recipe_set_no > 0 else 1
    return f"{product}_SET{set_no:03d}_{ts}"

def begin_recipe_set(recipe_name: str):
    global current_product_id, session_product_id, session_csv_path, session_started_at
    global screw_counter, result_rows, current_recipe_set_no, recipe_sequence_active
    recipe_name = (recipe_name or "").strip().upper()
    if not recipe_name: raise RuntimeError("Recipe ID must be set before starting a set")
    with data_lock:
        next_set_no = recipe_set_counters.get(recipe_name, 0) + 1
        recipe_set_counters[recipe_name] = next_set_no
        current_recipe_set_no  = next_set_no
        recipe_sequence_active = True
        current_product_id     = recipe_name
        session_product_id     = recipe_name
        session_started_at     = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        product_folder = get_product_folder(recipe_name)
        base_name      = build_session_base_name()
        session_csv_path = os.path.join(product_folder, f"{base_name}.csv")
        screw_counter = 0; result_rows = []
    log_debug(f"[SET] Recipe={recipe_name} Set={current_recipe_set_no}")
    return current_recipe_set_no, session_csv_path

def finish_recipe_set():
    global recipe_sequence_active, current_screw_index
    with data_lock:
        recipe_sequence_active = False; current_screw_index = -1

def safe_ui_call(callback):
    root = ui_root
    if root is None: return
    try: root.after(0, callback)
    except Exception as e: log_error(f"[UI] schedule error: {e}")

def show_corner_monitor():
    def _show():
        global corner_monitor
        if ui_root is None:
            return
        try:
            if corner_monitor is None:
                corner_monitor = CornerMonitor(ui_root)
            if hasattr(corner_monitor, "reset_view"):
                corner_monitor.reset_view()
            corner_monitor.deiconify()
            corner_monitor._place()
            corner_monitor.lift()
            corner_monitor.attributes("-topmost", True)
        except Exception as e:
            log_error(f"[UI] show error: {e}")
    safe_ui_call(_show)

def hide_corner_monitor():
    def _hide():
        global corner_monitor
        if corner_monitor is None:
            return
        try:
            corner_monitor.destroy()
            corner_monitor = None
        except Exception as e:
            log_error(f"[UI] hide error: {e}")
    safe_ui_call(_hide)

def build_screw_graph_names(product_id, size, length, index):
    return (
        f"{sanitize_filename(product_id or 'NO_PRODUCT')}_{sanitize_filename(f'{size}x{length}')}_S{index:03d}_torque.png",
        f"{sanitize_filename(product_id or 'NO_PRODUCT')}_{sanitize_filename(f'{size}x{length}')}_S{index:03d}_speed.png",
    )

def save_torque_graph_png(path):
    plt.figure(figsize=(12, 6))
    plt.plot(range(len(current_cycle_torque)), current_cycle_torque)
    plt.xlabel("Index"); plt.ylabel("Torque"); plt.title("Torque Waveform")
    plt.tight_layout(); plt.savefig(path, dpi=150); plt.close()

def save_speed_graph_png(path):
    plt.figure(figsize=(12, 6))
    plt.plot(range(len(current_cycle_speed)), current_cycle_speed)
    plt.xlabel("Index"); plt.ylabel("Speed"); plt.title("Speed Waveform")
    plt.tight_layout(); plt.savefig(path, dpi=150); plt.close()

def export_results_to_csv():
    global result_rows, session_csv_path
    if not result_rows: return session_csv_path
    if not session_csv_path:
        session_csv_path = os.path.join(
            get_product_folder(current_product_id),
            f"{build_session_base_name()}.csv",
        )
    headers = [
        "No","ProductID","RecipeName","RecipeSetNo","ScrewIndex","ScrewBlockID","ScrewBlockName",
        "ScrewSize","ScrewLength","RecipeTorque","CreateTime","GroupNo",
        "Torque","TorqueUnit","RotateSpeed","LockingAngle","TighteningAngle",
        "TimeMs","Direction","RemainingNumber","EntireGroupCompleted",
        "TightenedState","ErrorReport","Temp","MaxTorque","MinTorque",
        "MaxTighteningAngle","MinTighteningAngle","MaxLockingAngle",
        "MinLockingAngle","Mode","Batch","Group","RawDataHex","FrameHex",
        "TorqueGraphFile","SpeedGraphFile",
    ]
    file_exists = os.path.exists(session_csv_path)
    with open(session_csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists or os.path.getsize(session_csv_path) == 0:
            writer.writeheader()
        for row in result_rows:
            writer.writerow(row)
    result_rows = []
    return session_csv_path


# =========================================================
# CYCLE / SELECTOR HELPERS
# =========================================================
def reset_current_cycle():
    global current_cycle_torque, current_cycle_speed, current_cycle_packets
    current_cycle_torque = []; current_cycle_speed = []; current_cycle_packets = []

def handle_selector_status(status: BitSelectorStatus):
    global latest_selector_status, latest_selector_bits

    with selector_condition:
        latest_selector_status = status
        latest_selector_bits = [
            status.bit_1, status.bit_2, status.bit_3,
            status.bit_4, status.bit_5, status.bit_6
        ]
        selector_condition.notify_all()

    # First update recording/error state
    check_selector_held_during_recording()

    # Then refresh wrong-bit guidance using latest final state
    with selector_lock:
        expected_bit = current_expected_selector_bit

    if expected_bit and 1 <= expected_bit <= 6:
        active_wrong_bits = [
            i + 1 for i, v in enumerate(latest_selector_bits)
            if v == 1 and (i + 1) != expected_bit
        ]
        with selector_lock:
            current_wrong_selector_bits = set(active_wrong_bits)

    # Only sync buzzer once, after all states are final
    sync_selector_buzzer()


def process_selector_status_confirmed(status: BitSelectorStatus):
    """
    Accept selector bit change only after:
    1) a change is detected
    2) one more read is sent
    3) the same changed bits are received again

    Buzzer/state/UI update only happen after confirmation.
    """
    global selector_last_stable_bits, selector_pending_bits, selector_pending_same_count

    bits = tuple(status.bits)

    with selector_lock:
        stable_bits = selector_last_stable_bits
        pending_bits = selector_pending_bits

    # first valid selector frame
    if stable_bits is None:
        with selector_lock:
            selector_last_stable_bits = bits
            selector_pending_bits = None
            selector_pending_same_count = 0
        handle_selector_status(status)
        return True

    # no change from stable state
    if bits == stable_bits:
        with selector_lock:
            selector_pending_bits = None
            selector_pending_same_count = 0
        handle_selector_status(status)
        return True

    # changed state detected first time
    if pending_bits != bits:
        with selector_lock:
            selector_pending_bits = bits
            selector_pending_same_count = 1

        log_debug(f"[SELECTOR] Change detected, confirm read required: {bits}")
        send_selector_read_request()
        return False

    # same changed state received again
    with selector_lock:
        selector_pending_same_count += 1
        same_count = selector_pending_same_count

    if same_count >= 2:
        with selector_lock:
            selector_last_stable_bits = bits
            selector_pending_bits = None
            selector_pending_same_count = 0

        log_debug(f"[SELECTOR] Change confirmed: {bits}")
        handle_selector_status(status)
        return True

    return False

def get_latest_selector_status():
    with selector_lock: return latest_selector_status
def get_latest_selector_bits():
    with selector_lock: return tuple(latest_selector_bits)
def get_selector_bit_index_for_size(size_text):
    size_text = size_text.upper().strip()
    if size_text not in SIZE_TO_SELECTOR_BIT:
        raise ValueError(f"No selector bit mapping for size: {size_text}")
    return SIZE_TO_SELECTOR_BIT[size_text]
def get_selector_bit_value_for_size(size_text):
    bits = get_latest_selector_bits()
    return bits[get_selector_bit_index_for_size(size_text) - 1]
def get_selector_bit_value_text(size_text):
    bit_index = get_selector_bit_index_for_size(size_text)
    bit_value = get_selector_bit_value_for_size(size_text)
    if bit_value is None: return f"[SELECTOR] {size_text} bit_{bit_index} = UNKNOWN"
    return f"[SELECTOR] {size_text} bit_{bit_index} = {'1 (TAKEN)' if bit_value else '0 (NOT TAKEN)'}"
def selector_bit_to_size(bit_index):
    return str(bit_index) if 1 <= int(bit_index) <= 6 else f"BIT{bit_index}"

def set_selector_guidance(expected_bit=None, wrong_bits=None):
    global current_expected_selector_bit, current_wrong_selector_bits
    with selector_lock:
        current_expected_selector_bit = int(expected_bit) if expected_bit is not None else None
        current_wrong_selector_bits   = set(int(b) for b in (wrong_bits or []))
    sync_selector_buzzer()
def clear_selector_guidance(): set_selector_guidance(None, [])
def get_selector_guidance():
    with selector_lock: return current_expected_selector_bit, set(current_wrong_selector_bits)

def set_missing_selector_bits_unlocked(bit_list):
    global current_missing_selector_bits
    current_missing_selector_bits = set(int(b) for b in bit_list)
def set_missing_selector_bits(bit_list):
    with selector_lock: set_missing_selector_bits_unlocked(bit_list)
    sync_selector_buzzer()
def clear_missing_selector_bits(): set_missing_selector_bits([])
def clear_missing_selector_bits_unlocked(): set_missing_selector_bits_unlocked([])
def get_missing_selector_bits():
    with selector_lock: return set(current_missing_selector_bits)
def get_selector_expected_error():
    with selector_lock: return bool(selector_expected_error)

def set_selector_stop_wait(message="Waiting for all bits to place back..."):
    global selector_stop_wait_active, selector_stop_wait_message
    with selector_lock:
        selector_stop_wait_active  = True
        selector_stop_wait_message = str(message or "Waiting for all bits to place back...")
    sync_selector_buzzer(force=True)
def clear_selector_stop_wait():
    global selector_stop_wait_active, selector_stop_wait_message
    with selector_lock:
        selector_stop_wait_active = False
        selector_stop_wait_message = ""
    sync_selector_buzzer(force=True)
def get_selector_stop_wait():
    with selector_lock: return bool(selector_stop_wait_active), str(selector_stop_wait_message)

def wait_for_correct_selector_or_wrong(
    size_text: str,
    timeout_sec: Optional[float] = SELECTOR_MATCH_WAIT_SEC,
    skip_reported_bits: Optional[set] = None,
):
    expected_bit        = get_selector_bit_index_for_size(size_text)
    reported_wrong_bits = set(skip_reported_bits) if skip_reported_bits else set()
    deadline = None if timeout_sec is None else (time.time() + timeout_sec)
    with selector_condition:
        while True:
            bits             = latest_selector_bits[:]
            active_bits      = [i + 1 for i, v in enumerate(bits) if v == 1]
            reported_wrong_bits &= set(active_bits)
            active_wrong_bits   = [b for b in active_bits if b != expected_bit]
            new_wrong_bits      = [b for b in active_wrong_bits if b not in reported_wrong_bits]
            if new_wrong_bits:
                wrong_bit = new_wrong_bits[0]
                reported_wrong_bits.add(wrong_bit)
                return ("WRONG", wrong_bit)
            if expected_bit in active_bits and not active_wrong_bits:
                return ("OK", expected_bit)
            if deadline is None:
                selector_condition.wait(timeout=0.2); continue
            remaining = deadline - time.time()
            if remaining <= 0: return ("TIMEOUT", None)
            selector_condition.wait(timeout=min(remaining, 0.2))

def wait_until_all_selector_bits_back(timeout_sec: float = SELECTOR_ALL_BACK_WAIT_SEC):
    with selector_condition:
        while True:
            bits        = latest_selector_bits[:]
            active_bits = [i + 1 for i, v in enumerate(bits) if v == 1]
            set_missing_selector_bits_unlocked(active_bits)
            if None not in bits and all(v == 0 for v in bits):
                clear_missing_selector_bits_unlocked()
                return True
            selector_condition.wait(timeout=0.2)

# ── Outgoing protocol helpers ──────────────────────────────────────────────
def send_result_to_client(pkt):
    """Send RESULT,OK,<torque> or RESULT,NG,<torque>"""
    global client_conn
    if client_conn is None: return
    try:
        state = "OK" if pkt.tightened_state == 1 else "NG"
        msg   = f"RESULT,{state},{pkt.torque:.2f}"
        client_conn.sendall(msg.encode("utf-8"))
        log_debug(f"[SERVER] Sent: {msg}")
    except Exception as e: log_error(f"[ERROR] send_result_to_client: {e}")

def send_result_to_client_text(message: str):
    global client_conn
    if client_conn is None: return
    try:
        client_conn.sendall(str(message).encode("utf-8"))
        log_debug(f"[SERVER] Sent: {message}")
    except Exception as e: log_error(f"[ERROR] send_result_to_client_text: {e}")


def send_initial_connection_status_to_client():
    try:
        if screwdriver_connected:
            send_result_to_client_text("INFO,SCREWDRIVER_CONNECTED")
        else:
            send_result_to_client_text("ERROR,SCREWDRIVER_NOT_CONNECTED")
    except Exception:
        pass

    try:
        if selector_connected:
            send_result_to_client_text("INFO,SELECTOR_CONNECTED")
        else:
            send_result_to_client_text("ERROR,SELECTOR_NOT_CONNECTED")
    except Exception:
        pass
# ──────────────────────────────────────────────────────────────────────────

def check_selector_held_during_recording():
    global selector_has_been_correct, selector_missing_during_recording
    global selector_missing_error_sent, selector_expected_error
    global current_expected_selector_bit, current_wrong_selector_bits

    with data_lock:
        is_rec = recording
        expected_bit = int(current_selector_bit) if current_selector_bit else None

    if not is_rec or not expected_bit:
        return

    bits = get_latest_selector_bits()
    if not bits or None in bits:
        return

    expected_on = (bits[expected_bit - 1] == 1)
    active_wrong_bits = [i + 1 for i, v in enumerate(bits) if v == 1 and (i + 1) != expected_bit]

    with selector_lock:
        current_expected_selector_bit = expected_bit
        current_wrong_selector_bits = set(active_wrong_bits)

        if expected_on:
            selector_has_been_correct = True
            if selector_missing_during_recording:
                selector_missing_during_recording = False
                selector_missing_error_sent = False
                selector_expected_error = False
                log_debug(f"[SELECTOR] Correct bit restored: {expected_bit}")
                try:
                    send_result_to_client_text("INFO,SELECTOR_OK")
                except Exception:
                    pass
        else:
            if selector_has_been_correct:
                selector_missing_during_recording = True
                selector_expected_error = True
                if not selector_missing_error_sent:
                    selector_missing_error_sent = True
                    log_error(f"[ERROR] Selector removed during run, expected bit {expected_bit}")
                    try:
                        send_result_to_client_text("ERROR,SELECTOR_REMOVED")
                    except Exception:
                        pass

def finalize_one_screw(pkt):
    global screw_counter
    if not current_cycle_packets: return
    screw_counter += 1
    log_debug(f"[FINALIZE] Screw #{screw_counter} state={pkt.tightened_state_text}")
    product_folder = get_product_folder(current_product_id)
    torque_file, speed_file = build_screw_graph_names(current_product_id, current_size, current_length, screw_counter)
    save_torque_graph_png(os.path.join(product_folder, torque_file))
    save_speed_graph_png(os.path.join(product_folder, speed_file))
    result_rows.append({
        "No": screw_counter, "ProductID": current_product_id, "RecipeName": current_recipe_name,
        "RecipeSetNo": current_recipe_set_no, "ScrewIndex": current_screw_index,
        "ScrewBlockID": current_screw_block_id, "ScrewBlockName": current_screw_block_name,
        "ScrewSize": current_size, "ScrewLength": current_length, "RecipeTorque": current_torque,
        "CreateTime": pkt.create_time, "GroupNo": pkt.group_no, "Torque": pkt.torque,
        "TorqueUnit": pkt.torque_unit_text, "RotateSpeed": pkt.rotate_speed,
        "LockingAngle": pkt.locking_angle, "TighteningAngle": pkt.tightening_angle,
        "TimeMs": pkt.time_ms, "Direction": pkt.direction_text,
        "RemainingNumber": pkt.remaining_number,
        "EntireGroupCompleted": pkt.entire_group_completed_text,
        "TightenedState": pkt.tightened_state_text, "ErrorReport": pkt.error_report_text,
        "Temp": pkt.temp, "MaxTorque": pkt.max_torque, "MinTorque": pkt.min_torque,
        "MaxTighteningAngle": pkt.max_tightening_angle, "MinTighteningAngle": pkt.min_tightening_angle,
        "MaxLockingAngle": pkt.max_locking_angle, "MinLockingAngle": pkt.min_locking_angle,
        "Mode": pkt.mode_text, "Batch": pkt.batch, "Group": pkt.group,
        "RawDataHex": pkt.raw_data_hex, "FrameHex": pkt.frame_hex,
        "TorqueGraphFile": torque_file, "SpeedGraphFile": speed_file,
    })
    reset_current_cycle()
    send_result_to_client(pkt)

def push_to_corner(pkt):
    if corner_monitor is None: return
    corner_monitor.push_packet(CornerData(
        tightened_state=pkt.tightened_state, torque=pkt.torque,
        torque_unit=pkt.torque_unit_text, min_torque=pkt.min_torque,
        max_torque=pkt.max_torque, locking_angle=pkt.locking_angle,
        tightening_angle=pkt.tightening_angle,
        min_locking_angle=pkt.min_locking_angle, max_locking_angle=pkt.max_locking_angle,
        min_tightening_angle=pkt.min_tightening_angle, max_tightening_angle=pkt.max_tightening_angle,
        rotate_speed=pkt.rotate_speed, error_report=pkt.error_report_text,
    ))

def handle_live_packet(pkt):
    global latest_packet, prev_tightened_state
    global stable_zero_speed_count, last_locking_angle, cycle_completed, selector_missing_during_recording
    with data_lock:
        latest_packet = pkt
        push_to_corner(pkt)
        if not recording: return
        if selector_missing_during_recording:
            if DEBUG_LIVE_PKT: log_debug("[LIVE_PKT] Selector missing — ignore finalize")
            return
        if DEBUG_LIVE_PKT:
            log_debug(f"[LIVE_PKT] state={pkt.tightened_state_text} torque={pkt.torque} speed={pkt.rotate_speed}")
        if cycle_completed and pkt.rotate_speed > 50:
            cycle_completed = False; reset_current_cycle(); stable_zero_speed_count = 0
        current_cycle_torque.append(pkt.torque)
        current_cycle_speed.append(pkt.rotate_speed)
        current_cycle_packets.append(pkt)
        if prev_tightened_state is None:
            prev_tightened_state = pkt.tightened_state
            last_locking_angle = pkt.locking_angle; stable_zero_speed_count = 0
        if cycle_completed:
            prev_tightened_state = pkt.tightened_state; last_locking_angle = pkt.locking_angle; return
        if prev_tightened_state == 0 and pkt.tightened_state in (1, 2):
            finalize_one_screw(pkt); cycle_completed = True
            prev_tightened_state = pkt.tightened_state; stable_zero_speed_count = 0
            last_locking_angle = pkt.locking_angle; return
        angle_diff = abs(pkt.locking_angle - last_locking_angle)
        if pkt.rotate_speed <= 10 and angle_diff <= 1 and len(current_cycle_packets) > 10:
            stable_zero_speed_count += 1
        else:
            stable_zero_speed_count = 0
        if stable_zero_speed_count >= 5:
            if pkt.tightened_state in (1, 2): finalize_one_screw(pkt); cycle_completed = True
            else: log_debug("[LIVE_PKT] Stable stop but still Tightening — skip finalize")
            stable_zero_speed_count = 0; prev_tightened_state = pkt.tightened_state
            last_locking_angle = pkt.locking_angle; return
        prev_tightened_state = pkt.tightened_state; last_locking_angle = pkt.locking_angle


# =========================================================
# DRIVER COMMAND BUILDERS
# =========================================================
def cmd_stop():                 return build_frame(STOP_COMMAND)
def cmd_select_mode(mode, num): return build_frame(b"\x02\x05", bytes([mode, num]))
def cmd_save_parameters():      return build_frame(b"\x04\x00", b"\x00")
def cmd_read_selector_status(): return READ_SELECTOR_STATUS_ON_CONNECT_FRAME

def cmd_set_group_parameters(
    group_no, count_value, process_completion_time_s, max_locking_angle,
    min_locking_angle, reverse_angle, preparatory_angle_turn, single_completion_time_s,
    standby_time_s, fixture_delay_time_s, locking_mode, screw_type,
    max_tightening_torque, min_tightening_torque, max_tightening_angle, min_tightening_angle,
    torque_modification_value, torque_holding_time_s, reverse_mode, torque_unit=0,
):
    d = bytearray()
    d += bytes([group_no])
    d += u16_to_le_bytes(count_value)
    d += bytes([int(round(process_completion_time_s * 10))])
    d += u16_to_le_bytes(max_locking_angle); d += u16_to_le_bytes(min_locking_angle)
    d += u16_to_le_bytes(reverse_angle)
    d += bytes([int(round(preparatory_angle_turn * 10))])
    d += bytes([int(round(single_completion_time_s * 10))])
    d += bytes([standby_time_s])
    d += bytes([int(round(fixture_delay_time_s * 10))])
    d += bytes([locking_mode]); d += bytes([screw_type])
    d += u16_to_le_bytes(encode_torque_value(max_tightening_torque, torque_unit))
    d += u16_to_le_bytes(encode_torque_value(min_tightening_torque, torque_unit))
    d += u16_to_le_bytes(max_tightening_angle); d += u16_to_le_bytes(min_tightening_angle)
    d += u16_to_le_bytes(encode_torque_value(torque_modification_value, torque_unit) & 0xFFFF)
    d += bytes([int(round(torque_holding_time_s * 10))]); d += bytes([reverse_mode])
    return build_frame(b"\x02\x00", bytes(d))

def cmd_set_four_step_parameters(
    group_no, start_mode,
    initial_target_torque, initial_target_speed, initial_target_angle,
    tighten_target_torque, tighten_target_speed, tighten_target_angle,
    initial_tightening_mode,
    second_initial_target_torque, second_initial_target_speed, second_initial_target_angle,
    final_target_torque, final_target_speed, final_target_angle,
    torque_unit=0,
):
    d = bytearray()
    d += bytes([group_no]); d += bytes([start_mode])
    d += u16_to_le_bytes(encode_torque_value(initial_target_torque,        torque_unit))
    d += u16_to_le_bytes(initial_target_speed); d += u16_to_le_bytes(initial_target_angle)
    d += u16_to_le_bytes(encode_torque_value(tighten_target_torque,        torque_unit))
    d += u16_to_le_bytes(tighten_target_speed); d += u16_to_le_bytes(tighten_target_angle)
    d += bytes([initial_tightening_mode])
    d += u16_to_le_bytes(encode_torque_value(second_initial_target_torque, torque_unit))
    d += u16_to_le_bytes(second_initial_target_speed); d += u16_to_le_bytes(second_initial_target_angle)
    d += u16_to_le_bytes(encode_torque_value(final_target_torque,          torque_unit))
    d += u16_to_le_bytes(final_target_speed); d += u16_to_le_bytes(final_target_angle)
    return build_frame(b"\x02\x01", bytes(d))


# =========================================================
# PRESET WRITE
# Acquires preset_write_lock so the live worker pauses reads.
# Sets _preset_writing so disconnect notifications are suppressed.
# =========================================================
def wait_for_specific_ack(client, cmd0, cmd1, desc, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for frame in client.recv_frames():
                print(f"[PRESET][RX] {frame.hex(' ').upper()}")

                if not verify_frame(frame):
                    print(f"[PRESET][RX] invalid frame for {desc}")
                    continue

                if len(frame) >= 5:
                    print(f"[PRESET][RX] cmd=({frame[3]:02X},{frame[4]:02X}) waiting=({cmd0:02X},{cmd1:02X})")

                if len(frame) >= 5 and frame[3] == cmd0 and frame[4] == cmd1:
                    log_debug(f"[PRESET] ACK OK: {desc}")
                    return True
        except socket.timeout:
            continue

    log_error(f"[PRESET] ACK TIMEOUT: {desc}")
    return False


def send_with_ack(client, frame: bytes, ack0: int, ack1: int, desc: str,
                  timeout: float = 5.0,
                  retries: int = PRESET_ACK_RETRIES,
                  settle_sec: float = PRESET_STEP_SETTLE_SEC):
    last_error = RuntimeError(f"{desc} ACK failed")
    for attempt in range(1, max(1, retries) + 1):
        try:
            client.buffer = b""
            client.send_frame(frame)
            if wait_for_specific_ack(client, ack0, ack1, desc, timeout=timeout):
                time.sleep(settle_sec)
                return True
            last_error = RuntimeError(f"{desc} ACK timeout")
            log_error(f"[PRESET] Retry {attempt}/{retries} failed: {desc}")
        except Exception as e:
            last_error = e
            log_error(f"[PRESET] Retry {attempt}/{retries} error on {desc}: {e}")
        time.sleep(0.2)
    raise last_error

def apply_screw_preset_to_driver(size_text, length_text, torque_value):
    global _preset_writing, live_worker
    size_text   = size_text.upper().strip()
    length_text = normalize_length_text(length_text)
    recipe      = get_recipe_by_spec(size_text, length_text, torque_value, DEFAULT_TORQUE_UNIT)
    final_target = recipe["step4_torque"]
    min_torque   = round(final_target * 0.90, 2)
    max_torque   = round(final_target * 1.10, 2)
    group_max_locking_angle = min(recipe["total_angle"] + 2000, 36000)

    turns_text = recipe["turns"] if recipe.get("turns") is not None else "CUSTOM"
    log_debug(f"[PRESET] {size_text}x{length_text} torque={torque_value} turns={turns_text} total_angle={recipe['total_angle']}")

    basic_param = {
        "group_no": DEFAULT_GROUP_NO, "torque_unit": DEFAULT_TORQUE_UNIT, "count_value": 20,
        "process_completion_time_s": 0.0, "max_locking_angle": group_max_locking_angle,
        "min_locking_angle": 0, "reverse_angle": 0, "preparatory_angle_turn": 0.0,
        "single_completion_time_s": 0.0, "standby_time_s": 0, "fixture_delay_time_s": 0.0,
        "locking_mode": 0, "screw_type": 0,
        "max_tightening_torque": max_torque, "min_tightening_torque": min_torque,
        "max_tightening_angle": min(recipe["total_angle"] + 2000, 36000), "min_tightening_angle": 0,
        "torque_modification_value": 0.0, "torque_holding_time_s": 0.0, "reverse_mode": 0,
    }
    four_step_param = {
        "group_no": DEFAULT_GROUP_NO, "start_mode": 1,
        "initial_target_torque": recipe["step1_torque"], "initial_target_speed": recipe["step1_speed"],
        "initial_target_angle":  recipe["step1_angle"],
        "tighten_target_torque": recipe["step2_torque"], "tighten_target_speed": recipe["step2_speed"],
        "tighten_target_angle":  recipe["step2_angle"],
        "initial_tightening_mode": 1,
        "second_initial_target_torque": recipe["step3_torque"],
        "second_initial_target_speed":  recipe["step3_speed"],
        "second_initial_target_angle":  recipe["step3_angle"],
        "final_target_torque": recipe["step4_torque"], "final_target_speed": recipe["step4_speed"],
        "final_target_angle":  recipe["step4_angle"],  "torque_unit": DEFAULT_TORQUE_UNIT,
    }
    try:
        validate_group_limits(**basic_param)
        validate_four_step_limits(**four_step_param)
    except Exception as e:
        popup_error("Parameter Limit Error", str(e)); raise

    _preset_writing = True
    try:
        with preset_write_lock:
            worker = live_worker
            client = worker.client if (worker and worker.is_alive()) else None
            if client is None or client.sock is None:
                raise RuntimeError("Live screwdriver connection is not available for preset write")

            client.buffer = b""

            log_debug("[PRESET] Stop")
            client.send_frame(cmd_stop())
            time.sleep(0.2)

            log_debug("[PRESET] Select mode")
            send_with_ack(
                client,
                cmd_select_mode(0, DEFAULT_GROUP_NO),
                0x82, 0x05,
                "Select mode",
                timeout=5.0,
            )

            log_debug("[PRESET] Group param")
            send_with_ack(
                client,
                cmd_set_group_parameters(**basic_param),
                0x82, 0x00,
                "Group parameter",
                timeout=5.0,
            )

            log_debug("[PRESET] Four-step param")
            send_with_ack(
                client,
                cmd_set_four_step_parameters(**four_step_param),
                0x82, 0x01,
                "Four-step parameter",
                timeout=5.0,
            )

            log_debug("[PRESET] Save")
            send_with_ack(
                client,
                cmd_save_parameters(),
                0x84, 0x00,
                "Save parameter",
                timeout=5.0,
            )
            log_debug("[PRESET] Done")
    finally:
        _preset_writing = False
    # ───────────────────────────────────────────────────────────


# =========================================================
# WORKERS
# =========================================================
class LiveStreamWorker(threading.Thread):
    def __init__(self, reconnect_delay: float = 1.0):
        super().__init__(daemon=True)
        self.running = True
        self.client  = None
        self.reconnect_delay = reconnect_delay

    def stop(self):
        self.running = False
        client = self.client; self.client = None
        if client:
            try: client.close()
            except Exception: pass
        set_screwdriver_connection_status(False, "worker stopped")

    def run(self):
        while self.running:
            try:
                set_screwdriver_connection_status(False, f"connecting to {SCREW_HOST}:{SCREW_PORT}")
                self.client = SudongTCPClient(SCREW_HOST, SCREW_PORT, SCREW_TIMEOUT)
                self.client.connect()
                self.client.send_frame(build_frame(ENABLE_STREAM_COMMAND, ENABLE_STREAM_DATA))
                log_debug("[LIVE] Worker connected, stream enabled")
                set_screwdriver_connection_status(True, "stream enabled")
                notify_screwdriver_connected()

                while self.running:
                    try:
                        # ── If preset write is in progress, pause reads without disconnecting ──
                        if preset_write_lock.locked():
                            time.sleep(0.1)
                            continue
                        # ──────────────────────────────────────────────────────────────────────
                        for frame in self.client.recv_frames():
                            if verify_frame(frame) and (frame[3], frame[4]) == (0x81, 0x00):
                                handle_live_packet(parse_81_00(frame))
                    except socket.timeout:
                        continue
                    except ConnectionError as e:
                        if self.running:
                            log_error(f"[LIVE] Connection lost: {e}")
                            set_screwdriver_connection_status(False, f"lost: {e}")
                            notify_screwdriver_disconnected(e)
                        break
                    except Exception as e:
                        if self.running:
                            log_error(f"[LIVE] Read error: {e}")
                            set_screwdriver_connection_status(False, f"read error: {e}")
                            notify_screwdriver_disconnected(e)
                        break

            except Exception as e:
                if self.running:
                    log_error(f"[LIVE] Reconnect reason: {e}")
                    set_screwdriver_connection_status(False, f"reconnect: {e}")
            finally:
                client = self.client; self.client = None
                if client:
                    try: client.close()
                    except Exception: pass
            if self.running:
                log_debug(f"[LIVE] Reconnecting in {self.reconnect_delay:.1f}s")
                time.sleep(self.reconnect_delay)


class BitSelectorWorker(threading.Thread):
    def __init__(self, reconnect_delay=1.0, poll_delay=0.1, read_timeout=0.02):
        super().__init__(daemon=True)
        self.running = True
        self.client = None
        self.last_bits = None
        self.reconnect_delay = float(reconnect_delay)
        self.poll_delay = max(0.02, float(poll_delay))
        self.read_timeout = max(0.01, float(read_timeout))

    def stop(self):
        self.running = False
        client = self.client
        self.client = None
        if client:
            try:
                client.close()
            except Exception:
                pass
        set_selector_connection_status(False, "worker stopped")

    def _apply_fast_socket_timeout(self):
        """
        Make selector recv timeout short enough so polling cadence is not stretched
        by a long blocking recv().
        """
        try:
            client = self.client
            if client and client.sock:
                client.sock.settimeout(self.read_timeout)
        except Exception as e:
            log_error(f"[SELECTOR] failed to set fast socket timeout: {e}")

    def _send_periodic_read(self):
        client = self.client
        if client is None or client.sock is None:
            raise ConnectionError("Selector client not connected")

        with selector_lock:
            client.send_frame(cmd_read_selector_status())

    def _drain_selector_frames(self, drain_window_sec=0.06):
        """
        Read as many selector frames as available for a short time window
        without blocking the whole polling loop too long.
        """
        deadline = time.time() + max(0.01, float(drain_window_sec))

        while self.running and time.time() < deadline:
            try:
                frames = self.client.recv_frames()
                if not frames:
                    continue

                for frame in frames:
                    if not verify_frame(frame):
                        continue

                    if (frame[3], frame[4]) in ((0x03, 0x12), (0x02, 0x10)):
                        status = parse_selector_status(frame)
                        applied = process_selector_status_confirmed(status)

                        if applied:
                            current_bits = tuple(status.bits)
                            if current_bits != self.last_bits:
                                if DEBUG_SELECTOR:
                                    log_debug(f"[SELECTOR] bits confirmed={current_bits}")
                                self.last_bits = current_bits

            except socket.timeout:
                break
            except ConnectionError:
                raise
            except Exception as e:
                raise RuntimeError(f"selector drain error: {e}") from e

    def run(self):
        global selector_last_stable_bits, selector_pending_bits, selector_pending_same_count

        while self.running:
            try:
                set_selector_connection_status(False, f"connecting to {BIT_SELECTOR_HOST}:{BIT_SELECTOR_PORT}")
                self.client = BitSelectorTCPClient(BIT_SELECTOR_HOST, BIT_SELECTOR_PORT, BIT_SELECTOR_TIMEOUT)
                self.client.connect()
                self._apply_fast_socket_timeout()

                log_debug("[SELECTOR] Worker connected")

                with selector_lock:
                    selector_last_stable_bits = None
                    selector_pending_bits = None
                    selector_pending_same_count = 0
                    self.last_bits = None

                log_debug(f"[SELECTOR] Poll read interval = {self.poll_delay:.3f}s")
                log_debug(f"[SELECTOR] Read timeout = {self.read_timeout:.3f}s")

                # send read status once after connect / reconnect
                with selector_lock:
                    self.client.send_frame(READ_SELECTOR_STATUS_ON_CONNECT_FRAME)
                log_debug("[SELECTOR] Sent read-status-on-connect frame")

                # quickly read initial reply if available
                try:
                    self._drain_selector_frames(drain_window_sec=0.15)
                except socket.timeout:
                    pass

                next_poll_time = time.time()

                while self.running:
                    now = time.time()

                    if now >= next_poll_time:
                        self._send_periodic_read()
                        next_poll_time += self.poll_delay

                        # prevent drift after a long hiccup
                        if now - next_poll_time > self.poll_delay:
                            next_poll_time = now + self.poll_delay

                    self._drain_selector_frames(
                        drain_window_sec=min(0.08, max(0.02, self.poll_delay * 0.8))
                    )

                    sleep_for = max(0.005, min(0.02, next_poll_time - time.time()))
                    time.sleep(sleep_for)

            except ConnectionError as e:
                if self.running:
                    log_debug(f"[SELECTOR] Connection lost: {e}")
                    set_selector_connection_status(False, f"lost: {e}")

            except Exception as e:
                if self.running:
                    log_debug(f"[SELECTOR] Reconnect reason: {e}")
                    set_selector_connection_status(False, f"reconnect: {e}")

            finally:
                client = self.client
                self.client = None
                if client:
                    try:
                        client.close()
                    except Exception:
                        pass

            if self.running:
                log_debug(f"[SELECTOR] Reconnecting in {self.reconnect_delay:.1f}s")
                time.sleep(self.reconnect_delay)


def start_live_worker():
    global live_worker
    if live_worker is None or not live_worker.is_alive():
        live_worker = LiveStreamWorker(); live_worker.start()
        log_debug("[LIVE] Worker started")

def start_selector_worker():
    global selector_worker
    if selector_worker is None or not selector_worker.is_alive():
        selector_worker = BitSelectorWorker(
            reconnect_delay=1.0,
            poll_delay=0.1,
            read_timeout=0.02,
        )
        selector_worker.start()
        log_debug("[SELECTOR] Worker started")


# =========================================================
# RECORDING CONTROL
# =========================================================
def start_recording():
    global recording, latest_packet, prev_tightened_state, cycle_completed
    global stable_zero_speed_count, last_locking_angle
    global selector_has_been_correct, selector_missing_during_recording
    global selector_missing_error_sent, selector_expected_error
    with data_lock:
        if recording:           return "ALREADY_RECORDING"
        if not current_recipe_name: raise RuntimeError("No recipe loaded")
        if not current_size or not current_length: raise RuntimeError("Screw not set")
        recording               = True
        latest_packet           = None
        prev_tightened_state    = 0
        cycle_completed         = False
        stable_zero_speed_count = 0
        last_locking_angle      = 0
        reset_current_cycle()
        selector_has_been_correct         = True
        selector_missing_during_recording = False
        selector_missing_error_sent       = False
        selector_expected_error           = False
    start_live_worker(); start_selector_worker()
    log_debug("[RECORDER] Started")
    return "STARTED"

def stop_recording():
    global recording, prev_tightened_state, cycle_completed
    global stable_zero_speed_count, last_locking_angle, selector_expected_error
    with data_lock:
        if not recording: return None
        recording = False
    csv_path = export_results_to_csv()
    with data_lock:
        prev_tightened_state    = None
        cycle_completed         = False
        stable_zero_speed_count = 0
        last_locking_angle      = 0
        reset_current_cycle()
        selector_expected_error = False
    clear_selector_stop_wait()
    log_debug(f"[RECORDER] Stopped — csv={csv_path}")
    return csv_path


# =========================================================
# COMMAND SERVER
# =========================================================
# ── Standardised reply format ─────────────────────────────
# OK,RECIPE_LOADED
# OK,START
# OK,STOP
# INFO,SCREWDRIVER_CONNECTED
# INFO,SELECTOR_OK
# ERROR,RECIPE_LOAD_FAILED
# ERROR,START_FAILED
# ERROR,STOP_FAILED
# ERROR,UNKNOWN_COMMAND
# ERROR,SCREWDRIVER_DISCONNECTED
# ERROR,WRONG_SCREW
# ERROR,SELECTOR_REMOVED
# RESULT,OK,<torque>
# RESULT,NG,<torque>
# ─────────────────────────────────────────────────────────

def parse_client_message(message):
    msg = str(message).strip()
    low = msg.lower()

    if low == "screw_start":
        return "CMD", "START"

    if low == "screw_stop":
        return "CMD", "STOP"

    if is_recipe_name(msg):
        return "RECIPE_NAME", msg

    return "TEXT", msg

def send_reply(conn, reply: str):
    conn.sendall(str(reply).encode("utf-8"))
    log_debug(f"[SERVER] → {reply}")

def handle_client(conn, addr):
    global client_conn
    client_conn = conn
    log_debug(f"[SERVER] Client connected: {addr}")
    send_initial_connection_status_to_client()
    try:
        while True:
            data = conn.recv(1024)
            if not data: break
            message = data.decode("utf-8", errors="ignore").strip()
            if not message: continue
            log_debug(f"[SERVER] ← {message}")
            msg_type, value = parse_client_message(message)

            # ── RECIPE NAME ───────────────────────────────────────
            if msg_type == "RECIPE_NAME":
                try:
                    with data_lock:
                        if recording:
                            send_reply(conn, "ERROR,RECIPE_LOAD_FAILED")
                            continue
                    load_recipe_by_name(value)
                    send_reply(conn, "OK,RECIPE_LOADED")
                except Exception as e:
                    log_error(f"[ERROR] LOAD_RECIPE {value}: {e}")
                    send_reply(conn, "ERROR,RECIPE_LOAD_FAILED")
                continue

            # ── SCREW_START ────────────────────────────────────────
            if msg_type == "CMD" and value == "START":
                try:
                    with data_lock:
                        has_recipe   = bool(current_recipe_name and all_recipe_screws)
                        need_new_set = not recipe_sequence_active
                    if not has_recipe:
                        send_reply(conn, "ERROR,START_FAILED"); continue
                    if need_new_set:
                        begin_recipe_set(current_recipe_name)
                        set_current_screw_by_index(0)
                    elif current_screw_index < 0:
                        set_current_screw_by_index(0)
                    show_corner_monitor()
                    ok = prepare_current_screw_from_recipe(conn)
                    if not ok:
                        send_reply(conn, "ERROR,START_FAILED"); continue
                    start_recording()
                    send_reply(conn, "OK,START")
                except Exception as e:
                    log_error(f"[ERROR] START: {e}")
                    send_reply(conn, "ERROR,START_FAILED")
                continue

            # ── SCREW_STOP ─────────────────────────────────────────
            if msg_type == "CMD" and value == "STOP":
                try:
                    stop_recording()
                    clear_selector_guidance()
                    clear_missing_selector_bits()
                    clear_selector_stop_wait()
                    hide_corner_monitor()
                    next_cfg = move_to_next_screw_block()
                    if next_cfg is None:
                        finish_recipe_set()
                    send_reply(conn, "OK,STOP")
                except Exception as e:
                    log_error(f"[ERROR] STOP: {e}")
                    send_reply(conn, "ERROR,STOP_FAILED")
                continue

            # ── UNKNOWN ────────────────────────────────────────────
            send_reply(conn, "ERROR,UNKNOWN_COMMAND")

    except Exception as e:
        log_error(f"[ERROR] Client handler: {e}")
        try: send_reply(conn, "ERROR,UNKNOWN_COMMAND")
        except Exception: pass
    finally:
        if client_conn is conn: client_conn = None
        conn.close()
        log_debug(f"[SERVER] Client disconnected: {addr}")

def start_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((SERVER_HOST, SERVER_PORT)); srv.listen(5)
    log_debug(f"[SERVER] Listening on {SERVER_HOST}:{SERVER_PORT}")
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

def start_server_thread():
    global server_thread
    if server_thread is None or not server_thread.is_alive():
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()


# =============================================================================
# CORNER MONITOR UI
# =============================================================================
P_DEEP = "#0a0f18"; P_PANEL = "#0d1420"; P_CARD = "#111b27"; P_BORDER = "#1a2840"
P_DIM  = "#4a6a8a"; P_MID   = "#94a3b8"; P_BRIGHT = "#e2e8f0"
P_CYAN = "#0ea5e9"; P_BLUE  = "#38bdf8"; P_RED  = "#ef4444"; P_GREEN = "#22c55e"
P_RED_BG = "#450a0a"; P_GREEN_BG = "#052e16"; P_BLUE_BG = "#0c2840"; P_IDLE_BG = "#1e293b"
LED_NAMES = ["1", "2", "3", "4", "5", "6"]

@dataclass
class CornerData:
    tightened_state: int = 0;  torque: float = 0.0; torque_unit: str = "kgf.cm"
    min_torque: float = 0.0;   max_torque: float = 0.0
    locking_angle: int = 0;    tightening_angle: int = 0
    min_locking_angle: int = 0; max_locking_angle: int = 0
    min_tightening_angle: int = 0; max_tightening_angle: int = 0
    rotate_speed: int = 0;     error_report: str = "none"

class AnimF:
    def __init__(self, v=0.0, ms=300):
        self._c = v; self._t = v; self._s = v; self._t0 = time.monotonic(); self._d = ms / 1000.0
    def set(self, v): self._s = self._c; self._t = v; self._t0 = time.monotonic()
    @property
    def value(self):
        e = time.monotonic() - self._t0
        if e >= self._d: self._c = self._t
        else:
            p = e / self._d; self._c = self._s + (self._t - self._s) * (1 - (1-p)**3)
        return self._c

class TorqueBar(tk.Canvas):
    def __init__(self, master, **kw):
        kw.setdefault("height", 10); kw.setdefault("bg", P_PANEL); kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw); self._pct = 0; self._mn = 0; self._mx = 0
        self.bind("<Configure>", lambda e: self._draw())
    def update_values(self, val, mn, mx, lim):
        lim = max(lim, 0.01)
        self._pct = min(val/lim, 1.0); self._mn = min(mn/lim, 1.0); self._mx = min(mx/lim, 1.0)
        self._draw()
    def _draw(self):
        self.delete("all"); w = self.winfo_width() or 1; h = self.winfo_height() or 1
        pad = 2; bh = 6; y0 = (h-bh)//2
        self.create_rectangle(pad, y0, w-pad, y0+bh, fill="#1a2332", outline="")
        fw = int((w-2*pad)*self._pct)
        if fw > 0: self.create_rectangle(pad, y0, pad+fw, y0+bh, fill=P_CYAN, outline="")
        if self._mn > 0:
            x = pad+int((w-2*pad)*self._mn); self.create_rectangle(x-1, y0-3, x+1, y0+bh+3, fill=P_RED,   outline="")
        if self._mx > 0:
            x = pad+int((w-2*pad)*self._mx); self.create_rectangle(x-1, y0-3, x+1, y0+bh+3, fill=P_GREEN, outline="")

class LEDIndicator(tk.Canvas):
    def __init__(self, master, label, **kw):
        kw.setdefault("width", 62); kw.setdefault("height", 58)
        kw.setdefault("bg", P_CARD); kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self._label = label; self._state = None; self._blink_on = True
        self.bind("<Configure>", lambda e: self._draw()); self._draw()

    def set_state(self, state):
        if state != self._state: self._state = state; self._draw()

    def set_blink_phase(self, blink_on):
        if blink_on != self._blink_on:
            self._blink_on = blink_on
            if self._state in ("wrong","missing","take_again","putback"): self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 62; h = self.winfo_height() or 58
        cx = w // 2; r = 12
        s = self._state
        if s == 1:
            self.create_oval(cx-r-6,2,cx+r+6,2*r+14,fill="#0b3d2e",outline="")
            self.create_oval(cx-r,7,cx+r,7+2*r,fill=P_GREEN,outline="#34d399",width=2)
            self.create_oval(cx-r+4,11,cx-r+9,16,fill="#bbf7d0",outline="")
        elif s == "expected":
            self.create_oval(cx-r-4,4,cx+r+4,2*r+12,fill="#09251c",outline="")
            self.create_oval(cx-r,7,cx+r,7+2*r,fill="#123f31",outline=P_GREEN,width=2)
            self.create_oval(cx-r+4,11,cx-r+9,16,fill="#6ee7b7",outline="")
        elif s == "wrong":
            if self._blink_on:
                self.create_oval(cx-r-6,2,cx+r+6,2*r+14,fill="#3a1010",outline="")
                self.create_oval(cx-r,7,cx+r,7+2*r,fill=P_RED,outline="#f87171",width=2)
                self.create_oval(cx-r+4,11,cx-r+9,16,fill="#fecaca",outline="")
            else:
                self.create_oval(cx-r,7,cx+r,7+2*r,fill="#2a1111",outline="#5f1d1d",width=1)
        elif s in ("missing","putback"):
            if self._blink_on:
                self.create_oval(cx-r-6,2,cx+r+6,2*r+14,fill="#3f3208",outline="")
                self.create_oval(cx-r,7,cx+r,7+2*r,fill="#facc15",outline="#fde047",width=2)
                self.create_oval(cx-r+4,11,cx-r+9,16,fill="#fef9c3",outline="")
            else:
                self.create_oval(cx-r,7,cx+r,7+2*r,fill="#3d3314",outline="#6b5c19",width=1)
        elif s == "take_again":
            if self._blink_on:
                self.create_oval(cx-r-6,2,cx+r+6,2*r+14,fill="#0b2942",outline="")
                self.create_oval(cx-r,7,cx+r,7+2*r,fill="#38bdf8",outline="#7dd3fc",width=2)
                self.create_oval(cx-r+4,11,cx-r+9,16,fill="#e0f2fe",outline="")
            else:
                self.create_oval(cx-r,7,cx+r,7+2*r,fill="#163246",outline="#2b5870",width=1)
        elif s == 0:
            self.create_oval(cx-r,7,cx+r,7+2*r,fill="#1a2332",outline="#2a3a50",width=1)
        else:
            self.create_oval(cx-r,7,cx+r,7+2*r,fill="#78350f",outline="#a16207",width=1)
        self.create_text(cx, 7+2*r+12, text=self._label, fill=P_DIM, font=("Consolas",8,"bold"), anchor="center")


# =========================================================
# TOOLTIP HELPER
# =========================================================
class ToolTip:
    def __init__(self, widget, text_fn):
        self._w = widget; self._fn = text_fn; self._tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _=None):
        self._hide()
        try:
            x = self._w.winfo_rootx() + self._w.winfo_width() // 2
            y = self._w.winfo_rooty() + self._w.winfo_height() + 4
            self._tip = tw = tk.Toplevel(self._w)
            tw.overrideredirect(True); tw.attributes("-topmost", True)
            lbl = tk.Label(tw, text=self._fn(), bg="#1a2840", fg=P_BRIGHT,
                           font=("Consolas", 8), padx=8, pady=4, justify="left", relief="flat", bd=0)
            lbl.pack()
            tw.update_idletasks()
            tw.geometry(f"+{x - lbl.winfo_width()//2}+{y}")
        except Exception: pass

    def _hide(self, _=None):
        if self._tip:
            try: self._tip.destroy()
            except Exception: pass
            self._tip = None


# =========================================================
# CORNER MONITOR
# =========================================================
class CornerMonitor(tk.Toplevel):
    WIDTH = 320; REFRESH_MS = 40; PAD = 16; RESULT_HOLD_SEC = 4.0

    def __init__(self, master=None):
        super().__init__(master)
        self.overrideredirect(True); self.attributes("-topmost", True)
        self.configure(bg=P_DEEP)
        self._collapsed = False; self._data = CornerData()
        self._win_width  = self.WIDTH   # resizable instance width
        self._win_height = None         # None = auto from content
        self._saved_x = None; self._saved_y = None
        self._resizing = False          # suppresses _tick during resize
        self._load_win_config()         # restore saved pos/size/collapsed
        self._at = AnimF(); self._al = AnimF(); self._atn = AnimF(); self._asp = AnimF()
        self._drag_x = 0; self._drag_y = 0
        self._result_state = 0; self._result_time = 0.0
        self._result_torque = 0.0; self._result_angle = 0; self._result_error = "none"
        self._blink_on = True; self._selector_blink_on = True
        self._set_selector_message("Waiting selector...", P_DIM)
        self._build(); self._place()
        self._apply_font_scale(self._win_width, self._win_height or self._exph())
        self._tick()

    def push_packet(self, d: CornerData):
        prev = self._data.tightened_state; self._data = d
        self._at.set(d.torque); self._al.set(float(d.locking_angle))
        self._atn.set(float(d.tightening_angle)); self._asp.set(float(d.rotate_speed))
        if d.tightened_state in (1, 2) and prev not in (1, 2):
            self._result_state  = d.tightened_state; self._result_time = time.monotonic()
            self._result_torque = d.torque; self._result_angle = d.locking_angle
            self._result_error  = d.error_report

    def _build(self):
        outer = tk.Frame(self, bg=P_BORDER, padx=1, pady=1); outer.pack(fill="both", expand=True)
        self._inner = tk.Frame(outer, bg=P_PANEL); self._inner.pack(fill="both", expand=True)
        # collapsed bar
        self._coll = tk.Frame(self._inner, bg=P_PANEL)
        self._coll_dot = tk.Canvas(self._coll, width=14, height=14, bg=P_PANEL, highlightthickness=0)
        self._coll_dot.pack(side="left", padx=(12,6), pady=8)
        self._coll_lbl = tk.Label(self._coll, text="IDLE", bg=P_PANEL, fg=P_DIM, font=("Consolas",10,"bold"))
        self._coll_lbl.pack(side="left")
        eb = tk.Label(self._coll, text="\u25c2", bg=P_PANEL, fg=P_DIM, font=("Consolas",14), cursor="hand2")
        eb.pack(side="right", padx=(0,10))
        eb.bind("<Button-1>", lambda e: self._toggle())
        self._coll.bind("<Button-1>", lambda e: self._toggle())
        # expanded panel
        self._exp = tk.Frame(self._inner, bg=P_PANEL)
        self._build_header(); self._build_result_banner(); self._build_led_row()
        self._build_torque(); self._build_divider(); self._build_angles(); self._build_speed()
        self._exp.pack(fill="both", expand=True)
        self._hdr.bind("<Button-1>",       self._sd)
        self._hdr.bind("<B1-Motion>",       self._dd)
        self._hdr.bind("<ButtonRelease-1>", self._du)
        # ── resize grip (bottom-right corner) ────────────────────────────
        self._grip = tk.Label(self, text="\u22bf", bg=P_DEEP, fg=P_DIM,
                              font=("Consolas", 9), cursor="sizing")
        self._grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        self._grip.bind("<Button-1>",        self._rs)
        self._grip.bind("<B1-Motion>",       self._rd)
        self._grip.bind("<ButtonRelease-1>", self._rr)

    # ── Header with 4 status dots ─────────────────────────────────────────
    def _build_header(self):
        self._hdr = tk.Frame(self._exp, bg="#0f1923", padx=14, pady=7)
        self._hdr.pack(fill="x")
        tk.Label(self._hdr, text="TIGHTENING RESULT", bg="#0f1923", fg=P_BRIGHT,
                 font=("Consolas",11,"bold")).pack(side="left")
        cb = tk.Label(self._hdr, text="\u2715", bg="#0f1923", fg=P_DIM,
                      font=("Consolas",11), cursor="hand2")
        cb.pack(side="right", padx=(6,0))
        cb.bind("<Button-1>", lambda e: self._toggle())
        # IDLE pill
        self._h_pill = tk.Frame(self._hdr, bg=P_IDLE_BG, padx=6, pady=1)
        self._h_pill.pack(side="right", padx=(0,8))
        self._h_dot = tk.Canvas(self._h_pill, width=7, height=7, bg=P_IDLE_BG, highlightthickness=0)
        self._h_dot.pack(side="left", padx=(0,4))
        self._h_dot.create_oval(1,1,6,6,fill=P_DIM,outline="")
        self._h_lbl = tk.Label(self._h_pill, text="IDLE", bg=P_IDLE_BG, fg=P_DIM,
                                font=("Consolas",7,"bold"))
        self._h_lbl.pack(side="left")
        # 4 connection-status dots
        _DOT_DEFS = [
            ("SD",  lambda: f"Screwdriver\n{last_screwdriver_status_text}"),
            ("SEL", lambda: f"Bit Selector\n{last_selector_status_text}"),
            ("SRV", lambda: f"TCP Server ({SERVER_HOST}:{SERVER_PORT})\n"
                            f"{'RUNNING' if (server_thread and server_thread.is_alive()) else 'STOPPED'}"),
            ("CLI", lambda: f"Client\n{'CONNECTED' if client_conn is not None else 'DISCONNECTED'}"),
        ]
        dot_frame = tk.Frame(self._hdr, bg="#0f1923")
        dot_frame.pack(side="right", padx=(0,6))
        self._status_dots = []
        for abbr, tip_fn in _DOT_DEFS:
            col = tk.Frame(dot_frame, bg="#0f1923"); col.pack(side="left", padx=(0,5))
            c = tk.Canvas(col, width=10, height=10, bg="#0f1923", highlightthickness=0); c.pack()
            c.create_oval(1,1,9,9,fill=P_DIM,outline="",tags="dot")
            tk.Label(col, text=abbr, bg="#0f1923", fg=P_DIM, font=("Consolas",6)).pack()
            ToolTip(c, tip_fn)
            self._status_dots.append(c)
        tk.Frame(self._exp, bg=P_BORDER, height=1).pack(fill="x")

    def _build_result_banner(self):
        self._banner = tk.Frame(self._exp, bg=P_CARD)
        self._banner.pack(fill="both", expand=True, padx=10, pady=(6,2))
        self._bi = tk.Frame(self._banner, bg=P_CARD)
        self._bi.pack(fill="both", expand=True, padx=2, pady=2)
        self._b_state = tk.Label(self._bi, text="\u2014", bg=P_CARD, fg=P_DIM,
                                  font=("Consolas",30,"bold"), anchor="center")
        self._b_state.pack(fill="both", expand=True)
        self._b_detail = tk.Label(self._bi, text="Waiting...", bg=P_CARD, fg=P_DIM,
                                   font=("Consolas",10), anchor="center")
        self._b_detail.pack(fill="x", pady=(2,6))

    def _build_led_row(self):
        outer = tk.Frame(self._exp, bg=P_PANEL, padx=10, pady=4); outer.pack(fill="x")
        tk.Label(outer, text="BIT SELECTOR", bg=P_PANEL, fg=P_BRIGHT, font=("Consolas",10,"bold")).pack(anchor="w")
        row = tk.Frame(outer, bg=P_CARD, padx=6, pady=6,
                       highlightbackground=P_BORDER, highlightthickness=1)
        row.pack(fill="x", pady=(4,6))
        self._selector_row = row; self._leds = []
        for i, name in enumerate(LED_NAMES):
            row.grid_columnconfigure(i, weight=1)
            led = LEDIndicator(row, name)
            led.grid(row=0, column=i, padx=3, pady=3, sticky="nsew")
            self._leds.append(led)
        # selector message card
        msg_card = tk.Frame(outer, bg=P_CARD, padx=10, pady=7,
                            highlightbackground=P_BORDER, highlightthickness=1)
        msg_card.pack(fill="x", pady=(0,4))
        self._selector_msg_font = tkfont.Font(family="Consolas", size=14, weight="bold")
        self._selector_msg = tk.Label(msg_card, text="Waiting selector...", bg=P_CARD, fg=P_CYAN,
                                      font=self._selector_msg_font, anchor="w", justify="left")
        self._selector_msg.pack(fill="x")

    def _wrap_text_to_width(self, text, max_width_px, font_obj):
        words = str(text).split()
        if not words: return ""
        lines = []; current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if font_obj.measure(trial) <= max_width_px: current = trial
            else: lines.append(current); current = word
        lines.append(current); return "\n".join(lines)

    def _set_selector_message(self, text, color=P_CYAN):
        if not hasattr(self, "_selector_msg"): return
        try:
            self.update_idletasks()
            width_px = max((self._selector_row.winfo_width() if hasattr(self,"_selector_row") else 0) - 12, 160)
        except Exception: width_px = 260
        chosen_size = 14; wrapped_text = str(text)
        for size in (14,13,12,11,10,9,8):
            self._selector_msg_font.configure(size=size)
            wrapped = self._wrap_text_to_width(str(text), width_px, self._selector_msg_font)
            if len(wrapped.splitlines() or [""]) <= 3:
                chosen_size = size; wrapped_text = wrapped; break
            chosen_size = size; wrapped_text = wrapped
        self._selector_msg_font.configure(size=chosen_size)
        self._selector_msg.configure(text=wrapped_text, fg=color)

    def _build_selector_message(self, bits, expected_bit, wrong_bits, missing_bits):
        missing_names = [selector_bit_to_size(b) for b in sorted(missing_bits)]
        stop_wait_active, stop_wait_message = get_selector_stop_wait()
        if stop_wait_active:
            active_bits  = [i+1 for i,v in enumerate(bits or []) if v==1]
            active_names = [selector_bit_to_size(b) for b in active_bits]
            if active_bits:
                return (f"{stop_wait_message} Put back {', '.join(active_names)}.", "#facc15")
            return stop_wait_message, "#facc15"
        active_wrong = sorted(
            b for b in set(wrong_bits or [])
            if isinstance(bits,(list,tuple)) and (b-1)<len(bits) and bits[b-1]==1
        )
        active_wrong_names  = [selector_bit_to_size(b) for b in active_wrong]
        expected_is_active  = bool(
            expected_bit and isinstance(bits,(list,tuple)) and
            (expected_bit-1)<len(bits) and bits[expected_bit-1]==1
        )
        if get_selector_expected_error() and expected_bit:
            if active_wrong:
                if expected_is_active:
                    return (f"Wrong bit taken: {', '.join(active_wrong_names)}. Put back wrong bit(s) only.", P_RED)
                return (f"Wrong bit taken: {', '.join(active_wrong_names)}. Put back, then take {expected_bit}.", P_RED)
            return (f"Error: put back bit {expected_bit}. Take it again.", P_RED)
        if missing_bits and not expected_bit:
            return (f"Put back: {', '.join(missing_names)}.", "#facc15")
        if active_wrong:
            if expected_is_active:
                return (f"Wrong bit(s) taken: {', '.join(active_wrong_names)}. Put back wrong bit(s) only.", P_RED)
            return (f"Wrong bit taken: {', '.join(active_wrong_names)}. Please take {expected_bit or 'correct bit'}.", P_RED)
        if expected_bit:
            if isinstance(bits,(list,tuple)) and (expected_bit-1)<len(bits) and bits[expected_bit-1]==1:
                return f"Bit {expected_bit} selected. Ready.", P_GREEN
            return f"Please take bit {expected_bit}.", P_CYAN
        return "Waiting...", P_CYAN

    def _build_torque(self):
        sec = tk.Frame(self._exp, bg=P_PANEL, padx=14, pady=6); sec.pack(fill="x")
        r = tk.Frame(sec, bg=P_PANEL); r.pack(fill="x")
        tk.Label(r, text="TORQUE", bg=P_PANEL, fg=P_BRIGHT, font=("Consolas",10,"bold")).pack(side="left")
        self._unit = tk.Label(r, text="kgf.cm", bg=P_BLUE_BG, fg=P_BLUE,
                               font=("Consolas",8,"bold"), padx=8, pady=1)
        self._unit.pack(side="right")
        self._tq = tk.Label(sec, text="0.00", bg=P_PANEL, fg=P_BRIGHT, font=("Consolas",30,"bold"))
        self._tq.pack(pady=(2,1))
        self._tbar = TorqueBar(sec); self._tbar.pack(fill="x", pady=(0,3))
        mm = tk.Frame(sec, bg=P_PANEL); mm.pack(fill="x")
        self._mnt = tk.Label(mm, text="MIN 0.00", bg=P_PANEL, fg=P_RED,   font=("Consolas",8,"bold"))
        self._mnt.pack(side="left")
        self._mxt = tk.Label(mm, text="MAX 0.00", bg=P_PANEL, fg=P_GREEN, font=("Consolas",8,"bold"))
        self._mxt.pack(side="right")

    def _build_divider(self):
        c = tk.Canvas(self._exp, height=1, bg=P_PANEL, highlightthickness=0); c.pack(fill="x", padx=14)
        c.bind("<Configure>", lambda e, cv=c: self._gl(cv))
    @staticmethod
    def _gl(cv):
        cv.delete("all"); w = cv.winfo_width()
        if w < 4: return
        m = w // 2
        for x in range(w):
            r = max(0, 1 - abs(x-m)/m)
            cv.create_line(x,0,x,1, fill=f"#{int(0x1a*r):02x}{int(0x28*r):02x}{int(0x40*r):02x}")

    def _build_angles(self):
        sec = tk.Frame(self._exp, bg=P_PANEL, padx=14, pady=6); sec.pack(fill="x")
        sec.grid_columnconfigure(0, weight=1); sec.grid_columnconfigure(1, weight=1)
        self._lw = self._acard(sec, "LOCK ANGLE",  0)
        self._tw = self._acard(sec, "TIGHT ANGLE", 1)

    def _acard(self, par, title, col):
        c = tk.Frame(par, bg=P_CARD, padx=10, pady=6,
                     highlightbackground=P_BORDER, highlightthickness=1)
        c.grid(row=0, column=col, padx=4, sticky="nsew")
        tk.Label(c, text=title, bg=P_CARD, fg=P_BRIGHT, font=("Consolas",10,"bold")).pack(anchor="w")
        vf = tk.Frame(c, bg=P_CARD); vf.pack(anchor="w", pady=(3,3))
        v = tk.Label(vf, text="0", bg=P_CARD, fg=P_BRIGHT, font=("Consolas",20,"bold")); v.pack(side="left")
        tk.Label(vf, text="\u00b0", bg=P_CARD, fg=P_DIM, font=("Consolas",12)).pack(side="left", anchor="s", pady=(0,2))
        lf = tk.Frame(c, bg=P_CARD); lf.pack(fill="x")
        mn = tk.Label(lf, text="\u21930", bg=P_CARD, fg=P_RED,   font=("Consolas",7,"bold")); mn.pack(side="left")
        mx = tk.Label(lf, text="\u21910", bg=P_CARD, fg=P_GREEN, font=("Consolas",7,"bold")); mx.pack(side="right")
        return {"v": v, "mn": mn, "mx": mx}

    def _build_speed(self):
        sec = tk.Frame(self._exp, bg=P_PANEL, padx=14, pady=5); sec.pack(fill="x")
        tk.Label(sec, text="SPEED", bg=P_PANEL, fg=P_BRIGHT, font=("Consolas",10,"bold")).pack(side="left")
        rf = tk.Frame(sec, bg=P_PANEL); rf.pack(side="right")
        self._spv = tk.Label(rf, text="0", bg=P_PANEL, fg=P_MID, font=("Consolas",13,"bold")); self._spv.pack(side="left")
        tk.Label(rf, text=" RPM", bg=P_PANEL, fg=P_DIM, font=("Consolas",8,"bold")).pack(side="left")

    _ST = {0:("IDLE",P_DIM,P_IDLE_BG), 1:("OK",P_GREEN,P_GREEN_BG), 2:("NG",P_RED,P_RED_BG), 3:("RUNNING",P_CYAN,P_BLUE_BG)}
    def _set_pill(self, s):
        lbl, fg, bg = self._ST.get(s, self._ST[0])
        self._h_lbl.configure(text=lbl, fg=fg, bg=bg); self._h_pill.configure(bg=bg)
        self._h_dot.configure(bg=bg); self._h_dot.delete("all"); self._h_dot.create_oval(1,1,6,6,fill=fg,outline="")
        self._coll_lbl.configure(text=lbl, fg=fg)
        self._coll_dot.delete("all"); self._coll_dot.create_oval(1,1,13,13,fill=fg,outline="")

    def _update_banner(self):
        age = time.monotonic() - self._result_time; rs = self._result_state
        if rs == 0 or self._result_time == 0:
            self._set_banner_bg(P_CARD)
            self._b_state.configure(text="\u2014", fg=P_DIM, bg=P_CARD)
            self._b_detail.configure(text="Waiting...", fg=P_DIM, bg=P_CARD); return
        is_ok = rs == 1
        state_txt = "\u2713  O K" if is_ok else "\u2717  N G"
        col   = P_GREEN if is_ok else P_RED
        bg_on = P_GREEN_BG if is_ok else P_RED_BG
        if age < 2.0:
            self._blink_on = not self._blink_on
            bg = bg_on if self._blink_on else P_CARD; fg = col if self._blink_on else P_DIM
        elif age < self.RESULT_HOLD_SEC: bg = bg_on; fg = col
        else: bg = P_CARD; fg = col
        self._set_banner_bg(bg)
        self._b_state.configure(text=state_txt, fg=fg, bg=bg, font=("Consolas",30,"bold"))
        detail = f"T={self._result_torque:.2f}   A={self._result_angle}\u00b0"
        if self._result_error and self._result_error != "none":
            detail += f"   ERR: {self._result_error}"
        self._b_detail.configure(text=detail, fg=fg, bg=bg)

    def _set_banner_bg(self, bg):
        self._banner.configure(bg=bg); self._bi.configure(bg=bg)

    def _toggle(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._exp.pack_forget(); self._coll.pack(fill="x"); self.geometry("180x44")
        else:
            self._coll.pack_forget(); self._exp.pack(fill="both", expand=True)
            self.geometry(f"{self._win_width}x{self._exph()}")
        self._place(); self._save_win_config()

    def _exph(self):
        self.update_idletasks(); return self._exp.winfo_reqheight() + 4

    def _place(self):
        self.update_idletasks()
        w = self._win_width if not self._collapsed else 180
        h = (self._win_height if (self._win_height and not self._collapsed)
             else (self._exph() if not self._collapsed else 44))
        if self._saved_x is not None:
            x, y = self._saved_x, self._saved_y
            sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
            x = max(0, min(x, sw - w)); y = max(0, min(y, sh - 30))
        else:
            sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
            x = (sw - w) // 2; y = (sh - h) // 2 + 130
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── drag to move ──────────────────────────────────────────────────────
    def _sd(self, e): self._drag_x = e.x; self._drag_y = e.y
    def _dd(self, e):
        nx = self.winfo_x() + e.x - self._drag_x
        ny = self.winfo_y() + e.y - self._drag_y
        self.geometry(f"+{nx}+{ny}")
        self._saved_x = nx; self._saved_y = ny
    def _du(self, e): self._save_win_config()

    # ── font scaling (applied once on resize release) ─────────────────────
    _BASE_W = 320; _BASE_H = 650

    def _apply_font_scale(self, w, h):
        sw = max(0.55, w / self._BASE_W)
        sh = max(0.55, h / self._BASE_H)
        sz_banner = max(18, int(30 * min(sw * 1.1, sh * 1.6)))
        sz_detail = max(8,  int(10 * sw))
        sz_torque = max(16, int(30 * sw))
        sz_angle  = max(12, int(20 * sw))
        sz_speed  = max(9,  int(13 * sw))
        sz_label  = max(7,  int(8  * sw))
        try:
            self._b_state .configure(font=("Consolas", sz_banner, "bold"))
            self._b_detail.configure(font=("Consolas", sz_detail))
            self._tq      .configure(font=("Consolas", sz_torque, "bold"))
            self._unit    .configure(font=("Consolas", sz_label,  "bold"))
            self._mnt     .configure(font=("Consolas", sz_label,  "bold"))
            self._mxt     .configure(font=("Consolas", sz_label,  "bold"))
            self._spv     .configure(font=("Consolas", sz_speed,  "bold"))
            for d in (self._lw, self._tw):
                d["v"] .configure(font=("Consolas", sz_angle, "bold"))
                d["mn"].configure(font=("Consolas", sz_label, "bold"))
                d["mx"].configure(font=("Consolas", sz_label, "bold"))
        except Exception: pass

    # ── resize grip handlers ──────────────────────────────────────────────
    _MIN_W = 362; _MIN_H = 592

    def _rs(self, e):
        self._resizing = True
        self._rsx = e.x_root; self._rsy = e.y_root
        self._rsw = self._win_width
        self._rsh = self._win_height if self._win_height else self.winfo_height()

    def _rd(self, e):
        new_w = self._rsw + (e.x_root - self._rsx)
        new_h = self._rsh + (e.y_root - self._rsy)
        if new_w < self._MIN_W:
            new_w = self._MIN_W; self._rsx = e.x_root; self._rsw = self._MIN_W
        if new_h < self._MIN_H:
            new_h = self._MIN_H; self._rsy = e.y_root; self._rsh = self._MIN_H
        self._win_width = new_w; self._win_height = new_h
        if not self._collapsed:
            self.geometry(f"{new_w}x{new_h}+{self.winfo_x()}+{self.winfo_y()}")

    def _rr(self, e):
        self._resizing = False
        self._apply_font_scale(self._win_width, self._win_height or self.winfo_height())
        self._save_win_config()

    # ── persistent config ─────────────────────────────────────────────────
    _CFG_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "sudong_ui_config.json"
    )

    def _load_win_config(self):
        try:
            with open(self._CFG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self._saved_x    = cfg.get("x")
            self._saved_y    = cfg.get("y")
            self._win_width  = int(cfg.get("width",  self.WIDTH))
            self._win_height = cfg.get("height")
            self._collapsed  = bool(cfg.get("collapsed", False))
        except Exception: pass

    def _save_win_config(self):
        try:
            with open(self._CFG_PATH, "w", encoding="utf-8") as f:
                json.dump({"x": self.winfo_x(), "y": self.winfo_y(),
                           "width": self._win_width, "height": self._win_height,
                           "collapsed": self._collapsed}, f, indent=2)
        except Exception: pass

    def _tick(self):
        try:
            if self._resizing:
                self.after(self.REFRESH_MS, self._tick); return
            self._selector_blink_on = not self._selector_blink_on
            d = self._data
            self._set_pill(d.tightened_state); self._update_banner()
            tv = self._at.value; self._tq.configure(text=f"{tv:.2f}"); self._unit.configure(text=d.torque_unit)
            self._mnt.configure(text=f"MIN {d.min_torque:.2f}"); self._mxt.configure(text=f"MAX {d.max_torque:.2f}")
            lim = max(d.max_torque, d.torque, 1)
            self._tbar.update_values(tv, d.min_torque, d.max_torque, lim)
            self._tq.configure(fg={1:P_GREEN,2:P_RED}.get(d.tightened_state, P_BRIGHT))
            self._lw["v"].configure(text=str(int(round(self._al.value))))
            self._lw["mn"].configure(text=f"\u21930{d.min_locking_angle}")
            self._lw["mx"].configure(text=f"\u21910{d.max_locking_angle}")
            self._tw["v"].configure(text=str(int(round(self._atn.value))))
            self._tw["mn"].configure(text=f"\u21930{d.min_tightening_angle}")
            self._tw["mx"].configure(text=f"\u21910{d.max_tightening_angle}")
            self._spv.configure(text=str(int(round(self._asp.value))))

            bits = get_latest_selector_bits(); expected_bit, wrong_bits = get_selector_guidance()
            missing_bits = get_missing_selector_bits()
            selector_msg, selector_color = self._build_selector_message(bits, expected_bit, wrong_bits, missing_bits)
            self._set_selector_message(selector_msg, selector_color)
            stop_wait_active, _ = get_selector_stop_wait()
            for i, led in enumerate(self._leds):
                bit_no    = i + 1
                raw_state = bits[i] if i < len(bits) else None
                led.set_blink_phase(self._selector_blink_on)
                if stop_wait_active and raw_state == 1: led.set_state("putback")
                elif bit_no in wrong_bits and raw_state == 1: led.set_state("wrong")
                elif bit_no in missing_bits and raw_state == 1: led.set_state("putback")
                elif expected_bit == bit_no:
                    if get_selector_expected_error():
                        led.set_state(1 if raw_state == 1 else "take_again")
                    else:
                        led.set_state(1 if raw_state == 1 else "expected")
                else: led.set_state(raw_state)

            # ── Update 4 connection-status dots ───────────────────
            for dot_canvas, is_online in zip(self._status_dots, [
                screwdriver_connected,
                selector_connected,
                bool(server_thread and server_thread.is_alive()),
                client_conn is not None,
            ]):
                dot_canvas.itemconfig("dot", fill=P_GREEN if is_online else P_RED)
            # ──────────────────────────────────────────────────────

        except Exception:
            pass
        self.after(self.REFRESH_MS, self._tick)

    def reset_view(self):
        self._data = CornerData()
        self._at = AnimF(); self._al = AnimF(); self._atn = AnimF(); self._asp = AnimF()
        self._result_state = 0; self._result_time = 0.0
        self._result_torque = 0.0; self._result_angle = 0; self._result_error = "none"
        self._blink_on = True; self._selector_blink_on = True


# =========================================================
# BOOT / MAIN
# =========================================================
def clear_loaded_recipe():
    global current_product_id, current_recipe_path, current_recipe_name
    global all_recipe_screws, current_screw_index
    global current_size, current_length, current_torque
    global current_screw_count, current_screw_block_id, current_screw_block_name
    global session_product_id, session_csv_path, session_started_at
    global recipe_sequence_active, current_recipe_set_no, screw_counter, result_rows
    global selector_has_been_correct, selector_missing_during_recording
    global selector_missing_error_sent, selector_expected_error
    with data_lock:
        current_product_id = ""; current_recipe_path = ""; current_recipe_name = ""
        all_recipe_screws  = []; current_screw_index = -1
        current_size = ""; current_length = ""; current_torque = 0.0
        current_screw_count = 0; current_screw_block_id = ""; current_screw_block_name = ""
        session_product_id = ""; session_csv_path = ""; session_started_at = ""
        recipe_sequence_active = False; current_recipe_set_no = 0
        screw_counter = 0; result_rows = []
        selector_has_been_correct = False; selector_missing_during_recording = False
        selector_missing_error_sent = False; selector_expected_error = False
    clear_selector_guidance(); clear_missing_selector_bits(); clear_selector_stop_wait()

def boot_runtime():
    ensure_output_folder()
    clear_loaded_recipe()
    log_debug("[BOOT] Ready — waiting for client")
    start_live_worker()
    start_selector_worker()
    start_server_thread()

def run_desktop_app():
    global corner_monitor, ui_root
    root = tk.Tk()
    root.withdraw()
    ui_root = root
    corner_monitor = None
    log_debug("[UI] UI runtime ready (corner monitor not created yet)")
    boot_runtime()
    try:
        root.mainloop()
    finally:
        if live_worker:
            live_worker.stop()
        if selector_worker:
            selector_worker.stop()

def main():
    run_desktop_app()

if __name__ == "__main__":
    main()