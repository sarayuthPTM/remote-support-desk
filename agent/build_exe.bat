@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==================================================
echo   AnySupport Web - Build RemoteAgent.exe (UAC Admin)
echo ==================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ไม่พบ Python ในเครื่อง กรุณาติดตั้ง Python 3.10+ แล้วลองใหม่อีกครั้ง
    pause
    exit /b 1
)

echo [1/4] กำลังติดตั้ง/ตรวจสอบแพ็กเกจจาก requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] ติดตั้งแพ็กเกจไม่สำเร็จ
    pause
    exit /b 1
)

echo [2/4] กำลังสร้างไอคอนโปรแกรม (agent.ico)...
python -c "from PIL import Image, ImageDraw; imgs=[]; [imgs.append((lambda s: (lambda im: (ImageDraw.Draw(im).rounded_rectangle([0,0,s-1,s-1], radius=max(4,s//5), fill=(30,58,138,255)), ImageDraw.Draw(im).ellipse([s//5,s//5,s-s//5,s-s//5], outline=(251,191,36,255), width=max(2,s//12)), ImageDraw.Draw(im).ellipse([s//2-s//8,s//2-s//8,s//2+s//8,s//2+s//8], fill=(251,191,36,255)), im)[3])(Image.new('RGBA',(s,s),(0,0,0,0))))(sz)) for sz in (256,128,64,48,32,16)]; imgs[0].save('agent.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)], append_images=imgs[1:])"
if errorlevel 1 (
    echo [WARN] สร้างไอคอนไม่สำเร็จ จะ Build โดยใช้ไอคอนเริ่มต้น
    set ICON_OPT=
) else (
    set ICON_OPT=--icon=agent.ico
)

echo [3/4] กำลัง Build RemoteAgent.exe ด้วย PyInstaller (System Tray + UAC Admin)...
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin %ICON_OPT% --name RemoteAgent agent.py
if errorlevel 1 (
    echo [ERROR] PyInstaller Build ไม่สำเร็จ
    pause
    exit /b 1
)

echo [4/4] กำลังคัดลอก RemoteAgent.exe ไปยังโฟลเดอร์หลัก...
copy /y "dist\RemoteAgent.exe" "..\RemoteAgent.exe" >nul
if errorlevel 1 (
    echo [ERROR] คัดลอกไฟล์ RemoteAgent.exe ไม่สำเร็จ
    pause
    exit /b 1
)

echo.
echo [SUCCESS] สร้างไฟล์ RemoteAgent.exe เรียบร้อยแล้ว!
echo ตำแหน่งไฟล์: %~dp0..\RemoteAgent.exe
echo.
pause
