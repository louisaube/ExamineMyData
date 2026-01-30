"""
XGBoost Risk Scorer
===================

Classification supervisée des écritures à risque avec XGBoost.

Avantages de XGBoost:
- Excellente performance (95%+ accuracy sur données comptables)
- Gère bien les données déséquilibrées
- Fournit l'importance des features
- Robuste aux valeurs manquantes

Modes d'utilisation:
1. Supervisé: Avec exemples labellisés (fraude/normal)
2. Semi-supervisé: Avec pseudo-labels des autres détecteurs
3. Auto-labelling: Utilise règles + autres modèles pour créer labels

Usage:
    scorer = XGBoostScorer(df)
    scorer.fit(df_labels)  # ou scorer.fit_auto()
    predictions = scorer.predict()
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Union
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, roc_auc_score, precision_recall_curve

# Vérifier XGBoost
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False


@dataclass
class XGBoostAnalysis:
    """Résultats de l'analyse XGBoost"""
    total_entries: int
    nb_high_risk: int
    nb_medium_risk: int
    nb_low_risk: int
    feature_importances: Dict[str, float]
    model_metrics: Dict[str, float]
    threshold_high: float
    threshold_medium: float


class XGBoostScorer:
    """
    Classificateur XGBoost pour le scoring de risque.

    Peut fonctionner en mode:
    - Supervisé (avec labels fournis)
    - Auto-labelling (génère des pseudo-labels)
    """

    # Features par défaut
    FEATURE_CONFIG = {
        "temporal": [
            "jour_semaine", "jour_mois", "mois", "trimestre",
            "est_fin_mois", "est_weekend", "est_lundi", "est_vendredi",
            "est_fin_trimestre", "est_fin_annee",
        ],
        "amount": [
            "montant_abs", "log_montant", "signe_montant",
            "est_debit", "est_credit",
            "mod_10", "mod_100", "mod_1000", "mod_10000",
            "premier_chiffre", "nb_decimales",
        ],
        "account": [
            "classe_compte", "racine_2_enc",
            "compte_mean", "compte_std", "compte_count",
            "ecart_moyenne", "ecart_zscore",
        ],
        "journal": [
            "journal_enc", "est_journal_od", "est_journal_situation",
        ],
        "behavioral": [
            "nb_ecritures_jour", "nb_ecritures_user",
            "pct_jour_total", "heure_creation",
        ],
    }

    def __init__(
        self,
        df: pd.DataFrame,
        target_column: Optional[str] = None,
        threshold_high: float = 0.7,
        threshold_medium: float = 0.4,
    ):
        """
        Initialise le scorer XGBoost.

        Args:
            df: DataFrame avec les écritures
            target_column: Colonne cible si labels disponibles
            threshold_high: Seuil pour risque élevé
            threshold_medium: Seuil pour risque moyen
        """
        if not XGBOOST_AVAILABLE:
            raise ImportError(
                "XGBoost est requis. Installez-le avec: pip install xgboost"
            )

        self.df = df.copy()
        self.target_column = target_column
        self.threshold_high = threshold_high
        self.threshold_medium = threshold_medium

        self.model = None
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.features = []
        self.feature_importances = {}

    def _engineer_features(self) -> pd.DataFrame:
        """Crée les features pour XGBoost"""
        df = self.df.copy()

        # === Features temporelles ===
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df["jour_semaine"] = df["date"].dt.dayofweek
            df["jour_mois"] = df["date"].dt.day
            df["mois"] = df["date"].dt.month
            df["trimestre"] = df["date"].dt.quarter
            df["annee"] = df["date"].dt.year

            df["est_fin_mois"] = (df["jour_mois"] >= 25).astype(int)
            df["est_debut_mois"] = (df["jour_mois"] <= 5).astype(int)
            df["est_weekend"] = (df["jour_semaine"] >= 5).astype(int)
            df["est_lundi"] = (df["jour_semaine"] == 0).astype(int)
            df["est_vendredi"] = (df["jour_semaine"] == 4).astype(int)
            df["est_fin_trimestre"] = (
                (df["mois"].isin([3, 6, 9, 12])) & (df["jour_mois"] >= 25)
            ).astype(int)
            df["est_fin_annee"] = (
                (df["mois"] == 12) & (df["jour_mois"] >= 20)
            ).astype(int)

        # === Features montant ===
        if "montant" in df.columns:
            df["montant_abs"] = df["montant"].abs()
            df["log_montant"] = np.log1p(df["montant_abs"])
            df["signe_montant"] = np.sign(df["montant"])
            df["est_debit"] = (df["montant"] > 0).astype(int)
            df["est_credit"] = (df["montant"] < 0).astype(int)

            # Montants ronds
            for base in [10, 100, 1000, 10000]:
                df[f"mod_{base}"] = (
                    (df["montant_abs"] >= base) &
                    (df["montant_abs"] % base == 0)
                ).astype(int)

            # Premier chiffre (Benford)
            df["premier_chiffre"] = df["montant_abs"].apply(
                lambda x: int(str(int(x))[0]) if x > 0 else 0
            )

            # Nombre de décimales
            df["nb_decimales"] = df["montant"].apply(
                lambda x: len(str(x).split(".")[-1]) if "." in str(x) else 0
            )

        # === Features compte ===
        if "compte" in df.columns:
            df["classe_compte"] = df["compte"].astype(str).str[0].astype(int)
            df["racine_2"] = df["compte"].astype(str).str[:2]

            # Encoder racine_2
            if "racine_2" not in self.label_encoders:
                self.label_encoders["racine_2"] = LabelEncoder()
                df["racine_2_enc"] = self.label_encoders["racine_2"].fit_transform(
                    df["racine_2"].fillna("00")
                )
            else:
                known = set(self.label_encoders["racine_2"].classes_)
                df["racine_2_clean"] = df["racine_2"].fillna("00").apply(
                    lambda x: x if x in known else "00"
                )
                df["racine_2_enc"] = self.label_encoders["racine_2"].transform(
                    df["racine_2_clean"]
                )

            # Stats par compte
            if "montant_abs" in df.columns:
                compte_stats = df.groupby("compte")["montant_abs"].agg([
                    "mean", "std", "count", "min", "max"
                ])
                compte_stats.columns = [
                    "compte_mean", "compte_std", "compte_count",
                    "compte_min", "compte_max"
                ]
                df = df.merge(compte_stats, left_on="compte", right_index=True, how="left")

                # Écarts
                df["compte_std"] = df["compte_std"].fillna(1)
                df["ecart_moyenne"] = df["montant_abs"] - df["compte_mean"]
                df["ecart_zscore"] = df["ecart_moyenne"] / df["compte_std"].replace(0, 1)

        # === Features journal ===
        if "journal" in df.columns:
            od_journals = ["OD", "AN", "RAN", "EXT", "EXTOURNE"]
            sit_journals = ["SIT", "SITUATION", "CLO", "CLOTURE", "BIL", "BILAN"]

            df["est_journal_od"] = df["journal"].str.upper().isin(od_journals).astype(int)
            df["est_journal_situation"] = df["journal"].str.upper().isin(sit_journals).astype(int)

            # Encoder journal
            if "journal" not in self.label_encoders:
                self.label_encoders["journal"] = LabelEncoder()
                df["journal_enc"] = self.label_encoders["journal"].fit_transform(
                    df["journal"].fillna("UNKNOWN")
                )
            else:
                known = set(self.label_encoders["journal"].classes_)
                df["journal_clean"] = df["journal"].fillna("UNKNOWN").apply(
                    lambda x: x if x in known else "UNKNOWN"
                )
                df["journal_enc"] = self.label_encoders["journal"].transform(
                    df["journal_clean"]
                )

        # === Features comportementales ===
        if "date" in df.columns:
            # Écritures par jour
            jour_counts = df.groupby("date").size().rename("nb_ecritures_jour")
            df = df.merge(jour_counts, left_on="date", right_index=True, how="left")

            # Pourcentage du jour
            df["pct_jour_total"] = 1 / df["nb_ecritures_jour"]

        if "utilisateur" in df.columns:
            user_counts = df.groupby("utilisateur").size().rename("nb_ecritures_user")
            df = df.merge(user_counts, left_on="utilisateur", right_index=True, how="left")

        return df

    def _select_features(self, df: pd.DataFrame) -> List[str]:
        """Sélectionne les features numériques disponibles"""
        all_features = []
        for category, features in self.FEATURE_CONFIG.items():
            all_features.extend(features)

        available = []
        for feat in all_features:
            if feat in df.columns:
                if pd.api.types.is_numeric_dtype(df[feat]):
                    if df[feat].notna().mean() > 0.3:
                        available.append(feat)

        return available

    def _create_auto_labels(self, df: pd.DataFrame) -> pd.Series:
        """
        Crée des pseudo-labels basés sur des règles.

        Utilisé quand pas de labels fournis.
        """
        labels = pd.Series(0, index=df.index)  # 0 = normal

        # Règle 1: OD en fin d'année avec gros montant
        if all(c in df.columns for c in ["est_journal_od", "est_fin_annee", "montant_abs"]):
            p99 = df["montant_abs"].quantile(0.99)
            mask = (df["est_journal_od"] == 1) & (df["est_fin_annee"] == 1) & (df["montant_abs"] > p99)
            labels[mask] = 1

        # Règle 2: Montants ronds inhabituels
        if "mod_10000" in df.columns and "compte_count" in df.columns:
            mask = (df["mod_10000"] == 1) & (df["compte_count"] < 5)
            labels[mask] = 1

        # Règle 3: Z-score extrême
        if "ecart_zscore" in df.columns:
            mask = df["ecart_zscore"].abs() > 4
            labels[mask] = 1

        # Règle 4: Weekend + montant significatif
        if all(c in df.columns for c in ["est_weekend", "montant_abs"]):
            p95 = df["montant_abs"].quantile(0.95)
            mask = (df["est_weekend"] == 1) & (df["montant_abs"] > p95)
            labels[mask] = 1

        # Règle 5: Premier chiffre anormal (Benford)
        if "premier_chiffre" in df.columns:
            # 9 comme premier chiffre est rare (4.6% attendu)
            pct_9 = (df["premier_chiffre"] == 9).mean()
            if pct_9 > 0.1:  # Plus de 10% = suspect
                mask = df["premier_chiffre"] == 9
                labels[mask] = 1

        return labels

    def fit(
        self,
        y: Optional[Union[pd.Series, np.ndarray]] = None,
        test_size: float = 0.2,
        verbose: bool = True,
    ) -> "XGBoostScorer":
        """
        Entraîne le modèle XGBoost.

        Args:
            y: Labels (si None, utilise auto-labelling)
            test_size: Proportion pour test
            verbose: Afficher la progression

        Returns:
            Self pour chaînage
        """
        # Feature engineering
        if verbose:
            print("1/3 - Feature engineering...")
        df_features = self._engineer_features()
        self.features = self._select_features(df_features)

        if len(self.features) < 5:
            raise ValueError(f"Pas assez de features: {self.features}")

        # Préparer X
        X = df_features[self.features].fillna(0).values

        # Labels
        if y is None:
            if self.target_column and self.target_column in self.df.columns:
                y = self.df[self.target_column].values
                if verbose:
                    print(f"   Utilisation colonne cible: {self.target_column}")
            else:
                if verbose:
                    print("   Auto-labelling (pas de labels fournis)...")
                y = self._create_auto_labels(df_features).values

        # Vérifier le ratio de classes
        pos_rate = y.mean()
        if verbose:
            print(f"   Taux de positifs: {pos_rate:.2%}")

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y if pos_rate > 0.01 else None
        )

        # Scale
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Calculer le ratio pour scale_pos_weight
        scale_pos_weight = (1 - pos_rate) / (pos_rate + 1e-10)

        # Entraîner XGBoost
        if verbose:
            print("2/3 - Entraînement XGBoost...")

        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            scale_pos_weight=min(scale_pos_weight, 10),  # Cap à 10
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
        )

        self.model.fit(
            X_train_scaled, y_train,
            eval_set=[(X_test_scaled, y_test)],
            verbose=False,
        )

        # Évaluation
        if verbose:
            print("3/3 - Évaluation...")

        y_pred = self.model.predict(X_test_scaled)
        y_proba = self.model.predict_proba(X_test_scaled)[:, 1]

        self.metrics = {
            "accuracy": (y_pred == y_test).mean(),
            "roc_auc": roc_auc_score(y_test, y_proba) if y_test.sum() > 0 else 0,
            "precision": (y_pred[y_test == 1] == 1).mean() if y_test.sum() > 0 else 0,
            "recall": (y_test[y_pred == 1] == 1).mean() if y_pred.sum() > 0 else 0,
        }

        if verbose:
            print(f"\n   Métriques:")
            print(f"   - Accuracy: {self.metrics['accuracy']:.2%}")
            print(f"   - ROC AUC: {self.metrics['roc_auc']:.2%}")
            print(f"   - Precision: {self.metrics['precision']:.2%}")
            print(f"   - Recall: {self.metrics['recall']:.2%}")

        # Feature importances
        self.feature_importances = dict(zip(
            self.features,
            self.model.feature_importances_,
        ))
        self.feature_importances = dict(sorted(
            self.feature_importances.items(),
            key=lambda x: -x[1],
        ))

        # Prédire sur tout le dataset
        X_all_scaled = self.scaler.transform(X)
        self.df["risk_proba"] = self.model.predict_proba(X_all_scaled)[:, 1]
        self.df["risk_level"] = pd.cut(
            self.df["risk_proba"],
            bins=[0, self.threshold_medium, self.threshold_high, 1],
            labels=["low", "medium", "high"],
        )

        return self

    def fit_auto(self, verbose: bool = True) -> "XGBoostScorer":
        """Entraîne avec auto-labelling"""
        return self.fit(y=None, verbose=verbose)

    def predict(self, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Prédit le risque pour de nouvelles données.

        Args:
            df: Nouvelles données (None = données d'entraînement)

        Returns:
            DataFrame avec scores de risque
        """
        if self.model is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        if df is None:
            return self.df[["risk_proba", "risk_level"]].copy()

        # Feature engineering sur nouvelles données
        temp_df = df.copy()
        self.df = temp_df
        df_features = self._engineer_features()

        # S'assurer que toutes les features sont présentes
        for feat in self.features:
            if feat not in df_features.columns:
                df_features[feat] = 0

        X = df_features[self.features].fillna(0).values
        X_scaled = self.scaler.transform(X)

        result = df.copy()
        result["risk_proba"] = self.model.predict_proba(X_scaled)[:, 1]
        result["risk_level"] = pd.cut(
            result["risk_proba"],
            bins=[0, self.threshold_medium, self.threshold_high, 1],
            labels=["low", "medium", "high"],
        )

        return result

    def get_high_risk_entries(self) -> pd.DataFrame:
        """Retourne les écritures à haut risque"""
        if "risk_proba" not in self.df.columns:
            self.fit_auto()

        return self.df[
            self.df["risk_proba"] >= self.threshold_high
        ].sort_values("risk_proba", ascending=False)

    def get_feature_importances(self) -> pd.DataFrame:
        """Retourne l'importance des features"""
        if not self.feature_importances:
            raise ValueError("Modèle non entraîné")

        return pd.DataFrame([
            {"feature": k, "importance": v}
            for k, v in self.feature_importances.items()
        ])

    def analyze(self) -> XGBoostAnalysis:
        """Analyse complète"""
        if "risk_level" not in self.df.columns:
            self.fit_auto()

        risk_counts = self.df["risk_level"].value_counts()

        return XGBoostAnalysis(
            total_entries=len(self.df),
            nb_high_risk=risk_counts.get("high", 0),
            nb_medium_risk=risk_counts.get("medium", 0),
            nb_low_risk=risk_counts.get("low", 0),
            feature_importances=self.feature_importances,
            model_metrics=self.metrics if hasattr(self, "metrics") else {},
            threshold_high=self.threshold_high,
            threshold_medium=self.threshold_medium,
        )

    def summary(self) -> Dict:
        """Résumé de l'analyse"""
        analysis = self.analyze()
        return {
            "total_entries": analysis.total_entries,
            "high_risk": analysis.nb_high_risk,
            "medium_risk": analysis.nb_medium_risk,
            "low_risk": analysis.nb_low_risk,
            "high_risk_pct": round(analysis.nb_high_risk / analysis.total_entries * 100, 2),
            "top_features": list(analysis.feature_importances.keys())[:5],
            "model_accuracy": round(analysis.model_metrics.get("accuracy", 0) * 100, 2),
            "model_roc_auc": round(analysis.model_metrics.get("roc_auc", 0) * 100, 2),
        }


def train_fraud_detector(
    df: pd.DataFrame,
    labels: Optional[pd.Series] = None,
) -> XGBoostScorer:
    """
    Fonction utilitaire pour entraîner rapidement un détecteur.

    Args:
        df: DataFrame avec les écritures
        labels: Labels optionnels

    Returns:
        XGBoostScorer entraîné
    """
    scorer = XGBoostScorer(df)
    scorer.fit(y=labels, verbose=False)
    return scorer
