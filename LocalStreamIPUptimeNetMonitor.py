import tkinter as tk
from tkinter import ttk
from ping3 import ping
import time
import requests
from datetime import datetime
import pandas as pd

# Global variable to control the timer
timer_running = False

# Dictionary to store uptime and last successful ping time for each IP
uptime_data = {}

def read_ip_addresses_and_urls(file_path):
    if file_path.endswith('.xlsx'):
        df = pd.read_excel(file_path)
    else:
        raise ValueError("Unsupported file format. Please provide an XLSX file.")
    
    ip_url_pairs = list(df.itertuples(index=False, name=None))
    return ip_url_pairs

def ping_ip(ip):
    try:
        response = ping(ip, timeout=2)
        return response is not None
    except OSError as e:
        print(f"Error pinging IP {ip}: {e}")
        return False

def check_url(url):
    try:
        response = requests.get(url, timeout=5)
        return response.status_code != 404
    except requests.RequestException as e:
        print(f"Error checking URL {url}: {e}")
        return False

def update_status(tree, ip, status, url_status, description):
    for item in tree.get_children():
        if tree.item(item, 'values')[0] == ip:
            uptime_seconds = uptime_data.get(ip, {}).get('uptime', 0)
            uptime_formatted = format_uptime(uptime_seconds)
            tree.item(item, values=(ip, status, url_status, time.strftime('%Y-%m-%d %H:%M:%S'), uptime_formatted, description))
            break

def log_unavailable_ip(listbox, ip, description, failed_checks):
    log_entry = f"{ip} ({description}) - {time.strftime('%Y-%m-%d %H:%M:%S')} - {failed_checks}"
    listbox.insert(tk.END, log_entry)

def ping_all_ips_and_check_urls(tree, ip_url_pairs, listbox):
    for pair in ip_url_pairs:
        ip, url, description = pair[0], pair[1], pair[2]
        is_available = ping_ip(ip)
        is_url_found = check_url(url)
        url_status = 'Found' if is_url_found else '404 Not Found'
        current_time = time.time()
        
        if ip not in uptime_data:
            uptime_data[ip] = {'last_successful_ping': None, 'uptime': 0}

        if is_available:
            if uptime_data[ip]['last_successful_ping'] is None:
                uptime_data[ip]['last_successful_ping'] = current_time
            else:
                uptime_data[ip]['uptime'] += current_time - uptime_data[ip]['last_successful_ping']
                uptime_data[ip]['last_successful_ping'] = current_time
        else:
            log_unavailable_ip(listbox, ip, description, "Ping failed")
            uptime_data[ip]['last_successful_ping'] = None
            uptime_data[ip]['uptime'] = 0

        if not is_url_found:
            log_unavailable_ip(listbox, ip, description, "URL check failed")

        status = 'Available' if is_available else 'Unavailable'
        update_status(tree, ip, status, url_status, description)

def show_ips_on_start(tree, file_path):
    ip_url_pairs = read_ip_addresses_and_urls(file_path)
    for pair in ip_url_pairs:
        ip, url, description = pair[0], pair[1], pair[2]
        tree.insert('', 'end', values=(ip, 'Unknown', 'Unknown', '', '00:00:00', description))

def start_ping(tree, file_path, listbox):
    ip_url_pairs = read_ip_addresses_and_urls(file_path)
    for item in tree.get_children():
        tree.delete(item)
    for pair in ip_url_pairs:
        ip, url, description = pair[0], pair[1], pair[2]
        tree.insert('', 'end', values=(ip, 'Checking...', 'Checking...', '', '00:00:00', description))
    ping_all_ips_and_check_urls(tree, ip_url_pairs, listbox)

def start_timer(tree, file_path, listbox, timer_label):
    global timer_running
    timer_running = True
    timer_label.config(text="Timer Enabled: Checking every 1 minute")
    schedule_ping(tree, file_path, listbox, timer_label)

def stop_timer(timer_label):
    global timer_running
    timer_running = False
    timer_label.config(text="Timer Disabled")

def schedule_ping(tree, file_path, listbox, timer_label):
    if timer_running:
        start_ping(tree, file_path, listbox)
        tree.after(1 * 60 * 1000, lambda: schedule_ping(tree, file_path, listbox, timer_label))

def format_uptime(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def save_logs_to_file(listbox):
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename_txt = f"logs_{now}.txt"
    filename_xlsx = f"logs_{now}.xlsx"

    # Save to TXT file
    with open(filename_txt, "w") as file:
        for entry in listbox.get(0, tk.END):
            file.write(entry + "\n")
    print(f"Logs saved to {filename_txt}")

    # Save to XLSX file
    logs = [entry.split(" - ") for entry in listbox.get(0, tk.END)]
    df = pd.DataFrame(logs, columns=["IP Address", "Description", "Date Time", "Failed Check"])
    df.to_excel(filename_xlsx, index=False)
    print(f"Logs saved to {filename_xlsx}")

def create_gui():
    root = tk.Tk()
    root.title("Stream IP Uptime Net Monitor by SolucionesMelis")

    # Open the application maximized
    root.state('zoomed')

    main_frame = ttk.Frame(root, padding="10")
    main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    tree_frame = ttk.Frame(main_frame)
    tree_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    main_frame.grid_rowconfigure(0, weight=1)
    main_frame.grid_columnconfigure(0, weight=1)

    tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
    tree_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

    tree = ttk.Treeview(tree_frame, columns=('IP Address', 'Status', 'URL Status', 'Last Checked', 'Uptime', 'Description'), show='headings', yscrollcommand=tree_scrollbar.set)
    tree.heading('IP Address', text='IP Address')
    tree.heading('Status', text='Status')
    tree.heading('URL Status', text='URL Status')
    tree.heading('Last Checked', text='Last Checked')
    tree.heading('Uptime', text='Uptime (HH:MM:SS)')
    tree.heading('Description', text='Description')
    tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    tree_scrollbar.config(command=tree.yview)
    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)

    button_frame = ttk.Frame(main_frame, padding="10")
    button_frame.grid(row=1, column=0, sticky=tk.W)

    start_button = ttk.Button(button_frame, text="Start Ping", command=lambda: start_ping(tree, 'IP_FILE_LIST.xlsx', listbox))  # Change the file name accordingly
    start_button.pack(side=tk.LEFT, padx=5)

    timer_button = ttk.Button(button_frame, text="Start Timer", command=lambda: start_timer(tree, 'IP_FILE_LIST.xlsx', listbox, timer_label))  # Change the file name accordingly
    timer_button.pack(side=tk.LEFT, padx=5)

    stop_timer_button = ttk.Button(button_frame, text="Stop Timer", command=lambda: stop_timer(timer_label))
    stop_timer_button.pack(side=tk.LEFT, padx=5)

    save_logs_button = ttk.Button(button_frame, text="Save Logs", command=lambda: save_logs_to_file(listbox))
    save_logs_button.pack(side=tk.LEFT, padx=5)

    timer_label = ttk.Label(main_frame, text="Timer Disabled")
    timer_label.grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)

    log_frame = ttk.LabelFrame(root, text="Unavailable IPs Log", padding="10")
    log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)
    root.grid_rowconfigure(3, weight=1)
    root.grid_columnconfigure(0, weight=1)

    listbox = tk.Listbox(log_frame, height=10)
    listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    scrollbar = tk.Scrollbar(log_frame, orient="vertical")
    scrollbar.config(command=listbox.yview)
    listbox.config(yscrollcommand=scrollbar.set)

    scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

    log_frame.grid_columnconfigure(0, weight=1)
    log_frame.grid_rowconfigure(0, weight=1)

    # Show IPs on start
    show_ips_on_start(tree, 'IP_FILE_LIST.xlsx')  # Change the file name accordingly

    root.mainloop()

if __name__ == "__main__":
    create_gui()
