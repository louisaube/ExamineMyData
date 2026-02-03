import os
import uuid
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pandas as pd

import gl_normalizer as gln
from gl_normalizer import (
    GLLoader,
    GLAnalyzer,
    GLComparator,
    validate_file_extension,
    SecurityError,
    generate_excel_report,
    check_file_size,
)

app = FastAPI(title="GL Normalizer", description="Analyse et normalisation du P&L")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = Path(tempfile.gettempdir()) / "gl_uploads"
RESULTS_DIR = Path(tempfile.gettempdir()) / "gl_results"
UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

CACHE_TTL_SECONDS = 3600  # 1 hour


class AnalysisCache:
    def __init__(self, ttl: int = 3600):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl
    
    def set(self, job_id: str, data: Dict[str, Any]) -> None:
        self._cache[job_id] = {
            "data": data,
            "created_at": time.time()
        }
        self._cleanup()
    
    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        if job_id not in self._cache:
            return None
        entry = self._cache[job_id]
        if time.time() - entry["created_at"] > self._ttl:
            del self._cache[job_id]
            return None
        return entry["data"]
    
    def _cleanup(self) -> None:
        now = time.time()
        expired = [k for k, v in self._cache.items() if now - v["created_at"] > self._ttl]
        for k in expired:
            del self._cache[k]


analysis_cache = AnalysisCache(ttl=CACHE_TTL_SECONDS)


def save_upload(file: UploadFile) -> Path:
    validate_file_extension(file.filename)
    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix
    file_path = UPLOAD_DIR / f"{file_id}{ext}"
    content = file.file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    check_file_size(file_path)
    return file_path


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/analyze")
async def analyze_redirect():
    return RedirectResponse(url="/", status_code=303)


@app.post("/analyze")
async def analyze(
    request: Request,
    file1: UploadFile = File(...),
    file2: Optional[UploadFile] = File(None),
    year1: int = Form(...),
    year2: Optional[int] = Form(None),
):
    job_id = str(uuid.uuid4())
    
    try:
        path1 = save_upload(file1)
        
        loader1 = GLLoader(str(path1))
        df1 = loader1.load()
        
        if file2 and file2.filename:
            path2 = save_upload(file2)
            comparator = GLComparator(str(path1), str(path2))
            comparison = comparator.compare()
            
            analysis_cache.set(job_id, {
                "type": "comparison",
                "comparison": comparison,
                "year1": year1,
                "year2": year2 or year1 - 1,
                "path1": str(path1),
                "path2": str(path2),
            })
        else:
            analyzer = GLAnalyzer(df1, year1)
            result = analyzer.analyze()
            
            analysis_cache.set(job_id, {
                "type": "single",
                "result": result,
                "year": year1,
                "path": str(path1),
                "df": df1,
            })
        
        return RedirectResponse(url=f"/results/{job_id}", status_code=303)
        
    except SecurityError as e:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": f"Erreur de sécurité: {str(e)}"},
            status_code=400,
        )
    except Exception as e:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": f"Erreur: {str(e)}"},
            status_code=400,
        )


@app.get("/results/{job_id}", response_class=HTMLResponse)
async def results(request: Request, job_id: str):
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analyse non trouvée ou expirée")
    
    if data["type"] == "comparison":
        comparison = data["comparison"]
        context = {
            "request": request,
            "job_id": job_id,
            "type": "comparison",
            "year1": data["year1"],
            "year2": data["year2"],
            "variation_brute": comparison.variation_brute,
            "variation_normalisee": comparison.variation_normalisee,
            "ecart": comparison.ecart_normalisation,
            "total_n1": comparison.total_n1,
            "total_n": comparison.total_n,
            "provisions_n1": len(comparison.provisions_n1) if hasattr(comparison, 'provisions_n1') else 0,
            "provisions_n": len(comparison.provisions_n) if hasattr(comparison, 'provisions_n') else 0,
        }
    else:
        result = data["result"]
        context = {
            "request": request,
            "job_id": job_id,
            "type": "single",
            "year": data["year"],
            "run_rate": result.run_rate if hasattr(result, 'run_rate') else None,
            "anomalies": result.anomalies[:20] if hasattr(result, 'anomalies') else [],
            "total_entries": result.total_entries if hasattr(result, 'total_entries') else 0,
            "regularizations": result.regularizations[:10] if hasattr(result, 'regularizations') else [],
        }
    
    return templates.TemplateResponse("results.html", context)


@app.get("/report/{job_id}")
async def download_report(job_id: str):
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analyse non trouvée ou expirée")
    
    report_path = RESULTS_DIR / f"rapport_{job_id}.xlsx"
    
    try:
        if data["type"] == "comparison":
            generate_excel_report(data["comparison"], str(report_path))
        else:
            result = data["result"]
            with pd.ExcelWriter(str(report_path), engine='openpyxl') as writer:
                summary_data = {
                    "Métrique": ["Année", "Total écritures", "Anomalies détectées", "Régularisations détectées"],
                    "Valeur": [
                        data["year"],
                        getattr(result, 'total_entries', 0),
                        len(result.anomalies) if hasattr(result, 'anomalies') else 0,
                        len(result.regularizations) if hasattr(result, 'regularizations') else 0,
                    ]
                }
                if hasattr(result, 'run_rate') and result.run_rate:
                    run_rate = result.run_rate
                    summary_data["Métrique"].extend([
                        "Run rate mensuel",
                        "Total annuel",
                    ])
                    summary_data["Valeur"].extend([
                        getattr(run_rate, 'run_rate_mensuel', 0),
                        getattr(run_rate, 'total_annuel', 0),
                    ])
                pd.DataFrame(summary_data).to_excel(writer, sheet_name="Synthèse", index=False)
                
                if hasattr(result, 'anomalies') and result.anomalies:
                    anomalies_data = []
                    for a in result.anomalies:
                        anomalies_data.append({
                            "Compte": getattr(a, 'compte', ''),
                            "Catégorie": getattr(a.category, 'value', '') if hasattr(a, 'category') and a.category else '',
                            "Score": round(getattr(a, 'score', 0), 2),
                            "Description": getattr(a, 'description', ''),
                        })
                    pd.DataFrame(anomalies_data).to_excel(writer, sheet_name="Anomalies", index=False)
                
                if hasattr(result, 'regularizations') and result.regularizations:
                    reg_data = []
                    for r in result.regularizations:
                        reg_data.append({
                            "Type": getattr(r.type, 'value', '') if hasattr(r, 'type') and r.type else '',
                            "Journal": getattr(r, 'journal', ''),
                            "Compte": getattr(r, 'compte', ''),
                            "Montant": getattr(r, 'montant', 0),
                            "Libellé": getattr(r, 'libelle', ''),
                        })
                    pd.DataFrame(reg_data).to_excel(writer, sheet_name="Régularisations", index=False)
        
        return FileResponse(
            path=str(report_path),
            filename=f"rapport_gl_{job_id[:8]}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur génération rapport: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
