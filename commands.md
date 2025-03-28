# Commands

## Admite varias solicitudes y las divide en varios workers de uvicorn
```bash
uvicorn main:app --reload --workers 4 --host 0.0.0.0 --port 8000
```

## Administrar dependencias
```bash
pip install -r requirements.txt
```

## virtualenv
```bash
python -m venv .venv
```

## Activar virtualenv
```bash
source .venv/bin/activate

