# utils/constants.py
import os

# UI Constants
BTN_HEIGHT = 64
BTN_FONT = 26
BTN_WIDTH = 360
SPACING = 16
TITLE_FONT = 40

# Password
def load_password():
    try:
        with open("password.txt", "r") as f:
            return f.read().strip()
    except:
        return "1234"

TECH_PASSWORD = load_password()

# YOLO Availability
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False