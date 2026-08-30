import sys
import os
import ssl
import subprocess
import pandas as pd
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                             QTextEdit, QHeaderView, QLabel, QSpinBox, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QCursor

# --- Lógica de Red (Worker) ---
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.set_ciphers('DEFAULT@SECLEVEL=1')
        kwargs['ssl_context'] = context
        return super(SSLAdapter, self).init_poolmanager(*args, **kwargs)

class ScannerWorker(QThread):
    result_signal = pyqtSignal(int, bool, object, str)
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal()

    def __init__(self, data):
        super().__init__()
        self.data = data

    def run(self):
        session = requests.Session()
        session.mount("https://", SSLAdapter())
        for row in self.data:
            if self.isInterruptionRequested():
                break
            table_row = row['table_row']
            u_ok = False
            try:
                self.progress_signal.emit(table_row, "CHECKING URL...")
                # Only fetch response headers; monitoring URLs may be infinite streams.
                with session.get(row['URL'], headers={'User-Agent': 'Mozilla/5.0'},
                                  stream=True, timeout=(5, 5)) as response:
                    u_ok = response.status_code in (200, 206)
            except requests.RequestException:
                u_ok = False
            
            # A working URL is enough to consider the service online. Avoid an
            # unnecessary ICMP request in that case; some hosts block ping.
            i_ok = None
            if not u_ok:
                self.progress_signal.emit(table_row, "CHECKING PING...")
                param = '-n' if os.name == 'nt' else '-c'
                ping_args = ['ping', param, '1', row['IP']]
                if os.name == 'nt':
                    # Windows ping otherwise waits several seconds per unreachable host.
                    ping_args.extend(['-w', '1000'])
                kwargs = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.STDOUT}
                if os.name == 'nt': kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                try:
                    i_ok = subprocess.call(ping_args, **kwargs) == 0
                except (OSError, ValueError):
                    i_ok = False

            ts = datetime.now().strftime("%H:%M:%S")
            ip_status = "SKIP" if i_ok is None else ('UP' if i_ok else 'DN')
            log = f"URL: {'UP' if u_ok else 'DN'} / IP: {ip_status} / {ts} - {row['URL']}"
            self.result_signal.emit(table_row, u_ok, i_ok, log)
        self.finished_signal.emit()

# --- Estilo Dark Mode Midnight ---
DARK_STYLE = """
    QMainWindow { background-color: #0f111a; }
    QFrame#Dashboard { background-color: #1a1d2b; border-radius: 8px; border: 1px solid #2e344e; }
    QLabel { color: #8f93a2; font-family: 'Segoe UI'; font-weight: bold; }
    
    QPushButton { 
        background-color: #24283b; color: #c0caf5; border: 1px solid #414868; 
        border-radius: 4px; padding: 7px; font-weight: bold; 
    }
    QPushButton:hover { background-color: #414868; border: 1px solid #7aa2f7; }
    
    QPushButton#btnStart { background-color: #1b4d3e; color: #73daca; border: 1px solid #1b4d3e; }
    QPushButton#btnStart:hover { background-color: #246b57; border: 1px solid #73daca; }
    
    QPushButton#btnStop { background-color: #4d1b1b; color: #f7768e; border: 1px solid #4d1b1b; }
    QPushButton#btnStop:hover { background-color: #6b2424; border: 1px solid #f7768e; }

    QTableWidget { background-color: #1a1d2b; color: #a9b1d6; gridline-color: #2e344e; border: 1px solid #2e344e; }
    QHeaderView::section { background-color: #0f111a; color: #7aa2f7; padding: 6px; border: 1px solid #2e344e; font-weight: bold; }
    
    QSpinBox { background-color: #1a1d2b; color: #7aa2f7; border: 1px solid #414868; }
    
    QTextEdit#Console { background-color: #0d0f16; border: 1px solid #2e344e; color: #9ece6a; font-family: 'Consolas'; }
    QTextEdit#History { background-color: #161925; border: 1px solid #bb9af7; color: #bb9af7; font-family: 'Consolas'; font-size: 9pt; }
"""

class UptimeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SolucionesMelis | Uptime Monitor Pro v0.14")
        self.resize(1450, 850)
        self.setStyleSheet(DARK_STYLE)
        
        self.stats = {}
        self.remaining_seconds = 0
        self.last_hour_log_time = None
        self.global_avg = 0.0
        self.worker = None
        self.base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        
        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self.start_scan)
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_elements)
        
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 1. Dashboard
        self.dash = QFrame(); self.dash.setObjectName("Dashboard")
        dash_layout = QHBoxLayout(self.dash)
        self.led = QLabel("●"); self.led.setStyleSheet("color: #444b6a; font-size: 32px;")
        self.lbl_global = QLabel("UPTIME GLOBAL: 0.00%"); self.lbl_global.setStyleSheet("font-size: 20px; color: #bb9af7;")
        self.lbl_timer = QLabel("PRÓXIMO SCAN: --S"); self.lbl_timer.setStyleSheet("color: #7aa2f7; font-family: Consolas; font-size: 15px;")
        dash_layout.addWidget(self.led); dash_layout.addWidget(self.lbl_global); dash_layout.addStretch(); dash_layout.addWidget(self.lbl_timer)
        main_layout.addWidget(self.dash)

        # 2. Área Central (Tabla + Historial Horario)
        center_layout = QHBoxLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["IP", "URL", "DESCRIPTION", "ESTADO", "UPTIME URL", "UPTIME IP", "CHECKS", "ONLINE"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsMovable(True)
        self.table.setColumnWidth(2, 260)
        center_layout.addWidget(self.table, 4)

        hist_panel = QVBoxLayout()
        hist_panel.addWidget(QLabel("🕒 LOG POR HORA (AUTO)"))
        self.hour_log_view = QTextEdit(); self.hour_log_view.setObjectName("History")
        self.hour_log_view.setReadOnly(True); self.hour_log_view.setFixedWidth(280)
        hist_panel.addWidget(self.hour_log_view)
        center_layout.addLayout(hist_panel, 1)
        main_layout.addLayout(center_layout)

        # 3. Botonera (Todo recuperado)
        btns = QHBoxLayout()
        self.btn_import = QPushButton("📂 CARGAR XLSX"); self.btn_import.clicked.connect(self.import_excel)
        self.btn_manual = QPushButton("🔍 SCAN MANUAL"); self.btn_manual.clicked.connect(self.start_scan)
        self.btn_export = QPushButton("💾 EXPORTAR REPORTE"); self.btn_export.clicked.connect(self.export_report)
        self.btn_start = QPushButton("▶ INICIAR MONITOR"); self.btn_start.setObjectName("btnStart"); self.btn_start.clicked.connect(self.start_auto)
        self.btn_stop = QPushButton("⏹ DETENER"); self.btn_stop.setObjectName("btnStop"); self.btn_stop.setEnabled(False); self.btn_stop.clicked.connect(self.stop_auto)
        
        for b in [self.btn_import, self.btn_manual, self.btn_export, self.btn_start, self.btn_stop]:
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btns.addWidget(b)
        
        btns.addWidget(QLabel("INT (S):")); self.spin = QSpinBox(); self.spin.setRange(5, 3600); self.spin.setSingleStep(5); self.spin.setValue(30)
        self.btn_interval_down = QPushButton("−"); self.btn_interval_down.setToolTip("Reducir intervalo")
        self.btn_interval_up = QPushButton("+"); self.btn_interval_up.setToolTip("Aumentar intervalo")
        self.btn_interval_down.clicked.connect(lambda: self.spin.setValue(self.spin.value() - self.spin.singleStep()))
        self.btn_interval_up.clicked.connect(lambda: self.spin.setValue(self.spin.value() + self.spin.singleStep()))
        btns.addWidget(self.btn_interval_down); btns.addWidget(self.btn_interval_up)
        btns.addWidget(self.spin)
        main_layout.addLayout(btns)

        # 4. Log Consola
        self.log_output = QTextEdit(); self.log_output.setObjectName("Console")
        self.log_output.setReadOnly(True); self.log_output.setFixedHeight(120)
        main_layout.addWidget(self.log_output)

    # --- Funciones ---
    def import_excel(self):
        path = os.path.join(self.base_dir, "IP_FILE_LIST.xlsx")
        if not os.path.exists(path):
            self.log_output.append(">> ERROR: IP_FILE_LIST.xlsx no encontrado.")
            return
        try:
            df = pd.read_excel(path)
        except (OSError, ValueError, KeyError) as e:
            self.log_output.append(f">> ERROR AL CARGAR XLSX: {e}")
            return
        if not {'IP', 'URL'}.issubset(df.columns):
            self.log_output.append(">> ERROR: el XLSX debe contener las columnas IP y URL.")
            return
        self.stats.clear()
        self.table.setRowCount(len(df))
        for i, row in df.iterrows():
            self.table.setItem(i, 0, QTableWidgetItem(str(row['IP'])))
            self.table.setItem(i, 1, QTableWidgetItem(str(row['URL'])))
            description = row.get('DESCRIPTION', '')
            self.table.setItem(i, 2, QTableWidgetItem("" if pd.isna(description) else str(description)))
            for c in range(3, 8): self.table.setItem(i, c, QTableWidgetItem("---"))
            self.stats[i] = {'url_up': 0, 'ip_up': 0, 'ip_checks': 0, 'total': 0, 'last_up_time': None, 'is_online': False}
        self.log_output.append(">> XLSX CARGADO.")

    def export_report(self):
        data = []
        for i in range(self.table.rowCount()):
            data.append({
                "IP": self.table.item(i,0).text(), "URL": self.table.item(i,1).text(),
                "DESCRIPTION": self.table.item(i,2).text(),
                "Uptime_URL": self.table.item(i,4).text(), "Uptime_IP": self.table.item(i,5).text(),
                "Online_Session": self.table.item(i,7).text()
            })
        pd.DataFrame(data).to_excel(os.path.join(self.base_dir, "REPORTE_ACTUAL.xlsx"), index=False)
        self.log_output.append(">> REPORTE GUARDADO EN REPORTE_ACTUAL.xlsx")

    def update_ui_elements(self):
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            self.lbl_timer.setText(f"PRÓXIMO SCAN: {self.remaining_seconds}S")
            color = "#73daca" if self.remaining_seconds % 2 == 0 else "#246b57"
            self.led.setStyleSheet(f"color: {color}; font-size: 32px;")
        else:
            self.lbl_timer.setText("ESCANEANDO...")

    def start_auto(self):
        self.btn_start.setEnabled(False); self.btn_stop.setEnabled(True)
        self.btn_import.setEnabled(False); self.btn_manual.setEnabled(False); self.spin.setEnabled(False)
        self.start_scan()
        self.scan_timer.start(self.spin.value() * 1000); self.ui_timer.start(1000)

    def stop_auto(self):
        self.scan_timer.stop(); self.ui_timer.stop()
        self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False)
        self.btn_import.setEnabled(True); self.btn_manual.setEnabled(True); self.spin.setEnabled(True)
        self.led.setStyleSheet("color: #444b6a; font-size: 32px;")
        self.lbl_timer.setText("PRÓXIMO SCAN: --S")

    def start_scan(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.remaining_seconds = self.spin.value()
        data = []
        for i in range(self.table.rowCount()):
            ip_item, url_item = self.table.item(i, 0), self.table.item(i, 1)
            if not ip_item or not url_item or not ip_item.text().strip() or not url_item.text().strip():
                self.log_output.append(f">> FILA {i + 1} OMITIDA: IP o URL vacía.")
                continue
            data.append({"IP": ip_item.text().strip(), "URL": url_item.text().strip(), "table_row": i})
        if data:
            self.worker = ScannerWorker(data)
            self.worker.progress_signal.connect(self.update_checking_row)
            self.worker.result_signal.connect(self.update_row)
            self.worker.finished_signal.connect(self.finalize_scan)
            self.worker.start()

    def update_checking_row(self, row, check_name):
        self.table.clearSelection()
        self.table.selectRow(row)
        for column in range(self.table.columnCount()):
            item = self.table.item(row, column)
            if item:
                item.setBackground(QColor("#4f4122"))
        checking_item = QTableWidgetItem(check_name)
        checking_item.setForeground(QColor("#e0af68"))
        checking_item.setBackground(QColor("#4f4122"))
        self.table.setItem(row, 3, checking_item)

    def update_row(self, row, url_ok, ip_ok, log_line):
        s = self.stats[row]
        self.table.clearSelection()
        for column in range(self.table.columnCount()):
            item = self.table.item(row, column)
            if item:
                item.setBackground(QColor("#1a1d2b"))
        s['total'] += 1
        if url_ok: s['url_up'] += 1
        if ip_ok is not None:
            s['ip_checks'] += 1
            if ip_ok: s['ip_up'] += 1
        
        ahora = datetime.now()
        if url_ok:
            if not s['is_online']: s['last_up_time'] = ahora; s['is_online'] = True
            dur = ahora - s['last_up_time']
            h, r = divmod(dur.total_seconds(), 3600); m, seg = divmod(r, 60)
            tiempo_str = f"{int(h):02}:{int(m):02}:{int(seg):02}"
        else:
            s['is_online'] = False; tiempo_str = "OFFLINE"

        item_st = QTableWidgetItem(f"{'✔' if url_ok else '✘'} URL | {'✔' if ip_ok else '✘'} IP")
        item_st.setForeground(QColor("#73daca") if url_ok and ip_ok else QColor("#f7768e"))
        if ip_ok is None:
            item_st.setText("URL UP | IP SKIPPED")
        item_st.setForeground(QColor("#73daca") if url_ok else QColor("#f7768e"))
        self.table.setItem(row, 3, item_st)
        self.table.setItem(row, 4, QTableWidgetItem(f"{(s['url_up']/s['total'])*100:.1f}%"))
        ip_uptime = "---" if s['ip_checks'] == 0 else f"{(s['ip_up']/s['ip_checks'])*100:.1f}%"
        self.table.setItem(row, 5, QTableWidgetItem(ip_uptime))
        self.table.setItem(row, 6, QTableWidgetItem(str(s['total'])))
        # URL availability is authoritative for the user-facing ONLINE status.
        online_item = QTableWidgetItem("ONLINE" if url_ok else "OFFLINE")
        online_item.setForeground(QColor("#73daca") if url_ok else QColor("#8f93a2"))
        self.table.setItem(row, 7, online_item)
        self.log_output.append(log_line)

    def finalize_scan(self):
        if not self.stats: return
        
        # Calcular el promedio global de la sesión actual
        monitored_stats = [s for s in self.stats.values() if s['total'] > 0]
        sum_avg = sum(
            ((s['url_up'] / s['total']) +
             ((s['ip_up'] / s['ip_checks']) if s['ip_checks'] else (s['url_up'] / s['total']))) / 2
            for s in monitored_stats
        )
        self.global_avg = (sum_avg / len(monitored_stats)) * 100 if monitored_stats else 0.0
        self.lbl_global.setText(f"UPTIME GLOBAL: {self.global_avg:.2f}%")
        
        # --- Lógica de Log Horario y Autoguardado con FECHA ---
        ahora = datetime.now()
        
        # Solo registra si es la primera vez o si ha pasado 1 hora
        if self.last_hour_log_time is None or (ahora - self.last_hour_log_time) >= timedelta(hours=1):
            # Formato corregido: [Día-Mes-Año Hora:Minuto]
            timestamp_completo = ahora.strftime('%d-%m-%Y %H:%M')
            entry = f"[{timestamp_completo}] Uptime Global: {self.global_avg:.2f}%\n"
            
            # Actualizar la interfaz (columna derecha)
            self.hour_log_view.append(entry)
            
            # Auto-scroll para ver siempre el último registro
            self.hour_log_view.ensureCursorVisible()
            
            # Guardar la referencia del tiempo
            self.last_hour_log_time = ahora
            
            # Guardar en el archivo físico uptimelog.txt
            try:
                with open(os.path.join(self.base_dir, "uptimelog.txt"), "a", encoding="utf-8") as f:
                    f.write(entry)
            except Exception as e:
                self.log_output.append(f">> ERROR AL ESCRIBIR EN ARCHIVO: {e}")

    def closeEvent(self, event):
        self.scan_timer.stop(); self.ui_timer.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption(); self.worker.wait(2000)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UptimeApp(); window.showMaximized()
    sys.exit(app.exec())
