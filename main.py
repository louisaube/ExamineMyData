import os
import uuid
import tempfile
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
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
from gl_normalizer.secrets_manager import (
    get_secrets_manager,
    SecretType,
    KNOWN_SECRETS,
)
from gl_normalizer.autonomous_drilldown import (
    AutonomousAnalyzer,
    run_autonomous_analysis,
)

app = FastAPI(title="GL Normalizer", description="Analyse et normalisation du P&L")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = Path(tempfile.gettempdir()) / "gl_uploads"
RESULTS_DIR = Path(tempfile.gettempdir()) / "gl_results"
UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

CACHE_TTL_SECONDS = 3600  # 1 hour


class JobStatus(Enum):
    PENDING = "pending"
    LOADING = "loading"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    ERROR = "error"
    NEEDS_MAPPING = "needs_mapping"


class AnalysisCache:
    def __init__(self, ttl: int = 3600):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def set(self, job_id: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._cache[job_id] = {
                "data": data,
                "created_at": time.time()
            }
            self._cleanup()

    def update_status(self, job_id: str, status: JobStatus, message: str = "", progress: int = 0) -> None:
        with self._lock:
            if job_id in self._cache:
                self._cache[job_id]["data"]["status"] = status.value
                self._cache[job_id]["data"]["message"] = message
                self._cache[job_id]["data"]["progress"] = progress

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
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


def run_analysis_background(job_id: str, path1: Path, year1: int, path2: Optional[Path] = None, year2: Optional[int] = None):
    """Exécute l'analyse en arrière-plan"""
    try:
        # Phase 1: Chargement
        analysis_cache.update_status(job_id, JobStatus.LOADING, "Chargement du fichier...", 10)
        loader1 = GLLoader(str(path1))
        df1 = loader1.load()
        row_count = len(df1)

        analysis_cache.update_status(job_id, JobStatus.LOADING, f"Fichier chargé: {row_count:,} écritures", 30)

        if path2:
            # Comparaison N vs N-1
            analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Comparaison des exercices...", 50)
            comparator = GLComparator(str(path1), str(path2))
            comparison = comparator.compare()

            analysis_cache.set(job_id, {
                "type": "comparison",
                "status": JobStatus.COMPLETED.value,
                "comparison": comparison,
                "year1": year1,
                "year2": year2 or year1 - 1,
                "path1": str(path1),
                "path2": str(path2),
                "message": "Analyse terminée",
                "progress": 100,
            })
        else:
            # Analyse simple
            analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Profilage des données...", 40)
            analyzer = GLAnalyzer(df1, year1)

            analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Détection des anomalies...", 60)
            result = analyzer.analyze()

            analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Calcul du run rate...", 80)

            # STORY-030: Analyse autonome IA (drill-down proactif)
            analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Analyse proactive IA...", 90)
            try:
                autonomous_analysis = run_autonomous_analysis(df1, auto_execute=False)
            except Exception:
                autonomous_analysis = None

            analysis_cache.set(job_id, {
                "type": "single",
                "status": JobStatus.COMPLETED.value,
                "result": result,
                "year": year1,
                "path": str(path1),
                "df": df1,
                "autonomous_analysis": autonomous_analysis,
                "message": "Analyse terminée",
                "progress": 100,
            })

    except Exception as e:
        analysis_cache.set(job_id, {
            "type": "error",
            "status": JobStatus.ERROR.value,
            "error": str(e),
            "message": f"Erreur: {str(e)}",
            "progress": 0,
        })


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/analyze")
async def analyze_redirect():
    return RedirectResponse(url="/", status_code=303)


@app.post("/analyze")
async def analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    file1: UploadFile = File(...),
    file2: Optional[UploadFile] = File(None),
    year1: int = Form(...),
    year2: Optional[int] = Form(None),
):
    job_id = str(uuid.uuid4())

    try:
        path1 = save_upload(file1)
        path2 = None

        if file2 and file2.filename:
            path2 = save_upload(file2)

        # Initialiser le job en attente
        analysis_cache.set(job_id, {
            "type": "pending",
            "status": JobStatus.PENDING.value,
            "message": "Démarrage de l'analyse...",
            "progress": 0,
            "year": year1,
        })

        # Lancer l'analyse en arrière-plan
        background_tasks.add_task(
            run_analysis_background,
            job_id,
            path1,
            year1,
            path2,
            year2
        )

        # Rediriger vers la page de chargement
        return RedirectResponse(url=f"/loading/{job_id}", status_code=303)

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


@app.get("/loading/{job_id}", response_class=HTMLResponse)
async def loading_page(request: Request, job_id: str):
    """Page de chargement avec polling"""
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    return templates.TemplateResponse("loading.html", {
        "request": request,
        "job_id": job_id,
        "year": data.get("year", ""),
    })


@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    """API pour vérifier le statut d'un job"""
    data = analysis_cache.get(job_id)
    if data is None:
        return JSONResponse({"status": "not_found"}, status_code=404)

    return JSONResponse({
        "status": data.get("status", "unknown"),
        "message": data.get("message", ""),
        "progress": data.get("progress", 0),
        "ready": data.get("status") == JobStatus.COMPLETED.value,
        "error": data.get("status") == JobStatus.ERROR.value,
    })


@app.get("/results/{job_id}", response_class=HTMLResponse)
async def results(request: Request, job_id: str):
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analyse non trouvée ou expirée")

    # Si encore en cours, rediriger vers la page de chargement
    if data.get("status") in [JobStatus.PENDING.value, JobStatus.LOADING.value, JobStatus.ANALYZING.value]:
        return RedirectResponse(url=f"/loading/{job_id}", status_code=303)

    # Si erreur, afficher l'erreur
    if data.get("status") == JobStatus.ERROR.value:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": data.get("error", "Erreur inconnue")},
            status_code=400,
        )

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
            "total_entries": result.row_count if hasattr(result, 'row_count') else 0,
            "account_count": result.account_count if hasattr(result, 'account_count') else 0,
            "data_quality": result.data_quality if hasattr(result, 'data_quality') else "unknown",
            "overall_risk_score": result.overall_risk_score if hasattr(result, 'overall_risk_score') else 0,
            "regularizations": result.regularization_result.regularizations[:10] if hasattr(result, 'regularization_result') and result.regularization_result else [],
            "summary": result.summary if hasattr(result, 'summary') else {},
            "warnings": result.warnings[:5] if hasattr(result, 'warnings') else [],
            "recommendations": result.recommendations[:5] if hasattr(result, 'recommendations') else [],
            # STORY-030: Analyse autonome IA
            "autonomous_analysis": data.get("autonomous_analysis"),
        }

    return templates.TemplateResponse("results.html", context)


@app.get("/report/{job_id}")
async def download_report(job_id: str):
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analyse non trouvée ou expirée")

    if data.get("status") != JobStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Analyse pas encore terminée")

    report_path = RESULTS_DIR / f"rapport_{job_id}.xlsx"

    try:
        if data["type"] == "comparison":
            generate_excel_report(data["comparison"], str(report_path))
        else:
            result = data["result"]
            with pd.ExcelWriter(str(report_path), engine='openpyxl') as writer:
                # Synthèse
                summary_data = {
                    "Métrique": [
                        "Année",
                        "Total écritures",
                        "Nombre de comptes",
                        "Qualité des données",
                        "Score de risque",
                        "Anomalies détectées",
                        "Régularisations détectées",
                    ],
                    "Valeur": [
                        data["year"],
                        getattr(result, 'row_count', 0),
                        getattr(result, 'account_count', 0),
                        getattr(result, 'data_quality', 'unknown'),
                        f"{getattr(result, 'overall_risk_score', 0):.0%}",
                        len(result.anomalies) if hasattr(result, 'anomalies') else 0,
                        len(result.regularization_result.regularizations) if hasattr(result, 'regularization_result') and result.regularization_result else 0,
                    ]
                }
                if hasattr(result, 'run_rate') and result.run_rate:
                    run_rate = result.run_rate
                    summary_data["Métrique"].extend([
                        "Run rate mensuel",
                        "Charges brutes annuelles",
                        "Produits bruts annuels",
                    ])
                    summary_data["Valeur"].extend([
                        f"{getattr(run_rate, 'run_rate_mensuel', 0):,.0f} €",
                        f"{getattr(run_rate, 'charges_brutes', 0):,.0f} €",
                        f"{getattr(run_rate, 'produits_bruts', 0):,.0f} €",
                    ])
                pd.DataFrame(summary_data).to_excel(writer, sheet_name="Synthèse", index=False)

                # Anomalies
                if hasattr(result, 'anomalies') and result.anomalies:
                    anomalies_data = []
                    for a in result.anomalies:
                        anomalies_data.append({
                            "Compte": getattr(a, 'compte', ''),
                            "Type": getattr(a, 'anomaly_type', ''),
                            "Catégorie": getattr(a.category, 'value', '') if hasattr(a, 'category') and a.category else '',
                            "Sévérité": getattr(a, 'severity', ''),
                            "Montant": getattr(a, 'montant', 0),
                            "Détails": getattr(a, 'details', ''),
                            "Contexte PCG": getattr(a, 'pcg_context', ''),
                            "Attendu": "Oui" if getattr(a, 'is_expected', False) else "Non",
                            "Recommandation": getattr(a, 'recommendation', ''),
                        })
                    pd.DataFrame(anomalies_data).to_excel(writer, sheet_name="Anomalies", index=False)

                # Régularisations
                if hasattr(result, 'regularization_result') and result.regularization_result:
                    reg_data = []
                    for r in result.regularization_result.regularizations:
                        reg_data.append({
                            "Type": getattr(r.type, 'value', '') if hasattr(r, 'type') and r.type else '',
                            "Journal": getattr(r, 'journal', ''),
                            "Compte": getattr(r, 'compte', ''),
                            "Libellé compte": getattr(r, 'libelle_compte', ''),
                            "Libellé écriture": getattr(r, 'libelle', ''),
                            "Montant": getattr(r, 'montant', 0),
                            "Date": getattr(r, 'date', ''),
                            "Confiance": f"{getattr(r, 'confidence', 0):.0%}",
                            "Contexte PCG": getattr(r, 'pcg_context', ''),
                        })
                    pd.DataFrame(reg_data).to_excel(writer, sheet_name="Régularisations", index=False)

                # Warnings et recommandations
                if hasattr(result, 'warnings') or hasattr(result, 'recommendations'):
                    notes_data = []
                    for w in getattr(result, 'warnings', []):
                        notes_data.append({"Type": "Attention", "Message": w})
                    for r in getattr(result, 'recommendations', []):
                        notes_data.append({"Type": "Recommandation", "Message": r})
                    if notes_data:
                        pd.DataFrame(notes_data).to_excel(writer, sheet_name="Notes", index=False)

        return FileResponse(
            path=str(report_path),
            filename=f"rapport_gl_{job_id[:8]}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur génération rapport: {str(e)}")


# =====================================================
# SETTINGS - Configuration des tokens API (STORY-027)
# =====================================================

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Page de configuration des tokens API"""
    secrets_mgr = get_secrets_manager()

    # Construire la liste des providers avec leur statut
    providers = []
    for secret_type, config in KNOWN_SECRETS.items():
        value = secrets_mgr.get_secret(secret_type, prompt_if_missing=False)
        configured = value is not None

        providers.append({
            "type": secret_type.value,
            "name": config.name,
            "description": config.description,
            "configured": configured,
            "masked": secrets_mgr.mask_secret(value) if configured else "",
            "placeholder": f"Commence par {config.required_prefix}..." if config.required_prefix else "Entrez votre token",
            "hint": f"Variable env: {config.env_var}",
        })

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "providers": providers,
        "ai_ready": secrets_mgr.is_ai_ready(),
    })


@app.get("/api/settings/status")
async def get_settings_status():
    """Retourne le statut des tokens (sans les valeurs)"""
    secrets_mgr = get_secrets_manager()
    status = secrets_mgr.get_status()

    return JSONResponse({
        "ai_ready": secrets_mgr.is_ai_ready(),
        "providers": status,
    })


@app.post("/api/settings/token")
async def save_token(request: Request):
    """Sauvegarde un token API"""
    try:
        data = await request.json()
        token_type = data.get("type")
        token_value = data.get("token")

        if not token_type or not token_value:
            return JSONResponse({"success": False, "error": "Type et token requis"}, status_code=400)

        # Trouver le SecretType correspondant
        secret_type = None
        for st in SecretType:
            if st.value == token_type:
                secret_type = st
                break

        if secret_type is None:
            return JSONResponse({"success": False, "error": "Type de token inconnu"}, status_code=400)

        secrets_mgr = get_secrets_manager()

        # Valider le format
        validation = secrets_mgr.validate_secret(token_value, secret_type)
        if not validation.is_valid:
            return JSONResponse({
                "success": False,
                "error": f"Format invalide: {', '.join(validation.errors)}"
            }, status_code=400)

        # Sauvegarder
        secrets_mgr.set_secret(secret_type, token_value)

        return JSONResponse({"success": True, "message": "Token configuré"})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.delete("/api/settings/token/{token_type}")
async def delete_token(token_type: str):
    """Supprime un token API"""
    try:
        secret_type = None
        for st in SecretType:
            if st.value == token_type:
                secret_type = st
                break

        if secret_type is None:
            return JSONResponse({"success": False, "error": "Type de token inconnu"}, status_code=400)

        secrets_mgr = get_secrets_manager()
        secrets_mgr.delete_secret(secret_type)

        return JSONResponse({"success": True, "message": "Token supprimé"})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/settings/test/{token_type}")
async def test_token(token_type: str, request: Request):
    """Teste la validité d'un token"""
    try:
        data = await request.json()
        token_value = data.get("token")

        if not token_value:
            return JSONResponse({"valid": False, "error": "Token requis"}, status_code=400)

        secret_type = None
        for st in SecretType:
            if st.value == token_type:
                secret_type = st
                break

        if secret_type is None:
            return JSONResponse({"valid": False, "error": "Type de token inconnu"}, status_code=400)

        secrets_mgr = get_secrets_manager()
        validation = secrets_mgr.validate_secret(token_value, secret_type)

        return JSONResponse({
            "valid": validation.is_valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
        })

    except Exception as e:
        return JSONResponse({"valid": False, "error": str(e)}, status_code=500)


# =====================================================
# DRILLDOWN API - Analyse autonome IA (STORY-030)
# =====================================================

@app.post("/api/drilldown/{job_id}/{question_id}")
async def execute_drilldown(job_id: str, question_id: str):
    """Exécute une analyse drill-down spécifique"""
    try:
        data = analysis_cache.get(job_id)
        if data is None:
            return JSONResponse({"success": False, "error": "Job non trouvé"}, status_code=404)

        if data.get("status") != JobStatus.COMPLETED.value:
            return JSONResponse({"success": False, "error": "Analyse pas encore terminée"}, status_code=400)

        df = data.get("df")
        if df is None:
            return JSONResponse({"success": False, "error": "Données non disponibles"}, status_code=400)

        autonomous_data = data.get("autonomous_analysis")
        if not autonomous_data or not autonomous_data.get("questions"):
            return JSONResponse({"success": False, "error": "Pas de questions disponibles"}, status_code=400)

        # Trouver la question
        question = None
        for q in autonomous_data["questions"]:
            if q["id"] == question_id:
                question = q
                break

        if question is None:
            return JSONResponse({"success": False, "error": "Question non trouvée"}, status_code=404)

        # Recréer l'analyzer et exécuter
        analyzer = AutonomousAnalyzer(df)
        analyzer.patterns = []  # On a juste besoin d'exécuter

        # Reconstruire la question object
        from gl_normalizer.autonomous_drilldown import Question, QuestionType, DrilldownExecutor
        q_obj = Question(
            question_id=question["id"],
            question_type=QuestionType(question["type"]),
            text=question["text"],
            pattern_ref=question.get("pattern_ref"),
            parameters=question.get("parameters", {}),
            priority=question.get("priority", 5)
        )

        executor = DrilldownExecutor(df)
        result = executor.execute(q_obj)

        # Ajouter au cache pour affichage futur
        if "executed_results" not in autonomous_data:
            autonomous_data["executed_results"] = []
        autonomous_data["executed_results"].append(result.to_dict())

        return JSONResponse(result.to_dict())

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# =====================================================
# COLUMN MAPPING - Mapping manuel des colonnes (STORY-031)
# =====================================================

@app.get("/mapping/{job_id}", response_class=HTMLResponse)
async def mapping_page(request: Request, job_id: str):
    """Page de mapping manuel des colonnes"""
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job non trouve")

    # Verifier qu'on a bien besoin du mapping
    if data.get("status") not in [JobStatus.NEEDS_MAPPING.value, "needs_mapping"]:
        # Rediriger vers la page appropriee
        if data.get("status") == JobStatus.COMPLETED.value:
            return RedirectResponse(url=f"/results/{job_id}", status_code=303)
        return RedirectResponse(url=f"/loading/{job_id}", status_code=303)

    return templates.TemplateResponse("mapping.html", {
        "request": request,
        "job_id": job_id,
        "filename": data.get("filename", "Fichier inconnu"),
        "columns": data.get("columns", []),
        "year": data.get("year", 2024),
        "preview_data": data.get("preview_data", []),
    })


@app.post("/mapping/{job_id}")
async def submit_mapping(
    request: Request,
    background_tasks: BackgroundTasks,
    job_id: str,
    compte_column: str = Form(...),
    date_column: str = Form(...),
    montant_column: str = Form(...),
    libelle_column: str = Form(...),
    journal_column: Optional[str] = Form(None),
    save_mapping: Optional[str] = Form(None),
    year: int = Form(...),
):
    """Soumet le mapping des colonnes et lance l'analyse"""
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job non trouve")

    try:
        # Construire le mapping
        column_mapping = {
            "compte": compte_column,
            "date": date_column,
            "montant": montant_column,
            "libelle": libelle_column,
        }
        if journal_column:
            column_mapping["journal"] = journal_column

        # Mettre a jour le cache avec le mapping
        path = Path(data.get("path", ""))
        if not path.exists():
            return templates.TemplateResponse("mapping.html", {
                "request": request,
                "job_id": job_id,
                "filename": data.get("filename", ""),
                "columns": data.get("columns", []),
                "year": year,
                "error": "Fichier non trouve. Veuillez recharger le fichier.",
            })

        # Reinitialiser le job
        analysis_cache.set(job_id, {
            "type": "pending",
            "status": JobStatus.PENDING.value,
            "message": "Demarrage de l'analyse avec mapping...",
            "progress": 0,
            "year": year,
            "column_mapping": column_mapping,
            "path": str(path),
        })

        # Lancer l'analyse avec le mapping
        background_tasks.add_task(
            run_analysis_with_mapping,
            job_id,
            path,
            year,
            column_mapping,
        )

        return RedirectResponse(url=f"/loading/{job_id}", status_code=303)

    except Exception as e:
        return templates.TemplateResponse("mapping.html", {
            "request": request,
            "job_id": job_id,
            "filename": data.get("filename", ""),
            "columns": data.get("columns", []),
            "year": year,
            "error": f"Erreur: {str(e)}",
        })


@app.get("/api/preview/{job_id}")
async def get_preview_data(
    job_id: str,
    compte: str,
    date: str,
    montant: str,
    libelle: str,
    journal: Optional[str] = None,
):
    """Retourne un apercu des donnees avec le mapping specifie"""
    data = analysis_cache.get(job_id)
    if data is None:
        return JSONResponse({"success": False, "error": "Job non trouve"}, status_code=404)

    try:
        path = Path(data.get("path", ""))
        if not path.exists():
            return JSONResponse({"success": False, "error": "Fichier non trouve"}, status_code=404)

        # Lire les 5 premieres lignes
        df = pd.read_excel(str(path), nrows=5)

        # Construire l'apercu avec le mapping
        preview = []
        for _, row in df.iterrows():
            preview.append({
                "compte": str(row.get(compte, "-")) if compte in df.columns else "-",
                "date": str(row.get(date, "-")) if date in df.columns else "-",
                "montant": str(row.get(montant, "-")) if montant in df.columns else "-",
                "libelle": str(row.get(libelle, "-")) if libelle in df.columns else "-",
                "journal": str(row.get(journal, "-")) if journal and journal in df.columns else "-",
            })

        return JSONResponse({"success": True, "preview": preview})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


def run_analysis_with_mapping(job_id: str, path: Path, year: int, column_mapping: dict):
    """Execute l'analyse avec un mapping de colonnes personnalise"""
    try:
        # Phase 1: Chargement avec mapping
        analysis_cache.update_status(job_id, JobStatus.LOADING, "Chargement du fichier avec mapping...", 10)

        loader = GLLoader(str(path), custom_mapping=column_mapping)
        df = loader.load()
        row_count = len(df)

        analysis_cache.update_status(job_id, JobStatus.LOADING, f"Fichier charge: {row_count:,} ecritures", 30)

        # Phase 2: Analyse
        analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Profilage des donnees...", 40)
        analyzer = GLAnalyzer(df, year)

        analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Detection des anomalies...", 60)
        result = analyzer.analyze()

        analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Calcul du run rate...", 80)

        # Analyse autonome IA
        analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Analyse proactive IA...", 90)
        try:
            autonomous_analysis = run_autonomous_analysis(df, auto_execute=False)
        except Exception:
            autonomous_analysis = None

        analysis_cache.set(job_id, {
            "type": "single",
            "status": JobStatus.COMPLETED.value,
            "result": result,
            "year": year,
            "path": str(path),
            "df": df,
            "column_mapping": column_mapping,
            "autonomous_analysis": autonomous_analysis,
            "message": "Analyse terminee",
            "progress": 100,
        })

    except Exception as e:
        analysis_cache.set(job_id, {
            "type": "error",
            "status": JobStatus.ERROR.value,
            "error": str(e),
            "message": f"Erreur: {str(e)}",
            "progress": 0,
        })


@app.get("/api/drilldown/{job_id}")
async def get_drilldown_data(job_id: str):
    """Récupère les données de l'analyse autonome"""
    try:
        data = analysis_cache.get(job_id)
        if data is None:
            return JSONResponse({"success": False, "error": "Job non trouvé"}, status_code=404)

        autonomous_data = data.get("autonomous_analysis")
        if not autonomous_data:
            return JSONResponse({
                "success": True,
                "patterns": [],
                "questions": [],
                "results": [],
                "summary": {"pattern_count": 0, "question_count": 0}
            })

        return JSONResponse({
            "success": True,
            **autonomous_data
        })

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
