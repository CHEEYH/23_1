import socket
import threading
import time
from PySide6.QtCore import QObject, Signal


class HeartbeatManager(QObject):
    """Manages TCP connection heartbeat"""

    # Signals for UI updates
    connection_status_changed = Signal(bool, str)  # connected, message
    heartbeat_sent = Signal(str)  # heartbeat message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.socket = None
        self.connected = False
        self.server_ip = None
        self.server_port = None
        self.heartbeat_thread = None
        self.stop_heartbeat = threading.Event()
        self.lock = threading.Lock()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3

    def connect(self, server_ip, server_port, heartbeat_interval=5):
        """Connect to server and start heartbeat"""
        self.server_ip = server_ip
        self.server_port = server_port
        self.heartbeat_interval = heartbeat_interval

        # Close any existing connection
        self.disconnect()

        # Reset reconnect attempts on manual connect
        self.reconnect_attempts = 0

        try:
            # Create socket with better timeout settings
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # Set socket options for better reconnection handling
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

            # Set a shorter connection timeout
            self.socket.settimeout(3)  # 3 second connection timeout

            # Connect with timeout
            self.socket.connect((server_ip, server_port))

            # Set longer timeout for operations after connection
            self.socket.settimeout(heartbeat_interval + 2)

            self.connected = True
            self.stop_heartbeat.clear()

            # Start heartbeat thread
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()

            self.connection_status_changed.emit(True, f"Connected to {server_ip}:{server_port}")
            return True, "Connected successfully"

        except socket.timeout:
            error_msg = f"Connection timeout to {server_ip}:{server_port}"
            self._cleanup_socket()
            self.connection_status_changed.emit(False, error_msg)
            return False, error_msg

        except ConnectionRefusedError:
            error_msg = f"Connection refused by {server_ip}:{server_port} - Server may be offline"
            self._cleanup_socket()
            self.connection_status_changed.emit(False, error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            self._cleanup_socket()
            self.connection_status_changed.emit(False, error_msg)
            return False, str(e)

    def _cleanup_socket(self):
        """Safely cleanup socket resources"""
        with self.lock:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                finally:
                    self.socket = None
            self.connected = False

    def disconnect(self):
        """Disconnect from server and stop heartbeat"""
        print("\n" + "=" * 60)
        print("🔌 HEARTBEAT MANAGER DISCONNECT")
        print("=" * 60)

        # Stop heartbeat thread first
        self.stop_heartbeat.set()
        print("  ✅ Stop signal set")

        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=3)
            if self.heartbeat_thread.is_alive():
                print("  ⚠️ Heartbeat thread still alive after timeout")
            else:
                print("  ✅ Heartbeat thread stopped")

        with self.lock:
            if self.socket:
                print(f"  Socket found: {self.socket}")
                try:
                    # Send proper disconnect message (if socket is still usable)
                    try:
                        disconnect_msg = "DISCONNECT\n"
                        self.socket.send(disconnect_msg.encode('utf-8'))
                        print(f"  📤 Sent disconnect message: {disconnect_msg.strip()}")
                    except (socket.error, BrokenPipeError) as e:
                        print(f"  ⚠️ Could not send disconnect message: {e}")

                    # Give server time to process
                    time.sleep(0.5)

                    # Shutdown and close socket
                    try:
                        self.socket.shutdown(socket.SHUT_RDWR)
                        print("  ✅ shutdown() successful")
                    except (socket.error, OSError) as e:
                        print(f"  ⚠️ shutdown() error (normal if already closed): {e}")

                    self.socket.close()
                    print("  ✅ close() successful")

                except Exception as e:
                    print(f"  ⚠️ Error during disconnect: {e}")
                    try:
                        self.socket.close()
                        print("  ✅ Forced close() successful")
                    except:
                        pass

                self.socket = None
                print("  ✅ Socket reference cleared")

            self.connected = False
            print("  ✅ Connected flag set to False")

        # Clear any pending signals
        try:
            self.connection_status_changed.emit(False, "Disconnected by client")
            print("  ✅ Status signal emitted")
        except:
            pass

        print("=" * 60)
        print("✅ HEARTBEAT MANAGER FULLY DISCONNECTED")
        print("=" * 60 + "\n")

    def _heartbeat_loop(self):
        """Send heartbeat messages periodically"""
        heartbeat_count = 0
        consecutive_failures = 0

        while not self.stop_heartbeat.is_set() and self.connected:
            try:
                # Send heartbeat
                heartbeat_msg = f"HEARTBEAT"
                if self._send_message(heartbeat_msg):
                    self.heartbeat_sent.emit(f"Heartbeat #{heartbeat_count} sent")
                    consecutive_failures = 0  # Reset on success

                    # Try to receive response (non-blocking check)
                    try:
                        self.socket.settimeout(1)  # Short timeout for response
                        response = self.socket.recv(1024)
                        if response:
                            self.heartbeat_sent.emit(f"Server response: {response.decode().strip()}")
                        self.socket.settimeout(self.heartbeat_interval + 2)  # Restore timeout
                    except socket.timeout:
                        # No response expected, ignore
                        self.socket.settimeout(self.heartbeat_interval + 2)  # Restore timeout
                        pass
                    except Exception as e:
                        print(f"Heartbeat receive error: {e}")
                        self.socket.settimeout(self.heartbeat_interval + 2)  # Restore timeout
                else:
                    consecutive_failures += 1
                    print(f"Heartbeat send failed ({consecutive_failures} consecutive failures)")

                heartbeat_count += 1

                # Check if we've had too many failures
                if consecutive_failures >= 3:
                    print("Too many heartbeat failures, disconnecting...")
                    self.connected = False
                    self.connection_status_changed.emit(False, "Lost connection to server")
                    break

                # Wait for next heartbeat (with stop flag checking)
                for _ in range(self.heartbeat_interval * 2):
                    if self.stop_heartbeat.wait(0.5):
                        break

            except Exception as e:
                if not self.stop_heartbeat.is_set():
                    print(f"Heartbeat loop error: {e}")
                    consecutive_failures += 1

                    if consecutive_failures >= 3:
                        self.connected = False
                        self.connection_status_changed.emit(False, f"Heartbeat failed: {str(e)}")
                        break

                    # Brief pause before retry
                    time.sleep(1)

    def _send_message(self, message):
        """Send a message with proper formatting"""
        with self.lock:
            if not self.socket or not self.connected:
                return False

            try:
                # Check if socket is still valid
                try:
                    # This is a non-destructive way to check socket status
                    self.socket.getpeername()
                except socket.error:
                    print("Socket appears to be closed")
                    self.connected = False
                    return False

                formatted_msg = message + "\n" if not message.endswith("\n") else message
                self.socket.send(formatted_msg.encode('utf-8'))
                return True

            except BrokenPipeError:
                print("Broken pipe - connection lost")
                self.connected = False
                return False

            except ConnectionResetError:
                print("Connection reset by peer")
                self.connected = False
                return False

            except socket.error as e:
                print(f"Socket error during send: {e}")
                self.connected = False
                return False

            except Exception as e:
                print(f"Unexpected send error: {e}")
                return False

    def send_data(self, data):
        """Send data to server (for predictions, coordinates, etc.)"""
        return self._send_message(data)

    def is_connected(self):
        """Check if connected"""
        with self.lock:
            if not self.connected or not self.socket:
                return False

            # Additional check to verify connection is still alive
            try:
                self.socket.getpeername()
                return True
            except:
                self.connected = False
                return False