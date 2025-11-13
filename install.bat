@echo off
chcp 65001 >nul
echo ╔═══════════════════════════════════════════════════╗
echo ║   DeepSeek AI System - ULTRA Optimized Kurulum   ║
echo ╚═══════════════════════════════════════════════════╝
echo.

cd /d D:\AI_Platform\Ana_Beyin_FastAPI\code

echo [1/5] Python bağımlılıkları kuruluyor...
cd backend
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Python paketleri kurulamadı!
    pause
    exit /b 1
)
echo ✅ Python paketleri kuruldu
echo.

echo [2/5] Playwright tarayıcıları kuruluyor...
playwright install chromium
if errorlevel 1 (
    echo ❌ Playwright kurulamadı!
    pause
    exit /b 1
)
echo ✅ Playwright kuruldu
echo.

echo [3/5] Frontend bağımlılıkları kuruluyor...
cd ..\frontend
call npm install
if errorlevel 1 (
    echo ❌ npm paketleri kurulamadı!
    pause
    exit /b 1
)
echo ✅ npm paketleri kuruldu
echo.

echo [4/5] Gerekli klasörler oluşturuluyor...
cd ..
if not exist "backend\chroma_db" mkdir backend\chroma_db
if not exist "logs" mkdir logs
echo ✅ Klasörler oluşturuldu
echo.

echo [5/5] Ollama kontrol ediliyor...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Ollama kurulu değil!
    echo Lütfen https://ollama.com/download adresinden kurun
    pause
    exit /b 1
)
echo ✅ Ollama kurulu
echo.

echo Modelfile konumu: D:\AI_Platform\Ana_Beyin_FastAPI\models\llama\Modelfile
echo.

echo ╔═══════════════════════════════════════════════════╗
echo ║           KURULUM TAMAMLANDI! 🎉                 ║
echo ╚═══════════════════════════════════════════════════╝
echo.
echo ŞİMDİ YAPMANIZ GEREKENLER:
echo 1. Modelfile'ı yükleyin (talimatlar aşağıda)
echo 2. start.bat çalıştırın
echo.
echo MODELFİLE YÜKLEME:
echo cd D:\AI_Platform\Ana_Beyin_FastAPI\models\llama
echo ollama create deepseek-uncensored -f Modelfile
echo.
pause