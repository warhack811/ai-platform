@echo off
chcp 65001 >nul
title DeepSeek AI System Starter

echo ╔═══════════════════════════════════════════════════╗
echo ║   DeepSeek AI System - TAM SISTEM BASLATMA       ║
echo ╚═══════════════════════════════════════════════════╝
echo.

rem === 0. ADIM: Ana klasore gec ===
cd /d "D:\AI"

echo [1/7] Ollama servisi baslatiliyor...
tasklist /fi "imagename eq ollama.exe" | find /i "ollama.exe" >nul
if errorlevel 1 (
    echo 🚀 Ollama servisi baslatiliyor...
    start "" "ollama" serve
    timeout /t 5 /nobreak >nul
) else (
    echo ✅ Ollama zaten calisiyor
)

echo [2/7] Ollama kontrol ediliyor...
timeout /t 3 /nobreak >nul
ollama list >nul 2>&1
if errorlevel 1 (
    echo ❌ Ollama hala calismiyor! Manuel baslatma deneyin:
    echo   1. Ollama Desktop uygulamasini acin
    echo   2. Veya komut isteminde: ollama serve
    pause
    exit /b 1
)
echo ✅ Ollama aktif
echo.

echo [3/7] Model kontrol ediliyor (mistral-turkish)...
ollama list | findstr /C:"mistral-turkish" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ 'mistral-turkish' modeli yuklu degil!
    echo Model yukleniyor...
    cd /d "D:\AI\models"
    ollama create mistral-turkish -f Modelfile
    cd /d "D:\AI"
) else (
    echo ✅ Model yuklu
)
echo.

echo [4/7] SearXNG kontrol ediliyor...
curl -s http://localhost:8888 >nul 2>&1
if errorlevel 1 (
    echo ⚠️ SearXNG calismiyor! Baslatiliyor...
    call searxng_setup.bat
) else (
    echo ✅ SearXNG aktif (Port 8888)
)
echo.

echo [5/7] Backend baslatiliyor...
cd /d "D:\AI\backend"
start "" /B python main.py
timeout /t 8 /nobreak >nul
echo ✅ Backend baslatildi (Port 8000)
echo.

echo [6/7] Frontend baslatiliyor...
cd /d "D:\AI\frontend"
start "" /B npm start
timeout /t 5 /nobreak >nul
echo ✅ Frontend baslatildi (Port 3000)
echo.

echo [7/7] Ollama Web UI baslatiliyor...
echo ✅ Ollama Web UI acildi
echo.

echo ╔═══════════════════════════════════════════════════╗
echo ║         TUM SISTEM BASLATILDI! 🚀                ║
echo ╚═══════════════════════════════════════════════════╝
echo.
echo 📊 Admin Panel: http://localhost:3000
echo 🔌 Backend API: http://localhost:8000
echo 🔍 SearXNG: http://localhost:8888
echo 🤖 Ollama API: http://localhost:11434
echo 🌐 Ollama Web: http://localhost:11434 (tarayicida acik)
echo.
echo ✅ CALISAN OZELLIKLER:
echo    - Yerel model sohbeti (mistral-turkish)
echo    - Web arama (SearXNG)
echo    - Dosya yukleme ve indeksleme
echo    - PDF analizi
echo    - Vektor veritabani
echo.
timeout /t 3 /nobreak >nul
echo.
echo 🎯 Sistem hazir! Herhangi bir tusa basarak cikabilirsiniz...
pause
