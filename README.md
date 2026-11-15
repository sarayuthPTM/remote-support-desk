# AnySupport Web — ระบบช่วยเหลือและซ่อมคอมพิวเตอร์ระยะไกล (Remote Support Desk)

ระบบแชร์หน้าจอ ควบคุมเมาส์/คีย์บอร์ด สนทนาด้วยเสียง วาดชี้เป้าบนหน้าจอ และส่งไฟล์แบบ Peer-to-Peer (WebRTC) พร้อมโปรแกรมผู้ช่วยฝั่ง Windows (`RemoteAgent.exe`)

---

## โครงสร้างไฟล์

- `index.html` — หน้าเว็บแอปพลิเคชัน (รองรับทั้งโหมด **ผู้ขอความช่วยเหลือ / Host** และ **ผู้ช่วยเหลือ / Admin**)
- `agent.py` — โปรแกรมฝั่ง Windows (System Tray Icon + WebSocket `127.0.0.1:8765` + Win32 `SendInput` DPI-Aware + UAC Admin)
- `requirements.txt` — รายการแพ็กเกจ Python ที่ต้องใช้
- `build_exe.bat` — สคริปต์สร้างไฟล์ `RemoteAgent.exe` (ไม่มีหน้าต่างดำ + ขอสิทธิ์ Administrator อัตโนมัติ)
- `vercel.json`, `manifest.json`, `package.json` — ไฟล์ตั้งค่าสำหรับ Deploy ขึ้น GitHub + Vercel

---

## การทดสอบบนเครื่อง (Local Development)

1. **เปิดเว็บฝั่ง Frontend:**
   ```bash
   npx serve . -l 3000
   ```
   จากนั้นเปิด `http://localhost:3000` (WebRTC `getDisplayMedia` ต้องรันบน `https://` หรือ `localhost` เท่านั้น)

2. **รัน Agent ฝั่ง Python (หรือเปิด `RemoteAgent.exe`):**
   ```bash
   pip install -r requirements.txt
   python agent.py
   ```
   > หมายเหตุ: หากไม่ได้เปิดด้วยสิทธิ์ Administrator ตัวโปรแกรมจะขอ UAC Elevation อัตโนมัติเพื่อให้สามารถควบคุมหน้าต่างระบบอย่าง Task Manager หรือหน้าต่างติดตั้งโปรแกรมได้

---

## การ Build ไฟล์ `RemoteAgent.exe`

ดับเบิลคลิกไฟล์ `build_exe.bat` หรือรันใน CMD/PowerShell:
```bat
build_exe.bat
```
จะได้ไฟล์ `RemoteAgent.exe` อยู่ในโฟลเดอร์โปรเจกต์ทันที (พร้อมฝัง Manifest `--uac-admin` และรันแบบ System Tray `--windowed`)

---

## การ Deploy ขึ้น GitHub + Vercel

1. **Push โค้ดขึ้น GitHub Repository** (รวมไฟล์ `RemoteAgent.exe` หากต้องการให้กดดาวน์โหลด `./RemoteAgent.exe` จากเว็บ Vercel ได้โดยตรง หรืออัปโหลด `.exe` ไว้ใน GitHub Releases แล้วแก้ลิงก์ดาวน์โหลดใน `index.html`)
2. **เชื่อมต่อใน Vercel:**
   - เลือก **Import Git Repository**
   - ตั้งค่า **Framework Preset**: `Other`
   - ตั้งค่า **Root Directory**: `./` (หรือโฟลเดอร์ของโปรเจกต์นี้)
   - กด **Deploy** (จะได้ URL แบบ `https://...vercel.app` พร้อมใช้งาน WebRTC ทันที)

> **คำแนะนำด้านเครือข่ายโรงเรียน/องค์กร:** หากนำไปใช้งานข้ามเครือข่ายที่มี Firewall หรือ Symmetric NAT เข้มงวด สามารถกดปุ่ม **ตั้งค่า ICE / TURN** บนหน้าเว็บเพื่อระบุ TURN Server (เช่น Metered / coturn) เพิ่มเติมได้
