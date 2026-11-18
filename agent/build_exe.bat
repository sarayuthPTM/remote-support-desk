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

echo [1/5] กำลังติดตั้ง/ตรวจสอบแพ็กเกจจาก requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] ติดตั้งแพ็กเกจไม่สำเร็จ
    pause
    exit /b 1
)

echo [2/5] กำลังสร้างไอคอนและข้อมูลเวอร์ชัน (agent.ico + version_info.txt)...
python -c "from PIL import Image, ImageDraw; imgs=[]; [imgs.append((lambda s: (lambda im: (ImageDraw.Draw(im).rounded_rectangle([0,0,s-1,s-1], radius=max(4,s//5), fill=(30,58,138,255)), ImageDraw.Draw(im).ellipse([s//5,s//5,s-s//5,s-s//5], outline=(251,191,36,255), width=max(2,s//12)), ImageDraw.Draw(im).ellipse([s//2-s//8,s//2-s//8,s//2+s//8,s//2+s//8], fill=(251,191,36,255)), im)[3])(Image.new('RGBA',(s,s),(0,0,0,0))))(sz)) for sz in (256,128,64,48,32,16)]; imgs[0].save('agent.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)], append_images=imgs[1:])"
if errorlevel 1 (
    echo [WARN] สร้างไอคอนไม่สำเร็จ จะ Build โดยใช้ไอคอนเริ่มต้น
    set ICON_OPT=
) else (
    set ICON_OPT=--icon=agent.ico
)

python -c "open('version_info.txt','w',encoding='utf-8').write('''VSVersionInfo(\n  ffi=FixedFileInfo(\n    filevers=(2, 5, 0, 0),\n    prodvers=(2, 5, 0, 0),\n    mask=0x3f,\n    flags=0x0,\n    OS=0x40004,\n    fileType=0x1,\n    subtype=0x0,\n    date=(0, 0)\n  ),\n  kids=[\n    StringFileInfo([StringTable('040904B0', [\n      StringStruct('CompanyName', 'AnySupport Web'),\n      StringStruct('FileDescription', 'AnySupport Remote Support Agent'),\n      StringStruct('FileVersion', '2.5.0.0'),\n      StringStruct('InternalName', 'RemoteAgent'),\n      StringStruct('OriginalFilename', 'RemoteAgent.exe'),\n      StringStruct('ProductName', 'AnySupport Web Remote Desk'),\n      StringStruct('ProductVersion', '2.5.0.0')\n    ])]),\n    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n  ]\n)''')"

echo [3/5] กำลัง Build RemoteAgent.exe ด้วย PyInstaller (ขนาดกระชับ + System Tray + UAC Admin)...
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin %ICON_OPT% --version-file=version_info.txt --exclude-module numpy --exclude-module pygame --exclude-module matplotlib --exclude-module pandas --exclude-module scipy --exclude-module cv2 --exclude-module onnxruntime --name RemoteAgent agent.py
if errorlevel 1 (
    echo [ERROR] PyInstaller Build ไม่สำเร็จ
    pause
    exit /b 1
)

echo [4/5] กำลังคัดลอก RemoteAgent.exe และสร้าง RemoteAgent.zip...
copy /y "dist\RemoteAgent.exe" "..\RemoteAgent.exe" >nul
if errorlevel 1 (
    echo [ERROR] คัดลอกไฟล์ RemoteAgent.exe ไม่สำเร็จ
    pause
    exit /b 1
)
powershell -NoProfile -Command "Compress-Archive -Force -Path '..\RemoteAgent.exe' -DestinationPath '..\RemoteAgent.zip'"

echo [5/5] ทำความสะอาดไฟล์ชั่วคราว...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q RemoteAgent.spec agent.ico version_info.txt 2>nul

echo.
echo [SUCCESS] สร้างไฟล์ RemoteAgent.exe และ RemoteAgent.zip เรียบร้อยแล้ว!
echo ตำแหน่งไฟล์: %~dp0..\RemoteAgent.exe
echo.
pause
