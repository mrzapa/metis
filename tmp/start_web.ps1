Set-Location "c:\Users\samwe\Documents\metis\apps\metis-web"
$env:NEXT_PUBLIC_METIS_API_BASE = "http://127.0.0.1:8000"
node "c:\Users\samwe\Documents\metis\apps\metis-web\node_modules\next\dist\bin\next" dev --hostname 127.0.0.1 --port 3000
