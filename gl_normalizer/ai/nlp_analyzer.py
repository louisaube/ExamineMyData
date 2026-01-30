"""
NLP Label Analyzer
==================

Analyse des libellés d'écritures comptables par NLP.

Techniques utilisées:
1. Détection de mots-clés suspects (règles)
2. Embeddings de phrases (Sentence-BERT ou TF-IDF)
3. Détection d'anomalies sémantiques
4. Cohérence libellé/compte

Usage:
    analyzer = NLPAnalyzer(df)
    analyzer.fit()
    suspicious = analyzer.get_suspicious_labels()
"""

import re
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
from collections import Counter

# Vérifier les dépendances optionnelles
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


@dataclass
class LabelAnalysisResult:
    """Résultat d'analyse pour un libellé"""
    index: int
    libelle: str
    risk_score: float  # 0-100
    keywords_found: List[str]
    is_suspicious: bool
    anomaly_type: str  # "keyword", "semantic", "coherence", "duplicate"
    details: str


@dataclass
class NLPAnalysis:
    """Analyse NLP complète"""
    total_entries: int
    nb_suspicious: int
    keywords_stats: Dict[str, int]
    top_suspicious_patterns: List[Tuple[str, int]]
    semantic_clusters: int
    coherence_issues: int


class NLPAnalyzer:
    """
    Analyseur NLP pour les libellés comptables.

    Détecte:
    - Mots-clés suspects (error, adjust, override, etc.)
    - Libellés anormalement courts/longs
    - Patterns de régularisation
    - Incohérences libellé/compte
    - Libellés dupliqués suspects
    """

    # Mots-clés suspects par catégorie (FR + EN)
    SUSPICIOUS_KEYWORDS = {
        "error": [
            r"\berr(eur|or)\b", r"\bmistake\b", r"\bwrong\b",
            r"\bfaux\b", r"\bfaute\b",
        ],
        "correction": [
            r"\bcorrect(ion|if)?\b", r"\brectif", r"\bmodif",
            r"\bamend", r"\bfix\b", r"\brepair",
        ],
        "adjustment": [
            r"\bajust", r"\badjust", r"\bregul", r"\brégul",
            r"\bredress", r"\breclass",
        ],
        "override": [
            r"\boverride\b", r"\bbypass\b", r"\bforce\b",
            r"\bmanuel", r"\bmanual\b", r"\bexcept",
        ],
        "reversal": [
            r"\brevers", r"\bextourne", r"\bcontre.?pass",
            r"\bannul", r"\bcancel", r"\bstorn",
        ],
        "provision": [
            r"\bprovision", r"\bdotation", r"\breprise",
            r"\bdep[ré]c", r"\bamort",
        ],
        "accrual": [
            r"\bfnp\b", r"\bfae\b", r"\bcca\b", r"\bpca\b",
            r"\bcharge.?[àa].?payer", r"\bproduit.?[àa].?recevoir",
            r"\baccru", r"\bdefer",
        ],
        "suspicious_person": [
            r"\bceo\b", r"\bcfo\b", r"\bdg\b", r"\bdaf\b",
            r"\bdirec", r"\bchief\b", r"\bpresident",
        ],
        "urgent": [
            r"\burgent", r"\basap\b", r"\bvite\b", r"\brapide",
            r"\bimmediat", r"\bexception",
        ],
        "round_description": [
            r"\barrondi", r"\bround", r"\bsolde", r"\bapure",
            r"\bécart", r"\bdiff[ée]rence",
        ],
    }

    # Patterns de libellés normaux par classe de compte
    EXPECTED_PATTERNS = {
        "6": ["achat", "fourniture", "service", "charge", "frais", "honoraire"],
        "7": ["vente", "prestation", "produit", "chiffre", "revenu", "factur"],
        "4": ["client", "fournisseur", "tva", "social", "fiscal", "tiers"],
        "5": ["banque", "caisse", "virement", "cheque", "prelevement", "encaiss"],
    }

    def __init__(
        self,
        df: pd.DataFrame,
        libelle_column: str = "libelle",
        compte_column: str = "compte",
        use_embeddings: bool = True,
        embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2",
    ):
        """
        Initialise l'analyseur NLP.

        Args:
            df: DataFrame avec les écritures
            libelle_column: Colonne des libellés
            compte_column: Colonne des comptes
            use_embeddings: Utiliser les embeddings (plus précis mais plus lent)
            embedding_model: Modèle Sentence-BERT à utiliser
        """
        self.df = df.copy()
        self.libelle_column = libelle_column
        self.compte_column = compte_column
        self.use_embeddings = use_embeddings and SENTENCE_TRANSFORMERS_AVAILABLE
        self.embedding_model_name = embedding_model

        self.embeddings = None
        self.vectorizer = None
        self.tfidf_matrix = None
        self.model = None

        # Résultats
        self.keyword_matches = None
        self.semantic_scores = None
        self.coherence_scores = None

    def _normalize_text(self, text: str) -> str:
        """Normalise un texte pour l'analyse"""
        if pd.isna(text):
            return ""
        text = str(text).lower()
        # Garder lettres, chiffres, espaces
        text = re.sub(r"[^a-zàâäéèêëïîôùûüç0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _detect_keywords(self, text: str) -> Dict[str, List[str]]:
        """Détecte les mots-clés suspects dans un texte"""
        text_norm = self._normalize_text(text)
        found = {}

        for category, patterns in self.SUSPICIOUS_KEYWORDS.items():
            matches = []
            for pattern in patterns:
                if re.search(pattern, text_norm, re.IGNORECASE):
                    matches.append(pattern)
            if matches:
                found[category] = matches

        return found

    def _calculate_keyword_score(self, keywords_found: Dict[str, List[str]]) -> float:
        """Calcule un score basé sur les mots-clés trouvés"""
        if not keywords_found:
            return 0

        # Pondération par catégorie
        weights = {
            "error": 30,
            "override": 25,
            "reversal": 20,
            "correction": 15,
            "adjustment": 15,
            "provision": 10,
            "accrual": 10,
            "suspicious_person": 20,
            "urgent": 15,
            "round_description": 10,
        }

        score = 0
        for category in keywords_found:
            score += weights.get(category, 10)

        return min(score, 100)

    def _check_coherence(self, libelle: str, compte: str) -> Tuple[bool, str]:
        """Vérifie la cohérence libellé/compte"""
        if pd.isna(compte) or pd.isna(libelle):
            return True, ""

        classe = str(compte)[0]
        text_norm = self._normalize_text(libelle)

        expected = self.EXPECTED_PATTERNS.get(classe, [])
        if not expected:
            return True, ""

        # Vérifier si au moins un pattern attendu est présent
        for pattern in expected:
            if pattern in text_norm:
                return True, ""

        # Pas de pattern attendu trouvé
        return False, f"Libellé inhabituel pour compte classe {classe}"

    def fit(self, verbose: bool = True) -> "NLPAnalyzer":
        """
        Analyse les libellés.

        Args:
            verbose: Afficher la progression

        Returns:
            Self pour chaînage
        """
        if self.libelle_column not in self.df.columns:
            raise ValueError(f"Colonne {self.libelle_column} non trouvée")

        libelles = self.df[self.libelle_column].fillna("").astype(str)
        n = len(libelles)

        # 1. Détection de mots-clés
        if verbose:
            print("1/4 - Détection des mots-clés...")

        self.keyword_matches = []
        keyword_scores = []

        for idx, lib in enumerate(libelles):
            found = self._detect_keywords(lib)
            self.keyword_matches.append(found)
            keyword_scores.append(self._calculate_keyword_score(found))

        self.df["keyword_score"] = keyword_scores

        # 2. Cohérence libellé/compte
        if verbose:
            print("2/4 - Vérification cohérence...")

        if self.compte_column in self.df.columns:
            coherence_results = []
            for idx, row in self.df.iterrows():
                is_coherent, msg = self._check_coherence(
                    row[self.libelle_column],
                    row[self.compte_column],
                )
                coherence_results.append({"coherent": is_coherent, "message": msg})

            self.df["is_coherent"] = [r["coherent"] for r in coherence_results]
            self.df["coherence_message"] = [r["message"] for r in coherence_results]
        else:
            self.df["is_coherent"] = True
            self.df["coherence_message"] = ""

        # 3. Embeddings et anomalies sémantiques
        if self.use_embeddings and n > 100:
            if verbose:
                print("3/4 - Calcul des embeddings (peut prendre du temps)...")

            try:
                self.model = SentenceTransformer(self.embedding_model_name)
                normalized_libelles = [self._normalize_text(l) for l in libelles]
                self.embeddings = self.model.encode(
                    normalized_libelles,
                    show_progress_bar=verbose,
                )

                # Calculer la distance moyenne au centroïde
                centroid = self.embeddings.mean(axis=0)
                distances = np.linalg.norm(self.embeddings - centroid, axis=1)

                # Normaliser en score (plus loin = plus anormal)
                self.df["semantic_distance"] = distances
                self.df["semantic_score"] = (
                    (distances - distances.min()) /
                    (distances.max() - distances.min() + 1e-10) * 50
                )
            except Exception as e:
                if verbose:
                    print(f"   Erreur embeddings: {e}. Utilisation TF-IDF...")
                self.use_embeddings = False

        # 3bis. Fallback TF-IDF si pas d'embeddings
        if not self.use_embeddings or self.embeddings is None:
            if verbose:
                print("3/4 - Calcul TF-IDF...")

            normalized_libelles = [self._normalize_text(l) for l in libelles]
            self.vectorizer = TfidfVectorizer(
                max_features=1000,
                ngram_range=(1, 2),
                min_df=2,
            )

            try:
                self.tfidf_matrix = self.vectorizer.fit_transform(normalized_libelles)

                # Distance au centroïde
                centroid = self.tfidf_matrix.mean(axis=0).A1
                distances = []
                for i in range(self.tfidf_matrix.shape[0]):
                    vec = self.tfidf_matrix[i].toarray().flatten()
                    dist = np.linalg.norm(vec - centroid)
                    distances.append(dist)

                distances = np.array(distances)
                self.df["semantic_distance"] = distances
                self.df["semantic_score"] = (
                    (distances - distances.min()) /
                    (distances.max() - distances.min() + 1e-10) * 50
                )
            except Exception as e:
                if verbose:
                    print(f"   Erreur TF-IDF: {e}")
                self.df["semantic_distance"] = 0
                self.df["semantic_score"] = 0

        # 4. Détection de libellés anormaux (longueur)
        if verbose:
            print("4/4 - Analyse de la longueur...")

        lengths = libelles.str.len()
        mean_len = lengths.mean()
        std_len = lengths.std()

        self.df["libelle_length"] = lengths
        self.df["length_zscore"] = (lengths - mean_len) / (std_len + 1)

        # Score final combiné
        self.df["nlp_risk_score"] = (
            self.df["keyword_score"] * 0.5 +
            self.df.get("semantic_score", 0) * 0.3 +
            (~self.df["is_coherent"]).astype(int) * 20 +
            (self.df["length_zscore"].abs() > 3).astype(int) * 10
        ).clip(0, 100)

        if verbose:
            print("Analyse NLP terminée.")

        return self

    def get_suspicious_labels(
        self,
        threshold: float = 30,
        top_n: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Retourne les écritures avec libellés suspects.

        Args:
            threshold: Seuil de score de risque
            top_n: Limiter aux N plus suspects

        Returns:
            DataFrame des écritures suspectes
        """
        if "nlp_risk_score" not in self.df.columns:
            self.fit()

        result = self.df[self.df["nlp_risk_score"] >= threshold].copy()

        # Ajouter les détails des mots-clés trouvés
        result["keywords_found"] = [
            ", ".join(f"{cat}: {len(pats)}" for cat, pats in self.keyword_matches[i].items())
            if i < len(self.keyword_matches) else ""
            for i in result.index
        ]

        if top_n:
            result = result.nlargest(top_n, "nlp_risk_score")

        return result.sort_values("nlp_risk_score", ascending=False)

    def get_keyword_statistics(self) -> pd.DataFrame:
        """
        Retourne les statistiques sur les mots-clés détectés.

        Returns:
            DataFrame avec les comptages par catégorie
        """
        if self.keyword_matches is None:
            self.fit()

        stats = Counter()
        for matches in self.keyword_matches:
            for category in matches:
                stats[category] += 1

        df_stats = pd.DataFrame([
            {"category": cat, "count": count}
            for cat, count in stats.most_common()
        ])

        if not df_stats.empty:
            df_stats["percentage"] = df_stats["count"] / len(self.df) * 100

        return df_stats

    def get_duplicate_labels(
        self,
        min_count: int = 5,
        min_amount: float = 1000,
    ) -> pd.DataFrame:
        """
        Détecte les libellés dupliqués avec montants significatifs.

        Les duplications peuvent indiquer des écritures automatisées
        ou des fraudes par répétition.

        Args:
            min_count: Nombre minimum de répétitions
            min_amount: Montant minimum total

        Returns:
            DataFrame des libellés dupliqués
        """
        if self.libelle_column not in self.df.columns:
            return pd.DataFrame()

        # Normaliser les libellés
        self.df["libelle_norm"] = self.df[self.libelle_column].apply(self._normalize_text)

        # Grouper par libellé normalisé
        grouped = self.df.groupby("libelle_norm").agg({
            self.libelle_column: "first",
            "montant": ["count", "sum", "mean", "std"] if "montant" in self.df.columns else ["count"],
        })

        grouped.columns = ["_".join(col).strip("_") for col in grouped.columns]

        # Renommer les colonnes
        col_map = {
            f"{self.libelle_column}_first": "libelle_exemple",
            "montant_count": "nb_occurrences",
            "montant_sum": "montant_total",
            "montant_mean": "montant_moyen",
            "montant_std": "montant_std",
        }
        grouped = grouped.rename(columns=col_map)

        # Filtrer
        if "nb_occurrences" in grouped.columns:
            mask = grouped["nb_occurrences"] >= min_count
            if "montant_total" in grouped.columns:
                mask &= grouped["montant_total"].abs() >= min_amount
            grouped = grouped[mask]

        return grouped.sort_values(
            "nb_occurrences" if "nb_occurrences" in grouped.columns else grouped.columns[0],
            ascending=False,
        )

    def find_similar_labels(
        self,
        query: str,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        Trouve les libellés similaires à une requête.

        Utile pour investiguer un pattern spécifique.

        Args:
            query: Libellé à rechercher
            top_n: Nombre de résultats

        Returns:
            DataFrame des libellés similaires
        """
        query_norm = self._normalize_text(query)

        if self.use_embeddings and self.model is not None:
            # Utiliser embeddings
            query_emb = self.model.encode([query_norm])
            similarities = cosine_similarity(query_emb, self.embeddings)[0]
        elif self.vectorizer is not None:
            # Utiliser TF-IDF
            query_vec = self.vectorizer.transform([query_norm])
            similarities = cosine_similarity(query_vec, self.tfidf_matrix)[0]
        else:
            # Fallback: recherche par sous-chaîne
            similarities = self.df[self.libelle_column].apply(
                lambda x: 1 if query_norm in self._normalize_text(str(x)) else 0
            ).values

        result = self.df.copy()
        result["similarity"] = similarities

        return result.nlargest(top_n, "similarity")[
            [self.libelle_column, "similarity"] +
            [c for c in ["compte", "montant", "date", "journal"] if c in result.columns]
        ]

    def analyze(self) -> NLPAnalysis:
        """Analyse complète"""
        if "nlp_risk_score" not in self.df.columns:
            self.fit()

        keyword_stats = self.get_keyword_statistics()
        keywords_dict = dict(zip(
            keyword_stats["category"],
            keyword_stats["count"],
        )) if not keyword_stats.empty else {}

        return NLPAnalysis(
            total_entries=len(self.df),
            nb_suspicious=(self.df["nlp_risk_score"] >= 30).sum(),
            keywords_stats=keywords_dict,
            top_suspicious_patterns=list(keywords_dict.items())[:5],
            semantic_clusters=0,  # À implémenter si besoin
            coherence_issues=(~self.df["is_coherent"]).sum(),
        )

    def summary(self) -> Dict:
        """Retourne un résumé de l'analyse"""
        analysis = self.analyze()
        return {
            "total_entries": analysis.total_entries,
            "nb_suspicious": analysis.nb_suspicious,
            "suspicious_rate_pct": round(analysis.nb_suspicious / analysis.total_entries * 100, 2),
            "top_keywords": analysis.top_suspicious_patterns,
            "coherence_issues": analysis.coherence_issues,
            "method": "embeddings" if self.use_embeddings else "tfidf",
        }


def analyze_labels(
    df: pd.DataFrame,
    libelle_column: str = "libelle",
) -> NLPAnalysis:
    """
    Fonction utilitaire pour analyser rapidement les libellés.

    Args:
        df: DataFrame avec les écritures
        libelle_column: Colonne des libellés

    Returns:
        NLPAnalysis
    """
    analyzer = NLPAnalyzer(df, libelle_column=libelle_column, use_embeddings=False)
    analyzer.fit(verbose=False)
    return analyzer.analyze()
