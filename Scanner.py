import socket
import threading
import serial
import re

# ========== CONFIGURATION ==========
SERVER_IP = '127.0.0.1'
SERVER_PORT = 1220
COM_PORT_NAME = 'COM3'
COM_PORT_BAUDRATE = 9600
COM_PORT_TIMEOUT = 1
# ===================================

class TCPServer:
    def __init__(self, host=None, port=None):
        self.host = host or SERVER_IP
        self.port = port or SERVER_PORT
        self.server_socket = None
        self.mode = None                # 'learn', 'check', or None
        self.com_port = None
        self.scan_active = False
        self.running = True
        self.current_client_socket = None

    def start(self):
        """Start the TCP server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            print(f"TCP Server started on {self.host}:{self.port}")
            print(f"COM Port: {COM_PORT_NAME}, Baudrate: {COM_PORT_BAUDRATE}")
            print("Waiting for connections...")

            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    print(f"Client connected from {client_address}")

                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket,)
                    )
                    client_thread.daemon = True
                    client_thread.start()

                except OSError:
                    break

        except Exception as e:
            print(f"Error starting server: {e}")

    def handle_client(self, client_socket):
        """Handle client connection"""
        try:
            while self.running:
                data = client_socket.recv(1024).decode('utf-8').strip()
                if not data:
                    break

                print(f"Received: {data}")

                if data.lower() in ["learn", "check"]:
                    if self.mode is None:
                        self.mode = data.lower()          # 'learn' or 'check'
                        self.current_client_socket = client_socket
                        self.start_scanning(client_socket)
                    else:
                        client_socket.send("Already in a scanning mode. Wait for completion.\n".encode('utf-8'))

                elif data.lower() == "exit":
                    break

                else:
                    print("Unknown command. Send 'learn' or 'check' to start scanning.")

        except ConnectionResetError:
            print("Client disconnected unexpectedly")
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            if self.current_client_socket == client_socket:
                self.current_client_socket = None
                self.mode = None
            client_socket.close()
            self.cleanup()

    def start_scanning(self, client_socket):
        """
        Called when 'learn' or 'check' is received.
        Immediately starts scanning. Exits when 'ok' is received or client disconnects.
        """
        self.scanning_loop(client_socket)

    def extract_data_between_pipes(self, data):
        """Extract data between || symbols from the received string"""
        try:
            pattern = r'\|\|(.*?)\|\|'
            matches = re.findall(pattern, data)
            if matches:
                extracted_data = matches[0]
                print(f"Extracted data: {extracted_data}")
                return extracted_data
            else:
                print(f"No data found between || symbols in: {data}")
                return None
        except Exception as e:
            print(f"Error extracting data: {e}")
            return None

    def scanning_loop(self, client_socket):
        """
        Scan loop: reads from COM port and sends data to client.
        - In 'learn' mode: tries to extract text between ||, sends raw if no pipes.
        - In 'check' mode: sends all raw data, but replaces underscores with newlines.
        Runs until 'ok' is received or client disconnects.
        """
        if self.scan_active:
            return

        self.scan_active = True
        try:
            self.com_port = serial.Serial(
                port=COM_PORT_NAME,
                baudrate=COM_PORT_BAUDRATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=COM_PORT_TIMEOUT
            )

            while self.scan_active and self.running and self.mode is not None:
                try:
                    # Check for client commands (non-blocking)
                    client_socket.settimeout(0.1)
                    try:
                        data = client_socket.recv(1024).decode('utf-8').strip()
                        if data.lower() == "ok":
                            print("Exiting scanning mode")
                            self.mode = None
                            break
                    except socket.timeout:
                        pass  # No command, continue reading COM port

                    # Read from COM port if data available
                    if self.com_port.in_waiting > 0:
                        com_data = self.com_port.read(self.com_port.in_waiting)
                        if com_data:
                            decoded_data = com_data.decode('utf-8', errors='ignore')
                            print(f"Raw data from {COM_PORT_NAME}: {decoded_data}")

                            # Choose what to send based on mode
                            if self.mode == 'check':
                                # Replace underscores with newlines so data appears on separate lines
                                processed_data = decoded_data.replace('_', '\n')
                                client_socket.send(f"{processed_data}\n".encode('utf-8'))
                            else:  # 'learn' mode
                                extracted_data = self.extract_data_between_pipes(decoded_data)
                                if extracted_data:
                                    client_socket.send(f"{extracted_data}\n".encode('utf-8'))
                                else:
                                    client_socket.send(f" {decoded_data}\n".encode('utf-8'))

                except Exception as e:
                    print(f"Error during scan: {e}")
                    break

        except serial.SerialException as e:
            client_socket.send(f"Error opening {COM_PORT_NAME}: {e}\n".encode('utf-8'))
        except Exception as e:
            client_socket.send(f"Unexpected error: {e}\n".encode('utf-8'))
        finally:
            self.close_com_port()
            self.scan_active = False
            client_socket.settimeout(None)

    def close_com_port(self):
        """Close the COM port if open"""
        if self.com_port and self.com_port.is_open:
            try:
                self.com_port.close()
                print(f"{COM_PORT_NAME} closed")
            except Exception as e:
                print(f"Error closing {COM_PORT_NAME}: {e}")
            finally:
                self.com_port = None

    def cleanup(self):
        """Cleanup resources"""
        self.close_com_port()
        self.mode = None
        self.scan_active = False
        self.current_client_socket = None

    def stop(self):
        """Stop the server"""
        self.running = False
        self.cleanup()
        if self.server_socket:
            self.server_socket.close()
        print("Server stopped")