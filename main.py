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

# GL Crystal - Analyse topologique v2.0
from gl_crystal import SemanticClassifier, UniversSemantique
from gl_crystal.normalizer import GLSchema, GLEntry, GLEnricher
from gl_crystal.layer1_crystallinity import ICCCalculator

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


def run_crystal_analysis(df: pd.DataFrame, year: int) -> Optional[Dict[str, Any]]:
    """
    Exécute l'analyse GL Crystal (topologique) sur le DataFrame.
    Version ultra-optimisée: Polars (x5-9) + Numba JIT (x170) pour les calculs.

    Returns:
        Dictionnaire avec les résultats Crystal ou None si erreur
    """
    try:
        from datetime import date, datetime
        import polars as pl

        if len(df) < 10:
            return None

        # Conversion pandas → Polars pour traitement rapide
        work_df = None
        try:
            pl_df = pl.from_pandas(df)

            # Détection des colonnes (case-insensitive)
            cols = {c.lower(): c for c in pl_df.columns}

            compte_name = cols.get('compte', None)
            if compte_name is None:
                raise ValueError("Colonne compte non trouvée")

            # Sélection et transformation avec Polars (parallélisé)
            expressions = [
                pl.col(compte_name).cast(pl.Utf8).str.slice(0, 10).alias('compte'),
            ]

            date_name = cols.get('date', None)
            if date_name:
                expressions.append(
                    pl.col(date_name).cast(pl.Date, strict=False).alias('date_parsed')
                )

            journal_name = cols.get('journal', None)
            if journal_name:
                expressions.append(pl.col(journal_name).cast(pl.Utf8).str.slice(0, 10).alias('journal'))

            libelle_name = cols.get('libelle', None)
            if libelle_name:
                expressions.append(pl.col(libelle_name).cast(pl.Utf8).str.slice(0, 200).alias('libelle'))

            piece_name = cols.get('piece', None)
            if piece_name:
                expressions.append(pl.col(piece_name).cast(pl.Utf8).str.slice(0, 50).alias('piece'))

            debit_name = cols.get('debit', None)
            if debit_name:
                expressions.append(pl.col(debit_name).cast(pl.Float64, strict=False).fill_null(0.0).alias('debit'))

            credit_name = cols.get('credit', None)
            if credit_name:
                expressions.append(pl.col(credit_name).cast(pl.Float64, strict=False).fill_null(0.0).alias('credit'))

            analytique_name = cols.get('analytique', None)
            if analytique_name:
                expressions.append(pl.col(analytique_name).cast(pl.Utf8).alias('analytique'))

            pl_work = pl_df.select(expressions).filter(pl.col('compte').str.len_chars() > 0)

            if len(pl_work) < 10:
                return None

            # Conversion vers pandas pour créer les GLEntry
            work_df = pl_work.to_pandas()
            default_date = date(year, 1, 1)

            # Gestion des colonnes manquantes et conversion en types corrects
            if 'date_parsed' in work_df.columns:
                work_df['date'] = work_df['date_parsed'].apply(lambda x: x if pd.notna(x) else default_date)
            else:
                work_df['date'] = default_date

            # Colonnes texte : conversion explicite en string (évite les float NaN)
            if 'journal' in work_df.columns:
                work_df['journal'] = work_df['journal'].fillna('OD').astype(str).replace('nan', 'OD').replace('None', 'OD')
            else:
                work_df['journal'] = 'OD'

            if 'libelle' in work_df.columns:
                work_df['libelle'] = work_df['libelle'].fillna('').astype(str).replace('nan', '').replace('None', '')
            else:
                work_df['libelle'] = ''

            if 'piece' in work_df.columns:
                work_df['piece'] = work_df['piece'].fillna('').astype(str).replace('nan', '').replace('None', '')
            else:
                work_df['piece'] = ''

            if 'debit' not in work_df.columns:
                work_df['debit'] = 0.0
            if 'credit' not in work_df.columns:
                work_df['credit'] = 0.0

            if 'analytique' in work_df.columns:
                work_df['analytique'] = work_df['analytique'].apply(lambda x: str(x) if pd.notna(x) and x != '' else None)
            else:
                work_df['analytique'] = None

        except Exception:
            # Fallback vers pandas si Polars échoue
            work_df = None

        if work_df is None:
            # Fallback pandas si Polars échoue
            def get_col(dataframe, names):
                for name in names:
                    if name in dataframe.columns:
                        return dataframe[name]
                return None

            compte_col = get_col(df, ['Compte', 'compte', 'COMPTE'])
            if compte_col is None:
                return None

            work_df = pd.DataFrame()
            work_df['compte'] = compte_col.astype(str).str[:10]

            date_col = get_col(df, ['Date', 'date', 'DATE'])
            default_date = date(year, 1, 1)
            if date_col is not None:
                parsed_dates = pd.to_datetime(date_col, errors='coerce')
                work_df['date'] = parsed_dates.dt.date.fillna(default_date)
            else:
                work_df['date'] = default_date

            journal_col = get_col(df, ['Journal', 'journal', 'JOURNAL'])
            if journal_col is not None:
                work_df['journal'] = journal_col.fillna('OD').astype(str).str[:10].replace('nan', 'OD').replace('None', 'OD')
            else:
                work_df['journal'] = 'OD'

            libelle_col = get_col(df, ['Libelle', 'libelle', 'LIBELLE'])
            if libelle_col is not None:
                work_df['libelle'] = libelle_col.fillna('').astype(str).str[:200].replace('nan', '').replace('None', '')
            else:
                work_df['libelle'] = ''

            piece_col = get_col(df, ['Piece', 'piece', 'PIECE'])
            if piece_col is not None:
                work_df['piece'] = piece_col.fillna('').astype(str).str[:50].replace('nan', '').replace('None', '')
            else:
                work_df['piece'] = ''

            debit_col = get_col(df, ['Debit', 'debit', 'DEBIT'])
            work_df['debit'] = pd.to_numeric(debit_col, errors='coerce').fillna(0) if debit_col is not None else 0.0

            credit_col = get_col(df, ['Credit', 'credit', 'CREDIT'])
            work_df['credit'] = pd.to_numeric(credit_col, errors='coerce').fillna(0) if credit_col is not None else 0.0

            analytique_col = get_col(df, ['Analytique', 'analytique', 'ANALYTIQUE'])
            if analytique_col is not None:
                work_df['analytique'] = analytique_col.apply(lambda x: str(x) if pd.notna(x) and x != '' else None)
            else:
                work_df['analytique'] = None

            valid_mask = work_df['compte'].str.len() > 0
            work_df = work_df[valid_mask].reset_index(drop=True)

            if len(work_df) < 10:
                return None

        # Création des GLEntry avec itertuples (x13 plus rapide que iterrows)
        entries = []
        for row in work_df.itertuples(index=True):
            analytique_val = str(row.analytique) if pd.notna(row.analytique) and row.analytique else None
            entry = GLEntry(
                date_ecriture=row.date,
                piece=getattr(row, 'piece', '') or '',
                journal_code=getattr(row, 'journal', 'OD') or 'OD',
                journal_libelle='',
                compte_general=row.compte or '',
                compte_libelle='',
                compte_auxiliaire=None,
                libelle_ecriture=getattr(row, 'libelle', '') or '',
                debit=getattr(row, 'debit', 0.0),
                credit=getattr(row, 'credit', 0.0),
                analytique=analytique_val,
                ligne_id=row.Index,
            )
            entries.append(entry)

        if len(entries) < 10:
            return None

        schema = GLSchema(
            source_file='uploaded_file',
            source_format='generic',
            date_extraction=date.today(),
            entries=entries,
        )
        schema.compute_stats()

        # Enrichissement
        enricher = GLEnricher()
        enriched = enricher.enrich(schema)

        # Classification sémantique (Layer 0)
        classifier = SemanticClassifier(min_ecritures=3)
        classification = classifier.classify(enriched)

        # Calcul ICC avec classification (Layer 1)
        calculator = ICCCalculator(use_univers_weights=True)
        icc_results = calculator.compute(enriched, classification=classification)

        # Prépare les résultats pour l'affichage
        stats = icc_results.get_stats()

        # Top alertes (surprises)
        top_surprises = []
        for score in icc_results.top_surprises(n=10):
            top_surprises.append({
                'compte': score.compte,
                'analytique': score.analytique or '-',
                'icc': score.icc,
                'univers': score.univers.value if score.univers else 'NON_CLASSE',
                'surprise': score.surprise or 0,
                'classification': score.classification,
                'n_ecritures': score.n_ecritures,
            })

        # Répartition par univers
        univers_distribution = {}
        for univers in UniversSemantique:
            scores = icc_results.get_by_univers(univers)
            if scores:
                univers_distribution[univers.value] = {
                    'count': len(scores),
                    'pct': len(scores) / len(icc_results.scores) * 100 if icc_results.scores else 0,
                }

        # Classification summary
        classification_summary = classification.summary.to_dict() if classification.summary else {}

        return {
            'n_couples': stats.get('n_couples', 0),
            'icc_mean': stats.get('icc_mean', 0),
            'icc_std': stats.get('icc_std', 0),
            'n_cristallins': stats.get('n_cristallins', 0),
            'n_amorphes': stats.get('n_amorphes', 0),
            'n_alertes_surprise': stats.get('n_alertes_surprise', 0),
            'top_surprises': top_surprises,
            'univers_distribution': univers_distribution,
            'classification_summary': classification_summary,
            'has_classification': True,
        }

    except Exception as e:
        # Log error but don't fail the main analysis
        print(f"Crystal analysis error: {e}")
        return None


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
            analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Analyse proactive IA...", 85)
            try:
                autonomous_analysis = run_autonomous_analysis(df1, auto_execute=False)
            except Exception:
                autonomous_analysis = None

            # GL Crystal - Analyse topologique v2.0
            analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Analyse topologique Crystal...", 95)
            try:
                crystal_analysis = run_crystal_analysis(df1, year1)
            except Exception:
                crystal_analysis = None

            analysis_cache.set(job_id, {
                "type": "single",
                "status": JobStatus.COMPLETED.value,
                "result": result,
                "year": year1,
                "path": str(path1),
                "df": df1,
                "autonomous_analysis": autonomous_analysis,
                "crystal_analysis": crystal_analysis,
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
            # Advanced Statistics (STORY-024, 025, 026)
            "mad_results": result.mad_results if hasattr(result, 'mad_results') else None,
            "iqr_results": result.iqr_results if hasattr(result, 'iqr_results') else None,
            "seasonality": result.seasonality if hasattr(result, 'seasonality') else None,
            "clustering": result.clustering if hasattr(result, 'clustering') else None,
            # AI Pipeline
            "ai_available": result.ai_available if hasattr(result, 'ai_available') else False,
            "benford_analysis": result.benford_analysis if hasattr(result, 'benford_analysis') else None,
            "isolation_forest": result.isolation_forest if hasattr(result, 'isolation_forest') else None,
            "nlp_analysis": result.nlp_analysis if hasattr(result, 'nlp_analysis') else None,
            "combined_risk_scores": result.combined_risk_scores if hasattr(result, 'combined_risk_scores') else None,
            # GL Crystal - Analyse topologique v2.0
            "crystal_analysis": data.get("crystal_analysis"),
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

                # GL Crystal - Analyse topologique
                crystal_data = data.get("crystal_analysis")
                if crystal_data and crystal_data.get("top_surprises"):
                    crystal_rows = []
                    for alert in crystal_data["top_surprises"]:
                        crystal_rows.append({
                            "Compte": alert.get("compte", ""),
                            "Analytique": alert.get("analytique", ""),
                            "Univers": alert.get("univers", ""),
                            "ICC": alert.get("icc", 0),
                            "Surprise": alert.get("surprise", 0),
                            "Classification": alert.get("classification", ""),
                            "Écritures": alert.get("n_ecritures", 0),
                        })
                    if crystal_rows:
                        pd.DataFrame(crystal_rows).to_excel(writer, sheet_name="Crystal ICC", index=False)

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
        analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Analyse proactive IA...", 85)
        try:
            autonomous_analysis = run_autonomous_analysis(df, auto_execute=False)
        except Exception:
            autonomous_analysis = None

        # GL Crystal - Analyse topologique v2.0
        analysis_cache.update_status(job_id, JobStatus.ANALYZING, "Analyse topologique Crystal...", 95)
        try:
            crystal_analysis = run_crystal_analysis(df, year)
        except Exception:
            crystal_analysis = None

        analysis_cache.set(job_id, {
            "type": "single",
            "status": JobStatus.COMPLETED.value,
            "result": result,
            "year": year,
            "path": str(path),
            "df": df,
            "column_mapping": column_mapping,
            "autonomous_analysis": autonomous_analysis,
            "crystal_analysis": crystal_analysis,
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


# =====================================================
# QUALIFICATION - Qualification des anomalies (STORY-032)
# =====================================================

# Storage for qualification data (per job)
qualification_cache: Dict[str, Dict[str, Any]] = {}


@app.get("/qualification/{job_id}", response_class=HTMLResponse)
async def qualification_page(request: Request, job_id: str, index: int = 0):
    """Page de qualification des anomalies"""
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analyse non trouvée ou expirée")

    if data.get("status") != JobStatus.COMPLETED.value:
        return RedirectResponse(url=f"/loading/{job_id}", status_code=303)

    # Récupérer les anomalies du résultat
    result = data.get("result")
    anomalies = []
    if result and hasattr(result, 'anomalies'):
        anomalies = result.anomalies

    if not anomalies:
        return templates.TemplateResponse("qualification.html", {
            "request": request,
            "job_id": job_id,
            "anomalies": [],
            "current_index": 0,
            "total_count": 0,
            "current_anomaly": None,
        })

    # Bound index
    total_count = len(anomalies)
    index = max(0, min(index, total_count - 1))

    # Récupérer les qualifications sauvegardées
    qual_data = qualification_cache.get(job_id, {})
    saved_qualifications = qual_data.get("qualifications", [None] * total_count)
    saved_comments = qual_data.get("comments", [""] * total_count)

    # Current anomaly
    current_anomaly = anomalies[index]

    return templates.TemplateResponse("qualification.html", {
        "request": request,
        "job_id": job_id,
        "anomalies": anomalies,
        "current_index": index + 1,  # 1-based for display
        "total_count": total_count,
        "current_anomaly": current_anomaly,
        "saved_qualifications": saved_qualifications,
        "saved_comments": saved_comments,
    })


@app.post("/qualification/{job_id}/save")
async def save_qualification(
    request: Request,
    job_id: str,
    anomaly_index: int = Form(...),
    qualification: Optional[str] = Form(None),
    comment: Optional[str] = Form(None),
    action: str = Form("next"),
):
    """Sauvegarde la qualification d'une anomalie"""
    data = analysis_cache.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analyse non trouvée")

    result = data.get("result")
    anomalies = result.anomalies if result and hasattr(result, 'anomalies') else []
    total_count = len(anomalies)

    if total_count == 0:
        return RedirectResponse(url=f"/results/{job_id}", status_code=303)

    # Initialiser le cache de qualification si nécessaire
    if job_id not in qualification_cache:
        qualification_cache[job_id] = {
            "qualifications": [None] * total_count,
            "comments": [""] * total_count,
        }

    # Sauvegarder la qualification
    if 0 <= anomaly_index < total_count:
        if qualification:
            qualification_cache[job_id]["qualifications"][anomaly_index] = qualification
        if comment:
            qualification_cache[job_id]["comments"][anomaly_index] = comment

    # Navigation
    if action == "finish":
        # Sauvegarder dans les résultats et retourner
        data["qualifications"] = qualification_cache[job_id]
        return RedirectResponse(url=f"/results/{job_id}", status_code=303)
    else:
        # Next anomaly
        next_index = anomaly_index + 1
        if next_index >= total_count:
            return RedirectResponse(url=f"/results/{job_id}", status_code=303)
        return RedirectResponse(url=f"/qualification/{job_id}?index={next_index}", status_code=303)


@app.post("/api/qualification/{job_id}/comment")
async def save_qualification_comment(request: Request, job_id: str):
    """Sauvegarde automatique d'un commentaire (AJAX)"""
    try:
        body = await request.json()
        index = body.get("index", 0)
        comment = body.get("comment", "")

        data = analysis_cache.get(job_id)
        if data is None:
            return JSONResponse({"success": False, "error": "Job non trouvé"}, status_code=404)

        result = data.get("result")
        anomalies = result.anomalies if result and hasattr(result, 'anomalies') else []
        total_count = len(anomalies)

        if job_id not in qualification_cache:
            qualification_cache[job_id] = {
                "qualifications": [None] * total_count,
                "comments": [""] * total_count,
            }

        if 0 <= index < total_count:
            qualification_cache[job_id]["comments"][index] = comment

        return JSONResponse({"success": True})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/qualification/{job_id}/summary")
async def get_qualification_summary(job_id: str):
    """Retourne un résumé des qualifications"""
    qual_data = qualification_cache.get(job_id, {})
    qualifications = qual_data.get("qualifications", [])

    summary = {
        "justified": sum(1 for q in qualifications if q == "justified"),
        "not_justified": sum(1 for q in qualifications if q == "not_justified"),
        "investigate": sum(1 for q in qualifications if q == "investigate"),
        "pending": sum(1 for q in qualifications if q is None),
        "total": len(qualifications),
    }

    return JSONResponse({"success": True, "summary": summary})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
