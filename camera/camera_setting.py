import sys
import time
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QGroupBox, QPushButton, QLabel,
                               QTextEdit, QTabWidget, QTableWidget, QTableWidgetItem,
                               QHeaderView, QComboBox, QSpinBox, QDoubleSpinBox,
                               QLineEdit, QMessageBox, QSplitter, QScrollArea,
                               QProgressBar, QCheckBox, QFrame, QTreeWidget,
                               QTreeWidgetItem, QFileDialog, QDialog,
                               QDialogButtonBox, QFormLayout, QSizePolicy)  # 添加 QSizePolicy
from PySide6.QtCore import Qt, QTimer, Signal, QThread, Slot
from PySide6.QtGui import QFont, QColor, QPalette, QBrush

from camera.SciCam_class import *
import socket
import struct
from ctypes import c_bool

from PySide6.QtGui import QImage, QPixmap

def show_image(self):

    w = self.camera_worker.last_width
    h = self.camera_worker.last_height
    data = bytes(self.camera_worker.last_image_data)

    img = QImage(data, w, h, w, QImage.Format_Grayscale8)
    self.image_label.setPixmap(QPixmap.fromImage(img))


# Replicate the GetEnumName function from the console script
def GetEnumName(enumCls, value):
    """Get enum name from value"""
    if enumCls is None:
        return None
    try:
        for name, member in enumCls.__members__.items():
            if member == value:
                return name
    except:
        pass
    return None


# Replicate the uint32_to_ipv4 function
def uint32_to_ipv4(ip_uint32):
    """Convert uint32 to IPv4 address string"""
    try:
        network_order_ip = socket.htonl(ip_uint32)
        packed_ip = struct.pack("!I", network_order_ip)
        ipv4_address = socket.inet_ntoa(packed_ip)
        return ipv4_address
    except:
        return "0.0.0.0"


# Modified GetNodeValueStr to accept camera instance
def GetNodeValueStr(camera, xmlType, node):
    """Get node value as string"""
    if camera is None:
        return "N/A"

    iVal = SCI_NODE_VAL_INT()
    bVal = c_bool()
    fVal = SCI_NODE_VAL_FLOAT()
    eVal = SCI_NODE_VAL_ENUM()
    sVal = SCI_NODE_VAL_STRING()
    strVal = "N/A"

    try:
        nodeType = node.type
        node_name = node.name.decode() if node.name else ""

        if nodeType == SciCamNodeType.SciCam_NodeType_Bool:
            reVal = camera.SciCam_GetBoolValueEx(xmlType, node_name, bVal)
            if reVal == SCI_CAMERA_OK:
                strVal = str(bVal.value)
        elif nodeType == SciCamNodeType.SciCam_NodeType_Int:
            reVal = camera.SciCam_GetIntValueEx(xmlType, node_name, iVal)
            if reVal == SCI_CAMERA_OK:
                strVal = str(iVal.nVal)
        elif nodeType == SciCamNodeType.SciCam_NodeType_Float:
            reVal = camera.SciCam_GetFloatValueEx(xmlType, node_name, fVal)
            if reVal == SCI_CAMERA_OK:
                strVal = str(fVal.dVal)
        elif nodeType == SciCamNodeType.SciCam_NodeType_Enum:
            reVal = camera.SciCam_GetEnumValueEx(xmlType, node_name, eVal)
            if reVal == SCI_CAMERA_OK:
                strVal = str(eVal.nVal)
        elif nodeType == SciCamNodeType.SciCam_NodeType_String:
            reVal = camera.SciCam_GetStringValueEx(xmlType, node_name, sVal)
            if reVal == SCI_CAMERA_OK:
                strVal = str(sVal.val.decode())
    except Exception as e:
        strVal = f"Error: {str(e)}"

    return strVal


class EditNodeDialog(QDialog):
    """Dialog for editing node values"""

    def __init__(self, camera, node, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.node = node
        self.setWindowTitle(f"Edit Node: {node.name.decode() if node.name else 'Unknown'}")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        form_layout = QFormLayout()

        # Node name (readonly)
        self.name_label = QLabel(self.node.name.decode() if self.node.name else "Unknown")
        form_layout.addRow("Node Name:", self.name_label)

        # Node type (readonly)
        node_type = GetEnumName(SciCamNodeType, self.node.type) or str(self.node.type)
        self.type_label = QLabel(node_type)
        form_layout.addRow("Node Type:", self.type_label)

        # Value editor based on node type
        self.value_widget = None
        if self.node.type == SciCamNodeType.SciCam_NodeType_Bool:
            self.value_widget = QCheckBox()
            # Try to get current value
            bVal = c_bool()
            reVal = self.camera.SciCam_GetBoolValueEx(SciCamDeviceXmlType.SciCam_DeviceXml_Camera,
                                                      self.node.name.decode(), bVal)
            if reVal == SCI_CAMERA_OK:
                self.value_widget.setChecked(bVal.value)
        elif self.node.type == SciCamNodeType.SciCam_NodeType_Int:
            self.value_widget = QSpinBox()
            self.value_widget.setRange(-1000000, 1000000)
            # Try to get current value and range
            iVal = SCI_NODE_VAL_INT()
            reVal = self.camera.SciCam_GetIntValueEx(SciCamDeviceXmlType.SciCam_DeviceXml_Camera,
                                                     self.node.name.decode(), iVal)
            if reVal == SCI_CAMERA_OK:
                self.value_widget.setValue(iVal.nVal)
                self.value_widget.setRange(iVal.nMin, iVal.nMax)
                if iVal.nInc > 0:
                    self.value_widget.setSingleStep(iVal.nInc)
        elif self.node.type == SciCamNodeType.SciCam_NodeType_Float:
            self.value_widget = QDoubleSpinBox()
            self.value_widget.setRange(-1000000.0, 1000000.0)
            self.value_widget.setDecimals(6)
            # Try to get current value and range
            fVal = SCI_NODE_VAL_FLOAT()
            reVal = self.camera.SciCam_GetFloatValueEx(SciCamDeviceXmlType.SciCam_DeviceXml_Camera,
                                                       self.node.name.decode(), fVal)
            if reVal == SCI_CAMERA_OK:
                self.value_widget.setValue(fVal.dVal)
                self.value_widget.setRange(fVal.dMin, fVal.dMax)
        elif self.node.type == SciCamNodeType.SciCam_NodeType_Enum:
            self.value_widget = QComboBox()
            # Try to get enum values
            eVal = SCI_NODE_VAL_ENUM()
            reVal = self.camera.SciCam_GetEnumValueEx(SciCamDeviceXmlType.SciCam_DeviceXml_Camera,
                                                      self.node.name.decode(), eVal)
            if reVal == SCI_CAMERA_OK:
                for i in range(eVal.itemCount):
                    item_text = f"{eVal.items[i].val}: {eVal.items[i].desc}"
                    self.value_widget.addItem(item_text, eVal.items[i].val)
                    if eVal.items[i].val == eVal.nVal:
                        self.value_widget.setCurrentIndex(i)
        elif self.node.type == SciCamNodeType.SciCam_NodeType_String:
            self.value_widget = QLineEdit()
            # Try to get current value
            sVal = SCI_NODE_VAL_STRING()
            reVal = self.camera.SciCam_GetStringValueEx(SciCamDeviceXmlType.SciCam_DeviceXml_Camera,
                                                        self.node.name.decode(), sVal)
            if reVal == SCI_CAMERA_OK:
                self.value_widget.setText(sVal.val.decode())

        if self.value_widget:
            form_layout.addRow("Value:", self.value_widget)

        layout.addLayout(form_layout)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.resize(400, 200)

    def get_value(self):
        """Get the edited value"""
        if self.node.type == SciCamNodeType.SciCam_NodeType_Bool:
            return self.value_widget.isChecked()
        elif self.node.type == SciCamNodeType.SciCam_NodeType_Int:
            return self.value_widget.value()
        elif self.node.type == SciCamNodeType.SciCam_NodeType_Float:
            return self.value_widget.value()
        elif self.node.type == SciCamNodeType.SciCam_NodeType_Enum:
            return self.value_widget.currentData()
        elif self.node.type == SciCamNodeType.SciCam_NodeType_String:
            return self.value_widget.text()
        return None


class CameraWorker(QThread):
    """Worker thread for camera operations"""
    log_signal = Signal(str)
    device_list_signal = Signal(list)
    image_grabbed_signal = Signal(bytes, int, int)  # 修改为发射图像数据和尺寸
    image_saved_signal = Signal(str)  # 添加图像保存信号

    def __init__(self):
        super().__init__()
        self.camera = SciCamera()
        self.devices = []
        self.current_device = None
        self.is_grabbing = False
        self.continuous_grab = False  # 添加连续抓取标志

        # 图像相关属性
        self.last_image_data = None
        self.last_width = 0
        self.last_height = 0
        self.last_pixel_type = SciCamPixelType.Mono8
        self.save_image_triggered = False
        self.save_image_path = ""

    def discovery_devices(self):
        """Discover available devices"""
        try:
            self.log_signal.emit("Discovering devices...")
            devInfos = SCI_DEVICE_INFO_LIST()
            reVal = SciCamera.SciCam_DiscoveryDevices(devInfos, SciCamTLType.SciCam_TLType_Unkown)

            if reVal != SCI_CAMERA_OK:
                self.log_signal.emit(f"Discovery failed: Error {reVal}")
                return

            device_list = []
            for index in range(devInfos.count):
                device_list.append({
                    'index': index,
                    'info': devInfos.pDevInfo[index]
                })

            self.devices = device_list
            self.device_list_signal.emit(device_list)
            self.log_signal.emit(f"Found {len(device_list)} device(s)")

        except Exception as e:
            self.log_signal.emit(f"Error discovering devices: {str(e)}")

    def open_device(self, device_index):
        """Open selected device"""
        try:
            if device_index < 0 or device_index >= len(self.devices):
                self.log_signal.emit("Invalid device index")
                return False

            device_info = self.devices[device_index]['info']
            reVal = self.camera.SciCam_CreateDevice(device_info)
            if reVal != SCI_CAMERA_OK:
                self.log_signal.emit(f"Create device failed: Error {reVal}")
                return False

            reVal = self.camera.SciCam_OpenDevice()
            if reVal != SCI_CAMERA_OK:
                self.log_signal.emit(f"Open device failed: Error {reVal}")
                return False

            self.current_device = device_info
            self.is_grabbing = False
            self.log_signal.emit("Device opened successfully")
            return True

        except Exception as e:
            self.log_signal.emit(f"Error opening device: {str(e)}")
            return False

    def close_device(self):
        """Close current device"""
        try:
            if self.camera:
                # Stop grabbing if active
                if self.is_grabbing:
                    self.stop_grabbing()

                reVal = self.camera.SciCam_CloseDevice()
                if reVal != SCI_CAMERA_OK:
                    self.log_signal.emit(f"Close device failed: Error {reVal}")
                else:
                    self.camera.SciCam_DeleteDevice()
                    self.current_device = None
                    self.is_grabbing = False
                    self.log_signal.emit("Device closed")

        except Exception as e:
            self.log_signal.emit(f"Error closing device: {str(e)}")

    def run(self):
        """Continuous grabbing thread"""
        while self.continuous_grab and self.is_grabbing:
            try:
                # 抓取单帧
                success = self.grab_single_image()
                if success and self.last_image_data:
                    # 确保图像数据是bytes类型
                    if isinstance(self.last_image_data, ctypes.Array):
                        image_bytes = bytes(self.last_image_data)
                    else:
                        image_bytes = self.last_image_data

                    # 发送图像数据到UI
                    self.image_grabbed_signal.emit(
                        image_bytes,
                        self.last_width,
                        self.last_height
                    )

                    # 如果触发了保存图像
                    if self.save_image_triggered and self.save_image_path:
                        self.save_current_image()

                # 控制帧率
                time.sleep(0.033)  # ~30 FPS

            except Exception as e:
                self.log_signal.emit(f"Error in continuous grabbing: {str(e)}")
                time.sleep(1)

    def start_grabbing(self, timeout, buffer_count, strategy):
        """Start continuous grabbing"""
        try:
            # Apply settings
            self.camera.SciCam_SetGrabTimeout(timeout)
            self.camera.SciCam_SetGrabBufferCount(buffer_count)
            self.camera.SciCam_SetGrabStrategy(strategy)

            # Start grabbing
            reVal = self.camera.SciCam_StartGrabbing()
            if reVal == SCI_CAMERA_OK:
                self.is_grabbing = True
                self.continuous_grab = True
                self.log_signal.emit("Continuous grabbing started")

                # 启动连续抓取线程
                if not self.isRunning():
                    self.start()

                return True
            else:
                self.log_signal.emit(f"Failed to start grabbing: Error {reVal}")
                return False

        except Exception as e:
            self.log_signal.emit(f"Error starting grabbing: {str(e)}")
            return False

    def stop_grabbing(self):
        """Stop continuous grabbing"""
        try:
            self.continuous_grab = False
            reVal = self.camera.SciCam_StopGrabbing()
            if reVal == SCI_CAMERA_OK:
                self.is_grabbing = False
                self.log_signal.emit("Continuous grabbing stopped")
                return True
            else:
                self.log_signal.emit(f"Failed to stop grabbing: Error {reVal}")
                return False

        except Exception as e:
            self.log_signal.emit(f"Error stopping grabbing: {str(e)}")
            return False

    def grab_single_image(self, timeout=None):
        """Grab a single image"""
        try:
            ppayload = ctypes.c_void_p()
            reVal = self.camera.SciCam_Grab(ppayload)
            if reVal != SCI_CAMERA_OK:
                self.log_signal.emit(f"Grab failed: Error {reVal}")
                return None

            payloadAttribute = SCI_CAM_PAYLOAD_ATTRIBUTE()
            SciCam_Payload_GetAttribute(ppayload, payloadAttribute)

            imgWidth = payloadAttribute.imgAttr.width
            imgHeight = payloadAttribute.imgAttr.height
            imgPixelType = payloadAttribute.imgAttr.pixelType

            imgData = ctypes.c_void_p()
            SciCam_Payload_GetImage(ppayload, imgData)

            dstImgSize = ctypes.c_int()

            # 判断是否为单色图像
            mono_formats = [
                SciCamPixelType.Mono1p, SciCamPixelType.Mono2p, SciCamPixelType.Mono4p,
                SciCamPixelType.Mono8s, SciCamPixelType.Mono8, SciCamPixelType.Mono10,
                SciCamPixelType.Mono10p, SciCamPixelType.Mono12, SciCamPixelType.Mono12p,
                SciCamPixelType.Mono14, SciCamPixelType.Mono16,
                SciCamPixelType.Mono10Packed, SciCamPixelType.Mono12Packed
            ]

            if imgPixelType in mono_formats:
                target_type = SciCamPixelType.Mono8
            else:
                target_type = SciCamPixelType.RGB8

            # 获取所需缓冲区大小
            SciCam_Payload_ConvertImage(
                payloadAttribute.imgAttr,
                imgData,
                target_type,
                None,
                dstImgSize,
                True
            )

            # 分配缓冲区
            pDstData = (ctypes.c_ubyte * dstImgSize.value)()

            SciCam_Payload_ConvertImageEx(
                payloadAttribute.imgAttr,
                imgData,
                target_type,
                pDstData,
                dstImgSize,
                True,
                0
            )

            # 存储图像数据
            self.last_image_data = bytes(pDstData)
            self.last_width = imgWidth
            self.last_height = imgHeight
            self.last_pixel_type = target_type

            self.camera.SciCam_FreePayload(ppayload)

            return True

        except Exception as e:
            self.log_signal.emit(f"Error grabbing image: {str(e)}")
            return False

    def trigger_save_image(self, file_path):
        """Trigger saving of the current image"""
        self.save_image_triggered = True
        self.save_image_path = file_path

    def save_current_image(self):
        """Save the current image to file"""
        try:
            if not self.last_image_data or not self.save_image_path:
                return False

            reVal = SciCam_Payload_SaveImage(
                self.save_image_path,
                self.last_pixel_type,
                self.last_image_data,
                self.last_width,
                self.last_height
            )

            if reVal == SCI_CAMERA_OK:
                self.image_saved_signal.emit(f"Image saved to {self.save_image_path}")
                self.log_signal.emit(f"Image saved to {self.save_image_path}")
            else:
                self.log_signal.emit(f"Save failed: Error {reVal}")

            # 重置保存标志
            self.save_image_triggered = False
            self.save_image_path = ""

            return reVal == SCI_CAMERA_OK

        except Exception as e:
            self.log_signal.emit(f"Error saving image: {str(e)}")
            self.save_image_triggered = False
            self.save_image_path = ""
            return False


class DeviceInfoWidget(QWidget):
    """Widget to display device information"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Device info group
        info_group = QGroupBox("Device Information")
        info_layout = QVBoxLayout()

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(300)
        self.info_text.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
            }
        """)

        info_layout.addWidget(self.info_text)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        self.setLayout(layout)

    def update_info(self, device_info):
        """Update device information display"""
        if not device_info:
            self.info_text.setText("No device selected")
            return

        info_str = ""

        # Device type
        devType = GetEnumName(SciCamDeviceType, device_info.devType)
        info_str += f"<b>Device Type:</b> {devType if devType else 'Unknown'}<br>"

        # Transfer type
        devTlType = GetEnumName(SciCamTLType, device_info.tlType)
        info_str += f"<b>Transfer Type:</b> {devTlType if devTlType else 'Unknown'}<br><br>"

        # Based on transfer type, show specific info
        if device_info.tlType == SciCamTLType.SciCam_TLType_Gige:
            info_str += self._get_gige_info(device_info)
        elif device_info.tlType == SciCamTLType.SciCam_TLType_Usb3:
            info_str += self._get_usb3_info(device_info)
        elif device_info.tlType == SciCamTLType.SciCam_TLType_CL:
            info_str += self._get_cl_info(device_info)

        self.info_text.setText(info_str)

    def _get_gige_info(self, device_info):
        """Get GigE device information"""
        info = device_info.info.gigeInfo
        info_str = ""

        # Camera name
        name = ''.join(chr(c) for c in info.name if c != 0)
        if name:
            info_str += f"<b>Camera Name:</b> {name}<br>"

        # Manufacturer
        manufacture = ''.join(chr(c) for c in info.manufactureName if c != 0)
        if manufacture:
            info_str += f"<b>Manufacturer:</b> {manufacture}<br>"

        # Model
        model = ''.join(chr(c) for c in info.modelName if c != 0)
        if model:
            info_str += f"<b>Model:</b> {model}<br>"

        # Serial number
        serial = ''.join(chr(c) for c in info.serialNumber if c != 0)
        if serial:
            info_str += f"<b>Serial Number:</b> {serial}<br>"

        # IP Address
        ip = uint32_to_ipv4(info.ip)
        info_str += f"<b>IP Address:</b> {ip}<br>"

        # MAC Address
        mac = ':'.join(f'{b:02x}' for b in info.mac[:6])
        info_str += f"<b>MAC Address:</b> {mac}<br>"

        return info_str

    def _get_usb3_info(self, device_info):
        """Get USB3 device information"""
        info = device_info.info.usb3Info
        info_str = ""

        # Camera name
        name = ''.join(chr(c) for c in info.name if c != 0)
        if name:
            info_str += f"<b>Camera Name:</b> {name}<br>"

        # Manufacturer
        manufacture = ''.join(chr(c) for c in info.manufactureName if c != 0)
        if manufacture:
            info_str += f"<b>Manufacturer:</b> {manufacture}<br>"

        # Model
        model = ''.join(chr(c) for c in info.modelName if c != 0)
        if model:
            info_str += f"<b>Model:</b> {model}<br>"

        # Serial number
        serial = ''.join(chr(c) for c in info.serialNumber if c != 0)
        if serial:
            info_str += f"<b>Serial Number:</b> {serial}<br>"

        # GUID
        guid = ''.join(chr(c) for c in info.guid if c != 0)
        if guid:
            info_str += f"<b>GUID:</b> {guid}<br>"

        return info_str

    def _get_cl_info(self, device_info):
        """Get CL device information"""
        info = device_info.info.clInfo
        info_str = ""

        # Card info
        card_name = ''.join(chr(c) for c in info.cardName if c != 0)
        if card_name:
            info_str += f"<b>Card Name:</b> {card_name}<br>"

        # Camera info
        camera_model = ''.join(chr(c) for c in info.cameraModel if c != 0)
        if camera_model:
            info_str += f"<b>Camera Model:</b> {camera_model}<br>"

        # Manufacturer
        manufacture = ''.join(chr(c) for c in info.cameraManufacture if c != 0)
        if manufacture:
            info_str += f"<b>Manufacturer:</b> {manufacture}<br>"

        # Serial number
        serial = ''.join(chr(c) for c in info.cameraSerialNumber if c != 0)
        if serial:
            info_str += f"<b>Serial Number:</b> {serial}<br>"

        return info_str


class NodeTreeWidget(QWidget):
    """Widget to display and control device nodes"""

    def __init__(self, camera_worker):
        super().__init__()
        self.camera_worker = camera_worker
        self.current_nodes = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Control buttons
        button_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh Nodes")
        self.refresh_btn.clicked.connect(self.refresh_nodes)

        self.edit_btn = QPushButton("Edit Selected Node")
        self.edit_btn.clicked.connect(self.edit_selected_node)
        self.edit_btn.setEnabled(False)

        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Node tree
        self.node_tree = QTreeWidget()
        self.node_tree.setHeaderLabels(["Node", "Type", "Value", "Access"])
        self.node_tree.setColumnWidth(0, 250)
        self.node_tree.setColumnWidth(1, 100)
        self.node_tree.setColumnWidth(2, 150)
        self.node_tree.setColumnWidth(3, 80)
        self.node_tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.node_tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        layout.addWidget(self.node_tree)

        self.setLayout(layout)

    def on_selection_changed(self):
        """Handle tree selection change"""
        selected_items = self.node_tree.selectedItems()
        if selected_items:
            # Get the node index from the item
            item = selected_items[0]
            node_idx = item.data(0, Qt.UserRole)
            if node_idx is not None and node_idx < len(self.current_nodes):
                node = self.current_nodes[node_idx]
                # Enable edit button only for RW nodes
                if node.accessMode == SciCamNodeAccessMode.SciCam_NodeAccessMode_RW:
                    self.edit_btn.setEnabled(True)
                else:
                    self.edit_btn.setEnabled(False)
        else:
            self.edit_btn.setEnabled(False)

    def on_item_double_clicked(self, item, column):
        """Handle double click on tree item"""
        node_idx = item.data(0, Qt.UserRole)
        if node_idx is not None and node_idx < len(self.current_nodes):
            node = self.current_nodes[node_idx]
            # Only allow editing for RW nodes
            if node.accessMode == SciCamNodeAccessMode.SciCam_NodeAccessMode_RW:
                self.edit_node(node_idx)

    def refresh_nodes(self):
        """Refresh the node tree"""
        if not self.camera_worker.camera:
            QMessageBox.warning(self, "Warning", "No camera connected")
            return

        try:
            nodesCount = ctypes.c_uint(0)
            reVal = self.camera_worker.camera.SciCam_GetNodes(None, nodesCount)

            if reVal != SCI_CAMERA_OK or nodesCount.value == 0:
                self.node_tree.clear()
                QMessageBox.information(self, "Info", "No nodes found or failed to get nodes")
                return

            nodes = (SCI_CAM_NODE * nodesCount.value)()
            reVal = self.camera_worker.camera.SciCam_GetNodes(
                ctypes.cast(nodes, PSCI_CAM_NODE).contents, nodesCount)

            if reVal == SCI_CAMERA_OK:
                self.current_nodes = nodes
                self.update_tree(nodes, nodesCount.value)
            else:
                QMessageBox.warning(self, "Warning", f"Failed to get nodes: Error {reVal}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to get nodes: {str(e)}")

    def update_tree(self, nodes, count):
        """Update the tree widget with nodes"""
        self.node_tree.clear()

        # Build parent-child relationships
        node_dict = {}

        # First pass: create all items
        for i in range(count):
            node = nodes[i]
            try:
                # Get node value using the camera instance
                node_value = GetNodeValueStr(
                    self.camera_worker.camera,
                    SciCamDeviceXmlType.SciCam_DeviceXml_Camera,
                    node
                )

                item = QTreeWidgetItem([
                    node.name.decode() if node.name else "Unknown",
                    GetEnumName(SciCamNodeType, node.type) if GetEnumName(SciCamNodeType, node.type) else str(
                        node.type),
                    node_value,
                    GetEnumName(SciCamNodeAccessMode, node.accessMode) if GetEnumName(SciCamNodeAccessMode,
                                                                                      node.accessMode) else str(
                        node.accessMode)
                ])

                # Store node index in item data
                item.setData(0, Qt.UserRole, i)

                # Color code based on access mode
                if node.accessMode == SciCamNodeAccessMode.SciCam_NodeAccessMode_RW:
                    # Green background for RW nodes
                    item.setBackground(3, QBrush(QColor(200, 255, 200)))
                elif node.accessMode == SciCamNodeAccessMode.SciCam_NodeAccessMode_RO:
                    # Yellow background for RO nodes
                    item.setBackground(3, QBrush(QColor(255, 255, 200)))
                elif node.accessMode == SciCamNodeAccessMode.SciCam_NodeAccessMode_WO:
                    # Blue background for WO nodes
                    item.setBackground(3, QBrush(QColor(200, 200, 255)))

                node_dict[i] = item
            except Exception as e:
                print(f"Error processing node {i}: {e}")
                # Create item with error info
                item = QTreeWidgetItem([
                    "Error",
                    "Error",
                    f"Error: {str(e)}",
                    "Error"
                ])
                node_dict[i] = item

        # Second pass: build hierarchy
        for i in range(count):
            if i >= len(nodes):
                continue

            node = nodes[i]
            item = node_dict[i]

            if node.level == 0:
                self.node_tree.addTopLevelItem(item)
            else:
                # Find parent based on level
                parent_idx = i - 1
                while parent_idx >= 0 and nodes[parent_idx].level >= node.level:
                    parent_idx -= 1

                if parent_idx >= 0:
                    parent_item = node_dict[parent_idx]
                    parent_item.addChild(item)

        # Expand all items
        self.node_tree.expandAll()

    def edit_selected_node(self):
        """Edit the selected node"""
        selected_items = self.node_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a node to edit")
            return

        item = selected_items[0]
        node_idx = item.data(0, Qt.UserRole)
        if node_idx is not None and node_idx < len(self.current_nodes):
            self.edit_node(node_idx)

    def edit_node(self, node_idx):
        """Edit a specific node"""
        node = self.current_nodes[node_idx]

        # Create edit dialog
        dialog = EditNodeDialog(self.camera_worker.camera, node, self)
        if dialog.exec() == QDialog.Accepted:
            new_value = dialog.get_value()
            if new_value is not None:
                self.apply_node_value(node, new_value)

    def apply_node_value(self, node, new_value):
        """Apply new value to node"""
        try:
            node_name = node.name.decode() if node.name else ""
            node_type = node.type
            reVal = SCI_CAMERA_OK

            if node_type == SciCamNodeType.SciCam_NodeType_Bool:
                reVal = self.camera_worker.camera.SciCam_SetBoolValueEx(
                    SciCamDeviceXmlType.SciCam_DeviceXml_Camera, node_name, new_value)
            elif node_type == SciCamNodeType.SciCam_NodeType_Int:
                reVal = self.camera_worker.camera.SciCam_SetIntValueEx(
                    SciCamDeviceXmlType.SciCam_DeviceXml_Camera, node_name, new_value)
            elif node_type == SciCamNodeType.SciCam_NodeType_Float:
                reVal = self.camera_worker.camera.SciCam_SetFloatValueEx(
                    SciCamDeviceXmlType.SciCam_DeviceXml_Camera, node_name, new_value)
            elif node_type == SciCamNodeType.SciCam_NodeType_Enum:
                reVal = self.camera_worker.camera.SciCam_SetEnumValueEx(
                    SciCamDeviceXmlType.SciCam_DeviceXml_Camera, node_name, new_value)
            elif node_type == SciCamNodeType.SciCam_NodeType_String:
                reVal = self.camera_worker.camera.SciCam_SetStringValueEx(
                    SciCamDeviceXmlType.SciCam_DeviceXml_Camera, node_name, new_value)

            if reVal == SCI_CAMERA_OK:
                QMessageBox.information(self, "Success", f"Node {node_name} updated successfully")
                # Refresh the node value in the tree
                self.refresh_nodes()
            else:
                QMessageBox.warning(self, "Error", f"Failed to update node {node_name}: Error {reVal}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update node: {str(e)}")


class ImageDisplayWidget(QWidget):
    """Widget for displaying camera images"""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.current_image = None
        self.scale_factor = 1.0

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_in_btn.setToolTip("Zoom In")

        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_out_btn.setToolTip("Zoom Out")

        self.zoom_fit_btn = QPushButton("Fit")
        self.zoom_fit_btn.clicked.connect(self.zoom_fit)
        self.zoom_fit_btn.setToolTip("Fit to Window")

        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        #self.zoom_label.setFixedWidth(60)

        self.size_label = QLabel("No image")
        self.size_label.setAlignment(Qt.AlignRight)

        toolbar_layout.addWidget(QLabel("Zoom:"))
        toolbar_layout.addWidget(self.zoom_in_btn)
        toolbar_layout.addWidget(self.zoom_out_btn)
        toolbar_layout.addWidget(self.zoom_fit_btn)
        toolbar_layout.addWidget(self.zoom_label)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.size_label)

        layout.addLayout(toolbar_layout)

        # 图像显示区域
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setAlignment(Qt.AlignCenter)
        self.image_scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: #2c2c2c;
            }
        """)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)  # 修改这里
        self.image_label.setScaledContents(False)
        self.image_label.setMinimumSize(320, 240)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #2c2c2c;
                border: none;
            }
        """)

        self.image_scroll.setWidget(self.image_label)
        layout.addWidget(self.image_scroll)

        # 状态信息
        self.info_label = QLabel("Ready")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 12px;
                padding: 4px;
            }
        """)
        layout.addWidget(self.info_label)

        self.setLayout(layout)

    def display_image(self, image_data, width, height, pixel_type=SciCamPixelType.Mono8):
        """Display image from raw data"""
        try:
            # 根据像素类型创建QImage
            if pixel_type == SciCamPixelType.Mono8:
                format = QImage.Format_Grayscale8
                bytes_per_line = width
            elif pixel_type == SciCamPixelType.RGB8:
                format = QImage.Format_RGB888
                bytes_per_line = width * 3
            else:
                self.info_label.setText(f"Unsupported pixel format: {pixel_type}")
                return

            # 确保图像数据是bytes类型
            if isinstance(image_data, ctypes.Array):
                image_data = bytes(image_data)
            elif isinstance(image_data, bytes):
                pass
            else:
                image_data = bytes(image_data)

            # 创建QImage
            image = QImage(image_data, width, height, bytes_per_line, format)

            # 检查图像是否有效
            if image.isNull():
                self.info_label.setText("Error: Invalid image data")
                return

            # 转换为QPixmap并显示
            pixmap = QPixmap.fromImage(image)
            self.current_image = pixmap

            # 重置缩放因子
            self.scale_factor = 1.0

            # 更新显示
            self.update_display()

            # 更新状态信息
            self.size_label.setText(f"{width} × {height}")
            pixel_type_name = GetEnumName(SciCamPixelType, pixel_type) or str(pixel_type)
            self.info_label.setText(f"Image loaded: {width} × {height}, {pixel_type_name}")

        except Exception as e:
            self.info_label.setText(f"Error displaying image: {str(e)}")

    def update_display(self):
        """Update the displayed image with current scale factor"""
        if self.current_image:
            # 计算缩放后的尺寸
            scaled_width = int(self.current_image.width() * self.scale_factor)
            scaled_height = int(self.current_image.height() * self.scale_factor)

            # 缩放图像
            scaled_pixmap = self.current_image.scaled(
                scaled_width,
                scaled_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # 设置图像
            self.image_label.setPixmap(scaled_pixmap)

            # 调整标签大小
            self.image_label.resize(scaled_pixmap.size())

            # 更新缩放比例显示
            self.zoom_label.setText(f"{int(self.scale_factor * 100)}%")

    def zoom_in(self):
        """Zoom in"""
        if self.current_image:
            self.scale_factor *= 1.2
            if self.scale_factor > 5.0:  # 限制最大缩放
                self.scale_factor = 5.0
            self.update_display()

    def zoom_out(self):
        """Zoom out"""
        if self.current_image:
            self.scale_factor /= 1.2
            if self.scale_factor < 0.1:  # 限制最小缩放
                self.scale_factor = 0.1
            self.update_display()

    def zoom_fit(self):
        """Zoom to fit"""
        if self.current_image and self.image_scroll.viewport().width() > 0:
            # 获取滚动区域可用大小
            viewport_width = self.image_scroll.viewport().width() - 20
            viewport_height = self.image_scroll.viewport().height() - 20

            if viewport_width > 0 and viewport_height > 0:
                # 计算适合窗口的缩放比例
                scale_x = viewport_width / self.current_image.width()
                scale_y = viewport_height / self.current_image.height()

                self.scale_factor = min(scale_x, scale_y, 1.0)
                self.update_display()

    def clear_image(self):
        """Clear the displayed image"""
        self.current_image = None
        self.image_label.clear()
        self.image_label.setText("No Image")
        self.size_label.setText("No image")
        self.info_label.setText("No image to display")
        self.zoom_label.setText("100%")
        self.scale_factor = 1.0


class CameraControlWidget(QWidget):
    """Main camera control widget"""

    close_requested = Signal()

    def __init__(self, existing_camera_worker=None):
        super().__init__()
        if existing_camera_worker:
            self.camera_worker = existing_camera_worker
            self.is_external_worker = True
        else:
            self.camera_worker = CameraWorker()
            self.is_external_worker = False
        self.current_device_index = -1
        self.frame_count = 0
        self.fps_timer = QTimer()
        self.last_fps_time = time.time()

        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        main_layout = QVBoxLayout()

        header_layout = QHBoxLayout()

        # Title
        title_label = QLabel("Camera Settings")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)

        # Back button (red color)
        self.back_btn = QPushButton("← Back")
        self.back_btn.setStyleSheet("""
                   QPushButton {
                       background-color: #dc3545;
                       color: white;
                       font-weight: bold;
                       padding: 8px 20px;
                       border-radius: 5px;
                       font-size: 14px;
                   }
                   QPushButton:hover {
                       background-color: #c82333;
                   }
               """)
        self.back_btn.clicked.connect(self.on_back_clicked)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.back_btn)

        main_layout.addLayout(header_layout)

        # 标题
        # #title_label = QLabel("SciCamera Control Panel")
        # title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # title_font = QFont()
        # title_font.setPointSize(16)
        # title_font.setBold(True)
        # title_label.setFont(title_font)
        # main_layout.addWidget(title_label)

        # 创建主分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：控制面板
        left_widget = QWidget()
        left_layout = QVBoxLayout()

        # 创建标签页
        self.tab_widget = QTabWidget()

        # 设备标签页
        self.device_tab = self.create_device_tab()
        self.tab_widget.addTab(self.device_tab, "Devices")

        # 采集标签页
        self.acquisition_tab = self.create_acquisition_tab()
        self.tab_widget.addTab(self.acquisition_tab, "Acquisition")

        # 节点标签页
        self.nodes_tab = self.create_nodes_tab()
        self.tab_widget.addTab(self.nodes_tab, "Nodes")

        # 状态标签页
        self.status_tab = self.create_status_tab()
        self.tab_widget.addTab(self.status_tab, "Status")

        left_layout.addWidget(self.tab_widget)
        left_widget.setLayout(left_layout)

        # 右侧：图像显示
        right_widget = QWidget()
        right_layout = QVBoxLayout()

        # 图像显示部件
        self.image_display = ImageDisplayWidget()
        right_layout.addWidget(self.image_display)

        # 快速操作按钮
        quick_buttons_layout = QHBoxLayout()

        self.live_view_btn = QPushButton("Live View")
        self.live_view_btn.clicked.connect(self.toggle_live_view)
        self.live_view_btn.setCheckable(True)

        self.save_btn = QPushButton("Save Image")
        self.save_btn.clicked.connect(self.save_current_image)

        quick_buttons_layout.addWidget(self.live_view_btn)
        quick_buttons_layout.addWidget(self.save_btn)
        quick_buttons_layout.addStretch()

        right_layout.addLayout(quick_buttons_layout)
        right_widget.setLayout(right_layout)

        # 添加到分割器
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)

        # 日志区域
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        self.setLayout(main_layout)

    def on_back_clicked(self):
        """Handle back button click - stop camera and close window"""
        # Stop grabbing if active
        if self.camera_worker.is_grabbing:
            reply = QMessageBox.question(
                self,
                "Stop Camera",
                "Camera is currently running. Stop and close?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                self.update_log("Stopping camera before closing...")
                self.camera_worker.stop_grabbing()
                # Small delay to ensure grabbing stops
                QTimer.singleShot(100, self.emit_close_signal)
            else:
                return  # Don't close if user cancels
        else:
            self.emit_close_signal()

    def emit_close_signal(self):
        """Emit close signal and cleanup"""
        self.update_log("Closing camera settings...")

        # If we own the camera worker (not external), close the device
        if not self.is_external_worker and self.camera_worker.current_device:
            self.camera_worker.close_device()

        self.close_requested.emit()

    def create_device_tab(self):
        """Create device management tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Device control buttons
        button_layout = QHBoxLayout()

        self.discover_btn = QPushButton("Discover Devices")
        self.discover_btn.clicked.connect(self.discover_devices)

        self.open_btn = QPushButton("Open Device")
        self.open_btn.clicked.connect(self.open_device)
        self.open_btn.setEnabled(False)

        self.close_btn = QPushButton("Close Device")
        self.close_btn.clicked.connect(self.close_device)
        self.close_btn.setEnabled(False)

        button_layout.addWidget(self.discover_btn)
        button_layout.addWidget(self.open_btn)
        button_layout.addWidget(self.close_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Device list
        device_group = QGroupBox("Available Devices")
        device_layout = QVBoxLayout()

        self.device_table = QTableWidget()
        self.device_table.setColumnCount(4)
        self.device_table.setHorizontalHeaderLabels(["Index", "Type", "Model", "Serial"])
        self.device_table.horizontalHeader().setStretchLastSection(True)
        self.device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.device_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.device_table.cellClicked.connect(self.on_device_selected)

        device_layout.addWidget(self.device_table)
        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # Device info widget
        self.device_info_widget = DeviceInfoWidget()
        layout.addWidget(self.device_info_widget)

        widget.setLayout(layout)
        return widget

    def create_acquisition_tab(self):
        """Create image acquisition tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Grab settings
        settings_group = QGroupBox("Grab Settings")
        settings_layout = QVBoxLayout()

        # Timeout setting
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("Timeout (ms):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(100, 10000)
        self.timeout_spin.setValue(1000)
        self.timeout_spin.setSingleStep(100)
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addStretch()
        settings_layout.addLayout(timeout_layout)

        # Buffer count
        buffer_layout = QHBoxLayout()
        buffer_layout.addWidget(QLabel("Buffer Count:"))
        self.buffer_spin = QSpinBox()
        self.buffer_spin.setRange(1, 100)
        self.buffer_spin.setValue(10)
        buffer_layout.addWidget(self.buffer_spin)
        buffer_layout.addStretch()
        settings_layout.addLayout(buffer_layout)

        # Grab strategy
        strategy_layout = QHBoxLayout()
        strategy_layout.addWidget(QLabel("Grab Strategy:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["OneByOne", "Latest", "Upcoming"])
        self.strategy_combo.setCurrentIndex(0)
        strategy_layout.addWidget(self.strategy_combo)
        strategy_layout.addStretch()
        settings_layout.addLayout(strategy_layout)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Acquisition control buttons
        acq_button_layout = QHBoxLayout()

        # self.start_grab_btn = QPushButton("Start Grabbing")
        # self.start_grab_btn.clicked.connect(self.start_grabbing)
        # self.start_grab_btn.setEnabled(False)

        # self.stop_grab_btn = QPushButton("Stop Grabbing")
        # self.stop_grab_btn.clicked.connect(self.stop_grabbing)
        # self.stop_grab_btn.setEnabled(False)

        # self.single_grab_btn = QPushButton("Grab Single")
        # self.single_grab_btn.clicked.connect(self.grab_single)
        # self.single_grab_btn.setEnabled(False)

        #acq_button_layout.addWidget(self.start_grab_btn)
        # acq_button_layout.addWidget(self.stop_grab_btn)
        # acq_button_layout.addWidget(self.single_grab_btn)
        # acq_button_layout.addStretch()

        layout.addLayout(acq_button_layout)

        # Image info display
        image_group = QGroupBox("Image Information")
        image_layout = QVBoxLayout()

        self.image_info_text = QTextEdit()
        self.image_info_text.setReadOnly(True)
        self.image_info_text.setMaximumHeight(100)
        image_layout.addWidget(self.image_info_text)

        image_group.setLayout(image_layout)
        layout.addWidget(image_group)

        widget.setLayout(layout)
        return widget

    def create_nodes_tab(self):
        """Create device nodes tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        self.node_widget = NodeTreeWidget(self.camera_worker)
        layout.addWidget(self.node_widget)

        widget.setLayout(layout)
        return widget

    def create_status_tab(self):
        """Create status monitoring tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # SDK version
        version_group = QGroupBox("SDK Information")
        version_layout = QVBoxLayout()

        self.version_label = QLabel("SDK Version: Unknown")
        version_layout.addWidget(self.version_label)

        self.get_version_btn = QPushButton("Get SDK Version")
        self.get_version_btn.clicked.connect(self.get_sdk_version)
        version_layout.addWidget(self.get_version_btn)

        version_group.setLayout(version_layout)
        layout.addWidget(version_group)

        # Device status
        status_group = QGroupBox("Device Status")
        status_layout = QVBoxLayout()

        self.device_status_label = QLabel("Device: Not Connected")
        status_layout.addWidget(self.device_status_label)

        self.camera_status_label = QLabel("Camera: Not Open")
        status_layout.addWidget(self.camera_status_label)

        self.grabbing_status_label = QLabel("Grabbing: Not Active")
        status_layout.addWidget(self.grabbing_status_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()

        self.fps_label = QLabel("FPS: 0.0")
        stats_layout.addWidget(self.fps_label)

        self.frame_count_label = QLabel("Frames Grabbed: 0")
        stats_layout.addWidget(self.frame_count_label)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        widget.setLayout(layout)
        return widget

    def connect_signals(self):
        """Connect camera worker signals"""
        self.camera_worker.log_signal.connect(self.update_log)
        self.camera_worker.device_list_signal.connect(self.update_device_list)
        self.camera_worker.image_grabbed_signal.connect(self.on_image_grabbed)
        self.camera_worker.image_saved_signal.connect(self.on_image_saved)

        # Setup FPS timer
        self.fps_timer.timeout.connect(self.update_fps)
        self.fps_timer.start(1000)  # Update every second

    # === 添加缺失的方法 ===

    def discover_devices(self):
        """Discover available devices"""
        self.discover_btn.setEnabled(False)
        self.update_log("Starting device discovery...")
        self.camera_worker.discovery_devices()
        self.discover_btn.setEnabled(True)

    def update_device_list(self, devices):
        """Update the device list table"""
        self.device_table.setRowCount(len(devices))

        for i, device in enumerate(devices):
            info = device['info']

            # Get device type
            dev_type = GetEnumName(SciCamDeviceType, info.devType) or "Unknown"

            # Get model name based on transfer type
            model_name = "Unknown"
            if info.tlType == SciCamTLType.SciCam_TLType_Gige:
                model_name = ''.join(chr(c) for c in info.info.gigeInfo.modelName if c != 0)
            elif info.tlType == SciCamTLType.SciCam_TLType_Usb3:
                model_name = ''.join(chr(c) for c in info.info.usb3Info.modelName if c != 0)
            elif info.tlType == SciCamTLType.SciCam_TLType_CL:
                model_name = ''.join(chr(c) for c in info.info.clInfo.cameraModel if c != 0)

            # Get serial number
            serial = "Unknown"
            if info.tlType == SciCamTLType.SciCam_TLType_Gige:
                serial = ''.join(chr(c) for c in info.info.gigeInfo.serialNumber if c != 0)
            elif info.tlType == SciCamTLType.SciCam_TLType_Usb3:
                serial = ''.join(chr(c) for c in info.info.usb3Info.serialNumber if c != 0)
            elif info.tlType == SciCamTLType.SciCam_TLType_CL:
                serial = ''.join(chr(c) for c in info.info.clInfo.cameraSerialNumber if c != 0)

            self.device_table.setItem(i, 0, QTableWidgetItem(str(i)))
            self.device_table.setItem(i, 1, QTableWidgetItem(dev_type))
            self.device_table.setItem(i, 2, QTableWidgetItem(model_name[:50]))
            self.device_table.setItem(i, 3, QTableWidgetItem(serial[:50]))

        self.update_log(f"Found {len(devices)} device(s)")

    def on_device_selected(self, row, column):
        """Handle device selection"""
        self.current_device_index = row
        self.device_info_widget.update_info(self.camera_worker.devices[row]['info'])
        self.open_btn.setEnabled(True)
        self.update_log(f"Selected device {row}")

    def open_device(self):
        """Open selected device"""
        if self.current_device_index >= 0:
            self.open_btn.setEnabled(False)
            self.update_log(f"Opening device {self.current_device_index}...")
            success = self.camera_worker.open_device(self.current_device_index)

            if success:
                self.close_btn.setEnabled(True)
                #self.start_grab_btn.setEnabled(True)
                #self.single_grab_btn.setEnabled(True)
                self.live_view_btn.setEnabled(True)
                self.save_btn.setEnabled(True)
                self.device_status_label.setText("Device: Connected")
                self.camera_status_label.setText("Camera: Open")
                self.update_log("Device opened successfully")
            else:
                self.open_btn.setEnabled(True)
                self.update_log("Failed to open device")

    def close_device(self):
        """Close current device"""
        self.update_log("Closing device...")
        self.camera_worker.close_device()
        self.close_btn.setEnabled(False)
        self.open_btn.setEnabled(True)
        #self.start_grab_btn.setEnabled(False)
        #self.stop_grab_btn.setEnabled(False)
        #self.single_grab_btn.setEnabled(False)
        self.live_view_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.device_status_label.setText("Device: Not Connected")
        self.camera_status_label.setText("Camera: Not Open")
        self.grabbing_status_label.setText("Grabbing: Not Active")
        self.update_log("Device closed")
        self.clear_device_selection()

    def clear_device_selection(self):
        """Clear the device table selection"""
        self.device_table.clearSelection()
        self.current_device_index = -1
        self.device_info_widget.update_info(None)

        # Reset the device info widget
        self.device_info_widget.info_text.setText("No device selected")

    def start_grabbing(self):
        """Start continuous grabbing"""
        try:
            self.update_log("Starting continuous grabbing...")
            # Apply settings
            timeout = self.timeout_spin.value()
            buffer_count = self.buffer_spin.value()

            # Set grab strategy
            strategy_map = {"OneByOne": 0, "Latest": 1, "Upcoming": 2}
            strategy = strategy_map[self.strategy_combo.currentText()]

            # Start grabbing
            success = self.camera_worker.start_grabbing(timeout, buffer_count, strategy)
            if success:
                #self.start_grab_btn.setEnabled(False)
                #self.stop_grab_btn.setEnabled(True)
                #self.single_grab_btn.setEnabled(False)
                self.live_view_btn.setChecked(True)
                self.grabbing_status_label.setText("Grabbing: Active")
                self.update_log("Continuous grabbing started")
            else:
                #self.start_grab_btn.setEnabled(True)
                self.update_log("Failed to start continuous grabbing")

        except Exception as e:
            self.update_log(f"Error starting grabbing: {str(e)}")
            #self.start_grab_btn.setEnabled(True)

    def stop_grabbing(self):
        """Stop continuous grabbing"""
        try:
            self.update_log("Stopping continuous grabbing...")
            success = self.camera_worker.stop_grabbing()
            if success:
                #self.start_grab_btn.setEnabled(True)
                #self.stop_grab_btn.setEnabled(False)
                #self.single_grab_btn.setEnabled(True)
                self.live_view_btn.setChecked(False)
                self.grabbing_status_label.setText("Grabbing: Not Active")
                self.update_log("Continuous grabbing stopped")
            else:
                self.stop_grab_btn.setEnabled(True)
                self.update_log("Failed to stop continuous grabbing")

        except Exception as e:
            self.update_log(f"Error stopping grabbing: {str(e)}")
            self.stop_grab_btn.setEnabled(True)

    def grab_single(self):
        """Grab a single image"""
        #self.single_grab_btn.setEnabled(False)
        self.update_log("Grabbing single image...")

        try:
            success = self.camera_worker.grab_single_image()
            if success:
                # 更新图像显示
                if (hasattr(self.camera_worker, 'last_image_data') and
                        self.camera_worker.last_image_data):
                    self.image_display.display_image(
                        self.camera_worker.last_image_data,
                        self.camera_worker.last_width,
                        self.camera_worker.last_height,
                        self.camera_worker.last_pixel_type
                    )

                self.frame_count += 1
                self.frame_count_label.setText(f"Frames Grabbed: {self.frame_count}")
                self.update_log("Single image grabbed successfully")

        except Exception as e:
            self.update_log(f"Error grabbing single image: {str(e)}")

        #self.single_grab_btn.setEnabled(True)

    def on_image_grabbed(self, image_data, width, height):
        """Handle grabbed image"""
        self.frame_count += 1

        current_scale_factor = self.image_display.scale_factor

        # 更新图像显示
        self.image_display.display_image(
            image_data,
            width,
            height,
            self.camera_worker.last_pixel_type
        )

        # 恢复缩放因子（如果不是首次显示）
        if hasattr(self.image_display, 'current_image') and self.image_display.current_image:
            if current_scale_factor != 1.0:  # 如果不是默认缩放
                self.image_display.scale_factor = current_scale_factor
                self.image_display.update_display()

        # 更新图像信息
        info_str = f"""
        <b>Resolution:</b> {width} × {height}<br>
        <b>Pixel Type:</b> {GetEnumName(SciCamPixelType, self.camera_worker.last_pixel_type) if GetEnumName(SciCamPixelType, self.camera_worker.last_pixel_type) else self.camera_worker.last_pixel_type}<br>
        <b>Data Size:</b> {len(image_data)} bytes
        """
        self.image_info_text.setText(info_str)

    def on_image_saved(self, message):
        """Handle image saved signal"""
        self.update_log(message)

    def toggle_live_view(self):
        """Toggle live view mode"""
        if self.live_view_btn.isChecked():
            # 开始实时视图
            self.update_log("Starting live view...")
            if not self.camera_worker.is_grabbing:
                self.start_grabbing()
            self.live_view_btn.setText("Stop Live")
        else:
            # 停止实时视图
            self.update_log("Stopping live view...")
            if self.camera_worker.is_grabbing:
                self.stop_grabbing()
            self.live_view_btn.setText("Live View")

    def save_current_image(self):
        """Save the current image"""
        if not hasattr(self.camera_worker, 'last_image_data') or not self.camera_worker.last_image_data:
            QMessageBox.warning(self, "Warning", "No image to save")
            return

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"camera_image_{timestamp}.bmp"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image",
            default_name,
            "BMP Files (*.bmp);;All Files (*.*)"
        )

        if file_path:
            # 触发保存
            self.update_log(f"Saving image to: {file_path}")
            self.camera_worker.trigger_save_image(file_path)

    def update_fps(self):
        """Update FPS display"""
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        if elapsed > 0:
            fps = self.frame_count / elapsed
            self.fps_label.setText(f"FPS: {fps:.1f}")
        self.last_fps_time = current_time
        self.frame_count = 0

    def get_sdk_version(self):
        """Get SDK version information"""
        try:
            version = ctypes.c_uint(SciCamera.SciCam_GetSDKVersion())
            verMain = (version.value >> 24) & 0xff
            verSub = (version.value >> 16) & 0xff
            verRev = (version.value >> 8) & 0xff
            verTest = version.value & 0xff

            version_str = f"SDK Version: V{verMain}.{verSub}.{verRev}.{verTest}"
            self.version_label.setText(version_str)
            self.update_log(version_str)

        except Exception as e:
            self.update_log(f"Error getting SDK version: {str(e)}")

    def update_log(self, message):
        """Update log display"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_entry = f"[{timestamp}] {message}"
            self.log_text.append(log_entry)

            # Auto-scroll to bottom
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            print(f"Error updating log: {e}")


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, existing_camera_worker=None):
        super().__init__()
        # self.setWindowTitle("SciCamera Control Panel")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget
        self.central_widget = CameraControlWidget(existing_camera_worker)
        self.setCentralWidget(self.central_widget)

        self.central_widget.close_requested.connect(self.close)

        # Create menu bar
        #self.create_menu_bar()

        # Apply style
        self.apply_style()

    # def create_menu_bar(self):
    #     """Create application menu bar"""
    #     menubar = self.menuBar()
    #
    #     # File menu
    #     file_menu = menubar.addMenu("File")
    #
    #     exit_action = file_menu.addAction("Exit")
    #     exit_action.triggered.connect(self.close)
    #
    #     # View menu
    #     view_menu = menubar.addMenu("View")
    #
    #     # Help menu
    #     help_menu = menubar.addMenu("Help")
    #
    #     about_action = help_menu.addAction("About")
    #     about_action.triggered.connect(self.show_about)

    def apply_style(self):
        """Apply stylesheet to the application"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 8px 16px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                margin: 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QTableWidget {
                background-color: white;
                alternate-background-color: #f9f9f9;
                gridline-color: #ddd;
            }
            QTableWidget::item:selected {
                background-color: #e0f7fa;
            }
            QTextEdit {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px;
            }
            QTreeWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)

    # def show_about(self):
    #     """Show about dialog"""
    #     QMessageBox.about(self, "About SciCamera Control Panel",
    #                       "SciCamera Control Panel\n\n"
    #                       "A PySide6-based GUI for SciCamera SDK\n"
    #                       "Provides control and monitoring for SciCamera devices")


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("SciCamera Control Panel")
    app.setOrganizationName("SciCamera")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()