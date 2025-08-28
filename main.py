import curses
import signal
import threading
import time
from ui import CursesUI
from network import get_all_network_interfaces, validate_ip
from sender import send_file, send_directory
from receiver import start_server, stop_server
from utils import clean_path
import json

CONFIG = json.load(open('config.json'))
PORT = CONFIG['PORT']

# ---- Global Signal Handling ----
def handle_sigint(signum, frame):
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, handle_sigint)


def main():
    def run_app(stdscr):
        ui = CursesUI()
        ui.init_screen(stdscr)
        
        # Thread-safe server control with lock
        app_state = {
            'local_ip': None,
            'selected_interface_id': None,
            'server_control': {'running': False, 'socket': None},
            'server_lock': threading.Lock(),
            'server_ready': threading.Event()
        }

        if not setup_direct_connection(ui, app_state):
            ui.show_message("Network setup failed. Cannot continue.", 'error')
            return

        try:
            main_menu(ui, app_state)
        except KeyboardInterrupt:
            raise   # let wrapper handle cleanup
        finally:
            # Ensure server is stopped before exit
            with app_state['server_lock']:
                if app_state['server_control']['running']:
                    stop_server(app_state['server_control'])

    try:
        curses.wrapper(run_app)
        print("\nApplication terminated gracefully")
    except KeyboardInterrupt:
        print("\nApplication terminated")
    except Exception as e:
        print(f"\nApplication error: {e}")


def setup_direct_connection(ui, app_state):
    """Setup direct laptop-to-laptop connection"""
    ui.draw_header("Network Interface Selection")

    interfaces = get_all_network_interfaces()

    if not interfaces:
        ui.print_colored(4, 2, "No network interfaces with IP addresses found!", 'error')
        ui.print_colored(6, 2, "Possible solutions:", 'warning')
        ui.print_colored(7, 4, "1. Make sure network cable/WiFi is connected", 'info')
        ui.print_colored(8, 4, "2. Check if network adapter is enabled", 'info')
        ui.print_colored(9, 4, "3. Try setting static IP manually", 'info')
        return ip_setup(ui, app_state)

    # Display interfaces with aligned columns
    ui.print_colored(4, 2, f"Found {len(interfaces)} network interface(s):", 'success')
    desc_col, adapter_col = 25, 20
    for i, (description, adapter_name, ip, interface_id) in enumerate(interfaces, 1):
        y_pos = 5 + i
        ui.stdscr.addstr(y_pos, 4, f"{i}. ")
        ui.stdscr.addstr(y_pos, 7, description.ljust(desc_col), ui.colors['warning'])
        ui.stdscr.addstr(y_pos, 7 + desc_col, adapter_name.ljust(adapter_col), ui.colors['info'])
        ui.stdscr.addstr(y_pos, 7 + desc_col + adapter_col, ip, ui.colors['success'])

    # Input line right below interfaces
    input_y = 6 + len(interfaces)

    while True:
        try:
            valid_choices = [str(i) for i in range(1, len(interfaces) + 1)]
            choice = ui.get_single_key(input_y, 2, f"Select interface (1-{len(interfaces)})", valid_choices)
            if choice is None:
                ui.show_message("Cancelled. Returning to IP setup...", 'warning')
                return ip_setup(ui, app_state)

            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(interfaces):
                selected = interfaces[choice_idx]
                app_state['local_ip'] = selected[2]
                app_state['selected_interface_id'] = selected[3]
                ui.show_message(
                    f"Selected Interface:\n  {selected[0]} ({selected[1]})\n  IP: {app_state['local_ip']}", 
                    'success'
                )
                return True
            else:
                ui.show_message("Invalid choice. Please try again.", 'error', 1)
        except ValueError:
            ui.show_message("Please select a valid number.", 'error', 1)


def ip_setup(ui, app_state):
    """Manual IP configuration helper"""
    ui.print_colored(12, 2, "Manual Setup Required", 'warning')
    all_interfaces = get_all_network_interfaces()

    if all_interfaces:
        ui.print_colored(14, 2, f"Found {len(all_interfaces)} interface(s) with IP addresses:", 'info')
        for i, (description, adapter_name, ip, interface_id) in enumerate(all_interfaces):
            y_pos = 15 + i
            x_pos = 4
            
            ui.stdscr.addstr(y_pos, x_pos, "- ")
            x_pos += 2
            
            ui.stdscr.addstr(y_pos, x_pos, description + " ", ui.colors['warning'])
            x_pos += len(description) + 1

            
            ui.stdscr.addstr(y_pos, x_pos, " - ")
            x_pos += 3
            
            ui.stdscr.addstr(y_pos, x_pos, adapter_name, ui.colors['info'])
            x_pos += len(adapter_name)
            
            ui.stdscr.addstr(y_pos, x_pos, ": ")
            x_pos += 2
            
            ui.stdscr.addstr(y_pos, x_pos, ip, ui.colors['success'])

        ui.print_colored(17 + len(all_interfaces), 2, "You can manually specify an IP from above, or set a custom one", 'info')

    manual_ip = ui.get_input(19 + len(all_interfaces), 2, "Enter your laptop's IP address (e.g., 192.168.1.10): ")

    if validate_ip(manual_ip):
        app_state['local_ip'] = manual_ip
        app_state['selected_interface_id'] = None
        ui.show_message(f"Manual IP set: {manual_ip}", 'success')
        return True
    else:
        ui.show_message("Invalid IP address format", 'error')
        return False


def main_menu(ui, app_state):
    while True:
        ui.draw_header("Tetherfile - File Transfer Utility")
        ui.print_colored(ui.height - 2, 0, "═" * (ui.width - 1), 'highlight')

        if app_state['local_ip']:
            ui.print_colored(4, 2, f"LOCAL IP: {app_state['local_ip']}", 'success')

        box_height = 9
        box_y = 6
        ui.draw_box(box_y, 2, box_height, ui.width - 4, "MAIN MENU")

        menu_items = [
            "1. Send File",
            "2. Send Directory/Folder",
            "3. Start Receiving Mode",
            "4. Change Network Settings",
            "5. Exit"
        ]

        for i, item in enumerate(menu_items):
            color = 'highlight' if i < 3 else 'info'
            ui.print_colored(box_y + 2 + i, 4, item, color)

        ui.stdscr.refresh()

        try:
            choice = ui.get_single_key(box_y + box_height + 1, 2, "Select option (1-5)", ['1', '2', '3', '4', '5'])

            if choice == '1':
                send_file_menu(ui, app_state)
            elif choice == '2':
                send_directory_menu(ui, app_state)
            elif choice == '3':
                receive_mode(ui, app_state)
            elif choice == '4':
                if setup_direct_connection(ui, app_state):
                    ui.show_message(f"Updated IP: {app_state['local_ip']}", 'success')
            elif choice == '5':
                break

        except KeyboardInterrupt:
            raise   # bubble up to wrapper


def get_target_ip(ui):
    ui.stdscr.erase()
    ui.stdscr.clear()
    ui.draw_header("Target Selection")
    ui.print_colored(4, 2, "Enter the IP address of the target device: ", 'info')
    ui.print_colored(5, 2, "Make sure the other device is running this program in receive mode.", 'warning')

    while True:
        target_ip = ui.get_input(7, 2, "Target IP: ")
        if validate_ip(target_ip):
            return target_ip
        else:
            ui.show_message("Invalid IP address format. Please try again.", 'error', 1)


def send_file_menu(ui, app_state):
    target_ip = get_target_ip(ui)
    if not target_ip:
        return

    ui.stdscr.erase()
    ui.stdscr.clear()
    ui.draw_header("Send File")
    ui.print_colored(4, 2, f"Target: {target_ip}", 'success')

    file_path = ui.get_input(6, 2, "Enter file path (or drag & drop): ")
    file_path = clean_path(file_path)

    if file_path:
        send_file(file_path, target_ip, PORT, app_state['local_ip'], ui)

    ui.print_colored(ui.height - 3, 2, "Press any key to continue...", 'highlight')
    ui.stdscr.refresh()
    ui.stdscr.getch()
    ui.stdscr.erase()
    ui.stdscr.clear()
    ui.stdscr.refresh()


def send_directory_menu(ui, app_state):
    target_ip = get_target_ip(ui)
    if not target_ip:
        return

    ui.stdscr.erase()
    ui.stdscr.clear()
    ui.draw_header("Send Directory")
    ui.print_colored(4, 2, f"Target: {target_ip}", 'success')

    dir_path = ui.get_input(6, 2, "Enter directory path (or drag & drop): ")
    dir_path = clean_path(dir_path)

    if dir_path:
        send_directory(dir_path, target_ip, PORT, app_state['local_ip'], ui)

    ui.print_colored(ui.height - 3, 2, "Press any key to continue...", 'highlight')
    ui.stdscr.refresh()
    ui.stdscr.getch()
    ui.stdscr.erase()
    ui.stdscr.clear()
    ui.stdscr.refresh()

def receive_mode(ui, app_state):
    # Thread-safe check and stop of existing server
    with app_state['server_lock']:
        if app_state['server_control']['running']:
            stop_server(app_state['server_control'])
            # Wait for clean shutdown
            time.sleep(0.5)
    
    ui.stdscr.erase()
    ui.stdscr.clear()
    
    # Clear the ready event before starting server
    app_state['server_ready'].clear()

    # Start server in a separate thread
    server_thread = threading.Thread(
        target=start_server_wrapper,
        args=(app_state['local_ip'], PORT, ui, app_state['server_control'], app_state['server_ready']),
        daemon=True
    )
    server_thread.start()

    # Wait for server to be ready (with timeout)
    ui.draw_header("Starting Server...")
    ui.print_colored(4, 2, f"Binding to {app_state['local_ip']}:{PORT}...", 'info')
    ui.stdscr.refresh()
    
    server_started = app_state['server_ready'].wait(timeout=10.0)
    
    if not server_started:
        ui.show_message("Server startup timeout - check network settings and port availability", 'error')
        return
    
    # Thread-safe check of server status
    with app_state['server_lock']:
        if not app_state['server_control']['running']:
            ui.show_message("Failed to start server", 'error')
            return

    # Server is running, show the interface
    ui.stdscr.erase()
    ui.stdscr.clear()
    ui.draw_header("📥 Receive Mode Active")
    ui.print_colored(4, 2, f"🎯 Server listening on {app_state['local_ip']}:{PORT}", 'success')
    ui.print_colored(5, 2, f"💾 Files will be saved in 'received_files' directory", 'info')
    ui.print_colored(6, 2, "🔗 Other laptop should use this IP as target", 'info')
    ui.print_colored(8, 2, "💡 Ready to receive files... (Press 'Q' to stop)", 'highlight')
    ui.stdscr.refresh()

    try:
        # Main receive mode loop
        while True:
            with app_state['server_lock']:
                if not app_state['server_control']['running']:
                    break
                    
            ui.stdscr.timeout(100)  # Non-blocking input with 100ms timeout
            key = ui.stdscr.getch()
            
            if key in (ord('q'), ord('Q')):
                break
            elif key == curses.KEY_RESIZE:
                ui.height, ui.width = ui.stdscr.getmaxyx()
                ui.stdscr.erase()
                ui.stdscr.clear()
                ui.draw_header("📥 Receive Mode Active")
                ui.print_colored(4, 2, f"🎯 Server listening on {app_state['local_ip']}:{PORT}", 'success')
                ui.print_colored(5, 2, f"💾 Files will be saved in 'received_files' directory", 'info')
                ui.print_colored(6, 2, "🔗 Other laptop should use this IP as target", 'info')
                ui.print_colored(8, 2, "💡 Server running... Press 'Q' to stop.", 'highlight')
                ui.stdscr.refresh()
            
    except KeyboardInterrupt:
        raise
    finally:
        # Thread-safe server shutdown
        with app_state['server_lock']:
            if app_state['server_control']['running']:
                stop_server(app_state['server_control'])
        
        # Clear any remaining input
        ui.stdscr.timeout(10)
        while ui.stdscr.getch() != -1:
            pass
        ui.stdscr.timeout(-1)

    ui.show_message("Receive mode stopped.", 'warning')
    time.sleep(1)
    ui.stdscr.erase()
    ui.stdscr.clear()
    ui.stdscr.refresh()


def start_server_wrapper(local_ip, port, ui, server_control, ready_event):
    """Wrapper to signal when server is ready - with proper error handling"""
    try:
        # We need to modify the start_server call to properly signal readiness
        # Since we can't modify receiver.py easily, we'll create the socket here first
        from network import create_server_socket
        
        # Test if we can bind to the socket
        test_socket = create_server_socket(local_ip, port)
        test_socket.listen(1)  # Minimal listen queue for testing
        test_socket.close()    # Close the test socket
        
        # If we get here, the socket binding worked, so signal ready
        ready_event.set()
        
        # Now start the actual server
        start_server(local_ip, port, ui, server_control)
        
    except Exception as e:
        # If server fails to start, don't set the ready event
        ui.show_message(f"Server startup failed: {e}", 'error')
        # Make sure server_control reflects the failure
        server_control['running'] = False


if __name__ == "__main__":
    main()