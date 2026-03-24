# Windows 11 VM Setup (UTM on macOS)

## 1. Install UTM

Download from https://mac.getutm.app (free) or the Mac App Store ($9.99, same app).

## 2. Get Windows 11 ARM

1. Go to https://www.microsoft.com/en-us/software-download/windows11arm64
2. Download the VHDX image (recommended) or ISO

## 3. Create the VM in UTM

1. Open UTM → "Create a New Virtual Machine" → **Virtualize** → **Windows**
2. Import the VHDX or mount the ISO
3. Recommended settings:
   - RAM: **4 GB** minimum (8 GB recommended)
   - CPU cores: **4**
   - Storage: **64 GB** minimum
4. Under **Network**: select **Bridged (Advanced)** → pick your active adapter (Wi-Fi or Ethernet)
   - This gives the VM its own IP on your LAN, which Playwright needs to connect to

## 4. Install Windows & Tooling

Inside the VM, open PowerShell as Administrator and run:

```powershell
# Install winget if not available (Windows 11 should have it)
# Then install dependencies:
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Git.Git
winget install MPC-BE.MPC-BE

# Restart terminal to pick up PATH changes
```

## 5. Clone & Run the Project

```powershell
cd ~
git clone <your-repo-url> video-downloader
cd video-downloader

# Backend
pip install -r server/requirements.txt

# Frontend
cd frontend
npm install
```

## 6. Start the App (bind to all interfaces)

```powershell
# Terminal 1 — Backend
cd ~/video-downloader
uvicorn server.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd ~/video-downloader/frontend
npm run dev -- --host 0.0.0.0
```

## 7. Find the VM's IP

In the VM, run:
```powershell
ipconfig
```
Look for the IPv4 address on your bridged adapter (e.g., `192.168.1.42`).

## 8. Run Playwright Tests from Mac

```bash
cd frontend
E2E_BASE_URL=http://192.168.1.42:5173 npm run test:e2e
```

## Troubleshooting

- **VM not reachable from Mac**: Ensure UTM network mode is "Bridged", not "Shared". Check Windows Firewall allows inbound on ports 5173 and 8000.
- **Slow VM**: Increase RAM/CPU cores in UTM settings. Close unnecessary apps in the VM.
- **Port already in use**: Kill existing processes with `netstat -ano | findstr :5173` then `taskkill /PID <pid> /F`.
