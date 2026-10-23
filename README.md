# 🖨️ PrinterYuta

> **Autonomous Linux Printing Optimizer & Self-Healing Daemon for Ubuntu**  
> Specially engineered for Canon CAPT (LBP2900, LBP3000, LBP3300), fragile GDI printers, and modern CUPS spoolers.

[![Linux](https://img.shields.io/badge/OS-Ubuntu%20%7C%20Debian-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![CUPS](https://img.shields.io/badge/Spooler-CUPS%20%2B%20CAPT-green)](https://cups.org)
[![Tests](https://img.shields.io/badge/Tests-15%2F15%20Passing-brightgreen)](#testing)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 📖 Bối cảnh & Vấn đề Cốt lõi (The Linux Printing Dilemma)

Trên Windows, các dòng máy in laser văn phòng phổ biến như **Canon LBP2900, LBP3000, LBP3300** cắm cáp USB vào là in ngay (Plug & Play). Nhưng trên Linux (Ubuntu/Debian), trải nghiệm in ấn thường là một cơn ác mộng:

### Tại sao in trên Linux lại "khoai" đến vậy?
1. **Kiến trúc phần cứng GDI / CAPT:**
   * Các dòng máy in này không có bộ vi xử lý mạnh, không có RAM đệm và **không hỗ trợ các ngôn ngữ in tiêu chuẩn ngành** như PCL6 hay PostScript.
   * Toàn bộ việc tính toán từng xung laser quét hạt mực (rasterization) đều do CPU máy tính tính toán, sau đó nén và bắn dữ liệu thô xuống máy in qua giao thức độc quyền **CAPT (Canon Advanced Printing Technology)**.
2. **Sự đứt gãy của chuỗi driver đóng trên Linux:**
   * Canon gần như đã ngừng cập nhật driver Linux từ năm 2017. Kiến trúc của họ bắt buộc phải có một dịch vụ nền bên ngoài tên là `ccpd` (Canon Communication Protocol Daemon) và tiến trình `captmon` để giao tiếp với kernel driver `usblp`.
   * **Lỗi rút/cắm USB (Dead Node):** Mỗi khi tắt/bật máy in hoặc cắm lại cổng USB, thiết bị nhảy từ `/dev/usb/lp0` sang `/dev/usb/lp1`. Dịch vụ `ccpd` giữ con trỏ tệp cũ sẽ bị "đóng băng" (stale file descriptor) và không in được nữa.
   * **Bẫy hàng đợi kép (Toxic Duplicate Queues):** Hệ thống CUPS (`cups-browsed`) thường tự động quét USB và tự tạo ra một hàng đợi phụ (ví dụ: `LBP3300-2` với URI `usb://...`). Khi người dùng vô tình bấm in vào hàng đợi này, tiến trình `libusb` sẽ **ngắt (detach) driver `usblp` của Linux Kernel**, làm biến mất toàn bộ file thiết bị `/dev/usb/lp*` và triệt hạ luôn daemon `ccpd`.
   * **Nghẽn Spooler (Zombie Jobs):** Khi một trang in gặp lỗi, CUPS giữ job ở trạng thái `ppdFilterEmitJCL: Filter function started`, treo toàn bộ hàng đợi vĩnh viễn.

---

## 🚀 Giải pháp: PrinterYuta

**PrinterYuta** được xây dựng để biến trải nghiệm in ấn trên Ubuntu thành **Zero-Touch (Tự chủ hoàn toàn)**:

```
┌────────────────────────────────────────────────────────┐
│                   PrinterYuta Suite                    │
├───────────────────┬───────────────────┬────────────────┤
│  Hardware Guard   │   Spooler Doctor  │ Pre-Flight Opt │
│  - Udev Symlinks  │  - Nuke Duplicates│ - A4 Page Fit  │
│  - Rebind usblp   │  - Fix FIFO pipe  │ - 600 DPI Down │
│  - Hotplug Daemon │  - Reap Stuck Jobs│ - Pure Mono GS │
└───────────────────┴───────────────────┴────────────────┘
```

1. **Auto-Healing Queue Doctor:** Tự động phát hiện và xóa sạch các hàng đợi giả mạo gây ngắt kết nối USB (`LBP3300-2`), nạp lại backend chuẩn `ccp:/var/ccpd/fifo0`.
2. **USB Hotplug & Udev Guard:** Tích hợp quy tắc Udev bắt sự kiện cắm/bật máy in, tự động restart `ccpd` và làm tươi pipe `/var/ccpd/fifo0` trong nền.
3. **Spooler Watchdog:** Tự động giải phóng các lệnh in bị kẹt (zombie filter jobs) và tự mở lại hàng đợi bị pause.
4. **Pre-flight Document Optimizer:** Chuẩn hóa PDF trước khi gửi vào CUPS: tự động nén ảnh về 600 DPI, chuyển hệ màu sang 8-bit Grayscale để giảm tải RAM cho Ghostscript, chống tràn bộ nhớ và tiết kiệm mực in.

---

## 🛠️ Cài đặt nhanh

### Cách 1: Sử dụng ngay không cần cài đặt (User CLI)
Repository đã tạo sẵn lệnh chạy trực tiếp trong terminal:
```bash
# Kiểm tra phiên bản
printeryuta --version

# Hiển thị bảng điều khiển sức khỏe máy in
printeryuta status
```

### Cách 2: Kích hoạt bảo vệ hệ thống vĩnh viễn (Zero-Touch Udev Guard)
Để mỗi lần cắm cáp hoặc bật máy in, hệ thống tự động sửa lỗi ngầm mà không cần gõ lệnh tay:
```bash
cd /home/tontonyuta/PrinterYuta
sudo bash scripts/install.sh
```

---

## 💻 Hướng dẫn sử dụng CLI

### 1. `printeryuta status`
Hiển thị bảng trạng thái thời gian thực trực quan bằng Rich CLI (Phần cứng USB, Module Kernel `usblp`, Hàng đợi CUPS, Sockets CCPD Port 59687 / 59787).

```bash
printeryuta status
```

### 2. `printeryuta doctor`
Bộ chẩn đoán sâu 9 bước (kiểm tra toàn diện cáp, kernel, hàng đợi độc hại, socket và named pipe).

```bash
printeryuta doctor
```

### 3. `printeryuta heal`
**Lệnh cứu tinh 1 chạm:** Tự động phát hiện lỗi, xóa hàng đợi xung đột, sửa URI về `ccp:/var/ccpd/fifo0`, tái tạo FIFO pipe và giải phóng hàng đợi.

```bash
printeryuta heal
```

### 4. `printeryuta print <tệp_tin>`
In thông minh với cơ chế tiền kiểm định (Pre-flight) và tối ưu hóa tự động:
* Tự động kiểm tra và sửa hàng đợi trước khi gửi lệnh.
* Chuyển đổi PDF màu sang Grayscale để tiết kiệm mực và tăng tốc truyền tải.
* Tự động co vừa khổ giấy A4 chuẩn.

```bash
# In thông thường với tự động tối ưu
printeryuta print tailieu.pdf

# In giữ nguyên màu hoặc tùy chỉnh DPI
printeryuta print --dpi 600 --fit-a4 tailieu.pdf
```

### 5. `printeryuta testpage`
Tạo và in ngay lập tức một trang in chẩn đoán chuẩn PostScript/PDF có thang đo độ mịn mực (Halftone calibration) và thông số hệ thống.

```bash
printeryuta testpage
```

### 6. `printeryuta daemon`
Khởi chạy tiến trình giám sát nền liên tục, sẵn sàng tự động chữa lành hệ thống mỗi 10 giây.

```bash
printeryuta daemon --interval 10
```

---

## 🧪 Testing

Dự án đi kèm bộ kiểm thử tự động 100% không phụ thuộc phần cứng (sử dụng mock runners cho kernel/CUPS/lsusb):

```bash
cd /home/tontonyuta/PrinterYuta
python3 -m unittest discover tests -v
```

**Kết quả kiểm thử:**
```text
test_parse_ccpd_conf (test_ccpd_manager.TestCcpdManager) ... ok
test_restart_script_content (test_ccpd_manager.TestCcpdManager) ... ok
test_doctor_command (test_cli.TestCli) ... ok
test_install_daemon_command (test_cli.TestCli) ... ok
test_status_command (test_cli.TestCli) ... ok
test_version_command (test_cli.TestCli) ... ok
test_heal_capt_queues_deletes_duplicate_and_fixes_backend (test_cups_manager.TestCupsManager) ... ok
test_parse_queues_identifies_toxic_duplicate (test_cups_manager.TestCupsManager) ... ok
test_known_models_mapping (test_detector.TestHardwareDetector) ... ok
test_parse_lsusb_finds_canon_lbp3300 (test_detector.TestHardwareDetector) ... ok
test_parse_lsusb_no_printers (test_detector.TestHardwareDetector) ... ok
test_scan_with_mock_runner (test_detector.TestHardwareDetector) ... ok
test_generate_diagnostic_page (test_optimizer.TestDocumentOptimizer) ... ok
test_optimize_fallback_when_gs_fails (test_optimizer.TestDocumentOptimizer) ... ok
test_scan_and_reap_cancels_failed_job (test_spooler_watchdog.TestSpoolerWatchdog) ... ok

Ran 15 tests in 0.456s
OK
```

---

## 🏛️ Cấu trúc Mã nguồn

```
PrinterYuta/
├── pyproject.toml              # Cấu hình đóng gói tiêu chuẩn Python
├── README.md                   # Tài liệu hướng dẫn chuyên sâu
├── scripts/
│   ├── install.sh              # Script kích hoạt udev & systemd service 1-click
│   └── uninstall.sh            # Script gỡ cài đặt sạch sẽ
├── printeryuta/
│   ├── __init__.py             # Định danh package & phiên bản
│   ├── cli.py                  # Giao diện dòng lệnh Rich / Click hiện đại
│   ├── core/
│   │   ├── detector.py         # Nhận diện phần cứng USB, sysfs, usblp & symlinks
│   │   ├── cups_manager.py     # Quản lý hàng đợi CUPS, diệt toxic duplicate queues
│   │   ├── ccpd_manager.py     # Quản lý Canon CCPD daemon, sockets & /var/ccpd/fifo0
│   │   ├── spooler_watchdog.py # Dọn dẹp lệnh in kẹt (zombie filter reaper)
│   │   └── optimizer.py        # Tiền xử lý PDF: Downsample DPI, Grayscale, Fit A4
│   ├── daemon/
│   │   ├── service.py          # Vòng lặp giám sát tự phục hồi liên tục
│   │   └── systemd_generator.py# Tạo file udev rule & systemd unit
│   └── assets/
│       ├── udev/               # Quy tắc Udev tự động bắt sự kiện cắm USB
│       └── systemd/            # File cấu hình service systemd
└── tests/                      # Bộ kiểm thử Unit test toàn diện
```

---

## 📄 License
Phát hành theo giấy phép **MIT License**. Tự do sử dụng, chỉnh sửa và tích hợp vào bất kỳ môi trường máy tính văn phòng hoặc máy chủ in ấn Linux nào.
