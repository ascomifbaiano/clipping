@echo off
echo ======================================================
echo  Iniciando Servidor Local - Clipping Completo (v2)
echo ======================================================
echo.
echo  Abra o seu navegador no link abaixo:
echo  http://localhost:8000
echo.
echo  Para fechar o servidor, feche esta janela.
echo ======================================================
python -m http.server 8000 --bind 127.0.0.1
pause
